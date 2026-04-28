#!/usr/bin/env python3
"""
医学 SFT 数据集知识蒸馏脚本 — 读取 medical_o1_sft_mix_Chinese.json，
通过本系统的 ExtractionPipeline + LLMEngine 提取实体/关系/知识，
并沉淀到 PersistenceService（SQLite/PostgreSQL）数据库。

用法:
    python tools/ingest_medical_sft.py --input <path_to_json>
    python tools/ingest_medical_sft.py --input <path_to_json> --batch-size 50 --limit 100
    python tools/ingest_medical_sft.py --input <path_to_json> --use-llm --llm-sample 200
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# 确保项目根目录在搜索路径中
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.extraction.base import PipelineResult
from src.extraction.extraction_pipeline import ExtractionPipeline
from src.infrastructure.persistence import PersistenceService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    handlers=[
        logging.FileHandler(_ROOT / "logs" / "ingest_medical_sft.log", encoding="utf-8", delay=True),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("ingest_medical_sft")

# ---------------------------------------------------------------------------
# 数据加载
# ---------------------------------------------------------------------------

def load_sft_dataset(path: Path, limit: int = 0) -> List[Dict[str, str]]:
    """加载 SFT 数据集 JSON，返回记录列表。"""
    logger.info("加载数据集: %s", path)
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        raise ValueError(f"数据集顶层应为 list，实际为 {type(data).__name__}")
    if limit > 0:
        data = data[:limit]
    logger.info("加载完成: %d 条记录", len(data))
    return data


# ---------------------------------------------------------------------------
# 单条记录 → 合并文本
# ---------------------------------------------------------------------------

def record_to_text(record: Dict[str, str]) -> str:
    """将 Question + Complex_CoT + Response 拼接为完整知识文本。"""
    parts: list[str] = []
    if record.get("Question"):
        parts.append(f"【问题】{record['Question']}")
    if record.get("Complex_CoT"):
        parts.append(f"【推理过程】{record['Complex_CoT']}")
    if record.get("Response"):
        parts.append(f"【回答】{record['Response']}")
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# 提取结果 → 持久化 payload
# ---------------------------------------------------------------------------

def pipeline_result_to_payload(
    result: PipelineResult,
    record: Dict[str, str],
    source_tag: str,
) -> Dict[str, Any]:
    """将 ExtractionPipeline 的结果转换为 PersistenceService 可接受的 payload。"""
    entities: List[Dict[str, Any]] = []
    for item in result.all_items:
        entities.append({
            "name": item.name,
            "type": item.entity_type,
            "confidence": item.confidence,
            "position": item.position,
            "length": item.length or (item.end_position - item.position),
            "description": item.original_text or "",
            "entity_metadata": item.metadata,
        })

    relationships: List[Dict[str, Any]] = []
    for rel in result.all_relations:
        relationships.append({
            "source_name": rel.source,
            "target_name": rel.target,
            "relationship_type": rel.relation_type,
            "confidence": rel.confidence,
            "evidence": getattr(rel, "evidence", ""),
        })

    stats = {}
    entity_result = result.module_results.get("entity_extractor")
    if entity_result:
        stats = entity_result.statistics

    quality = result.overall_quality or {}
    raw_score = quality.get("score", 0.0)
    # ExtractionPipeline 返回百分制，数据库 CHECK 约束要求 [0, 1]
    normalized_score = max(0.0, min(1.0, raw_score / 100.0 if raw_score > 1.0 else raw_score))

    return {
        "document": {
            "source_file": f"medical_sft::{result.document_id}",
            "objective": record.get("Question", "")[:500],
            "process_status": "COMPLETED",
            "quality_score": normalized_score,
            "notes": source_tag,
        },
        "entities": entities,
        "relationships": relationships,
        "statistics": stats,
        "quality_metrics": quality,
    }


# ---------------------------------------------------------------------------
# LLM 知识增强（可选）
# ---------------------------------------------------------------------------

def build_distillation_prompt(record: Dict[str, str]) -> str:
    """构造让 LLM 从 SFT 记录中提炼结构化中医知识的 Prompt。"""
    q = record.get("Question", "")[:600]
    r = record.get("Response", "")[:600]
    return (
        "请从以下中医问答中提取结构化知识，用 JSON 格式输出：\n"
        "{\n"
        '  "核心疾病或症候": "...",\n'
        '  "涉及方剂": ["方剂1", ...],\n'
        '  "涉及中药": ["药材1", ...],\n'
        '  "治法治则": "...",\n'
        '  "辩证要点": "...",\n'
        '  "学术价值摘要": "..."\n'
        "}\n\n"
        f"【问题】{q}\n\n"
        f"【回答】{r}\n\n"
        "请只输出 JSON，不要输出其他内容。"
    )


def parse_llm_knowledge(raw: str) -> Dict[str, Any]:
    """尝试解析 LLM 输出的 JSON，容错处理。"""
    raw = raw.strip()
    # 去除可能的 markdown 代码块标记
    if raw.startswith("```"):
        lines = raw.splitlines()
        lines = [l for l in lines if not l.strip().startswith("```")]
        raw = "\n".join(lines)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw_llm_output": raw[:500]}


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def run_ingestion(
    input_path: Path,
    *,
    limit: int = 0,
    batch_size: int = 50,
    use_llm: bool = False,
    llm_sample: int = 200,
    db_connection: str = "",
    output_report: str = "output/ingest_medical_sft_report.json",
) -> Dict[str, Any]:
    """执行完整的蒸馏入库流程。"""
    t0 = time.time()
    records = load_sft_dataset(input_path, limit=limit)
    total = len(records)

    # --- 初始化 ExtractionPipeline ---
    pipeline = ExtractionPipeline(
        enable_metadata=True,
        enable_medical_content=True,
        enable_clinical=True,
        enable_relation=True,
        enable_academic_assessment=True,
        enable_quality_check=True,
    )

    # --- 初始化 PersistenceService ---
    if not db_connection:
        db_connection = f"sqlite:///{_ROOT / 'data' / 'medical_sft_knowledge.db'}"
    persistence = PersistenceService(config={"connection_string": db_connection})
    if not persistence.initialize():
        raise RuntimeError("PersistenceService 初始化失败")

    # --- 可选 LLM ---
    llm = None
    if use_llm:
        try:
            from src.infra.llm_service import get_llm_service
            llm = get_llm_service("default")
            llm.load()
            logger.info("LLM 引擎已加载，将对前 %d 条进行知识增强", llm_sample)
        except Exception as exc:
            logger.warning("LLM 加载失败，跳过知识增强: %s", exc)
            llm = None

    # --- 统计 ---
    stats = {
        "total_records": total,
        "processed": 0,
        "persisted": 0,
        "errors": 0,
        "total_entities": 0,
        "total_relations": 0,
        "llm_enhanced": 0,
        "entity_type_counts": {},
    }
    source_tag = f"medical_o1_sft_mix_Chinese | ingested {datetime.now().isoformat()}"

    # --- 批量处理 ---
    for batch_start in range(0, total, batch_size):
        batch_end = min(batch_start + batch_size, total)
        batch = records[batch_start:batch_end]
        logger.info("处理批次 %d-%d / %d ...", batch_start + 1, batch_end, total)

        for idx, record in enumerate(batch, start=batch_start):
            doc_id = f"sft_{idx:06d}"
            text = record_to_text(record)
            if not text.strip():
                continue

            try:
                result = pipeline.process_document(
                    raw_text=text,
                    source_file=f"medical_sft::{doc_id}",
                    document_id=doc_id,
                )
                stats["processed"] += 1
                stats["total_entities"] += len(result.all_items)
                stats["total_relations"] += len(result.all_relations)

                # 统计实体类型
                for item in result.all_items:
                    et = item.entity_type
                    stats["entity_type_counts"][et] = stats["entity_type_counts"].get(et, 0) + 1

                # 可选 LLM 增强
                llm_knowledge: Dict[str, Any] = {}
                if llm and idx < llm_sample:
                    try:
                        raw = llm.generate(
                            build_distillation_prompt(record),
                            system_prompt="你是中医古籍知识提取专家，请严格按照 JSON 格式输出。",
                        )
                        llm_knowledge = parse_llm_knowledge(raw)
                        stats["llm_enhanced"] += 1
                    except Exception as llm_exc:
                        logger.warning("LLM 增强失败 [%s]: %s", doc_id, llm_exc)

                # 持久化
                payload = pipeline_result_to_payload(result, record, source_tag)
                if llm_knowledge:
                    payload["research_analysis"] = {
                        "analysis_type": "llm_distillation",
                        "findings": json.dumps(llm_knowledge, ensure_ascii=False),
                        "confidence": 0.75,
                    }
                persistence.execute({
                    "entity_type": "document_graph",
                    "operation": "upsert",
                    "data": payload,
                })
                stats["persisted"] += 1

            except Exception as exc:
                stats["errors"] += 1
                logger.error("处理失败 [%s]: %s", doc_id, exc, exc_info=False)

        logger.info(
            "批次完成: processed=%d, persisted=%d, errors=%d, entities=%d",
            stats["processed"], stats["persisted"], stats["errors"], stats["total_entities"],
        )

    # --- 卸载 LLM ---
    if llm:
        try:
            llm.unload()
        except Exception:
            pass

    # --- 清理 ---
    persistence.cleanup()

    # --- 导出报告 ---
    stats["duration_seconds"] = round(time.time() - t0, 2)
    stats["db_connection"] = db_connection
    stats["input_file"] = str(input_path)
    report_path = _ROOT / output_report
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("入库完成! 报告: %s", report_path)
    logger.info(
        "汇总: processed=%d, persisted=%d, entities=%d, relations=%d, llm_enhanced=%d, errors=%d, duration=%.1fs",
        stats["processed"], stats["persisted"], stats["total_entities"],
        stats["total_relations"], stats["llm_enhanced"], stats["errors"], stats["duration_seconds"],
    )
    return stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="医学 SFT 数据集知识蒸馏入库")
    parser.add_argument("--input", required=True, help="输入 JSON 文件路径")
    parser.add_argument("--limit", type=int, default=0, help="最多处理几条（0=全量）")
    parser.add_argument("--batch-size", type=int, default=50, help="每批处理条数")
    parser.add_argument("--use-llm", action="store_true", help="启用 LLM 知识增强")
    parser.add_argument("--llm-sample", type=int, default=200, help="LLM 增强的最大条数")
    parser.add_argument("--db", default="", help="数据库连接串（默认 SQLite）")
    parser.add_argument("--report", default="output/ingest_medical_sft_report.json", help="报告输出路径")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        logger.error("输入文件不存在: %s", input_path)
        return 1

    stats = run_ingestion(
        input_path,
        limit=args.limit,
        batch_size=args.batch_size,
        use_llm=args.use_llm,
        llm_sample=args.llm_sample,
        db_connection=args.db,
        output_report=args.report,
    )
    return 0 if stats["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
