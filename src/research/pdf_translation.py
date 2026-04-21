"""PDF论文全文翻译插件 — 借鉴 gpt_academic PDF_Translate.py 思路

功能：
  - 提取 PDF 题目 & 摘要
  - 智能切割 PDF 全文内容（按章节，每片段最大 Token 数）
  - 多线程并行翻译所有片段
  - 生成 Markdown + HTML 双格式翻译结果
  - 双库存档（可选）

支持多种 PDF 解析后端：
  - PyMuPDF (fitz)：轻量级，纯 Python，推荐
  - 未来可扩展：GROBID、DOC2X 等
"""

from __future__ import annotations

import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# 每个翻译片段最大 Token 计数
_DEFAULT_MAX_TOKENS_PER_FRAGMENT = 1024
# 默认并行翻译线程数（每个线程一个 LLM 调用）
_DEFAULT_MAX_WORKERS = 3


@dataclass
class PdfTranslationResult:
    """PDF 翻译结果数据类"""
    status: str                      # "completed" | "failed" | "partial"
    pdf_path: str
    title: str = ""
    abstract: str = ""
    abstract_translated: str = ""
    fragment_total: int = 0
    fragment_ok: int = 0
    char_count: int = 0
    output_markdown: str = ""        # 输出 Markdown 文件路径
    output_html: str = ""            # 输出 HTML 对比文件路径
    summary: str = ""
    output_json: str = ""
    error: str = ""
    fragment_results: List[Dict] = field(default_factory=list)


@dataclass
class PdfTranslationArtifacts:
    markdown_file: str
    html_file: str
    json_file: str


@dataclass
class PdfJsonPayload:
    ts: str
    pdf_path: str
    title: str
    title_translated: str
    abstract: str
    abstract_translated: str
    fragment_total: int
    fragment_ok: int
    char_count: int


# ────────────────────────────── PDF 工具函数 ──────────────────────────────

def _read_pdf_with_fitz(pdf_path: str) -> Tuple[str, str, str]:
    """
    用 PyMuPDF (fitz) 读取 PDF 文件。
    
    返回: (title, abstract, full_text)
    
    说明：
      - 第一页通常含标题/作者/摘要信息
      - full_text = 所有页面的纯文本
    """
    try:
        import fitz
    except ImportError:
        raise ImportError("请安装 PyMuPDF: pip install pymupdf")

    title = ""
    abstract = ""
    full_text = ""

    with fitz.open(pdf_path) as doc:
        # 读第一页用于提取标题和摘要
        if len(doc) > 0:
            first_page = doc[0]
            first_page_text = first_page.get_text()
            # 简单启发式：标题通常在前 500 字符内；摘要通常含 "Abstract"、"摘要" 等关键词
            lines = first_page_text[:1000].split("\n")
            if lines:
                title = lines[0][:200]  # 第一行作为标题
            # 查找摘要
            if "Abstract" in first_page_text:
                abstract_start = first_page_text.find("Abstract")
                abstract_end = first_page_text.find("Introduction", abstract_start)
                if abstract_end == -1:
                    abstract_end = min(abstract_start + 1500, len(first_page_text))
                abstract = first_page_text[abstract_start:abstract_end][:1000]

        # 读所有页面的文本
        for page in doc:
            full_text += page.get_text()

    return title, abstract, full_text


def _split_pdf_content(
    full_text: str,
    llm_model: str = "qwen-7b-instruct",
    max_tokens: int = _DEFAULT_MAX_TOKENS_PER_FRAGMENT,
) -> List[str]:
    """
    智能拆分 PDF 全文内容为翻译片段。
    
    策略：
      1. 优先按章节边界（\\n\\n）拆分
      2. 每片段字符数 ≈ max_tokens（启发式：1 token ≈ 4 字符）
      3. 避免在中间断章取义
    """
    # 简单启发式：1 token ≈ 4 字符
    max_chars_per_fragment = max_tokens * 4
    paragraphs = re.split(r"\n{2,}", full_text)

    fragments: List[str] = []
    current: List[str] = []
    current_len = 0

    for para in paragraphs:
        para_len = len(para)
        if current and current_len + para_len + 2 > max_chars_per_fragment:
            fragments.append("\n\n".join(current))
            current = []
            current_len = 0
        current.append(para)
        current_len += para_len + 2

    if current:
        fragments.append("\n\n".join(current))

    return [f for f in fragments if f.strip()]


def _build_pdf_translate_prompt(
    fragment: str,
    target_lang: str = "Chinese",
    additional_prompt: str = "",
) -> Tuple[str, str]:
    """构造与 gpt_academic 风格一致的翻译 prompt（针对论文）。"""
    user = (
        f"You are an academic paper translator. "
        f"Translate the following section into {target_lang}. "
        f"Do NOT modify any citations, equations, or Markdown formatting. "
        f"Maintain the original structure and meaning:\n\n{fragment}"
    )
    system = (
        "You are a professional academic translator specializing in scientific papers. "
        "Ensure accurate, idiomatic translation that preserves technical terminology."
        + (f" {additional_prompt}" if additional_prompt else "")
    )
    return user, system


def _translate_fragment_with_llm(
    fragment: str,
    target_lang: str,
    additional_prompt: str,
    engine,  # LLMEngine instance or None
) -> str:
    """调用 LLM 翻译单个片段。"""
    user_prompt, system_prompt = _build_pdf_translate_prompt(
        fragment, target_lang, additional_prompt
    )

    if engine is not None:
        try:
            return engine.generate(user_prompt, system_prompt)
        except Exception as exc:
            logger.warning(
                f"LLM 翻译失败（片段长 {len(fragment)} 字符），原样返回: {exc}"
            )
            return fragment

    # 无 LLM 时原样返回
    return fragment


# ────────────────────────────── 元数据提取 ──────────────────────────────

def _extract_pdf_metadata_with_llm(
    title: str,
    abstract: str,
    engine,
) -> Tuple[str, str]:
    """使用 LLM 提取并翻译论文元数据（标题、摘要）。"""
    translated_title = title
    translated_abstract = abstract

    if engine is not None and abstract.strip():
        try:
            # 翻译摘要
            user_prompt = (
                f"Translate the following academic abstract into Chinese. "
                f"Preserve all technical terms and maintain clarity:\n\n{abstract}"
            )
            system_prompt = "You are an expert academic translator."
            translated_abstract = engine.generate(user_prompt, system_prompt)
        except Exception as exc:
            logger.warning("摘要翻译失败: %s", exc)

        try:
            # 翻译标题
            user_prompt = (
                f"Translate the following paper title into Chinese:\n\n{title}"
            )
            system_prompt = "You are an expert academic translator."
            translated_title = engine.generate(user_prompt, system_prompt)
        except Exception as exc:
            logger.warning("标题翻译失败: %s", exc)

    return translated_title, translated_abstract


def _build_failed_pdf_result(out_dir: Path, ts: str, pdf_path: str, error: str) -> PdfTranslationResult:
    return PdfTranslationResult(
        status="failed",
        pdf_path=pdf_path,
        summary=error,
        output_json=str(out_dir / f"{ts}-result.json"),
        output_markdown=str(out_dir / f"{ts}-report.md"),
        error=error,
    )


def _load_pdf_engine(use_llm: bool):
    if not use_llm:
        return None

    try:
        from src.llm.llm_engine import LLMEngine

        engine = LLMEngine(temperature=0.1, max_tokens=2048)
        engine.load()
        logger.info("LLM已加载，开始翻译。")
        return engine
    except Exception as exc:
        logger.warning("LLM加载失败，将跳过翻译: %s", exc)
        return None


def _translate_pdf_fragments(
    fragments: List[str],
    target_language: str,
    additional_prompt: str,
    engine,
    max_workers: int,
) -> Tuple[List[str], int]:
    if not fragments:
        return [], 0

    fragment_results: List[Optional[str]] = [None] * len(fragments)
    fragment_ok = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_idx = {
            executor.submit(
                _translate_fragment_with_llm,
                frag,
                target_language,
                additional_prompt,
                engine,
            ): idx
            for idx, frag in enumerate(fragments)
        }

        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                fragment_results[idx] = future.result()
                fragment_ok += 1
                if (idx + 1) % max(1, len(fragments) // 5) == 0:
                    logger.info("翻译进度: %s/%s 片段完成", idx + 1, len(fragments))
            except Exception as exc:
                logger.error("片段 %s 翻译失败: %s", idx, exc)
                fragment_results[idx] = fragments[idx]

    return [item or fragments[i] for i, item in enumerate(fragment_results)], fragment_ok


def _build_pdf_artifact_paths(out_dir: Path, ts: str) -> PdfTranslationArtifacts:
    return PdfTranslationArtifacts(
        markdown_file=str(out_dir / f"{ts}-report.md"),
        html_file=str(out_dir / f"{ts}-report.html"),
        json_file=str(out_dir / f"{ts}-result.json"),
    )


def _write_pdf_artifacts(
    artifacts: PdfTranslationArtifacts,
    title: str,
    abstract: str,
    abstract_translated: str,
    fragments: List[str],
    translated_fragments: List[str],
    char_count: int,
) -> None:
    _write_markdown_output(
        artifacts.markdown_file,
        title,
        abstract,
        abstract_translated,
        fragments,
        translated_fragments,
        char_count,
    )
    _write_html_output(
        artifacts.html_file,
        title,
        abstract,
        abstract_translated,
        fragments,
        translated_fragments,
    )


def _write_pdf_json_output(
    artifacts: PdfTranslationArtifacts,
    payload: PdfJsonPayload,
) -> None:
    result_dict = {
        "timestamp": payload.ts,
        "pdf_path": payload.pdf_path,
        "title": payload.title,
        "title_translated": payload.title_translated,
        "abstract": payload.abstract,
        "abstract_translated": payload.abstract_translated,
        "fragment_total": payload.fragment_total,
        "fragment_ok": payload.fragment_ok,
        "char_count": payload.char_count,
        "output_markdown": artifacts.markdown_file,
        "output_html": artifacts.html_file,
    }

    with open(artifacts.json_file, "w", encoding="utf-8") as fh:
        json.dump(result_dict, fh, indent=2, ensure_ascii=False)


def _unload_pdf_engine(engine) -> None:
    if engine is None:
        return
    try:
        engine.unload()
    except Exception:
        pass


# ────────────────────────────── 输出生成 ──────────────────────────────

def _write_markdown_output(
    output_path: str,
    title: str,
    abstract: str,
    abstract_translated: str,
    fragments_orig: List[str],
    fragments_trans: List[str],
    char_count: int,
) -> None:
    """生成可读的 Markdown 翻译报告。"""
    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(f"# {title}\n\n")

        if abstract_translated:
            fh.write("## 摘要 (Abstract)\n\n")
            if abstract:
                fh.write(f"**原文：**\n\n{abstract}\n\n")
            fh.write(f"**翻译：**\n\n{abstract_translated}\n\n")

        fh.write("---\n\n## 翻译正文 (Full Translation)\n\n")

        for i, (orig, trans) in enumerate(zip(fragments_orig, fragments_trans)):
            fh.write(f"### 段落 {i + 1} / {len(fragments_orig)}\n\n")
            fh.write(f"**原文：**\n\n{orig}\n\n")
            fh.write(f"**翻译：**\n\n{trans}\n\n")
            fh.write("---\n\n")

        fh.write(
            f"*翻译统计：{len(fragments_orig)} 个片段，总计 {char_count} 字符。*\n"
        )


def _write_html_output(
    output_path: str,
    title: str,
    abstract: str,
    abstract_translated: str,
    fragments_orig: List[str],
    fragments_trans: List[str],
) -> None:
    """生成对比式 HTML 翻译报告（原文 | 翻译）。"""
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{ font-family: Georgia, serif; margin: 20px; line-height: 1.6; }}
        h1 {{ color: #333; }}
        .metadata {{ background: #f5f5f5; padding: 15px; border-radius: 5px; margin-bottom: 20px; }}
        .abstract-section {{ background: #fffacd; padding: 15px; border-left: 4px solid #ffa500; margin-bottom: 20px; }}
        .comparison {{ display: flex; gap: 20px; margin-bottom: 30px; }}
        .original, .translation {{ flex: 1; }}
        .original {{ background: #f0f0f0; padding: 15px; border-radius: 5px; }}
        .translation {{ background: #e8f5e9; padding: 15px; border-radius: 5px; }}
        .original h3 {{ color: #555; }}
        .translation h3 {{ color: #2e7d32; }}
        .fragment-label {{ font-size: 0.9em; color: #666; font-style: italic; }}
    </style>
</head>
<body>
    <h1>{title}</h1>
    <div class="metadata">
        <p><strong>翻译日期：</strong> {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>
    </div>
"""

    if abstract_translated:
        html += """    <div class="abstract-section">
        <h2>摘要对照 (Abstract Comparison)</h2>
"""
        newline_pattern = r'\n+'
        if abstract:
            abstract_html = re.sub(newline_pattern, '<br/>', abstract)
            html += f"        <h3>原文</h3>\n        <p>{abstract_html}</p>\n"
        abstract_translated_html = re.sub(newline_pattern, '<br/>', abstract_translated)
        html += f"        <h3>翻译</h3>\n        <p>{abstract_translated_html}</p>\n"
        html += "    </div>\n"

    html += """    <h2>正文对照 (Full Text Comparison)</h2>
"""

    for i, (orig, trans) in enumerate(zip(fragments_orig, fragments_trans)):
        orig_html = re.sub(r"\n+", "<br/>", orig)
        trans_html = re.sub(r"\n+", "<br/>", trans)
        html += f"""    <div class="fragment-label">段落 {i + 1} / {len(fragments_orig)}</div>
    <div class="comparison">
        <div class="original">
            <h3>原文</h3>
            <p>{orig_html}</p>
        </div>
        <div class="translation">
            <h3>翻译</h3>
            <p>{trans_html}</p>
        </div>
    </div>
"""

    html += """</body>
</html>
"""
    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(html)


# ────────────────────────────── 主函数 ──────────────────────────────

def run_pdf_full_text_translation(
    pdf_path: str,
    target_language: str = "Chinese",
    output_dir: str = "./output/pdf_translation",
    additional_prompt: str = "",
    max_tokens_per_fragment: int = _DEFAULT_MAX_TOKENS_PER_FRAGMENT,
    max_workers: int = _DEFAULT_MAX_WORKERS,
    use_llm: bool = True,
) -> PdfTranslationResult:
    """
    一键翻译 PDF 论文全文。

    Args:
        pdf_path:                  本地 PDF 文件路径。
        target_language:           目标翻译语言（默认"Chinese"）。
        output_dir:                输出目录。
        additional_prompt:         附加给翻译系统提示词的补充指令。
        max_tokens_per_fragment:   每个翻译片段最大 Token 数。
        max_workers:               并行翻译片段的线程数。
        use_llm:                   是否调用 LLM；False 时原样输出（测试用）。

    Returns:
        :class:`PdfTranslationResult` 实例。
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    artifacts = _build_pdf_artifact_paths(out_dir, ts)

    if not os.path.isfile(pdf_path):
        err = f"找不到PDF文件: {pdf_path}"
        logger.error(err)
        return _build_failed_pdf_result(out_dir, ts, pdf_path, err)

    try:
        title, abstract, full_text = _read_pdf_with_fitz(pdf_path)
        char_count = len(full_text)
        logger.info(
            f"PDF读取成功: 标题长{len(title)} | 摘要长{len(abstract)} | 正文{char_count}字符"
        )
    except Exception as exc:
        err = f"PDF读取失败: {exc}"
        logger.error(err)
        return _build_failed_pdf_result(out_dir, ts, pdf_path, err)

    fragments = _split_pdf_content(full_text, max_tokens=max_tokens_per_fragment)
    logger.info("PDF拆分成 %s 个翻译片段", len(fragments))
    engine = _load_pdf_engine(use_llm)

    try:
        title_trans, abstract_trans = _extract_pdf_metadata_with_llm(title, abstract, engine)
        logger.info("元数据翻译完成")
        fragments_trans_final, fragment_ok = _translate_pdf_fragments(
            fragments,
            target_language,
            additional_prompt,
            engine,
            max_workers,
        )
    finally:
        _unload_pdf_engine(engine)

    logger.info("翻译完成: %s/%s 片段成功", fragment_ok, len(fragments))

    try:
        _write_pdf_artifacts(
            artifacts,
            title,
            abstract,
            abstract_trans,
            fragments,
            fragments_trans_final,
            char_count,
        )
        logger.info("已生成报告: %s, %s", artifacts.markdown_file, artifacts.html_file)
    except Exception as exc:
        logger.error("输出文件生成失败: %s", exc)

    try:
        _write_pdf_json_output(
            artifacts,
            PdfJsonPayload(
                ts=ts,
                pdf_path=pdf_path,
                title=title,
                title_translated=title_trans,
                abstract=abstract,
                abstract_translated=abstract_trans,
                fragment_total=len(fragments),
                fragment_ok=fragment_ok,
                char_count=char_count,
            ),
        )
    except Exception as exc:
        logger.error("JSON 输出失败: %s", exc)

    summary = f"PDF翻译完成: {fragment_ok}/{len(fragments)} 片段，{char_count} 字符"

    return PdfTranslationResult(
        status="completed" if fragment_ok == len(fragments) else "partial",
        pdf_path=pdf_path,
        title=title,
        abstract=abstract,
        abstract_translated=abstract_trans,
        fragment_total=len(fragments),
        fragment_ok=fragment_ok,
        char_count=char_count,
        output_markdown=artifacts.markdown_file,
        output_html=artifacts.html_file,
        summary=summary,
        output_json=artifacts.json_file,
        error="",
    )
