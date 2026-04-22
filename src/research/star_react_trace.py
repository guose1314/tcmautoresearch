"""STaR / ReAct 风格推理 trace 契约（Phase M-1）。

把 hypothesis 等阶段的"推理过程"显式记录为 thought/action/observation 步骤，
便于离线评测、Self-Refine 训练数据导出与可解释性分析。

公开 API：
  - STAR_REACT_TRACE_CONTRACT_VERSION
  - StepKind / TraceStep / ReasoningTrace
  - build_reasoning_trace(...)
  - export_traces_for_offline_eval(traces)

设计原则（和 Phase J/K/L 一致）：
  - 纯数据契约 + 工厂函数，零 IO，零外部依赖
  - dataclass 默认 frozen=False 以便 step 追加，但 to_dict/from_dict 完整往返
  - 不强制接入既有 phase（先沉淀契约，后续卡片再 wire）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence

STAR_REACT_TRACE_CONTRACT_VERSION = "star-react-trace-v1"

VALID_STEP_KINDS = frozenset({"thought", "action", "observation", "answer"})


@dataclass
class TraceStep:
    """单步推理记录。

    - kind: thought / action / observation / answer（ReAct 风格）
    - content: 文本内容（thought 文本、action 描述或 answer 文本）
    - tool_name / tool_args / tool_result: 仅当 kind='action' 时有意义
    - score: 可选打分，用于 STaR rationale 质量过滤
    """

    kind: str
    content: str
    tool_name: Optional[str] = None
    tool_args: Optional[Dict[str, Any]] = None
    tool_result: Any = None
    score: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.kind not in VALID_STEP_KINDS:
            raise ValueError(
                f"TraceStep.kind 必须为 {sorted(VALID_STEP_KINDS)}，收到 {self.kind!r}"
            )
        if not isinstance(self.content, str):
            raise TypeError("TraceStep.content 必须为 str")
        if self.kind == "action" and not self.tool_name:
            raise ValueError("kind='action' 时必须提供 tool_name")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "content": self.content,
            "tool_name": self.tool_name,
            "tool_args": dict(self.tool_args) if self.tool_args else None,
            "tool_result": self.tool_result,
            "score": self.score,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "TraceStep":
        return cls(
            kind=str(payload["kind"]),
            content=str(payload.get("content", "")),
            tool_name=payload.get("tool_name"),
            tool_args=dict(payload["tool_args"]) if payload.get("tool_args") else None,
            tool_result=payload.get("tool_result"),
            score=payload.get("score"),
            metadata=dict(payload.get("metadata") or {}),
        )


@dataclass
class ReasoningTrace:
    """单条完整推理轨迹。"""

    trace_id: str
    phase: str
    question: str
    steps: List[TraceStep] = field(default_factory=list)
    final_answer: Optional[str] = None
    overall_score: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    contract_version: str = STAR_REACT_TRACE_CONTRACT_VERSION

    def add_step(self, step: TraceStep) -> None:
        self.steps.append(step)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "contract_version": self.contract_version,
            "trace_id": self.trace_id,
            "phase": self.phase,
            "question": self.question,
            "steps": [s.to_dict() for s in self.steps],
            "final_answer": self.final_answer,
            "overall_score": self.overall_score,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "ReasoningTrace":
        return cls(
            trace_id=str(payload["trace_id"]),
            phase=str(payload["phase"]),
            question=str(payload.get("question", "")),
            steps=[TraceStep.from_dict(s) for s in payload.get("steps") or []],
            final_answer=payload.get("final_answer"),
            overall_score=payload.get("overall_score"),
            metadata=dict(payload.get("metadata") or {}),
            contract_version=str(
                payload.get("contract_version") or STAR_REACT_TRACE_CONTRACT_VERSION
            ),
        )


def build_reasoning_trace(
    *,
    trace_id: str,
    phase: str,
    question: str,
    steps: Iterable[TraceStep] | None = None,
    final_answer: Optional[str] = None,
    overall_score: Optional[float] = None,
    metadata: Optional[Mapping[str, Any]] = None,
) -> ReasoningTrace:
    """工厂方法，做轻量校验。"""
    if not trace_id:
        raise ValueError("trace_id 不能为空")
    if not phase:
        raise ValueError("phase 不能为空")
    return ReasoningTrace(
        trace_id=str(trace_id),
        phase=str(phase),
        question=str(question or ""),
        steps=list(steps or []),
        final_answer=final_answer,
        overall_score=overall_score,
        metadata=dict(metadata or {}),
    )


def export_traces_for_offline_eval(traces: Sequence[ReasoningTrace]) -> Dict[str, Any]:
    """把多条 trace 打包成离线评测用 payload。"""
    return {
        "contract_version": STAR_REACT_TRACE_CONTRACT_VERSION,
        "trace_count": len(traces),
        "traces": [t.to_dict() for t in traces],
    }
