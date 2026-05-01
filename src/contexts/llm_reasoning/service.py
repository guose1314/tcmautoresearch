"""LLM gateway service skeleton."""

from __future__ import annotations

import logging
from typing import Any, Callable, Dict, Mapping, Optional

from src.contexts.llm_reasoning.contracts import (
    LLMGatewayRequest,
    LLMGatewayResult,
)
from src.contexts.llm_reasoning.schema_registry import (
    SchemaResolution,
    SchemaValidation,
    build_schema_prompt_instruction,
    build_schema_warning,
    resolve_schema_binding,
    validate_schema_output,
)
from src.infra.llm_service import prepare_planned_llm_call

logger = logging.getLogger(__name__)


class LLMGateway:
    """Single entry point for LLM-facing bounded-context calls."""

    def __init__(
        self,
        llm_service: Any = None,
        *,
        llm_config: Optional[Dict[str, Any]] = None,
        template_preferences: Optional[Dict[str, float]] = None,
        auto_resolve_service: bool = False,
        planner_factory: Optional[Callable[..., Any]] = None,
    ) -> None:
        self._llm_service = llm_service
        self._llm_config = dict(llm_config or {}) if llm_config is not None else None
        self._template_preferences = dict(template_preferences or {})
        self._auto_resolve_service = bool(auto_resolve_service)
        self._planner_factory = planner_factory or prepare_planned_llm_call

    def generate(
        self, request: LLMGatewayRequest | Mapping[str, Any]
    ) -> LLMGatewayResult:
        normalized_request = self._normalize_request(request)
        schema_resolution = resolve_schema_binding(
            normalized_request.schema_name,
            context=normalized_request.context,
            metadata=normalized_request.metadata,
        )
        schema_prompt = build_schema_prompt_instruction(schema_resolution)
        generation_request = self._with_schema_prompt(
            normalized_request,
            schema_prompt,
        )
        base_warnings = list(schema_resolution.warnings)
        if self._llm_service is None and not self._auto_resolve_service:
            return LLMGatewayResult(
                reasoning_mode=normalized_request.reasoning_mode,
                schema_name=normalized_request.schema_name,
                metadata=self._build_result_metadata(
                    normalized_request,
                    schema_resolution=schema_resolution,
                    schema_prompt_applied=bool(schema_prompt),
                ),
                warnings=base_warnings + ["llm_service_missing"],
            )

        try:
            planned_call = self._prepare_planned_call(generation_request)
            wrapped_service = planned_call.create_proxy()
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLMGateway planning failed: %s", exc)
            return LLMGatewayResult(
                reasoning_mode=normalized_request.reasoning_mode,
                schema_name=normalized_request.schema_name,
                metadata=self._build_result_metadata(
                    normalized_request,
                    schema_resolution=schema_resolution,
                    schema_prompt_applied=bool(schema_prompt),
                ),
                warnings=base_warnings
                + [f"llm_planning_failed: {type(exc).__name__}: {exc}"],
            )

        if wrapped_service is None or not hasattr(wrapped_service, "generate"):
            return LLMGatewayResult(
                reasoning_mode=normalized_request.reasoning_mode,
                schema_name=normalized_request.schema_name,
                metadata=self._build_result_metadata(
                    normalized_request,
                    planned_call,
                    schema_resolution=schema_resolution,
                    schema_prompt_applied=bool(schema_prompt),
                ),
                llm_cost_report=self._build_llm_cost_report(planned_call),
                warnings=base_warnings + ["llm_service_missing"],
            )

        try:
            generated = wrapped_service.generate(
                generation_request.prompt,
                generation_request.system_prompt,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLMGateway generate failed: %s", exc)
            return LLMGatewayResult(
                reasoning_mode=normalized_request.reasoning_mode,
                schema_name=normalized_request.schema_name,
                metadata=self._build_result_metadata(
                    normalized_request,
                    planned_call,
                    schema_resolution=schema_resolution,
                    schema_prompt_applied=bool(schema_prompt),
                ),
                llm_cost_report=self._build_llm_cost_report(planned_call),
                warnings=base_warnings
                + [f"llm_generate_failed: {type(exc).__name__}: {exc}"],
            )

        warnings = list(base_warnings)
        if not planned_call.should_call_llm:
            fallback = str(getattr(planned_call, "fallback_path", "") or "rules_engine")
            warnings.append(f"llm_call_skipped: {fallback}")

        schema_validation = validate_schema_output(schema_resolution, generated)
        structured: Any = {}
        if schema_validation is not None:
            if schema_validation.schema_valid:
                structured = schema_validation.parsed
            else:
                warnings.append(build_schema_warning(schema_validation))

        return LLMGatewayResult(
            text=str(generated or ""),
            structured=structured,
            retrieval_trace=self._build_retrieval_trace(normalized_request),
            llm_cost_report=self._build_llm_cost_report(planned_call),
            warnings=warnings,
            reasoning_mode=normalized_request.reasoning_mode,
            schema_name=normalized_request.schema_name,
            metadata=self._build_result_metadata(
                normalized_request,
                planned_call,
                schema_resolution=schema_resolution,
                schema_validation=schema_validation,
                schema_prompt_applied=bool(schema_prompt),
            ),
        )

    def _prepare_planned_call(self, request: LLMGatewayRequest) -> Any:
        return self._planner_factory(
            phase=request.phase,
            task_type=request.task_type,
            dossier_sections=self._resolve_dossier_sections(request),
            llm_engine=self._llm_service,
            purpose=request.purpose,
            template_preferences=self._resolve_template_preferences(request),
            cache_hit_likelihood=self._resolve_float_option(
                request,
                "cache_hit_likelihood",
                default=0.0,
            ),
            retry_count=int(
                self._resolve_int_option(request, "retry_count", default=0) or 0
            ),
            llm_config=self._llm_config,
            role=self._resolve_text_option(request, "role"),
            kv_cache_descriptor=self._resolve_option(request, "kv_cache_descriptor"),
            max_input_tokens=request.max_input_tokens,
        )

    @staticmethod
    def _normalize_request(
        request: LLMGatewayRequest | Mapping[str, Any],
    ) -> LLMGatewayRequest:
        if isinstance(request, LLMGatewayRequest):
            return request
        if isinstance(request, Mapping):
            return LLMGatewayRequest(**dict(request))
        raise TypeError("LLMGateway.generate() requires LLMGatewayRequest or mapping")

    @staticmethod
    def _build_result_metadata(
        request: LLMGatewayRequest,
        planned_call: Any = None,
        *,
        schema_resolution: Optional[SchemaResolution] = None,
        schema_validation: Optional[SchemaValidation] = None,
        schema_prompt_applied: bool = False,
    ) -> Dict[str, Any]:
        metadata = {
            "phase": request.phase,
            "purpose": request.purpose,
            "task_type": request.task_type,
            "max_input_tokens": request.max_input_tokens,
        }
        if planned_call is not None and hasattr(planned_call, "to_metadata"):
            metadata["planned_call"] = planned_call.to_metadata()
        if request.schema_name:
            if schema_resolution is not None:
                schema_metadata = schema_resolution.to_metadata(
                    prompt_schema_included=schema_prompt_applied
                )
            else:
                schema_metadata = {
                    "schema_name": request.schema_name,
                    "schema_found": False,
                    "prompt_schema_included": False,
                }
            if schema_validation is not None:
                schema_metadata.update(schema_validation.to_metadata())
            metadata["schema_validation"] = schema_metadata
        return metadata

    @staticmethod
    def _with_schema_prompt(
        request: LLMGatewayRequest,
        schema_prompt: str,
    ) -> LLMGatewayRequest:
        schema_prompt = str(schema_prompt or "").strip()
        if not schema_prompt:
            return request
        prompt = "\n\n".join(
            section for section in (request.prompt, schema_prompt) if section.strip()
        )
        return LLMGatewayRequest(
            prompt=prompt,
            system_prompt=request.system_prompt,
            phase=request.phase,
            purpose=request.purpose,
            task_type=request.task_type,
            schema_name=request.schema_name,
            graph_rag=request.graph_rag,
            reasoning_mode=request.reasoning_mode,
            max_input_tokens=request.max_input_tokens,
            context=dict(request.context),
            metadata=dict(request.metadata),
        )

    @staticmethod
    def _build_retrieval_trace(request: LLMGatewayRequest) -> Dict[str, Any]:
        if not request.graph_rag.enabled:
            return {}
        return {"graph_rag": request.graph_rag.to_dict()}

    def _build_llm_cost_report(self, planned_call: Any) -> Dict[str, Any]:
        report: Dict[str, Any] = {}
        if hasattr(planned_call, "to_metadata"):
            report["planned_call"] = planned_call.to_metadata()
        if hasattr(planned_call, "get_cost_report"):
            try:
                optimizer_cost = planned_call.get_cost_report()
            except Exception:  # noqa: BLE001
                logger.debug(
                    "LLMGateway optimizer cost report unavailable", exc_info=True
                )
                optimizer_cost = None
            if isinstance(optimizer_cost, Mapping) and optimizer_cost:
                report["optimizer"] = dict(optimizer_cost)

        llm_service = getattr(planned_call, "llm_service", None)
        service_report = self._call_mapping_method(llm_service, "get_cost_report")
        if service_report:
            report["service"] = service_report
        cache_report = self._call_mapping_method(llm_service, "cache_stats")
        if cache_report:
            report["cache"] = cache_report
        return report

    @staticmethod
    def _call_mapping_method(target: Any, method_name: str) -> Dict[str, Any]:
        method = getattr(target, method_name, None)
        if method is None:
            return {}
        try:
            payload = method()
        except Exception:  # noqa: BLE001
            logger.debug("LLMGateway %s unavailable", method_name, exc_info=True)
            return {}
        return dict(payload or {}) if isinstance(payload, Mapping) else {}

    @staticmethod
    def _resolve_dossier_sections(request: LLMGatewayRequest) -> Dict[str, Any]:
        value = request.context.get("dossier_sections") or request.metadata.get(
            "dossier_sections"
        )
        return dict(value) if isinstance(value, Mapping) else {}

    def _resolve_template_preferences(
        self,
        request: LLMGatewayRequest,
    ) -> Dict[str, float]:
        raw = self._resolve_option(request, "template_preferences")
        source = raw if isinstance(raw, Mapping) else self._template_preferences
        preferences: Dict[str, float] = {}
        for key, value in dict(source or {}).items():
            try:
                preferences[str(key)] = float(value)
            except (TypeError, ValueError):
                continue
        return preferences

    @staticmethod
    def _resolve_option(request: LLMGatewayRequest, key: str) -> Any:
        if key in request.context:
            return request.context.get(key)
        return request.metadata.get(key)

    @classmethod
    def _resolve_text_option(cls, request: LLMGatewayRequest, key: str) -> str:
        value = cls._resolve_option(request, key)
        return str(value or "").strip()

    @classmethod
    def _resolve_float_option(
        cls,
        request: LLMGatewayRequest,
        key: str,
        *,
        default: float,
    ) -> float:
        value = cls._resolve_option(request, key)
        try:
            return float(value if value is not None else default)
        except (TypeError, ValueError):
            return default

    @classmethod
    def _resolve_int_option(
        cls,
        request: LLMGatewayRequest,
        key: str,
        *,
        default: int,
    ) -> int:
        value = cls._resolve_option(request, key)
        try:
            return int(value if value is not None else default)
        except (TypeError, ValueError):
            return default


__all__ = ["LLMGateway"]
