"""T4.4: 中医医学合规底线（Constitutional Guard）。

从 ``config/constitution.yml`` 加载规则，对 LLM 输出做 regex / require / llm_judge
检查；critical 违规由 :meth:`enforce` 抛 :class:`ConstitutionalViolation`。

接入点：:class:`SelfRefineRunner` 在 refine 阶段后强制调用 :meth:`check`，
critical 违规视为本轮 refine 失败。
"""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable, List, Mapping, Optional, Sequence, Union

logger = logging.getLogger(__name__)

_DEFAULT_CONSTITUTION_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "constitution.yml"
)

VALID_SEVERITIES = ("critical", "high", "medium", "low")
VALID_PATTERN_TYPES = ("regex", "require", "llm_judge")


@dataclass(frozen=True)
class ConstitutionalRule:
    """单条宪法规则。"""

    id: str
    severity: str
    pattern_type: str
    target: str
    body: str
    message: str = ""

    def __post_init__(self) -> None:  # pragma: no cover - dataclass guard
        if self.severity not in VALID_SEVERITIES:
            raise ValueError(
                f"rule {self.id}: invalid severity={self.severity}; "
                f"allowed={VALID_SEVERITIES}"
            )
        if self.pattern_type not in VALID_PATTERN_TYPES:
            raise ValueError(
                f"rule {self.id}: invalid pattern_type={self.pattern_type}; "
                f"allowed={VALID_PATTERN_TYPES}"
            )


@dataclass
class Violation:
    """一次违规记录。"""

    rule_id: str
    severity: str
    message: str
    target_path: str
    matched_text: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class ConstitutionalViolation(RuntimeError):
    """critical 级违规抛出的异常。"""

    def __init__(self, violations: Sequence[Violation]):
        self.violations: List[Violation] = list(violations)
        critical_ids = ", ".join(v.rule_id for v in self.violations)
        super().__init__(
            f"constitutional critical violations: {critical_ids or '(none)'}"
        )


# ---------------------------------------------------------------------------
# 加载
# ---------------------------------------------------------------------------

def _load_yaml(path: Path) -> dict:
    try:
        import yaml  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("ConstitutionalGuard requires PyYAML installed") from exc
    with path.open("r", encoding="utf-8") as fp:
        return yaml.safe_load(fp) or {}


def _build_rules(spec: Mapping[str, Any]) -> List[ConstitutionalRule]:
    rules: List[ConstitutionalRule] = []
    for raw in (spec.get("rules") or []):
        if not isinstance(raw, Mapping):
            continue
        rules.append(
            ConstitutionalRule(
                id=str(raw["id"]),
                severity=str(raw.get("severity") or "medium").lower(),
                pattern_type=str(raw.get("pattern_type") or "regex").lower(),
                target=str(raw.get("target") or "*"),
                body=str(raw.get("body") or ""),
                message=str(raw.get("message") or ""),
            )
        )
    return rules


# ---------------------------------------------------------------------------
# Path / 字段遍历
# ---------------------------------------------------------------------------

def _resolve_path(payload: Any, path: str) -> List[tuple[str, Any]]:
    """根据 dot path 取值。返回 (具体路径, 值) 列表（支持数组展开）。"""
    if path == "*":
        return list(_iter_string_leaves(payload, prefix=""))
    parts = path.split(".")
    nodes: List[tuple[str, Any]] = [("", payload)]
    for part in parts:
        next_nodes: List[tuple[str, Any]] = []
        for prefix, node in nodes:
            if isinstance(node, Mapping) and part in node:
                next_nodes.append(
                    (f"{prefix}.{part}" if prefix else part, node[part])
                )
            elif isinstance(node, list):
                # 中间允许直接对每个元素继续按 part 取
                for idx, item in enumerate(node):
                    if isinstance(item, Mapping) and part in item:
                        new_prefix = f"{prefix}[{idx}].{part}" if prefix else f"[{idx}].{part}"
                        next_nodes.append((new_prefix, item[part]))
        nodes = next_nodes
        if not nodes:
            return []
    return nodes


def _iter_string_leaves(value: Any, *, prefix: str) -> Iterable[tuple[str, str]]:
    if isinstance(value, str):
        if value:
            yield prefix or "$", value
    elif isinstance(value, Mapping):
        for k, v in value.items():
            sub = f"{prefix}.{k}" if prefix else str(k)
            yield from _iter_string_leaves(v, prefix=sub)
    elif isinstance(value, list):
        for idx, item in enumerate(value):
            sub = f"{prefix}[{idx}]" if prefix else f"[{idx}]"
            yield from _iter_string_leaves(item, prefix=sub)


def _stringify(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return str(value)


# ---------------------------------------------------------------------------
# Guard 主体
# ---------------------------------------------------------------------------


class ConstitutionalGuard:
    """从 yaml 加载规则的合规检查器。"""

    def __init__(
        self,
        rules: Optional[Sequence[ConstitutionalRule]] = None,
        *,
        config_path: Optional[Union[str, Path]] = None,
        llm_judge: Optional[Any] = None,
    ) -> None:
        if rules is not None:
            self._rules = list(rules)
        else:
            path = Path(config_path) if config_path else _DEFAULT_CONSTITUTION_PATH
            spec = _load_yaml(path)
            self._rules = _build_rules(spec)
        self._llm_judge = llm_judge
        # 预编译 regex
        self._compiled: dict[str, re.Pattern[str]] = {}
        for rule in self._rules:
            if rule.pattern_type in ("regex", "require"):
                try:
                    self._compiled[rule.id] = re.compile(rule.body, re.IGNORECASE)
                except re.error as exc:
                    raise ValueError(
                        f"rule {rule.id}: invalid regex {rule.body!r}: {exc}"
                    ) from exc

    @property
    def rules(self) -> List[ConstitutionalRule]:
        return list(self._rules)

    # ------------------------------------------------------------------ #
    # 检查
    # ------------------------------------------------------------------ #

    def check(self, output: Any) -> List[Violation]:
        """对 output 执行所有规则；返回违规列表（不抛异常）。"""
        violations: List[Violation] = []
        for rule in self._rules:
            try:
                violations.extend(self._check_rule(rule, output))
            except Exception:  # noqa: BLE001
                logger.warning(
                    "constitutional rule %s failed (skipped)", rule.id, exc_info=True
                )
        return violations

    def enforce(self, output: Any) -> List[Violation]:
        """检查并在 critical 违规时抛 :class:`ConstitutionalViolation`。

        非 critical 违规仅返回。
        """
        violations = self.check(output)
        critical = [v for v in violations if v.severity == "critical"]
        if critical:
            raise ConstitutionalViolation(critical)
        return violations

    # ------------------------------------------------------------------ #
    # 单规则
    # ------------------------------------------------------------------ #

    def _check_rule(self, rule: ConstitutionalRule, output: Any) -> List[Violation]:
        if rule.pattern_type == "regex":
            return self._check_regex(rule, output)
        if rule.pattern_type == "require":
            return self._check_require(rule, output)
        if rule.pattern_type == "llm_judge":
            return self._check_llm(rule, output)
        return []

    def _check_regex(self, rule: ConstitutionalRule, output: Any) -> List[Violation]:
        pattern = self._compiled[rule.id]
        results: List[Violation] = []
        for path, value in _resolve_path(output, rule.target):
            text = _stringify(value)
            if not text:
                continue
            match = pattern.search(text)
            if match:
                results.append(
                    Violation(
                        rule_id=rule.id,
                        severity=rule.severity,
                        message=rule.message,
                        target_path=path,
                        matched_text=match.group(0)[:200],
                    )
                )
        return results

    def _check_require(self, rule: ConstitutionalRule, output: Any) -> List[Violation]:
        """require：target 字段存在但未匹配 body 时违规。

        - 数组 target：每个元素必须各自匹配 body
        - dict / scalar：整体序列化后匹配
        """
        pattern = self._compiled[rule.id]
        results: List[Violation] = []
        nodes = _resolve_path(output, rule.target)
        if not nodes:
            # require 字段缺失同样视为违规
            results.append(
                Violation(
                    rule_id=rule.id,
                    severity=rule.severity,
                    message=rule.message or f"missing required field: {rule.target}",
                    target_path=rule.target,
                    matched_text="",
                )
            )
            return results
        for path, value in nodes:
            if isinstance(value, list):
                for idx, item in enumerate(value):
                    text = _stringify(item) if not isinstance(item, Mapping) else _serialize_mapping(item)
                    if not pattern.search(text):
                        results.append(
                            Violation(
                                rule_id=rule.id,
                                severity=rule.severity,
                                message=rule.message,
                                target_path=f"{path}[{idx}]",
                                matched_text=text[:200],
                            )
                        )
            else:
                text = _stringify(value) if not isinstance(value, Mapping) else _serialize_mapping(value)
                if not text or not pattern.search(text):
                    results.append(
                        Violation(
                            rule_id=rule.id,
                            severity=rule.severity,
                            message=rule.message,
                            target_path=path,
                            matched_text=text[:200],
                        )
                    )
        return results

    def _check_llm(self, rule: ConstitutionalRule, output: Any) -> List[Violation]:
        if self._llm_judge is None:
            logger.debug("rule %s skipped (no llm_judge)", rule.id)
            return []
        try:
            verdict = self._llm_judge.judge(rule=rule, output=output)
        except Exception:  # noqa: BLE001
            logger.warning("llm_judge failed for rule %s", rule.id, exc_info=True)
            return []
        if verdict and verdict.get("violated"):
            return [
                Violation(
                    rule_id=rule.id,
                    severity=rule.severity,
                    message=rule.message or str(verdict.get("reason") or ""),
                    target_path=rule.target,
                    matched_text=str(verdict.get("evidence") or "")[:200],
                )
            ]
        return []


def _serialize_mapping(value: Mapping[str, Any]) -> str:
    parts: List[str] = []
    for k, v in value.items():
        if isinstance(v, (str, int, float, bool)):
            parts.append(f"{k}={v}")
        else:
            parts.append(f"{k}={type(v).__name__}")
    return " ".join(parts)


def load_default_guard(
    config_path: Optional[Union[str, Path]] = None,
    *,
    llm_judge: Optional[Any] = None,
) -> ConstitutionalGuard:
    """从默认 ``config/constitution.yml`` 构造 guard。"""
    return ConstitutionalGuard(config_path=config_path, llm_judge=llm_judge)


__all__ = [
    "ConstitutionalGuard",
    "ConstitutionalRule",
    "ConstitutionalViolation",
    "Violation",
    "load_default_guard",
]
