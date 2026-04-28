"""T4.3: 通用 Self-Refine 执行器（draft → critique → refine）。

使用方式::

    runner = SelfRefineRunner(llm, prompt_registry_module, guard=guard)
    result = runner.run(
        purpose="hypothesis",
        inputs={"task_description": "...", "input_payload": "..."},
        max_refine_rounds=2,
    )

每轮调用都会构造一条 ``learning_feedback_library`` 风格的 feedback record
（``source_phase=<purpose>``），便于 reflect 阶段聚合分析。可通过
``feedback_sink`` 回调实时把 record 写出。
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

from src.llm.constitutional_guard import (
    ConstitutionalGuard,
    ConstitutionalViolation,
    Violation,
)

logger = logging.getLogger(__name__)


@dataclass
class RefineRound:
    """单轮 refine 的执行轨迹。"""

    round_index: int
    draft: str
    critique_raw: str
    issues: List[Dict[str, Any]] = field(default_factory=list)
    refined: str = ""
    violations: List[Dict[str, Any]] = field(default_factory=list)
    prompt_versions: Dict[str, str] = field(default_factory=dict)
    schema_versions: Dict[str, str] = field(default_factory=dict)


@dataclass
class RefineResult:
    """Self-Refine 执行结果。"""

    purpose: str
    final_output: str
    rounds: List[RefineRound] = field(default_factory=list)
    feedback_records: List[Dict[str, Any]] = field(default_factory=list)
    succeeded: bool = True
    last_violations: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "purpose": self.purpose,
            "final_output": self.final_output,
            "rounds": [asdict(r) for r in self.rounds],
            "feedback_records": list(self.feedback_records),
            "succeeded": self.succeeded,
            "last_violations": list(self.last_violations),
        }


FeedbackSink = Callable[[Dict[str, Any]], None]


class SelfRefineRunner:
    """draft → critique → refine 通用三步执行器。

    ``prompt_registry`` 期望提供以下接口（即 ``src.infra.prompt_registry`` 模块本身）：

      - ``get_prompt_template(name)`` → ``PromptTemplate``（用于读取 version / schema_version）
      - ``call_registered_prompt(llm, name, **vars)`` → ``str``
    """

    def __init__(
        self,
        llm_service: Any,
        prompt_registry: Any,
        guard: Optional[ConstitutionalGuard] = None,
        *,
        feedback_sink: Optional[FeedbackSink] = None,
    ) -> None:
        if llm_service is None or not hasattr(llm_service, "generate"):
            raise ValueError("SelfRefineRunner requires an LLMService with generate()")
        if prompt_registry is None or not hasattr(prompt_registry, "call_registered_prompt"):
            raise ValueError(
                "SelfRefineRunner requires the prompt_registry module "
                "(must expose call_registered_prompt + get_prompt_template)"
            )
        self.llm = llm_service
        self.registry = prompt_registry
        self.guard = guard
        self.feedback_sink = feedback_sink

    # ------------------------------------------------------------------ #
    # 主入口
    # ------------------------------------------------------------------ #

    def run(
        self,
        purpose: str,
        inputs: Dict[str, Any],
        max_refine_rounds: int = 1,
    ) -> RefineResult:
        if not purpose or not isinstance(purpose, str):
            raise ValueError("purpose must be a non-empty string")
        if max_refine_rounds < 0:
            raise ValueError("max_refine_rounds must be >= 0")
        inputs = dict(inputs or {})
        inputs.setdefault("task_description", purpose)
        inputs.setdefault("input_payload", "")

        result = RefineResult(purpose=purpose, final_output="")

        # 1) draft（仅一次）
        draft_name = self._resolve_prompt(purpose, "draft")
        draft_text, draft_versions = self._call(draft_name, inputs)
        current_output = draft_text

        # 2) critique → refine 循环
        for idx in range(max_refine_rounds):
            critique_name = self._resolve_prompt(purpose, "critique")
            critique_raw, critique_versions = self._call(
                critique_name,
                {**inputs, "draft": current_output},
            )
            issues = self._parse_issues(critique_raw)

            refine_name = self._resolve_prompt(purpose, "refine")
            issues_text = json.dumps(issues, ensure_ascii=False, indent=2) if issues else "[]"
            refined_text, refine_versions = self._call(
                refine_name,
                {**inputs, "draft": current_output, "issues": issues_text},
            )

            # 3) Constitutional check（refine 阶段后强制）
            violations: List[Violation] = []
            try:
                if self.guard is not None:
                    violations = self.guard.enforce(_as_payload(refined_text))
            except ConstitutionalViolation as exc:
                violations = exc.violations
                # critical 违规：保留 refined 但标记失败
                result.succeeded = False
                logger.warning(
                    "self_refine round=%d hit critical constitutional violations: %s",
                    idx,
                    [v.rule_id for v in violations],
                )

            round_record = RefineRound(
                round_index=idx,
                draft=current_output,
                critique_raw=critique_raw,
                issues=issues,
                refined=refined_text,
                violations=[v.to_dict() for v in violations],
                prompt_versions={
                    "draft": draft_versions["prompt_version"] if idx == 0 else "",
                    "critique": critique_versions["prompt_version"],
                    "refine": refine_versions["prompt_version"],
                },
                schema_versions={
                    "draft": draft_versions["schema_version"] if idx == 0 else "",
                    "critique": critique_versions["schema_version"],
                    "refine": refine_versions["schema_version"],
                },
            )
            result.rounds.append(round_record)

            # learning_feedback_library 风格条目（每轮 1 条）
            feedback_record = self._build_feedback_record(
                purpose=purpose,
                round_idx=idx,
                issues=issues,
                violations=round_record.violations,
                prompt_versions={
                    draft_name: draft_versions if idx == 0 else None,
                    critique_name: critique_versions,
                    refine_name: refine_versions,
                },
            )
            result.feedback_records.append(feedback_record)
            if self.feedback_sink is not None:
                try:
                    self.feedback_sink(feedback_record)
                except Exception:  # noqa: BLE001
                    logger.warning("feedback_sink failed (non-fatal)", exc_info=True)

            current_output = refined_text
            result.last_violations = round_record.violations
            if not result.succeeded:
                # critical 违规：终止后续轮，避免反复触发
                break

        result.final_output = current_output
        return result

    # ------------------------------------------------------------------ #
    # 内部
    # ------------------------------------------------------------------ #

    def _resolve_prompt(self, purpose: str, stage: str) -> str:
        """优先 ``<purpose>.<stage>``，否则回退到 ``self_refine.<stage>``。"""
        candidate = f"{purpose}.{stage}"
        try:
            self.registry.get_prompt_template(candidate)
            return candidate
        except KeyError:
            return f"self_refine.{stage}"

    def _call(self, prompt_name: str, variables: Dict[str, Any]) -> tuple[str, Dict[str, str]]:
        template = self.registry.get_prompt_template(prompt_name)
        text = self.registry.call_registered_prompt(self.llm, prompt_name, **variables)
        return str(text or ""), {
            "prompt_name": prompt_name,
            "prompt_version": getattr(template, "version", "v1"),
            "schema_version": getattr(template, "schema_version", "v1"),
        }

    @staticmethod
    def _parse_issues(critique_raw: str) -> List[Dict[str, Any]]:
        text = (critique_raw or "").strip()
        if not text:
            return []
        # 尝试直接 JSON 解析
        try:
            payload = json.loads(text)
        except Exception:
            # 尝试抓第一个 JSON 数组
            start = text.find("[")
            end = text.rfind("]")
            if start >= 0 and end > start:
                try:
                    payload = json.loads(text[start : end + 1])
                except Exception:
                    return []
            else:
                return []
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if isinstance(payload, dict) and isinstance(payload.get("issues"), list):
            return [item for item in payload["issues"] if isinstance(item, dict)]
        return []

    @staticmethod
    def _build_feedback_record(
        *,
        purpose: str,
        round_idx: int,
        issues: List[Dict[str, Any]],
        violations: List[Dict[str, Any]],
        prompt_versions: Dict[str, Optional[Dict[str, str]]],
    ) -> Dict[str, Any]:
        clean_versions = {
            k: v for k, v in prompt_versions.items() if v is not None
        }
        return {
            "source_phase": purpose,
            "feedback_scope": "self_refine",
            "round_index": round_idx,
            "issues_count": len(issues),
            "issue_fields": sorted({str(it.get("field") or "") for it in issues if it.get("field")}),
            "violations": violations,
            "prompt_versions": {
                name: {
                    "prompt_version": v["prompt_version"],
                    "schema_version": v["schema_version"],
                }
                for name, v in clean_versions.items()
            },
            "ts": time.time(),
        }


def _as_payload(text: str) -> Dict[str, Any]:
    """把 refine 输出尝试解析成 dict；失败时回退为 ``{"answer": text}`` 供 guard 检查。"""
    raw = (text or "").strip()
    if not raw:
        return {"answer": ""}
    try:
        loaded = json.loads(raw)
    except Exception:
        return {"answer": raw}
    if isinstance(loaded, dict):
        return loaded
    return {"answer": raw}


__all__ = [
    "SelfRefineRunner",
    "RefineRound",
    "RefineResult",
]
