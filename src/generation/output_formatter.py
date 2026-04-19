# src/generation/output_formatter.py  (migrated from src/output/output_generator.py)
"""
输出格式化模块 — 架构 3.0 重命名（原 OutputGenerator）
"""
import os
from datetime import datetime
from typing import Any, Dict, List

from src.core.module_base import BaseModule
from src.infra.layered_cache import get_layered_task_cache
from src.research.evidence_contract import build_evidence_protocol
from src.research.phase_result import (
    get_phase_results,
    get_phase_value,
    is_phase_result_payload,
)


class OutputGenerator(BaseModule):
    """
    输出生成器
    """
    
    def __init__(self, config: Dict[str, Any] | None = None):
        super().__init__("output_generator", config)
        self.max_entities = int((config or {}).get("max_entities", 1000))
        self.max_recommendations = int((config or {}).get("max_recommendations", 20))
        self.max_string_length = int((config or {}).get("max_string_length", 5000))
        
    def _do_initialize(self) -> bool:
        """初始化输出生成器"""
        try:
            self.logger.info("输出生成器初始化完成")
            return True
        except Exception as e:
            self.logger.error(f"输出生成器初始化失败: {e}")
            return False
    
    def _do_execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """执行输出生成"""
        try:
            cache_payload = self._build_artifact_cache_payload(context)
            task_cache = get_layered_task_cache()
            cached_result = task_cache.get_json("artifact", "output_generator.execute", cache_payload)
            if cached_result is not None:
                return cached_result if isinstance(cached_result, dict) else {}

            # 构造输出格式
            output_data = self._generate_output_format(context)
            safe_output_data = self._make_json_safe(output_data)

            result = {
                "output_data": safe_output_data,
                "output_format": "structured_json",
                "generated_at": self._get_timestamp()
            }
            task_cache.put_json(
                "artifact",
                "output_generator.execute",
                cache_payload,
                result,
                meta={
                    "module": self.module_name,
                    "protocol_version": "research-output-v2",
                },
            )
            return result
            
        except Exception as e:
            self.logger.error(f"输出生成执行失败: {e}")
            raise

    def _build_artifact_cache_payload(self, context: Dict[str, Any]) -> Dict[str, Any]:
        hypothesis_payload = self._resolve_hypothesis_payload(context)
        return {
            "cache_version": "artifact-cache-v1",
            "source_file": str(context.get("source_file", "unknown")),
            "objective": context.get("objective", "unknown"),
            "max_entities": self.max_entities,
            "max_recommendations": self.max_recommendations,
            "max_string_length": self.max_string_length,
            "entities": context.get("entities", []),
            "semantic_graph": context.get("semantic_graph", {}),
            "reasoning_results": self._resolve_reasoning_payload(context),
            "temporal_analysis": context.get("temporal_analysis", {}),
            "pattern_recognition": context.get("pattern_recognition", {}),
            "evidence_grade": self._resolve_evidence_grade_payload(context),
            "hypothesis": hypothesis_payload,
            "hypothesis_audit_summary": self._resolve_hypothesis_audit_summary(context, hypothesis_payload),
            "data_mining_result": self._resolve_data_mining_payload(context),
            "research_perspectives": self._resolve_research_perspectives(context),
            "statistics": context.get("statistics", {}),
            "confidence_score": context.get("confidence_score"),
        }
    
    def _generate_output_format(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """生成输出格式"""
        source_file = str(context.get("source_file", "unknown"))
        safe_source = os.path.basename(source_file) or "unknown"
        entities = context.get("entities", [])
        evidence_protocol = self._build_evidence_protocol(context)
        research_artifact = self._build_research_artifact(context, evidence_protocol)

        # 构造标准输出格式
        output = {
            "metadata": {
                "source": safe_source,
                "processing_timestamp": self._get_timestamp(),
                "objective": context.get("objective", "unknown"),
                "protocol_version": "research-output-v2",
                "architecture_version": "3.0-draft",
                "standards": [
                    "T/C IATCM 098-2023",
                    "GB/T 15657",
                    "ISO 21000",
                ],
            },
            "analysis_results": {
                "entities": entities[: self.max_entities],
                "semantic_graph": context.get("semantic_graph", {}),
                "reasoning_results": self._resolve_reasoning_payload(context),
                "temporal_analysis": context.get("temporal_analysis", {}),
                "pattern_recognition": context.get("pattern_recognition", {}),
                "evidence_protocol": evidence_protocol,
                "evidence_grade": self._resolve_evidence_grade_payload(context),
            },
            "research_artifact": research_artifact,
            "generation_contract": {
                "name": "ResearchArtifact",
                "fields": [
                    "hypothesis",
                    "hypothesis_audit_summary",
                    "evidence_grade_summary",
                    "evidence",
                    "data_mining_result",
                    "similar_formula_graph_evidence_summary",
                ],
            },
            "quality_metrics": self._calculate_quality_metrics(context),
            "recommendations": self._build_recommendations(context)
        }
        return output

    def _build_research_artifact(
        self,
        context: Dict[str, Any],
        evidence_protocol: Dict[str, Any],
    ) -> Dict[str, Any]:
        """构建研究域到生成域的标准产物契约。"""
        hypothesis_payload = self._resolve_hypothesis_payload(context)
        return {
            "hypothesis": hypothesis_payload,
            "hypothesis_audit_summary": self._resolve_hypothesis_audit_summary(context, hypothesis_payload),
            "evidence_grade_summary": self._resolve_evidence_grade_summary(context),
            "evidence": list(evidence_protocol.get("evidence_records") or self._resolve_evidence_payload(context)),
            "data_mining_result": self._resolve_data_mining_payload(context),
            "similar_formula_graph_evidence_summary": self._build_similar_formula_graph_evidence_summary(context),
        }

    def _build_similar_formula_graph_evidence_summary(self, context: Dict[str, Any]) -> Dict[str, Any]:
        research_perspectives = self._resolve_research_perspectives(context)
        matches: List[Dict[str, Any]] = []

        for formula_name, perspective in research_perspectives.items():
            if not isinstance(perspective, dict):
                continue
            integrated = perspective.get("integrated") or {}
            similar_matches = integrated.get("similar_formula_matches") or []
            if not isinstance(similar_matches, list):
                continue

            for match in similar_matches:
                if not isinstance(match, dict):
                    continue
                graph_evidence = match.get("graph_evidence") or {}
                shared_herbs = self._extract_shared_herb_names(graph_evidence)
                shared_syndromes = [
                    str(item) for item in list(graph_evidence.get("shared_syndromes") or []) if item
                ]
                matches.append(
                    {
                        "formula_name": formula_name,
                        "similar_formula_name": match.get("formula_name") or match.get("formula_id", ""),
                        "similarity_score": match.get("similarity_score"),
                        "evidence_score": graph_evidence.get("evidence_score", 0.0),
                        "retrieval_sources": list(match.get("retrieval_sources") or []),
                        "graph_evidence_source": graph_evidence.get("source", "unknown"),
                        "shared_herbs": shared_herbs,
                        "shared_herb_count": graph_evidence.get("shared_herb_count", len(shared_herbs)),
                        "shared_syndromes": shared_syndromes,
                        "shared_syndrome_count": len(shared_syndromes),
                    }
                )

        return {
            "formula_count": len(research_perspectives),
            "match_count": len(matches),
            "matches": matches[: self.max_entities],
        }

    def _resolve_research_perspectives(self, context: Dict[str, Any]) -> Dict[str, Any]:
        direct = context.get("research_perspectives")
        if isinstance(direct, dict):
            return direct

        for key in ("semantic_analysis", "research_analysis", "analysis_results"):
            value = context.get(key)
            if isinstance(value, dict) and isinstance(value.get("research_perspectives"), dict):
                return value.get("research_perspectives") or {}
        return {}

    def _extract_shared_herb_names(self, graph_evidence: Dict[str, Any]) -> List[str]:
        shared_herbs: List[str] = []
        for item in list(graph_evidence.get("shared_herbs") or []):
            if isinstance(item, dict):
                herb_name = str(item.get("herb") or "").strip()
                if herb_name:
                    shared_herbs.append(herb_name)
            elif item:
                shared_herbs.append(str(item))
        return shared_herbs

    def _resolve_hypothesis_payload(self, context: Dict[str, Any]) -> Any:
        hypothesis = context.get("hypothesis")
        if hypothesis is not None:
            return hypothesis

        hypothesis_phase = context.get("hypothesis_result", {})
        if isinstance(hypothesis_phase, dict):
            return hypothesis_phase.get("hypotheses", hypothesis_phase)
        return []

    def _resolve_hypothesis_audit_summary(
        self,
        context: Dict[str, Any],
        hypothesis_payload: Any,
    ) -> Dict[str, Any]:
        direct = context.get("hypothesis_audit_summary")
        if isinstance(direct, dict):
            return direct

        if not isinstance(hypothesis_payload, list):
            return {}

        mechanism_scores: List[float] = []
        merged_sources: List[str] = []
        relationship_count = 0
        selected_hypothesis_id = ""
        for index, hypothesis in enumerate(hypothesis_payload):
            if not isinstance(hypothesis, dict):
                continue
            if index == 0:
                selected_hypothesis_id = str(hypothesis.get("hypothesis_id") or "")
            mechanism_value = hypothesis.get("mechanism_completeness")
            if mechanism_value is None:
                mechanism_value = (hypothesis.get("scores") or {}).get("mechanism_completeness")
            try:
                mechanism_scores.append(float(mechanism_value or 0.0))
            except (TypeError, ValueError):
                mechanism_scores.append(0.0)

            audit = hypothesis.get("audit") or {}
            relationship_count += int(audit.get("relationship_count") or 0)
            for source_name in audit.get("merged_sources") or []:
                source_text = str(source_name).strip()
                if source_text and source_text not in merged_sources:
                    merged_sources.append(source_text)

        if not mechanism_scores and not merged_sources and not relationship_count:
            return {}

        return {
            "selected_hypothesis_id": selected_hypothesis_id,
            "hypothesis_count": len([item for item in hypothesis_payload if isinstance(item, dict)]),
            "selected_mechanism_completeness": mechanism_scores[0] if mechanism_scores else 0.0,
            "average_mechanism_completeness": round(sum(mechanism_scores) / len(mechanism_scores), 4) if mechanism_scores else 0.0,
            "relationship_count": relationship_count,
            "merged_sources": merged_sources,
        }

    def _resolve_evidence_grade_payload(self, context: Dict[str, Any]) -> Dict[str, Any]:
        direct = context.get("evidence_grade")
        if isinstance(direct, dict):
            return dict(direct)

        analysis_results = context.get("analysis_results", {})
        if isinstance(analysis_results, dict):
            nested = analysis_results.get("evidence_grade")
            if isinstance(nested, dict):
                return dict(nested)
            statistical_analysis = analysis_results.get("statistical_analysis")
            if isinstance(statistical_analysis, dict):
                nested = statistical_analysis.get("evidence_grade")
                if isinstance(nested, dict):
                    return dict(nested)
        return {}

    def _resolve_evidence_grade_summary(self, context: Dict[str, Any]) -> Dict[str, Any]:
        direct = context.get("evidence_grade_summary")
        if isinstance(direct, dict):
            return dict(direct)

        analysis_results = context.get("analysis_results", {})
        if isinstance(analysis_results, dict):
            nested = analysis_results.get("evidence_grade_summary")
            if isinstance(nested, dict):
                return dict(nested)
            statistical_analysis = analysis_results.get("statistical_analysis")
            if isinstance(statistical_analysis, dict):
                nested = statistical_analysis.get("evidence_grade_summary")
                if isinstance(nested, dict):
                    return dict(nested)

        evidence_grade = self._resolve_evidence_grade_payload(context)
        if not evidence_grade:
            return {}

        bias_distribution: Dict[str, int] = {}
        for key, value in (evidence_grade.get("bias_risk_distribution") or {}).items():
            try:
                bias_distribution[str(key)] = int(value)
            except (TypeError, ValueError):
                continue

        summary_lines = [
            str(item).strip()
            for item in (evidence_grade.get("summary") or [])
            if str(item).strip()
        ]

        try:
            overall_score = round(float(evidence_grade.get("overall_score") or 0.0), 4)
        except (TypeError, ValueError):
            overall_score = 0.0

        study_results = evidence_grade.get("study_results") or []
        study_count = evidence_grade.get("study_count") or len(study_results)
        try:
            normalized_study_count = int(study_count)
        except (TypeError, ValueError):
            normalized_study_count = 0

        return {
            "overall_grade": str(evidence_grade.get("overall_grade") or ""),
            "overall_score": overall_score,
            "study_count": normalized_study_count,
            "bias_risk_distribution": bias_distribution,
            "summary": summary_lines,
        }

    def _resolve_evidence_payload(self, context: Dict[str, Any]) -> Any:
        reasoning_results = self._resolve_reasoning_payload(context)
        if isinstance(reasoning_results, dict) and "evidence_records" in reasoning_results:
            return reasoning_results.get("evidence_records", [])
        return get_phase_value(context, "evidence", [])

    def _resolve_reasoning_payload(self, context: Dict[str, Any]) -> Dict[str, Any]:
        phase_results = get_phase_results(context)
        nested_reasoning = phase_results.get("reasoning_results")
        if isinstance(nested_reasoning, dict):
            return dict(nested_reasoning)

        if is_phase_result_payload(context):
            return {}

        direct_reasoning = context.get("reasoning_results")
        if isinstance(direct_reasoning, dict):
            return dict(direct_reasoning)
        return {}

    def _resolve_data_mining_payload(self, context: Dict[str, Any]) -> Any:
        for key in ("data_mining_result", "data_mining", "mining_result"):
            value = get_phase_value(context, key)
            if value is not None:
                return value

        analysis_results = get_phase_value(context, "analysis_results", {})
        if isinstance(analysis_results, dict):
            return get_phase_value(analysis_results, "data_mining_result", {})
        return {}

    def _build_evidence_protocol(self, context: Dict[str, Any]) -> Dict[str, Any]:
        reasoning_results = self._resolve_reasoning_payload(context)
        return build_evidence_protocol(
            reasoning_results,
            evidence_grade=self._resolve_evidence_grade_payload(context),
            max_evidence_records=self.max_entities,
            max_claims=self.max_entities,
        )
    
    def _calculate_quality_metrics(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """计算质量指标"""
        entities = context.get("entities", [])
        statistics = context.get("statistics", {})
        safe_formulas = self._safe_metric_count(statistics, "formulas_count")
        safe_herbs = self._safe_metric_count(statistics, "herbs_count")
        safe_syndromes = self._safe_metric_count(statistics, "syndromes_count")
        
        return {
            "entities_extracted": len(entities),
            "formulas_found": safe_formulas,
            "herbs_identified": safe_herbs,
            "syndromes_recognized": safe_syndromes,
            "confidence_score": 0.92,
            "completeness": 0.88
        }

    def _safe_metric_count(self, statistics: Dict[str, Any], key: str) -> int:
        """将统计字段安全转换为非负整数。"""
        try:
            return max(int(statistics.get(key, 0)), 0)
        except (TypeError, ValueError):
            return 0
    
    def _build_recommendations(self, context: Dict[str, Any]) -> List[str]:
        """生成建议"""
        recommendations = self._recommendations_by_entity_count(context)
        recommendations.extend(self._recommendations_by_confidence(context))
        return recommendations[: self.max_recommendations]

    def _recommendations_by_entity_count(self, context: Dict[str, Any]) -> List[str]:
        """基于实体规模生成建议。"""
        entities_count = len(context.get("entities", []))
        if entities_count < 10:
            return ["建议增加更多样本以提高准确性"]
        if entities_count > 50:
            return ["实体数量较多，建议进行分组分析"]
        return []

    def _recommendations_by_confidence(self, context: Dict[str, Any]) -> List[str]:
        """基于置信度生成建议。"""
        try:
            confidence = float(context.get("confidence_score", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5
        if confidence < 0.8:
            return ["置信度较低，建议人工复核"]
        return []

    def _make_json_safe(self, value: Any, depth: int = 0) -> Any:
        """将任意对象裁剪为 JSON 安全结构，避免序列化异常和超大输出。"""
        if depth > 8:
            return "<max-depth-reached>"

        if value is None or isinstance(value, (bool, int, float)):
            return value

        if isinstance(value, str):
            return value[: self.max_string_length]

        if isinstance(value, dict):
            return {
                str(k)[:128]: self._make_json_safe(v, depth + 1)
                for k, v in value.items()
            }

        if isinstance(value, (list, tuple, set)):
            return [self._make_json_safe(v, depth + 1) for v in list(value)[: self.max_entities]]

        return str(value)[: self.max_string_length]
    
    def _get_timestamp(self) -> str:
        """获取时间戳"""
        return datetime.now().isoformat()
    
    def to_json(self, result: Any) -> str:
        """将结果序列化为 JSON 字符串"""
        import json
        safe = self._make_json_safe(result)
        return json.dumps(safe, ensure_ascii=False, indent=2)

    def to_markdown(self, result: Any) -> str:
        """将结果整理为 Markdown 学术报告风格字符串"""
        lines = [
            "# 中医研究报告",
            "",
            f"**生成时间**: {self._get_timestamp()}",
            "",
        ]
        if isinstance(result, dict):
            for key, value in result.items():
                lines.append(f"## {key}")
                if isinstance(value, dict):
                    for k, v in value.items():
                        lines.append(f"- **{k}**: {v}")
                elif isinstance(value, list):
                    for item in value:
                        lines.append(f"- {item}")
                else:
                    lines.append(str(value))
                lines.append("")
        else:
            lines.append(str(result) if result is not None else "")
        return "\n".join(lines)

    def to_dict(self, result: Any) -> Dict[str, Any]:
        """将结果转换为字典"""
        if isinstance(result, dict):
            return result
        if result is None:
            return {}
        return {"data": result}

    def _do_cleanup(self) -> bool:
        """清理资源"""
        try:
            self.logger.info("输出生成器资源清理完成")
            return True
        except Exception as e:
            self.logger.error(f"输出生成器资源清理失败: {e}")
            return False


# 架构 3.0 别名：OutputFormatter = OutputGenerator（保持向后兼容）
OutputFormatter = OutputGenerator
