"""Contracts for the LLM reasoning bounded context."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
from enum import Enum
from typing import Any, Dict, List, Mapping, Optional


class LLMReasoningMode(str, Enum):
    """High-level reasoning path requested from the gateway."""

    AUTO = "auto"
    DIRECT = "direct"
    GRAPH_RAG = "graph_rag"
    SELF_DISCOVER = "self_discover"
    SELF_REFINE = "self_refine"
    SCHEMA_VALIDATED = "schema_validated"

    @classmethod
    def coerce(cls, value: Any) -> "LLMReasoningMode":
        if isinstance(value, cls):
            return value
        text = str(value or "").strip().lower()
        if not text:
            return cls.DIRECT
        for member in cls:
            if member.value == text:
                return member
        allowed = ", ".join(member.value for member in cls)
        raise ValueError(
            f"unsupported LLMReasoningMode={value!r}; expected one of {allowed}"
        )


@dataclass
class LLMRetrievalPolicy:
    """GraphRAG retrieval options carried by an LLM gateway request."""

    enabled: bool = False
    question_type: str = ""
    query: str = ""
    topic_keys: List[str] = field(default_factory=list)
    entity_ids: List[str] = field(default_factory=list)
    asset_type: str = ""
    cycle_id: str = ""
    max_results: int = 20
    include_traceability: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.enabled = bool(self.enabled)
        self.question_type = str(self.question_type or "").strip().lower()
        self.query = str(self.query or "").strip()
        self.topic_keys = _normalize_string_list(self.topic_keys)
        self.entity_ids = _normalize_string_list(self.entity_ids)
        self.asset_type = str(self.asset_type or "").strip().lower()
        self.cycle_id = str(self.cycle_id or "").strip()
        try:
            self.max_results = max(int(self.max_results), 0)
        except (TypeError, ValueError):
            self.max_results = 20
        self.include_traceability = bool(self.include_traceability)
        self.metadata = dict(self.metadata or {})

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "LLMRetrievalPolicy":
        metadata = (
            payload.get("metadata")
            if isinstance(payload.get("metadata"), Mapping)
            else {}
        )
        return cls(
            enabled=bool(payload.get("enabled", False)),
            question_type=str(payload.get("question_type") or ""),
            query=str(payload.get("query") or ""),
            topic_keys=list(payload.get("topic_keys") or []),
            entity_ids=list(payload.get("entity_ids") or []),
            asset_type=str(payload.get("asset_type") or ""),
            cycle_id=str(payload.get("cycle_id") or ""),
            max_results=payload.get("max_results") or 20,
            include_traceability=bool(payload.get("include_traceability", True)),
            metadata=dict(metadata),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "enabled": self.enabled,
            "question_type": self.question_type,
            "query": self.query,
            "topic_keys": list(self.topic_keys),
            "entity_ids": list(self.entity_ids),
            "asset_type": self.asset_type,
            "cycle_id": self.cycle_id,
            "max_results": self.max_results,
            "include_traceability": self.include_traceability,
            "metadata": _json_ready(self.metadata),
        }


@dataclass
class LLMGatewayRequest:
    """Request contract for a single gateway generation call."""

    prompt: str = ""
    system_prompt: str = ""
    prompt_version: str = "unknown"
    model_id: str = ""
    phase: str = "unknown"
    purpose: str = "default"
    task_type: str = "general"
    schema_name: str = ""
    graph_rag: LLMRetrievalPolicy | Mapping[str, Any] | bool = field(
        default_factory=LLMRetrievalPolicy
    )
    reasoning_mode: LLMReasoningMode | str = LLMReasoningMode.DIRECT
    max_input_tokens: Optional[int] = None
    token_budget: Optional[int] = None
    timeout_s: Optional[float] = None
    retry_count: int = 0
    json_output: bool = False
    gpu_params: Dict[str, Any] = field(default_factory=dict)
    context: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.prompt = str(self.prompt or "")
        self.system_prompt = str(self.system_prompt or "")
        self.prompt_version = str(self.prompt_version or "unknown").strip() or "unknown"
        self.model_id = str(self.model_id or "").strip()
        self.phase = str(self.phase or "unknown").strip().lower() or "unknown"
        self.purpose = str(self.purpose or "default").strip() or "default"
        self.task_type = str(self.task_type or "general").strip() or "general"
        self.schema_name = str(self.schema_name or "").strip()
        self.graph_rag = _coerce_retrieval_policy(self.graph_rag)
        self.reasoning_mode = LLMReasoningMode.coerce(self.reasoning_mode)
        self.max_input_tokens = _normalize_optional_positive_int(self.max_input_tokens)
        self.token_budget = _normalize_optional_positive_int(
            self.token_budget or self.max_input_tokens
        )
        if self.max_input_tokens is None and self.token_budget is not None:
            self.max_input_tokens = self.token_budget
        self.timeout_s = _normalize_optional_positive_float(self.timeout_s)
        try:
            self.retry_count = max(int(self.retry_count or 0), 0)
        except (TypeError, ValueError):
            self.retry_count = 0
        self.json_output = bool(self.json_output)
        self.gpu_params = dict(self.gpu_params or {})
        self.context = dict(self.context or {})
        self.metadata = dict(self.metadata or {})
        if self.prompt_version == "unknown":
            for source in (self.metadata, self.context):
                candidate = str(source.get("prompt_version") or "").strip()
                if candidate:
                    self.prompt_version = candidate
                    break
        if not self.model_id:
            for source in (self.metadata, self.context):
                candidate = str(source.get("model_id") or "").strip()
                if candidate:
                    self.model_id = candidate
                    break
        if self.token_budget is None:
            for source in (self.metadata, self.context):
                candidate = _normalize_optional_positive_int(source.get("token_budget"))
                if candidate is not None:
                    self.token_budget = candidate
                    self.max_input_tokens = self.max_input_tokens or candidate
                    break
        if self.timeout_s is None:
            for source in (self.metadata, self.context):
                candidate = _normalize_optional_positive_float(
                    source.get("timeout_s") or source.get("timeout_seconds")
                )
                if candidate is not None:
                    self.timeout_s = candidate
                    break
        if self.retry_count == 0:
            for source in (self.metadata, self.context):
                try:
                    candidate = int(source.get("retry_count") or 0)
                except (TypeError, ValueError):
                    candidate = 0
                if candidate > 0:
                    self.retry_count = candidate
                    break
        if not self.json_output:
            for source in (self.metadata, self.context):
                if source.get("json_output") is True:
                    self.json_output = True
                    break
                if str(source.get("response_format") or "").strip().lower() in {
                    "json",
                    "json_object",
                    "json_array",
                }:
                    self.json_output = True
                    break
        if not self.gpu_params:
            for source in (self.metadata, self.context):
                gpu_params = source.get("gpu_params")
                if isinstance(gpu_params, Mapping):
                    self.gpu_params = dict(gpu_params)
                    break

    def to_dict(self) -> Dict[str, Any]:
        return {
            "prompt": self.prompt,
            "system_prompt": self.system_prompt,
            "prompt_version": self.prompt_version,
            "model_id": self.model_id,
            "phase": self.phase,
            "purpose": self.purpose,
            "task_type": self.task_type,
            "schema_name": self.schema_name,
            "graph_rag": self.graph_rag.to_dict(),
            "reasoning_mode": self.reasoning_mode.value,
            "max_input_tokens": self.max_input_tokens,
            "token_budget": self.token_budget,
            "timeout_s": self.timeout_s,
            "retry_count": self.retry_count,
            "json_output": self.json_output,
            "gpu_params": _json_ready(self.gpu_params),
            "context": _json_ready(self.context),
            "metadata": _json_ready(self.metadata),
        }


@dataclass
class LLMGatewayResult:
    """Result contract returned by the LLM gateway."""

    text: str = ""
    structured: Any = field(default_factory=dict)
    citations: List[Dict[str, Any]] = field(default_factory=list)
    retrieval_trace: Dict[str, Any] = field(default_factory=dict)
    llm_cost_report: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    reasoning_mode: LLMReasoningMode | str = LLMReasoningMode.DIRECT
    schema_name: str = ""
    prompt_version: str = "unknown"
    model_id: str = "unknown"
    latency_s: float = 0.0
    token_budget: int = 0
    json_repair_status: str = "not_requested"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.text = str(self.text or "")
        self.citations = [
            dict(item) for item in self.citations if isinstance(item, Mapping)
        ]
        self.retrieval_trace = dict(self.retrieval_trace or {})
        self.llm_cost_report = dict(self.llm_cost_report or {})
        self.warnings = [str(item) for item in self.warnings if str(item).strip()]
        self.reasoning_mode = LLMReasoningMode.coerce(self.reasoning_mode)
        self.schema_name = str(self.schema_name or "").strip()
        self.prompt_version = str(self.prompt_version or "unknown").strip() or "unknown"
        self.model_id = str(self.model_id or "unknown").strip() or "unknown"
        try:
            self.latency_s = max(float(self.latency_s or 0.0), 0.0)
        except (TypeError, ValueError):
            self.latency_s = 0.0
        try:
            self.token_budget = max(int(self.token_budget or 0), 0)
        except (TypeError, ValueError):
            self.token_budget = 0
        self.json_repair_status = (
            str(self.json_repair_status or "not_requested").strip() or "not_requested"
        )
        self.metadata = dict(self.metadata or {})
        self.metadata.setdefault("prompt_version", self.prompt_version)
        self.metadata.setdefault("model_id", self.model_id)
        self.metadata.setdefault("latency_s", self.latency_s)
        self.metadata.setdefault("token_budget", self.token_budget)
        self.metadata.setdefault("json_repair_status", self.json_repair_status)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "text": self.text,
            "structured": _json_ready(self.structured),
            "citations": _json_ready(self.citations),
            "retrieval_trace": _json_ready(self.retrieval_trace),
            "llm_cost_report": _json_ready(self.llm_cost_report),
            "warnings": list(self.warnings),
            "reasoning_mode": self.reasoning_mode.value,
            "schema_name": self.schema_name,
            "prompt_version": self.prompt_version,
            "model_id": self.model_id,
            "latency_s": self.latency_s,
            "token_budget": self.token_budget,
            "json_repair_status": self.json_repair_status,
            "metadata": _json_ready(self.metadata),
        }


def _coerce_retrieval_policy(value: Any) -> LLMRetrievalPolicy:
    if isinstance(value, LLMRetrievalPolicy):
        return value
    if isinstance(value, Mapping):
        return LLMRetrievalPolicy.from_dict(value)
    if isinstance(value, bool):
        return LLMRetrievalPolicy(enabled=value)
    if value is None:
        return LLMRetrievalPolicy()
    raise TypeError(
        f"graph_rag must be LLMRetrievalPolicy, mapping or bool; got {type(value)!r}"
    )


def _normalize_string_list(values: Any) -> List[str]:
    if values in (None, ""):
        return []
    if isinstance(values, str):
        values = [values]
    return [str(item).strip() for item in values if str(item).strip()]


def _normalize_optional_positive_int(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return None
    return normalized if normalized > 0 else None


def _normalize_optional_positive_float(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        normalized = float(value)
    except (TypeError, ValueError):
        return None
    return normalized if normalized > 0 else None


def _json_ready(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return _json_ready(asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_ready(item) for item in value]
    return str(value)


__all__ = [
    "LLMGatewayRequest",
    "LLMGatewayResult",
    "LLMReasoningMode",
    "LLMRetrievalPolicy",
]
