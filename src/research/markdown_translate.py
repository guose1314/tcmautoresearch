"""Markdown 中英互译插件 — 借鉴 gpt_academic Markdown_Translate.py 思路

支持三种翻译模式：
  - ``'en->zh'``：英译中（默认）
  - ``'zh->en'``：中译英
  - 任意字符串（如 ``'Japanese'``、``'日语'``）：翻译为指定语言

输入格式（与 gpt_academic 对齐）：
  - 本地 .md 文件路径
  - 本地目录（递归查找所有 .md）
  - GitHub 项目主页 URL（自动获取 README）
  - GitHub 文件 URL（``/blob/``）
  - 原始 raw.githubusercontent.com URL
  - 其他 http/https URL（直接下载）
"""

from __future__ import annotations

import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

# 参数说明同 gpt_academic：每片段最大字符数
_DEFAULT_MAX_CHARS = 2400
# 翻译并行度（本地 LLM 因线程安全限制建议保持 1；OpenAI 等可调高）
_DEFAULT_MAX_WORKERS = 1


@dataclass
class MarkdownTranslateResult:
    status: str                   # "completed" | "failed" | "partial"
    language: str
    input_path: str
    input_files: List[str]
    output_files: List[str]
    fragment_total: int
    fragment_ok: int
    summary: str
    output_json: str
    output_markdown: str
    error: str = ""
    file_results: List[Dict] = field(default_factory=list)


@dataclass
class MarkdownArtifactBundle:
    out_dir: Path
    ts: str
    language: str
    input_path: str
    input_files: List[str]
    output_files: List[str]
    fragment_total: int
    fragment_ok: int
    error: str = ""
    file_results: List[Dict] = field(default_factory=list)


@dataclass
class MarkdownTranslationJob:
    out_dir: Path
    ts: str
    language: str
    max_chars_per_fragment: int
    additional_prompt: str
    engine: object
    max_workers: int


# ────────────────────────────── 工具函数 ──────────────────────────────

def _lang_label(language: str) -> str:
    """将模式参数转换为可读语言名。"""
    return {"en->zh": "Chinese", "zh->en": "English"}.get(language, language)


def _build_translate_prompt(fragment: str, language: str, additional_prompt: str = "") -> Tuple[str, str]:
    """构造与 gpt_academic 风格一致的翻译 prompt。"""
    lang_label = _lang_label(language)
    user = (
        f"This is a Markdown file, translate it into {lang_label}, "
        "do NOT modify any existing Markdown commands, "
        "do NOT use code wrapper (```), "
        "ONLY answer me with translated results:"
        f"\n\n{fragment}"
    )
    system = "You are a professional academic paper translator." + (
        f" {additional_prompt}" if additional_prompt else ""
    )
    return user, system


def _split_text(text: str, max_chars: int = _DEFAULT_MAX_CHARS) -> List[str]:
    """按段落边界拆分长文本，每片段不超过 max_chars 字符。"""
    paragraphs = re.split(r"\n{2,}", text)
    fragments: List[str] = []
    current: List[str] = []
    current_len = 0

    for para in paragraphs:
        para_len = len(para)
        if current and current_len + para_len + 2 > max_chars:
            fragments.append("\n\n".join(current))
            current = []
            current_len = 0
        # 如果单段本身就超过 max_chars，直接作为一片段（避免丢失内容）
        current.append(para)
        current_len += para_len + 2

    if current:
        fragments.append("\n\n".join(current))

    return [f for f in fragments if f.strip()]


def _resolve_github_markdown_url(txt: str, proxies: Optional[dict]) -> Optional[str]:
    if "github.com/" not in txt:
        return txt

    logger.info("检测到 GitHub URL，正在获取资源...")
    if txt.endswith(".md"):
        return txt.replace("https://github.com/", "https://raw.githubusercontent.com/").replace(
            "/blob/", "/"
        )

    api_url = txt.replace("https://github.com/", "https://api.github.com/repos/")
    api_url = api_url.rstrip("/") + "/readme"
    try:
        resp = requests.get(api_url, proxies=proxies, timeout=30)
        resp.raise_for_status()
        download_url = resp.json().get("download_url", "")
    except Exception as exc:
        logger.error("GitHub API 请求失败: %s", exc)
        return None

    if not download_url:
        logger.error("GitHub API 未返回 download_url: %s", api_url)
        return None
    return download_url


def _download_remote_markdown(txt: str, proxies: Optional[dict]) -> Tuple[bool, List[str], str]:
    import tempfile

    resolved_url = _resolve_github_markdown_url(txt, proxies)
    if not resolved_url:
        return False, [], ""

    try:
        response = requests.get(resolved_url, proxies=proxies, timeout=60)
        response.raise_for_status()
    except Exception as exc:
        logger.error("下载 Markdown 文件失败: %s", exc)
        return False, [], ""

    tmp_dir = tempfile.mkdtemp(prefix="md_translate_")
    filename = re.sub(r"[^a-zA-Z0-9._-]", "_", resolved_url.split("/")[-1].split("?")[0]) or "readme.md"
    if not filename.lower().endswith(".md"):
        filename += ".md"
    local_path = os.path.join(tmp_dir, filename)
    with open(local_path, "wb") as fh:
        fh.write(response.content)
    logger.info("已下载 %d 字节 → %s", len(response.content), local_path)
    return True, [local_path], tmp_dir


def _resolve_local_markdown_input(txt: str) -> Tuple[bool, List[str], str]:
    import glob

    if txt.lower().endswith(".md") and os.path.isfile(txt):
        return True, [txt], os.path.dirname(txt)

    if os.path.isdir(txt):
        manifest = sorted(glob.glob(os.path.join(txt, "**", "*.md"), recursive=True))
        return bool(manifest), manifest, txt

    logger.error("无法识别输入路径/链接: %s", txt)
    return False, [], ""


def _resolve_input(txt: str) -> Tuple[bool, List[str], str]:
    """
    把各类输入解析为 (success, file_manifest, project_folder)。

    支持格式与 gpt_academic get_files_from_everything 对齐：
      - GitHub 项目主页 → 自动获取 README
      - GitHub /blob/ 文件链接 → 转 raw URL
      - 其他 http(s) URL → 直接下载
      - 本地 .md 文件 → 直接使用
      - 本地目录 → 递归搜索 .md
    """
    if not txt:
        return False, [], ""

    txt = txt.strip()

    if txt.startswith("http"):
        return _download_remote_markdown(txt, _get_proxies())

    return _resolve_local_markdown_input(txt)


def _get_proxies() -> Optional[dict]:
    """读取系统代理配置。"""
    http_proxy = os.getenv("HTTP_PROXY") or os.getenv("http_proxy")
    https_proxy = os.getenv("HTTPS_PROXY") or os.getenv("https_proxy")
    if http_proxy or https_proxy:
        return {"http": http_proxy, "https": https_proxy}
    return None


def _translate_fragment_with_llm(
    fragment: str,
    language: str,
    additional_prompt: str,
    engine,  # LLMEngine instance or None
) -> str:
    """调用 LLM 翻译单个片段。"""
    user_prompt, system_prompt = _build_translate_prompt(fragment, language, additional_prompt)

    if engine is not None:
        try:
            return engine.generate(user_prompt, system_prompt)
        except Exception as exc:
            logger.warning("LLM 翻译失败（片段长 %d 字符），原样返回: %s", len(fragment), exc)
            return fragment

    # 无 LLM 时原样返回（供测试用）
    return fragment


def _load_markdown_engine(use_llm: bool):
    if not use_llm:
        return None

    try:
        from src.infra.llm_service import get_llm_service

        svc = get_llm_service("translation")
        svc.load()
        logger.info("LLM 已加载，开始翻译。")
        return svc
    except Exception as exc:
        logger.warning("LLM 加载失败，片段将原样输出: %s", exc)
        return None


def _read_markdown_file(file_path: str) -> Optional[str]:
    try:
        with open(file_path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except Exception as exc:
        logger.error("读取文件失败 %s: %s", file_path, exc)
        return None


def _translate_markdown_file(
    file_path: str,
    job: MarkdownTranslationJob,
) -> Tuple[Optional[Dict], int, int]:
    content = _read_markdown_file(file_path)
    if content is None:
        return {"file": file_path, "status": "failed", "error": "read_failed"}, 0, 0

    fragments = _split_text(content, max_chars=job.max_chars_per_fragment)
    logger.info("  文件 %s → %d 片段", Path(file_path).name, len(fragments))
    translated_frags = _translate_all_fragments(
        fragments,
        job.language,
        job.additional_prompt,
        job.engine,
        job.max_workers,
    )

    translated_text = "\n\n".join(trans for (_orig, trans) in translated_frags)
    out_name = f"{job.ts}-{Path(file_path).stem}.translated.md"
    out_path = job.out_dir / out_name
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write(translated_text)
    logger.info("  → 已写出: %s", out_path)

    return (
        {
            "source_file": file_path,
            "output_file": str(out_path),
            "status": "completed",
            "fragment_count": len(fragments),
            "char_count": len(content),
        },
        len(fragments),
        len(translated_frags),
    )


def _translate_markdown_manifest(
    file_manifest: List[str],
    job: MarkdownTranslationJob,
) -> Tuple[List[str], List[Dict], int, int]:
    output_files: List[str] = []
    file_results: List[Dict] = []
    total_frags = 0
    ok_frags = 0

    for file_path in file_manifest:
        file_result, fragment_total, fragment_ok = _translate_markdown_file(file_path, job)
        total_frags += fragment_total
        ok_frags += fragment_ok
        if file_result is None:
            continue
        file_results.append(file_result)
        output_file = file_result.get("output_file")
        if output_file:
            output_files.append(output_file)

    return output_files, file_results, total_frags, ok_frags


def _unload_engine(engine) -> None:
    if engine is None:
        return
    try:
        engine.unload()
    except Exception:
        pass


def _build_failed_markdown_result(
    out_dir: Path,
    ts: str,
    language: str,
    input_path: str,
    error: str,
) -> MarkdownTranslateResult:
    json_path, md_path = _write_artifacts(
        MarkdownArtifactBundle(
            out_dir=out_dir,
            ts=ts,
            language=language,
            input_path=input_path,
            input_files=[],
            output_files=[],
            fragment_total=0,
            fragment_ok=0,
            error=error,
        )
    )
    return MarkdownTranslateResult(
        status="failed",
        language=language,
        input_path=input_path,
        input_files=[],
        output_files=[],
        fragment_total=0,
        fragment_ok=0,
        summary=error,
        output_json=json_path,
        output_markdown=md_path,
        error=error,
    )


# ────────────────────────────── 主函数 ──────────────────────────────

def run_markdown_translate(
    input_path: str,
    language: str = "en->zh",
    output_dir: str = "./output/md_translate",
    additional_prompt: str = "",
    max_chars_per_fragment: int = _DEFAULT_MAX_CHARS,
    max_workers: int = _DEFAULT_MAX_WORKERS,
    use_llm: bool = True,
) -> MarkdownTranslateResult:
    """
    一键翻译 Markdown 文档中英互译。

    Args:
        input_path:             本地文件/目录路径，或 GitHub/HTTP URL。
        language:               翻译方向，``'en->zh'`` / ``'zh->en'`` / 任意语言名。
        output_dir:             输出目录。
        additional_prompt:      附加给翻译系统提示词的补充指令。
        max_chars_per_fragment: 每个翻译片段的最大字符数。
        max_workers:            并行翻译片段的线程数（本地 LLM 建议保持 1）。
        use_llm:                是否调用 LLM；False 时原样输出（用于调试/测试）。

    Returns:
        :class:`MarkdownTranslateResult` 实例。
    """
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    success, file_manifest, _project_folder = _resolve_input(input_path)
    if not success or not file_manifest:
        err = f"找不到任何 .md 文件: {input_path}"
        return _build_failed_markdown_result(out_dir, ts, language, input_path, err)

    logger.info("共找到 %d 个 Markdown 文件，翻译方向: %s", len(file_manifest), language)
    engine = _load_markdown_engine(use_llm)
    job = MarkdownTranslationJob(
        out_dir=out_dir,
        ts=ts,
        language=language,
        max_chars_per_fragment=max_chars_per_fragment,
        additional_prompt=additional_prompt,
        engine=engine,
        max_workers=max_workers,
    )

    try:
        output_files, file_results, total_frags, ok_frags = _translate_markdown_manifest(file_manifest, job)

    finally:
        _unload_engine(engine)

    summary = (
        f"翻译方向: {language} | 文件数: {len(file_manifest)} | "
        f"片段总数: {total_frags} | 输出文件: {len(output_files)}"
    )
    json_path, md_path = _write_artifacts(
        MarkdownArtifactBundle(
            out_dir=out_dir,
            ts=ts,
            language=language,
            input_path=input_path,
            input_files=file_manifest,
            output_files=output_files,
            fragment_total=total_frags,
            fragment_ok=ok_frags,
            error="",
            file_results=file_results,
        )
    )

    status = "completed" if output_files else "failed"
    return MarkdownTranslateResult(
        status=status,
        language=language,
        input_path=input_path,
        input_files=file_manifest,
        output_files=output_files,
        fragment_total=total_frags,
        fragment_ok=ok_frags,
        summary=summary,
        output_json=json_path,
        output_markdown=md_path,
        file_results=file_results,
    )


def _translate_all_fragments(
    fragments: List[str],
    language: str,
    additional_prompt: str,
    engine,
    max_workers: int,
) -> List[Tuple[str, str]]:
    """翻译所有片段，返回 [(原文, 译文)] 有序列表。"""
    results = [""] * len(fragments)

    if max_workers <= 1 or engine is None:
        # 顺序翻译（本地 LLM 必须顺序）
        for idx, frag in enumerate(fragments):
            translated = _translate_fragment_with_llm(frag, language, additional_prompt, engine)
            results[idx] = translated
            logger.debug("  片段 %d/%d 翻译完成", idx + 1, len(fragments))
    else:
        # 并行翻译（适合 API 类 LLM）
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            future_map = {
                pool.submit(
                    _translate_fragment_with_llm, frag, language, additional_prompt, engine
                ): idx
                for idx, frag in enumerate(fragments)
            }
            for future in as_completed(future_map):
                idx = future_map[future]
                try:
                    results[idx] = future.result()
                except Exception as exc:
                    logger.warning("片段 %d 翻译异常，原样保留: %s", idx, exc)
                    results[idx] = fragments[idx]

    return list(zip(fragments, results))


def _write_artifacts(
    bundle: MarkdownArtifactBundle,
) -> Tuple[str, str]:
    """写 JSON + Markdown 结果档案，返回 (json_path, md_path)。"""
    import json

    payload = {
        "timestamp": bundle.ts,
        "language": bundle.language,
        "input_path": bundle.input_path,
        "input_files": bundle.input_files,
        "output_files": bundle.output_files,
        "fragment_total": bundle.fragment_total,
        "fragment_ok": bundle.fragment_ok,
        "error": bundle.error,
        "file_results": bundle.file_results,
    }
    json_path = str(bundle.out_dir / f"{bundle.ts}-result.json")
    with open(json_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)

    md_lines = [
        "# Markdown 翻译报告",
        "",
        f"**时间**: {bundle.ts}",
        f"**翻译方向**: {bundle.language}",
        f"**输入**: {bundle.input_path}",
        f"**文件数**: {len(bundle.input_files)}",
        f"**片段总数**: {bundle.fragment_total}",
        f"**输出文件数**: {len(bundle.output_files)}",
    ]
    if bundle.error:
        md_lines += ["", f"**错误**: {bundle.error}"]
    if bundle.output_files:
        md_lines += ["", "## 输出文件", ""]
        for fp in bundle.output_files:
            md_lines.append(f"- {fp}")
    md_path = str(bundle.out_dir / f"{bundle.ts}-report.md")
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(md_lines))

    return json_path, md_path
