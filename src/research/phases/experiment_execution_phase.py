from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List

from src.research.learning_strategy import (
    has_learning_strategy,
    resolve_learning_flag,
    resolve_learning_strategy,
    resolve_numeric_learning_parameter,
)
from src.research.phase_result import build_phase_result, get_phase_value

if TYPE_CHECKING:
    from src.research.research_pipeline import ResearchCycle, ResearchPipeline


_EXECUTION_DISPLAY_NAME = "实验执行阶段"
_EXECUTION_BOUNDARY_NOTICE = "当前阶段仅接收外部实验执行、采样与结果导入，不在系统内自动开展真实实验。"


class ExperimentExecutionPhaseMixin:
    """Mixin: experiment_execution 阶段处理方法。"""

    pipeline: "ResearchPipeline"

    def execute_experiment_execution_phase(self, cycle: "ResearchCycle", context: Dict[str, Any]) -> Dict[str, Any]:
        context = context or {}
        protocol_design, selected_hypothesis, experiment_result = self._resolve_execution_protocol_context(cycle)
        if not protocol_design:
            return build_phase_result(
                "experiment_execution",
                status="blocked",
                results={
                    "protocol_design": {},
                    "selected_hypothesis": {},
                    "execution_records": [],
                    "analysis_records": [],
                    "execution_relationships": [],
                    "analysis_relationships": [],
                    "sampling_events": [],
                    "execution_summary": {},
                    "output_files": {},
                    "execution_status": "not_executed",
                    "real_world_validation_status": "not_started",
                },
                metadata={
                    "phase_semantics": "experiment_execution",
                    "phase_display_name": _EXECUTION_DISPLAY_NAME,
                    "execution_boundary": _EXECUTION_BOUNDARY_NOTICE,
                    "external_execution_required": True,
                    "validation_status": "blocked",
                    "reason": "missing_protocol_design",
                    "execution_status": "not_executed",
                    "real_world_validation_status": "not_started",
                    "learning_strategy_applied": has_learning_strategy(context, self.pipeline.config),
                },
            )

        document_fallback_enabled = self._resolve_execution_flag(
            context,
            "allow_document_fallback_import",
            True,
        )
        execution_documents = self._resolve_execution_documents(context)
        execution_records = self._resolve_execution_records(
            context,
            execution_documents,
            document_fallback_enabled,
        )
        execution_relationships = self._resolve_execution_relationships(
            context,
            execution_documents,
            document_fallback_enabled,
        )
        sampling_events = self._resolve_sampling_events(context)
        execution_summary = self._resolve_execution_summary(context)
        execution_artifacts = self._resolve_execution_artifacts(context)
        output_files = self._build_execution_output_file_map(context, execution_artifacts)

        has_structured_external_inputs = any(
            (
                execution_records,
                execution_relationships,
                sampling_events,
                execution_summary,
                output_files,
            )
        )
        has_external_inputs = has_structured_external_inputs or (
            document_fallback_enabled and bool(execution_documents)
        )
        execution_status = str(
            context.get("execution_status")
            or execution_summary.get("execution_status")
            or ("results_imported" if has_external_inputs else "not_executed")
        ).strip() or ("results_imported" if has_external_inputs else "not_executed")
        real_world_validation_status = str(
            context.get("real_world_validation_status")
            or execution_summary.get("real_world_validation_status")
            or ("results_imported" if has_external_inputs else "not_started")
        ).strip() or ("results_imported" if has_external_inputs else "not_started")
        status = "completed" if has_external_inputs else "skipped"

        metadata = {
            "phase_semantics": "experiment_execution",
            "phase_display_name": _EXECUTION_DISPLAY_NAME,
            "execution_boundary": _EXECUTION_BOUNDARY_NOTICE,
            "external_execution_required": True,
            "validation_status": "results_imported" if has_external_inputs else "awaiting_external_execution",
            "protocol_source": str(
                get_phase_value(experiment_result, "study_protocol", {}).get("protocol_source")
                or protocol_design.get("protocol_source")
                or (experiment_result.get("metadata") or {}).get("protocol_source")
                or ""
            ),
            "import_mode": str(context.get("import_mode") or "manual").strip() or "manual",
            "imported_record_count": len(execution_records),
            "imported_relationship_count": len(execution_relationships),
            "sampling_event_count": len(sampling_events),
            "imported_artifact_count": len(output_files),
            "document_count": len(execution_documents),
            "execution_status": execution_status,
            "real_world_validation_status": real_world_validation_status,
            "learning_strategy_applied": has_learning_strategy(context, self.pipeline.config),
            "document_fallback_import_enabled": document_fallback_enabled,
        }

        return build_phase_result(
            "experiment_execution",
            status=status,
            results={
                "protocol_design": protocol_design,
                "selected_hypothesis": selected_hypothesis,
                "documents": execution_documents,
                "execution_records": execution_records,
                "analysis_records": execution_records,
                "execution_relationships": execution_relationships,
                "analysis_relationships": execution_relationships,
                "sampling_events": sampling_events,
                "execution_summary": execution_summary,
                "output_files": output_files,
                "execution_status": execution_status,
                "real_world_validation_status": real_world_validation_status,
            },
            artifacts=execution_artifacts,
            metadata=metadata,
        )

    def _resolve_execution_protocol_context(
        self,
        cycle: "ResearchCycle",
    ) -> tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
        experiment_result = cycle.phase_executions.get(self.pipeline.ResearchPhase.EXPERIMENT, {}).get("result", {})
        if not isinstance(experiment_result, dict):
            return {}, {}, {}

        protocol_design = get_phase_value(experiment_result, "protocol_design", {}) or {}
        if not isinstance(protocol_design, dict) or not protocol_design:
            protocol_designs = get_phase_value(experiment_result, "protocol_designs", []) or []
            if isinstance(protocol_designs, list) and protocol_designs and isinstance(protocol_designs[0], dict):
                protocol_design = dict(protocol_designs[0])

        selected_hypothesis = get_phase_value(experiment_result, "selected_hypothesis", {}) or {}
        if not isinstance(selected_hypothesis, dict):
            selected_hypothesis = {}

        return protocol_design if isinstance(protocol_design, dict) else {}, selected_hypothesis, experiment_result

    def _resolve_execution_documents(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        for key in ("execution_documents", "imported_documents", "documents"):
            candidate = context.get(key)
            if isinstance(candidate, list):
                return [item for item in candidate if isinstance(item, dict)]
        return []

    def _resolve_execution_records(
        self,
        context: Dict[str, Any],
        execution_documents: List[Dict[str, Any]],
        allow_document_fallback_import: bool,
    ) -> List[Dict[str, Any]]:
        normalized_records: List[Dict[str, Any]] = []
        for key in ("analysis_records", "execution_records", "imported_records", "result_records", "records"):
            candidate = context.get(key)
            if not isinstance(candidate, list):
                continue
            normalized_records = self._normalize_analyze_records(candidate)
            if normalized_records:
                break

        if not normalized_records and allow_document_fallback_import:
            for index, document in enumerate(execution_documents, start=1):
                record = self._build_analyze_record_from_document(document, index)
                if record:
                    normalized_records.append(record)

        return normalized_records[: self._resolve_execution_max_records(context)]

    def _resolve_execution_relationships(
        self,
        context: Dict[str, Any],
        execution_documents: List[Dict[str, Any]],
        allow_document_fallback_import: bool,
    ) -> List[Dict[str, Any]]:
        relationships: List[Dict[str, Any]] = []
        for key in (
            "analysis_relationships",
            "execution_relationships",
            "imported_relationships",
            "semantic_relationships",
            "relationships",
        ):
            candidate = context.get(key)
            if isinstance(candidate, list) and candidate:
                relationships = self._deduplicate_analyze_relationships(
                    [item for item in candidate if isinstance(item, dict)]
                )
                break

        if not relationships and allow_document_fallback_import:
            for document in execution_documents:
                relationships.extend(
                    item for item in (document.get("semantic_relationships") or []) if isinstance(item, dict)
                )
        if not relationships:
            return []

        filtered_relationships = self._filter_execution_relationships_by_confidence(
            self._deduplicate_analyze_relationships(relationships),
            context,
        )
        return filtered_relationships[: self._resolve_execution_max_relationships(context)]

    def _resolve_sampling_events(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        for key in ("sampling_events", "samples", "sampling_records"):
            candidate = context.get(key)
            if not isinstance(candidate, list):
                continue
            normalized_events: List[Dict[str, Any]] = []
            for index, item in enumerate(candidate, start=1):
                if isinstance(item, dict):
                    normalized_events.append(dict(item))
                elif item not in (None, ""):
                    normalized_events.append({"event": str(item), "index": index})
            if normalized_events:
                return normalized_events[: self._resolve_execution_max_sampling_events(context)]
        return []

    def _resolve_execution_summary(self, context: Dict[str, Any]) -> Dict[str, Any]:
        for key in ("execution_summary", "import_summary", "external_execution_summary"):
            candidate = context.get(key)
            if isinstance(candidate, dict):
                return dict(candidate)
        return {}

    def _resolve_execution_artifacts(self, context: Dict[str, Any]) -> Any:
        for key in ("execution_artifacts", "imported_artifacts", "artifacts", "output_files"):
            candidate = context.get(key)
            if candidate not in (None, "", [], {}):
                return candidate
        return []

    def _build_execution_output_file_map(self, context: Dict[str, Any], artifacts: Any) -> Dict[str, str]:
        candidate = context.get("output_files")
        if isinstance(candidate, dict):
            return {
                str(name): str(path)
                for name, path in candidate.items()
                if path not in (None, "", [], {})
            }

        if isinstance(artifacts, dict):
            return {
                str(name): str(path)
                for name, path in artifacts.items()
                if path not in (None, "", [], {})
            }

        if not isinstance(artifacts, list):
            return {}

        output_files: Dict[str, str] = {}
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            name = str(artifact.get("name") or artifact.get("type") or "").strip()
            path = str(artifact.get("path") or "").strip()
            if name and path:
                output_files[name] = path
        return output_files

    def _resolve_execution_flag(
        self,
        context: Dict[str, Any],
        flag_name: str,
        default: bool,
    ) -> bool:
        prefixed_context_key = f"experiment_execution_{flag_name}"
        if prefixed_context_key in context:
            return bool(context.get(prefixed_context_key))
        if flag_name in context:
            return bool(context.get(flag_name))

        strategy = resolve_learning_strategy(context, self.pipeline.config)
        strategy_flag_name = f"experiment_execution_{flag_name}"
        if strategy_flag_name in strategy:
            return bool(strategy.get(strategy_flag_name))

        return resolve_learning_flag(flag_name, default, context, self.pipeline.config)

    def _resolve_execution_max_records(self, context: Dict[str, Any]) -> int:
        return self._resolve_execution_volume_limit(
            context,
            context_keys=("experiment_execution_max_records", "max_execution_records"),
            strategy_key="experiment_execution_max_records",
            default_without_strategy=200,
            low_quality_value=12,
            medium_quality_value=24,
            high_quality_value=40,
            very_high_quality_value=60,
            min_value=1,
            max_value=500,
        )

    def _resolve_execution_max_relationships(self, context: Dict[str, Any]) -> int:
        return self._resolve_execution_volume_limit(
            context,
            context_keys=("experiment_execution_max_relationships", "max_execution_relationships"),
            strategy_key="experiment_execution_max_relationships",
            default_without_strategy=400,
            low_quality_value=24,
            medium_quality_value=48,
            high_quality_value=80,
            very_high_quality_value=120,
            min_value=1,
            max_value=1000,
        )

    def _resolve_execution_max_sampling_events(self, context: Dict[str, Any]) -> int:
        return self._resolve_execution_volume_limit(
            context,
            context_keys=("experiment_execution_max_sampling_events", "max_execution_sampling_events"),
            strategy_key="experiment_execution_max_sampling_events",
            default_without_strategy=50,
            low_quality_value=6,
            medium_quality_value=10,
            high_quality_value=16,
            very_high_quality_value=20,
            min_value=1,
            max_value=100,
        )

    def _resolve_execution_volume_limit(
        self,
        context: Dict[str, Any],
        *,
        context_keys: tuple[str, ...],
        strategy_key: str,
        default_without_strategy: int,
        low_quality_value: int,
        medium_quality_value: int,
        high_quality_value: int,
        very_high_quality_value: int,
        min_value: int,
        max_value: int,
    ) -> int:
        for key in context_keys:
            explicit_value = context.get(key)
            if explicit_value is None:
                continue
            try:
                return max(min_value, min(int(explicit_value), max_value))
            except (TypeError, ValueError):
                break

        strategy = resolve_learning_strategy(context, self.pipeline.config)
        strategy_value = strategy.get(strategy_key)
        if strategy_value is not None:
            try:
                return max(min_value, min(int(strategy_value), max_value))
            except (TypeError, ValueError):
                pass

        if not has_learning_strategy(context, self.pipeline.config):
            return default_without_strategy

        quality_threshold = resolve_numeric_learning_parameter(
            "quality_threshold",
            0.7,
            context,
            self.pipeline.config,
            min_value=0.3,
            max_value=0.95,
        )
        if quality_threshold >= 0.82:
            return very_high_quality_value
        if quality_threshold >= 0.74:
            return high_quality_value
        if quality_threshold <= 0.55:
            return low_quality_value
        return medium_quality_value

    def _filter_execution_relationships_by_confidence(
        self,
        relationships: List[Dict[str, Any]],
        context: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        explicit_threshold = None
        for key in ("experiment_execution_confidence_threshold", "execution_confidence_threshold"):
            if context.get(key) is not None:
                explicit_threshold = context.get(key)
                break

        strategy = resolve_learning_strategy(context, self.pipeline.config)
        if explicit_threshold is None and strategy.get("experiment_execution_confidence_threshold") is not None:
            explicit_threshold = strategy.get("experiment_execution_confidence_threshold")

        if explicit_threshold is None and not has_learning_strategy(context, self.pipeline.config):
            return relationships

        if explicit_threshold is None:
            confidence_threshold = resolve_numeric_learning_parameter(
                "confidence_threshold",
                0.7,
                context,
                self.pipeline.config,
                min_value=0.0,
                max_value=1.0,
            )
        else:
            try:
                confidence_threshold = min(1.0, max(0.0, float(explicit_threshold)))
            except (TypeError, ValueError):
                confidence_threshold = 0.0

        if confidence_threshold <= 0.0:
            return relationships

        filtered_relationships: List[Dict[str, Any]] = []
        for relationship in relationships:
            metadata = relationship.get("metadata") or {}
            has_explicit_confidence = "confidence" in metadata or "confidence" in relationship
            if not has_explicit_confidence:
                filtered_relationships.append(relationship)
                continue
            try:
                confidence = float(metadata.get("confidence", relationship.get("confidence") or 0.0))
            except (TypeError, ValueError):
                confidence = 0.0
            if confidence >= confidence_threshold:
                filtered_relationships.append(relationship)
        return filtered_relationships