"""Canonical production LLM gateway.

This module is the stable import path for production LLM calls.  The concrete
implementation lives in the llm_reasoning bounded context, while this facade keeps
call sites under ``src.llm`` and exposes the audited request/result contracts.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

from src.contexts.llm_reasoning.contracts import (
    LLMGatewayRequest,
    LLMGatewayResult,
    LLMReasoningMode,
    LLMRetrievalPolicy,
)
from src.contexts.llm_reasoning.service import LLMGateway

LLM_GATEWAY_CONTRACT_VERSION = "llm-gateway-production-v1"


def generate_with_gateway(
    llm_service: Any,
    prompt: str,
    system_prompt: str = "",
    *,
    prompt_version: str = "unknown",
    model_id: str = "",
    phase: str = "unknown",
    purpose: str = "default",
    task_type: str = "general",
    schema_name: str = "",
    token_budget: Optional[int] = None,
    max_input_tokens: Optional[int] = None,
    timeout_s: Optional[float] = None,
    retry_count: int = 1,
    json_output: bool = False,
    context: Optional[Mapping[str, Any]] = None,
    metadata: Optional[Mapping[str, Any]] = None,
    gpu_params: Optional[Mapping[str, Any]] = None,
) -> LLMGatewayResult:
    """Run a generation request through the canonical audited gateway."""

    gateway = (
        llm_service if isinstance(llm_service, LLMGateway) else LLMGateway(llm_service)
    )
    return gateway.generate(
        LLMGatewayRequest(
            prompt=prompt,
            system_prompt=system_prompt,
            prompt_version=prompt_version,
            model_id=model_id,
            phase=phase,
            purpose=purpose,
            task_type=task_type,
            schema_name=schema_name,
            max_input_tokens=max_input_tokens,
            token_budget=token_budget,
            timeout_s=timeout_s,
            retry_count=retry_count,
            json_output=json_output,
            context=dict(context or {}),
            metadata=dict(metadata or {}),
            gpu_params=dict(gpu_params or {}),
        )
    )


__all__ = [
    "LLM_GATEWAY_CONTRACT_VERSION",
    "LLMGateway",
    "LLMGatewayRequest",
    "LLMGatewayResult",
    "LLMReasoningMode",
    "LLMRetrievalPolicy",
    "generate_with_gateway",
]
