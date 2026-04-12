from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, List

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
                },
            )

        execution_documents = self._resolve_execution_documents(context)
        execution_records = self._resolve_execution_records(context, execution_documents)
        execution_relationships = self._resolve_execution_relationships(context, execution_documents)
        sampling_events = self._resolve_sampling_events(context)
        execution_summary = self._resolve_execution_summary(context)
        execution_artifacts = self._resolve_execution_artifacts(context)
        output_files = self._build_execution_output_file_map(context, execution_artifacts)

        has_external_inputs = any(
            (
                execution_records,
                execution_relationships,
                sampling_events,
                execution_summary,
                output_files,
                execution_documents,
            )
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
            "execution_status": execution_status,
            "real_world_validation_status": real_world_validation_status,
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
    ) -> List[Dict[str, Any]]:
        for key in ("analysis_records", "execution_records", "imported_records", "result_records", "records"):
            candidate = context.get(key)
            if not isinstance(candidate, list):
                continue
            normalized_records = self._normalize_analyze_records(candidate)
            if normalized_records:
                return normalized_records

        records: List[Dict[str, Any]] = []
        for index, document in enumerate(execution_documents, start=1):
            record = self._build_analyze_record_from_document(document, index)
            if record:
                records.append(record)
        return records

    def _resolve_execution_relationships(
        self,
        context: Dict[str, Any],
        execution_documents: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        for key in (
            "analysis_relationships",
            "execution_relationships",
            "imported_relationships",
            "semantic_relationships",
            "relationships",
        ):
            candidate = context.get(key)
            if isinstance(candidate, list) and candidate:
                return self._deduplicate_analyze_relationships(
                    [item for item in candidate if isinstance(item, dict)]
                )

        relationships: List[Dict[str, Any]] = []
        for document in execution_documents:
            relationships.extend(
                item for item in (document.get("semantic_relationships") or []) if isinstance(item, dict)
            )
        if not relationships:
            return []
        return self._deduplicate_analyze_relationships(relationships)

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
                return normalized_events
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