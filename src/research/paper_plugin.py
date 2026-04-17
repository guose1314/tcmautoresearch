"""Paper reading plugin for PDF/LaTeX with optional translation and summary."""

from __future__ import annotations

import importlib
import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Tuple

logger = logging.getLogger(__name__)


@dataclass
class PaperPluginResult:
    status: str
    source_path: str
    source_type: str
    files: List[str]
    char_count: int
    translated: bool
    summary: str
    translation_excerpt: str
    output_json: str
    output_markdown: str
    error: str = ""


def _collect_tex_files(path: Path) -> List[Path]:
    if path.is_file() and path.suffix.lower() == ".tex":
        return [path]
    if path.is_dir():
        return sorted(path.rglob("*.tex"))
    return []


def _collect_pdf_files(path: Path) -> List[Path]:
    if path.is_file() and path.suffix.lower() == ".pdf":
        return [path]
    if path.is_dir():
        return sorted(path.rglob("*.pdf"))
    return []


def _read_tex(files: List[Path]) -> str:
    chunks: List[str] = []
    for fp in files:
        try:
            chunks.append(fp.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            chunks.append(fp.read_text(encoding="latin-1", errors="replace"))
    text = "\n\n".join(chunks)
    # remove comments
    text = re.sub(r"(?m)^\s*%.*$", "", text)
    return text


def _read_pdf(files: List[Path]) -> str:
    chunks: List[str] = []

    # Try PyMuPDF first.
    try:
        fitz = importlib.import_module("fitz")

        for fp in files:
            doc = fitz.open(str(fp))
            for page in doc:
                chunks.append(page.get_text("text"))
            doc.close()
        return "\n\n".join(chunks)
    except Exception:
        pass

    # Fallback to pypdf.
    try:
        pypdf_module = importlib.import_module("pypdf")
        PdfReader = getattr(pypdf_module, "PdfReader")

        for fp in files:
            reader = PdfReader(str(fp))
            for page in reader.pages:
                chunks.append(page.extract_text() or "")
        return "\n\n".join(chunks)
    except Exception as exc:
        raise RuntimeError("PDF parser unavailable (need PyMuPDF or pypdf).") from exc


def _normalize_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _extractive_summary(text: str, max_sentences: int = 8) -> str:
    if not text:
        return ""
    sentences = re.split(r"(?<=[。！？.!?])\s+", text)
    sentences = [s.strip() for s in sentences if s.strip()]
    if not sentences:
        return text[:800]
    return "\n".join(f"- {s}" for s in sentences[:max_sentences])


def _llm_translate_and_summarize(
    text: str,
    summary_lang: str,
    translate_to: str,
    use_llm: bool,
) -> Tuple[str, str, bool]:
    """Return (translated_text, summary, translated_flag)."""
    if not use_llm:
        summary = _extractive_summary(text)
        return text, summary, False

    try:
        from src.infra.llm_service import get_llm_service

        engine = get_llm_service("paper_plugin")
        engine.load()

        prompt_translate = (
            f"请把以下论文内容翻译为 {translate_to}，保留术语准确性。"
            "如果原文已经是目标语言，可做轻微润色。\n\n"
            f"内容:\n{text[:12000]}"
        )
        translated = engine.generate(prompt_translate, "You are an academic paper translator.")

        prompt_summary = (
            f"请用 {summary_lang} 输出论文摘要，结构为：研究问题、方法、结果、结论、局限。"
            "每个部分1-2句，保持简洁。\n\n"
            f"内容:\n{translated[:12000]}"
        )
        summary = engine.generate(prompt_summary, "You are an academic paper reading assistant.")
        return translated, summary, True
    except Exception as exc:
        logger.warning("LLM unavailable, fallback to extractive summary: %s", exc)
        summary = _extractive_summary(text)
        return text, summary, False


def run_paper_plugin(
    source_path: str,
    output_dir: str = "./output/paper_plugin",
    summary_lang: str = "中文",
    translate_to: str = "中文",
    use_llm: bool = True,
) -> PaperPluginResult:
    """One-click read PDF/LaTeX and produce translation + summary artifacts."""
    src = Path(source_path)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    try:
        tex_files = _collect_tex_files(src)
        pdf_files = _collect_pdf_files(src)

        source_type = ""
        files: List[Path] = []
        raw_text = ""

        if tex_files:
            source_type = "latex"
            files = tex_files
            raw_text = _read_tex(tex_files)
        elif pdf_files:
            source_type = "pdf"
            files = pdf_files
            raw_text = _read_pdf(pdf_files)
        else:
            raise FileNotFoundError("No .tex or .pdf files found in source path.")

        normalized = _normalize_text(raw_text)
        translated, summary, translated_flag = _llm_translate_and_summarize(
            normalized,
            summary_lang=summary_lang,
            translate_to=translate_to,
            use_llm=use_llm,
        )

        result_obj = {
            "timestamp": datetime.now().isoformat(),
            "source_path": str(src),
            "source_type": source_type,
            "files": [str(f) for f in files],
            "char_count": len(normalized),
            "translated": translated_flag,
            "summary_lang": summary_lang,
            "translate_to": translate_to,
            "summary": summary,
            "translation_excerpt": translated[:1200],
        }

        json_path = out_dir / f"paper_plugin_{ts}.json"
        md_path = out_dir / f"paper_plugin_{ts}.md"

        json_path.write_text(json.dumps(result_obj, ensure_ascii=False, indent=2), encoding="utf-8")

        md = (
            "# 论文阅读插件输出\n\n"
            f"- 时间: {result_obj['timestamp']}\n"
            f"- 来源类型: {source_type}\n"
            f"- 文件数: {len(files)}\n"
            f"- 字符数: {len(normalized)}\n"
            f"- 是否LLM翻译: {translated_flag}\n\n"
            "## 摘要\n\n"
            f"{summary}\n\n"
            "## 翻译节选\n\n"
            f"{translated[:4000]}\n"
        )
        md_path.write_text(md, encoding="utf-8")

        return PaperPluginResult(
            status="completed",
            source_path=str(src),
            source_type=source_type,
            files=[str(f) for f in files],
            char_count=len(normalized),
            translated=translated_flag,
            summary=summary,
            translation_excerpt=translated[:1200],
            output_json=str(json_path),
            output_markdown=str(md_path),
        )
    except Exception as exc:
        return PaperPluginResult(
            status="failed",
            source_path=str(src),
            source_type="unknown",
            files=[],
            char_count=0,
            translated=False,
            summary="",
            translation_excerpt="",
            output_json="",
            output_markdown="",
            error=str(exc),
        )
