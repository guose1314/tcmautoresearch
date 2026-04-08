"""run_cycle_demo 插件工作流实现。"""

import argparse
import importlib
import logging
import os
import subprocess
import time
from typing import Any, Dict

from .cycle_storage_persist import persist_paper_result_to_dual_storage
from .cycle_subprocess import safe_subprocess_run

logger = logging.getLogger(__name__)


def _load_attr(module_path: str, attr_name: str) -> Any:
    return getattr(importlib.import_module(module_path), attr_name)


def run_autorresearch_workflow(
    instruction: str,
    instruction_file: str,
    max_iters: int,
    timeout_seconds: int,
    strategy: str,
    rollback_mode: str,
    python_exe: str,
) -> Dict[str, Any]:
    """在主流程后触发 AutoResearch 循环。"""
    from pathlib import Path

    logger.info("=== 开始 AutoResearch 研究范式循环 ===")

    repo_root = Path(__file__).resolve().parents[2]
    runner = repo_root / "tools" / "autorresearch" / "autorresearch_runner.py"
    if not runner.exists():
        raise FileNotFoundError(f"AutoResearch runner 不存在: {runner}")

    cmd = [
        python_exe,
        str(runner),
        "--max-iters",
        str(max_iters),
        "--timeout-seconds",
        str(timeout_seconds),
        "--python-exe",
        python_exe,
        "--strategy",
        strategy,
        "--rollback-mode",
        rollback_mode,
    ]

    if instruction_file:
        cmd.extend(["--instruction-file", instruction_file])
    else:
        cmd.extend(["--instruction", instruction])

    started = time.time()
    with safe_subprocess_run():
        proc = subprocess.run(cmd, capture_output=True, text=True)
    duration = time.time() - started

    output_text = (proc.stdout or "") + "\n" + (proc.stderr or "")
    best_val_bpb = None
    report_path = None
    for line in output_text.splitlines():
        line = line.strip()
        if line.startswith("best_val_bpb="):
            try:
                best_val_bpb = float(line.split("=", 1)[1])
            except Exception:
                best_val_bpb = None
        if line.startswith("report="):
            report_path = line.split("=", 1)[1]

    result = {
        "status": "completed" if proc.returncode == 0 else "failed",
        "return_code": proc.returncode,
        "duration": duration,
        "best_val_bpb": best_val_bpb,
        "report_path": report_path,
        "stdout": proc.stdout,
        "stderr": proc.stderr,
    }

    if proc.returncode == 0:
        logger.info("AutoResearch 完成，best_val_bpb=%s", best_val_bpb)
        if report_path:
            logger.info("AutoResearch 报告: %s", report_path)
    else:
        logger.error("AutoResearch 运行失败")
        logger.error(proc.stderr)

    return result


def run_paper_plugin_workflow(
    source_path: str,
    output_dir: str,
    translate_lang: str,
    summary_lang: str,
    use_llm: bool,
    persist_storage: bool,
    pg_url: str,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str,
) -> Dict[str, Any]:
    """在主流程后触发论文读取/翻译/摘要插件。"""
    run_paper_plugin = _load_attr("src.research.paper_plugin", "run_paper_plugin")

    logger.info("=== 开始论文插件流程 ===")
    result = run_paper_plugin(
        source_path=source_path,
        output_dir=output_dir,
        summary_lang=summary_lang,
        translate_to=translate_lang,
        use_llm=use_llm,
    )

    logger.info("论文插件状态: %s", result.status)
    storage_result: Dict[str, Any] = {"status": "skipped", "document_id": "", "error": ""}
    if result.status == "completed":
        logger.info("论文来源类型: %s", result.source_type)
        logger.info("提取字符数: %s", result.char_count)
        logger.info("JSON 报告: %s", result.output_json)
        logger.info("Markdown 报告: %s", result.output_markdown)

        if persist_storage:
            storage_result = persist_paper_result_to_dual_storage(
                source_path=source_path,
                result_payload={
                    "source_type": result.source_type,
                    "char_count": result.char_count,
                    "summary": result.summary,
                    "translation_excerpt": result.translation_excerpt,
                    "output_json": result.output_json,
                    "output_markdown": result.output_markdown,
                    "translated": result.translated,
                },
                pg_url=pg_url,
                neo4j_uri=neo4j_uri,
                neo4j_user=neo4j_user,
                neo4j_password=neo4j_password,
            )
            if storage_result.get("status") == "completed":
                logger.info("论文插件双库存档完成，document_id=%s", storage_result.get("document_id"))
            else:
                logger.error("论文插件双库存档失败: %s", storage_result.get("error"))
                return {
                    "status": "failed",
                    "source_type": result.source_type,
                    "char_count": result.char_count,
                    "translated": result.translated,
                    "output_json": result.output_json,
                    "output_markdown": result.output_markdown,
                    "error": f"storage_failed: {storage_result.get('error')}",
                    "storage": storage_result,
                }
    else:
        logger.error("论文插件失败: %s", result.error)

    return {
        "status": result.status,
        "source_type": result.source_type,
        "char_count": result.char_count,
        "translated": result.translated,
        "output_json": result.output_json,
        "output_markdown": result.output_markdown,
        "error": result.error,
        "storage": storage_result if result.status == "completed" else {"status": "skipped"},
    }


def run_arxiv_fine_translation_workflow(
    arxiv_input: str,
    daas_url: str,
    output_dir: str,
    advanced_arg: str,
    timeout_sec: int,
    persist_storage: bool,
    pg_url: str,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str,
) -> Dict[str, Any]:
    """触发 Arxiv 精细翻译（Docker/DaaS）并可选双库存档。"""
    run_arxiv_fine_translation_docker = _load_attr(
        "src.research.arxiv_fine_translation",
        "run_arxiv_fine_translation_docker",
    )

    logger.info("=== 开始 Arxiv 精细翻译（Docker）流程 ===")
    result = run_arxiv_fine_translation_docker(
        arxiv_input=arxiv_input,
        server_url=daas_url,
        output_dir=output_dir,
        advanced_arg=advanced_arg,
        timeout_sec=timeout_sec,
    )

    logger.info("Arxiv 精细翻译状态: %s", result.status)
    if result.status != "completed":
        logger.error("Arxiv 精细翻译失败: %s", result.error)
        return {
            "status": "failed",
            "arxiv_id": result.arxiv_id,
            "output_json": result.output_json,
            "output_markdown": result.output_markdown,
            "output_files": result.output_files,
            "error": result.error,
            "storage": {"status": "skipped"},
        }

    storage_result = {"status": "skipped", "document_id": "", "error": ""}
    if persist_storage:
        storage_result = persist_paper_result_to_dual_storage(
            source_path=f"arxiv:{result.arxiv_id}",
            result_payload={
                "source_type": "arxiv_docker",
                "char_count": len(result.server_message),
                "summary": result.summary,
                "translation_excerpt": result.translation_excerpt,
                "output_json": result.output_json,
                "output_markdown": result.output_markdown,
                "translated": True,
            },
            pg_url=pg_url,
            neo4j_uri=neo4j_uri,
            neo4j_user=neo4j_user,
            neo4j_password=neo4j_password,
        )

    return {
        "status": "completed",
        "arxiv_id": result.arxiv_id,
        "output_json": result.output_json,
        "output_markdown": result.output_markdown,
        "output_files": result.output_files,
        "error": "",
        "storage": storage_result,
    }


def run_md_translate_workflow(
    input_path: str,
    language: str,
    output_dir: str,
    additional_prompt: str,
    max_workers: int,
    use_llm: bool,
    persist_storage: bool,
    pg_url: str,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str,
) -> Dict[str, Any]:
    """触发 Markdown 中英互译并可选双库存档。"""
    run_markdown_translate = _load_attr("src.research.markdown_translate", "run_markdown_translate")

    logger.info("=== 开始 Markdown 中英互译流程 ===")
    result = run_markdown_translate(
        input_path=input_path,
        language=language,
        output_dir=output_dir,
        additional_prompt=additional_prompt,
        max_workers=max_workers,
        use_llm=use_llm,
    )

    logger.info("Markdown 翻译状态: %s | %s", result.status, result.summary)
    if result.status == "failed":
        logger.error("Markdown 翻译失败: %s", result.error)
        return {
            "status": "failed",
            "output_json": result.output_json,
            "output_markdown": result.output_markdown,
            "output_files": result.output_files,
            "error": result.error,
            "storage": {"status": "skipped"},
        }

    storage_result: Dict[str, Any] = {"status": "skipped", "document_id": "", "error": ""}
    if persist_storage:
        storage_result = persist_paper_result_to_dual_storage(
            source_path=f"md_translate:{input_path}",
            result_payload={
                "source_type": "markdown_translate",
                "language": language,
                "fragment_total": result.fragment_total,
                "fragment_ok": result.fragment_ok,
                "summary": result.summary,
                "output_json": result.output_json,
                "output_markdown": result.output_markdown,
                "translated": True,
                "char_count": sum(fr.get("char_count", 0) for fr in result.file_results),
            },
            pg_url=pg_url,
            neo4j_uri=neo4j_uri,
            neo4j_user=neo4j_user,
            neo4j_password=neo4j_password,
        )

    return {
        "status": result.status,
        "language": language,
        "output_json": result.output_json,
        "output_markdown": result.output_markdown,
        "output_files": result.output_files,
        "summary": result.summary,
        "error": "",
        "storage": storage_result,
    }


def run_pdf_translation_workflow(
    pdf_path: str,
    target_language: str,
    output_dir: str,
    additional_prompt: str,
    max_tokens_per_fragment: int,
    max_workers: int,
    use_llm: bool,
    persist_storage: bool,
    pg_url: str,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str,
) -> Dict[str, Any]:
    """触发 PDF 论文全文翻译并可选双库存档。"""
    run_pdf_full_text_translation = _load_attr(
        "src.research.pdf_translation",
        "run_pdf_full_text_translation",
    )

    logger.info("=== 开始 PDF 论文全文翻译流程 ===")
    result = run_pdf_full_text_translation(
        pdf_path=pdf_path,
        target_language=target_language,
        output_dir=output_dir,
        additional_prompt=additional_prompt,
        max_tokens_per_fragment=max_tokens_per_fragment,
        max_workers=max_workers,
        use_llm=use_llm,
    )

    logger.info("PDF翻译状态: %s | %s", result.status, result.summary)
    if result.status == "failed":
        logger.error("PDF翻译失败: %s", result.error)
        return {
            "status": "failed",
            "pdf_path": pdf_path,
            "output_json": result.output_json,
            "output_markdown": result.output_markdown,
            "output_html": result.output_html,
            "error": result.error,
            "storage": {"status": "skipped"},
        }

    storage_result: Dict[str, Any] = {"status": "skipped", "document_id": "", "error": ""}
    if persist_storage:
        storage_result = persist_paper_result_to_dual_storage(
            source_path=f"pdf_translate:{pdf_path}",
            result_payload={
                "source_type": "pdf_full_text_translation",
                "title": result.title,
                "title_translated": result.abstract_translated,
                "abstract": result.abstract,
                "abstract_translated": result.abstract_translated,
                "fragment_total": result.fragment_total,
                "fragment_ok": result.fragment_ok,
                "summary": result.summary,
                "output_json": result.output_json,
                "output_markdown": result.output_markdown,
                "output_html": result.output_html,
                "translated": True,
                "char_count": result.char_count,
            },
            pg_url=pg_url,
            neo4j_uri=neo4j_uri,
            neo4j_user=neo4j_user,
            neo4j_password=neo4j_password,
        )

    return {
        "status": result.status,
        "pdf_path": pdf_path,
        "title": result.title,
        "title_translated": result.abstract_translated,
        "char_count": result.char_count,
        "fragment_total": result.fragment_total,
        "fragment_ok": result.fragment_ok,
        "output_json": result.output_json,
        "output_markdown": result.output_markdown,
        "output_html": result.output_html,
        "summary": result.summary,
        "error": "",
        "storage": storage_result,
    }


def run_arxiv_quick_helper_workflow(
    arxiv_url: str,
    output_dir: str,
    target_lang: str,
    enable_translation: bool,
    persist_storage: bool,
    pg_url: str,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str,
) -> Dict[str, Any]:
    """触发 Arxiv 快速助手并可选双库存档。"""
    run_arxiv_quick_helper = _load_attr("src.research.arxiv_quick_helper", "run_arxiv_quick_helper")

    logger.info("=== 开始 Arxiv 快速助手流程 ===")

    llm_engine = None
    if enable_translation:
        try:
            llm_engine = _load_attr("src.llm.llm_engine", "LLMEngine")()
        except Exception as exc:
            logger.warning("LLM 引擎初始化失败，将跳过摘要翻译: %s", exc)
            enable_translation = False

    result = run_arxiv_quick_helper(
        arxiv_url=arxiv_url,
        output_dir=output_dir,
        target_lang=target_lang,
        enable_translation=enable_translation,
        llm_engine=llm_engine,
    )

    logger.info("Arxiv 助手状态: %s | 论文 ID: %s", result.status, result.arxiv_id)
    if result.status == "error":
        logger.error("Arxiv 助手处理失败: %s", result.error)
        return {
            "status": "error",
            "arxiv_id": result.arxiv_id,
            "url": arxiv_url,
            "pdf_path": result.pdf_path,
            "error": result.error,
            "storage": {"status": "skipped"},
        }

    storage_result: Dict[str, Any] = {"status": "skipped", "document_id": "", "error": ""}
    if persist_storage:
        storage_result = persist_paper_result_to_dual_storage(
            source_path=f"arxiv_helper:{result.arxiv_id}",
            result_payload={
                "source_type": "arxiv_quick_helper",
                "arxiv_id": result.arxiv_id,
                "title": result.title,
                "authors": result.authors,
                "publish_date": result.publish_date,
                "abstract_en": result.abstract_en,
                "abstract_zh": result.abstract_zh,
                "pdf_path": result.pdf_path,
                "pdf_size_mb": result.pdf_size_mb,
                "translated": enable_translation,
                "target_language": target_lang,
            },
            pg_url=pg_url,
            neo4j_uri=neo4j_uri,
            neo4j_user=neo4j_user,
            neo4j_password=neo4j_password,
        )

    return {
        "status": result.status,
        "arxiv_id": result.arxiv_id,
        "url": arxiv_url,
        "title": result.title,
        "authors": result.authors,
        "publish_date": result.publish_date,
        "abstract_en": result.abstract_en,
        "abstract_zh": result.abstract_zh,
        "pdf_path": result.pdf_path,
        "pdf_size_mb": result.pdf_size_mb,
        "error": result.error,
        "storage": storage_result,
    }


def run_google_scholar_helper_workflow(
    scholar_url: str,
    output_dir: str,
    topic_hint: str,
    target_lang: str,
    max_papers: int,
    use_llm: bool,
    additional_prompt: str,
    persist_storage: bool,
    pg_url: str,
    neo4j_uri: str,
    neo4j_user: str,
    neo4j_password: str,
) -> Dict[str, Any]:
    """触发 Google Scholar 统合小助手并可选双库存档。"""
    run_google_scholar_related_works = _load_attr(
        "src.research.google_scholar_helper",
        "run_google_scholar_related_works",
    )

    logger.info("=== 开始 Google Scholar 统合小助手流程 ===")

    llm_engine = None
    if use_llm:
        try:
            llm_engine = _load_attr("src.llm.llm_engine", "LLMEngine")()
        except Exception as exc:
            logger.warning("LLM 引擎初始化失败，将使用 fallback 相关工作草稿: %s", exc)
            use_llm = False

    result = run_google_scholar_related_works(
        scholar_url=scholar_url,
        output_dir=output_dir,
        max_papers=max_papers,
        topic_hint=topic_hint,
        target_lang=target_lang,
        use_llm=use_llm,
        llm_engine=llm_engine,
        additional_prompt=additional_prompt,
    )

    logger.info("Scholar 助手状态: %s | 文献条目: %d", result.status, result.total_papers)
    if result.status == "error":
        logger.error("Scholar 助手处理失败: %s", result.error)
        return {
            "status": "error",
            "url": scholar_url,
            "total_papers": result.total_papers,
            "output_markdown": result.output_markdown,
            "output_json": result.output_json,
            "error": result.error,
            "storage": {"status": "skipped"},
        }

    storage_result: Dict[str, Any] = {"status": "skipped", "document_id": "", "error": ""}
    if persist_storage:
        storage_result = persist_paper_result_to_dual_storage(
            source_path=f"google_scholar_helper:{scholar_url}",
            result_payload={
                "source_type": "google_scholar_helper",
                "title": "Google Scholar Related Works",
                "authors": "",
                "publish_date": "",
                "abstract_en": "",
                "abstract_zh": result.related_works_md,
                "summary": f"parsed_papers={result.total_papers}",
                "pdf_path": "",
                "pdf_size_mb": 0,
                "translated": use_llm,
                "target_language": target_lang,
                "output_json": result.output_json,
                "output_markdown": result.output_markdown,
                "char_count": len(result.related_works_md or ""),
            },
            pg_url=pg_url,
            neo4j_uri=neo4j_uri,
            neo4j_user=neo4j_user,
            neo4j_password=neo4j_password,
        )

    return {
        "status": result.status,
        "url": scholar_url,
        "total_papers": result.total_papers,
        "output_markdown": result.output_markdown,
        "output_json": result.output_json,
        "related_works_md": result.related_works_md,
        "error": result.error,
        "storage": storage_result,
    }


def build_storage_connection_from_args(args: argparse.Namespace) -> Dict[str, str]:
    """构建论文插件持久化所需的双库连接参数。"""
    db_password = args.paper_db_password or os.getenv("DB_PASSWORD", "")
    db_host = args.paper_db_host or os.getenv("DB_HOST", "localhost")
    db_port = args.paper_db_port or os.getenv("DB_PORT", "5432")
    db_user = args.paper_db_user or os.getenv("DB_USER", "tcm_user")
    db_name = args.paper_db_name or os.getenv("DB_NAME", "tcm_autoresearch")

    neo4j_password = args.paper_neo4j_password or os.getenv("NEO4J_PASSWORD", "")
    neo4j_host = args.paper_neo4j_host or os.getenv("NEO4J_HOST", "localhost")
    neo4j_port = args.paper_neo4j_port or os.getenv("NEO4J_PORT", "7687")
    neo4j_user = args.paper_neo4j_user or os.getenv("NEO4J_USER", "neo4j")
    neo4j_scheme = args.paper_neo4j_scheme or os.getenv("NEO4J_SCHEME", "neo4j")

    pg_url = args.paper_pg_url or f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
    neo4j_uri = args.paper_neo4j_uri or f"{neo4j_scheme}://{neo4j_host}:{neo4j_port}"

    return {
        "pg_url": pg_url,
        "neo4j_uri": neo4j_uri,
        "neo4j_user": neo4j_user,
        "neo4j_password": neo4j_password,
    }
