"""LLM gateway service skeleton."""

from __future__ import annotations

import concurrent.futures
import json
import logging
import re
import time
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
from src.infra.layered_cache import describe_llm_engine
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
        started_at = time.perf_counter()
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
            metadata = self._with_observability_metadata(
                self._build_result_metadata(
                    normalized_request,
                    schema_resolution=schema_resolution,
                    schema_prompt_applied=bool(schema_prompt),
                ),
                normalized_request,
                planned_call=None,
                latency_s=self._elapsed(started_at),
                json_repair_status="not_requested",
            )
            return LLMGatewayResult(
                reasoning_mode=normalized_request.reasoning_mode,
                schema_name=normalized_request.schema_name,
                prompt_version=normalized_request.prompt_version,
                model_id=metadata["model_id"],
                latency_s=metadata["latency_s"],
                token_budget=metadata["token_budget"],
                json_repair_status=metadata["json_repair_status"],
                metadata=metadata,
                warnings=base_warnings + ["llm_service_missing"],
            )

        try:
            planned_call = self._prepare_planned_call(generation_request)
            wrapped_service = planned_call.create_proxy()
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLMGateway planning failed: %s", exc)
            metadata = self._with_observability_metadata(
                self._build_result_metadata(
                    normalized_request,
                    schema_resolution=schema_resolution,
                    schema_prompt_applied=bool(schema_prompt),
                ),
                normalized_request,
                planned_call=None,
                latency_s=self._elapsed(started_at),
                json_repair_status="not_requested",
            )
            return LLMGatewayResult(
                reasoning_mode=normalized_request.reasoning_mode,
                schema_name=normalized_request.schema_name,
                prompt_version=normalized_request.prompt_version,
                model_id=metadata["model_id"],
                latency_s=metadata["latency_s"],
                token_budget=metadata["token_budget"],
                json_repair_status=metadata["json_repair_status"],
                metadata=metadata,
                warnings=base_warnings
                + [f"llm_planning_failed: {type(exc).__name__}: {exc}"],
            )

        if wrapped_service is None or not hasattr(wrapped_service, "generate"):
            metadata = self._with_observability_metadata(
                self._build_result_metadata(
                    normalized_request,
                    planned_call,
                    schema_resolution=schema_resolution,
                    schema_prompt_applied=bool(schema_prompt),
                ),
                normalized_request,
                planned_call=planned_call,
                latency_s=self._elapsed(started_at),
                json_repair_status="not_requested",
            )
            return LLMGatewayResult(
                reasoning_mode=normalized_request.reasoning_mode,
                schema_name=normalized_request.schema_name,
                prompt_version=normalized_request.prompt_version,
                model_id=metadata["model_id"],
                latency_s=metadata["latency_s"],
                token_budget=metadata["token_budget"],
                json_repair_status=metadata["json_repair_status"],
                metadata=metadata,
                llm_cost_report=self._build_llm_cost_report(planned_call),
                warnings=base_warnings + ["llm_service_missing"],
            )

        attempts_used = 0
        generated: Any = ""
        generate_warnings: list[str] = []
        try:
            for attempt_index in range(max(normalized_request.retry_count, 0) + 1):
                attempts_used = attempt_index + 1
                try:
                    generated = self._invoke_generate(
                        wrapped_service,
                        generation_request.prompt,
                        generation_request.system_prompt,
                        timeout_s=normalized_request.timeout_s,
                    )
                    break
                except Exception as exc:  # noqa: BLE001
                    if attempt_index >= max(normalized_request.retry_count, 0):
                        raise
                    generate_warnings.append(
                        f"llm_generate_retry:{attempt_index + 1}: "
                        f"{type(exc).__name__}: {exc}"
                    )
        except Exception as exc:  # noqa: BLE001
            logger.warning("LLMGateway generate failed: %s", exc)
            metadata = self._with_observability_metadata(
                self._build_result_metadata(
                    normalized_request,
                    planned_call,
                    schema_resolution=schema_resolution,
                    schema_prompt_applied=bool(schema_prompt),
                ),
                normalized_request,
                planned_call=planned_call,
                latency_s=self._elapsed(started_at),
                json_repair_status="not_requested",
                attempts_used=attempts_used,
            )
            return LLMGatewayResult(
                reasoning_mode=normalized_request.reasoning_mode,
                schema_name=normalized_request.schema_name,
                prompt_version=normalized_request.prompt_version,
                model_id=metadata["model_id"],
                latency_s=metadata["latency_s"],
                token_budget=metadata["token_budget"],
                json_repair_status=metadata["json_repair_status"],
                metadata=metadata,
                llm_cost_report=self._build_llm_cost_report(planned_call),
                warnings=base_warnings
                + generate_warnings
                + [f"llm_generate_failed: {type(exc).__name__}: {exc}"],
            )

        warnings = list(base_warnings) + generate_warnings
        if not planned_call.should_call_llm:
            fallback = str(getattr(planned_call, "fallback_path", "") or "rules_engine")
            warnings.append(f"llm_call_skipped: {fallback}")

        repaired_text, json_repair_status, repair_warning = self._repair_json_output(
            normalized_request,
            str(generated or ""),
        )
        if repair_warning:
            warnings.append(repair_warning)

        schema_validation = validate_schema_output(schema_resolution, repaired_text)
        structured: Any = {}
        if schema_validation is not None:
            if schema_validation.schema_valid:
                structured = schema_validation.parsed
            else:
                warnings.append(build_schema_warning(schema_validation))
        elif not normalized_request.schema_name and json_repair_status in {
            "valid_json",
            "repaired",
        }:
            try:
                structured = json.loads(repaired_text)
            except Exception:  # noqa: BLE001
                structured = {}

        latency_s = self._elapsed(started_at)
        metadata = self._with_observability_metadata(
            self._build_result_metadata(
                normalized_request,
                planned_call,
                schema_resolution=schema_resolution,
                schema_validation=schema_validation,
                schema_prompt_applied=bool(schema_prompt),
            ),
            normalized_request,
            planned_call=planned_call,
            latency_s=latency_s,
            json_repair_status=json_repair_status,
            attempts_used=attempts_used,
        )

        return LLMGatewayResult(
            text=repaired_text,
            structured=structured,
            retrieval_trace=self._build_retrieval_trace(normalized_request),
            llm_cost_report=self._build_llm_cost_report(planned_call),
            warnings=warnings,
            reasoning_mode=normalized_request.reasoning_mode,
            schema_name=normalized_request.schema_name,
            prompt_version=normalized_request.prompt_version,
            model_id=metadata["model_id"],
            latency_s=latency_s,
            token_budget=metadata["token_budget"],
            json_repair_status=json_repair_status,
            metadata=metadata,
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
            retry_count=max(
                int(self._resolve_int_option(request, "retry_count", default=0) or 0),
                int(request.retry_count or 0),
            ),
            llm_config=self._llm_config,
            role=self._resolve_text_option(request, "role"),
            kv_cache_descriptor=self._resolve_option(request, "kv_cache_descriptor"),
            max_input_tokens=request.max_input_tokens or request.token_budget,
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
            "prompt_version": request.prompt_version,
            "model_id": request.model_id,
            "max_input_tokens": request.max_input_tokens,
            "token_budget": request.token_budget,
            "timeout_s": request.timeout_s,
            "retry_count": request.retry_count,
            "json_output": request.json_output,
            "gpu_params": dict(request.gpu_params),
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
            prompt_version=request.prompt_version,
            model_id=request.model_id,
            phase=request.phase,
            purpose=request.purpose,
            task_type=request.task_type,
            schema_name=request.schema_name,
            graph_rag=request.graph_rag,
            reasoning_mode=request.reasoning_mode,
            max_input_tokens=request.max_input_tokens,
            token_budget=request.token_budget,
            timeout_s=request.timeout_s,
            retry_count=request.retry_count,
            json_output=request.json_output,
            gpu_params=dict(request.gpu_params),
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
    def _invoke_generate(
        wrapped_service: Any,
        prompt: str,
        system_prompt: str,
        *,
        timeout_s: Optional[float],
    ) -> Any:
        if not timeout_s:
            return wrapped_service.generate(prompt, system_prompt)
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        future = executor.submit(wrapped_service.generate, prompt, system_prompt)
        try:
            return future.result(timeout=float(timeout_s))
        except concurrent.futures.TimeoutError as exc:
            future.cancel()
            raise TimeoutError(f"LLM 调用超过 timeout_s={timeout_s}") from exc
        finally:
            executor.shutdown(wait=False, cancel_futures=True)

    @classmethod
    def _repair_json_output(
        cls,
        request: LLMGatewayRequest,
        raw_text: str,
    ) -> tuple[str, str, str]:
        if not (request.json_output or request.schema_name):
            return raw_text, "not_requested", ""
        if not str(raw_text or "").strip():
            return "", "empty", "json_repair_empty_output"
        try:
            json.loads(raw_text)
            return raw_text, "valid_json", ""
        except Exception:
            pass

        repaired = cls._repair_json_text(raw_text)
        try:
            json.loads(repaired)
            return repaired, "repaired", "json_repair_applied"
        except Exception as exc:  # noqa: BLE001
            return repaired, "failed", f"json_repair_failed:{type(exc).__name__}: {exc}"

    @staticmethod
    def _repair_json_text(raw_text: str) -> str:
        text = str(raw_text or "")
        if "```" in text:
            inner = text.split("```", 1)[1]
            if inner.lstrip().startswith("json"):
                inner = inner.lstrip()[4:]
            text = inner.split("```", 1)[0]
        text = text.strip()
        text = re.sub(r",\s*([}\]])", r"\1", text)
        text = re.sub(r"'([^'\\]*(?:\\.[^'\\]*)*)'", r'"\1"', text)
        text = re.sub(r"[\x00-\x1f\x7f]", " ", text)
        return text.strip()

    def _with_observability_metadata(
        self,
        metadata: Dict[str, Any],
        request: LLMGatewayRequest,
        *,
        planned_call: Any,
        latency_s: float,
        json_repair_status: str,
        attempts_used: int = 0,
    ) -> Dict[str, Any]:
        model_id = self._resolve_model_id(request, planned_call)
        token_budget = self._resolve_token_budget(request, planned_call)
        gpu_params = self._resolve_gpu_params(request, planned_call)
        metadata.update(
            {
                "prompt_version": request.prompt_version,
                "model_id": model_id,
                "latency_s": round(float(latency_s or 0.0), 4),
                "token_budget": token_budget,
                "json_repair_status": json_repair_status,
                "retry_count": int(request.retry_count or 0),
                "attempts_used": int(attempts_used or 0),
                "timeout_s": request.timeout_s,
                "gpu_params": gpu_params,
            }
        )
        return metadata

    def _resolve_model_id(self, request: LLMGatewayRequest, planned_call: Any) -> str:
        if request.model_id:
            return request.model_id
        service = (
            getattr(planned_call, "llm_service", None)
            if planned_call is not None
            else None
        )
        if service is None:
            service = self._llm_service
        try:
            descriptor = describe_llm_engine(service)
        except Exception:  # noqa: BLE001
            descriptor = {}
        return str(descriptor.get("model") or "unknown")

    def _resolve_token_budget(
        self, request: LLMGatewayRequest, planned_call: Any
    ) -> int:
        for value in (request.token_budget, request.max_input_tokens):
            if value not in (None, ""):
                try:
                    return max(int(value), 0)
                except (TypeError, ValueError):
                    pass
        application = (
            getattr(planned_call, "prompt_application", {})
            if planned_call is not None
            else {}
        )
        if isinstance(application, Mapping):
            value = application.get("input_budget_tokens")
            if value not in (None, ""):
                try:
                    return max(int(value), 0)
                except (TypeError, ValueError):
                    pass
        service = (
            getattr(planned_call, "llm_service", None)
            if planned_call is not None
            else None
        )
        if service is None:
            service = self._llm_service
        for attr in ("n_ctx", "context_window", "context_window_tokens"):
            value = getattr(service, attr, None)
            if value not in (None, ""):
                try:
                    return max(int(value), 0)
                except (TypeError, ValueError):
                    continue
        return 0

    def _resolve_gpu_params(
        self, request: LLMGatewayRequest, planned_call: Any
    ) -> Dict[str, Any]:
        payload = dict(request.gpu_params or {})
        service = (
            getattr(planned_call, "llm_service", None)
            if planned_call is not None
            else None
        )
        if service is None:
            service = self._llm_service
        engine = getattr(service, "_engine", service)
        for key in ("n_gpu_layers", "n_ctx", "max_tokens", "temperature", "llm_mode"):
            value = getattr(engine, key, getattr(service, key, None))
            if value not in (None, ""):
                payload.setdefault(key, value)
        return payload

    @staticmethod
    def _elapsed(started_at: float) -> float:
        return round(max(time.perf_counter() - float(started_at), 0.0), 4)

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
