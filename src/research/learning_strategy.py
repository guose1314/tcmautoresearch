from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Mapping, Optional

# ---------------------------------------------------------------------------
# Strategy snapshot & fingerprint
# ---------------------------------------------------------------------------

def build_strategy_snapshot(
    context: Mapping[str, Any] | None,
    pipeline_config: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """Freeze the current learning strategy into an immutable snapshot with fingerprint.

    The fingerprint is a stable hash of sorted strategy + tuned_parameters,
    so two phases can cheaply verify they consumed the same strategy version.
    """
    strategy = resolve_learning_strategy(context, pipeline_config)
    tuned = resolve_tuned_parameters(context, pipeline_config)
    payload = {"strategy": strategy, "tuned_parameters": tuned}
    raw = json.dumps(payload, sort_keys=True, default=str)
    fingerprint = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return {
        "strategy": dict(strategy),
        "tuned_parameters": dict(tuned),
        "fingerprint": fingerprint,
    }


# ---------------------------------------------------------------------------
# StrategyApplicationTracker — records per-phase decisions
# ---------------------------------------------------------------------------

class StrategyApplicationTracker:
    """Accumulates learning-strategy decision records for a single phase.

    Each ``record()`` call logs one decision point (e.g. "sample_size adjusted
    from 100 to 110 because quality_threshold >= 0.82").  At the end of the
    phase, ``to_metadata()`` produces a dict suitable for inclusion in
    PhaseResult.metadata under the ``"learning"`` key.
    """

    def __init__(
        self,
        phase: str,
        context: Mapping[str, Any] | None,
        pipeline_config: Mapping[str, Any] | None = None,
    ) -> None:
        self.phase = phase
        self._applied = has_learning_strategy(context, pipeline_config)
        self._snapshot: Dict[str, Any] = (
            build_strategy_snapshot(context, pipeline_config) if self._applied else {}
        )
        self._decisions: List[Dict[str, Any]] = []

    @property
    def applied(self) -> bool:
        return self._applied

    @property
    def fingerprint(self) -> Optional[str]:
        return self._snapshot.get("fingerprint")

    def record(
        self,
        name: str,
        baseline: Any,
        adjusted: Any,
        reason: str,
        *,
        parameter: str | None = None,
        parameter_value: float | None = None,
    ) -> None:
        """Record a single strategy decision."""
        entry: Dict[str, Any] = {
            "name": name,
            "baseline": baseline,
            "adjusted": adjusted,
            "reason": reason,
        }
        if parameter is not None:
            entry["parameter"] = parameter
        if parameter_value is not None:
            entry["parameter_value"] = parameter_value
        self._decisions.append(entry)

    def to_metadata(self) -> Dict[str, Any]:
        """Return learning metadata block for PhaseResult."""
        meta: Dict[str, Any] = {"applied": self._applied}
        if not self._applied:
            return meta
        meta["strategy_fingerprint"] = self._snapshot.get("fingerprint")
        meta["strategy_version"] = self._snapshot.get("strategy", {}).get(
            "strategy_version", "unknown"
        )
        meta["decision_count"] = len(self._decisions)
        if self._decisions:
            meta["decisions"] = list(self._decisions)
        return meta


# ---------------------------------------------------------------------------
# Strategy diff — compare before/after reflect
# ---------------------------------------------------------------------------

def build_strategy_diff(
    before: Dict[str, Any],
    after: Dict[str, Any],
) -> Dict[str, Any]:
    """Compare two strategy snapshots and return a diff summary.

    *before* and *after* are dicts returned by ``build_strategy_snapshot()``.
    """
    changes: List[Dict[str, Any]] = []
    before_tuned = before.get("tuned_parameters") or {}
    after_tuned = after.get("tuned_parameters") or {}
    before_strategy = before.get("strategy") or {}
    after_strategy = after.get("strategy") or {}

    all_keys = sorted(set(before_tuned) | set(after_tuned))
    for key in all_keys:
        bv = before_tuned.get(key)
        av = after_tuned.get(key)
        if bv != av:
            changes.append({"parameter": key, "before": bv, "after": av, "scope": "tuned_parameters"})

    for key in sorted(set(before_strategy) | set(after_strategy)):
        if key == "tuned_parameters":
            continue
        bv = before_strategy.get(key)
        av = after_strategy.get(key)
        if bv != av:
            changes.append({"parameter": key, "before": bv, "after": av, "scope": "strategy"})

    return {
        "before_fingerprint": before.get("fingerprint"),
        "after_fingerprint": after.get("fingerprint"),
        "changed": before.get("fingerprint") != after.get("fingerprint"),
        "change_count": len(changes),
        "changes": changes,
    }


def resolve_learning_strategy(
    context: Mapping[str, Any] | None,
    pipeline_config: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    if isinstance(context, Mapping):
        strategy = context.get("learning_strategy")
        if isinstance(strategy, Mapping):
            return dict(strategy)

    if isinstance(pipeline_config, Mapping):
        strategy = pipeline_config.get("learning_strategy")
        if isinstance(strategy, Mapping):
            return dict(strategy)

    return {}


def resolve_previous_iteration_feedback(
    context: Mapping[str, Any] | None,
    pipeline_config: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    if isinstance(context, Mapping):
        feedback = context.get("previous_iteration_feedback")
        if isinstance(feedback, Mapping):
            return dict(feedback)

    if isinstance(pipeline_config, Mapping):
        feedback = pipeline_config.get("previous_iteration_feedback")
        if isinstance(feedback, Mapping):
            return dict(feedback)

    return {}


def resolve_tuned_parameters(
    context: Mapping[str, Any] | None,
    pipeline_config: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    strategy = resolve_learning_strategy(context, pipeline_config)
    tuned_parameters = strategy.get("tuned_parameters")
    if isinstance(tuned_parameters, Mapping) and tuned_parameters:
        return dict(tuned_parameters)

    feedback = resolve_previous_iteration_feedback(context, pipeline_config)
    learning_summary = feedback.get("learning_summary")
    if isinstance(learning_summary, Mapping):
        tuned_parameters = learning_summary.get("tuned_parameters")
        if isinstance(tuned_parameters, Mapping) and tuned_parameters:
            return dict(tuned_parameters)

    if isinstance(pipeline_config, Mapping):
        learned_runtime_parameters = pipeline_config.get("learned_runtime_parameters")
        if isinstance(learned_runtime_parameters, Mapping) and learned_runtime_parameters:
            return dict(learned_runtime_parameters)

    return {}


def has_learning_strategy(
    context: Mapping[str, Any] | None,
    pipeline_config: Mapping[str, Any] | None = None,
) -> bool:
    return bool(
        resolve_learning_strategy(context, pipeline_config)
        or resolve_tuned_parameters(context, pipeline_config)
    )


def resolve_numeric_learning_parameter(
    parameter_name: str,
    default: float,
    context: Mapping[str, Any] | None,
    pipeline_config: Mapping[str, Any] | None = None,
    *,
    min_value: float | None = None,
    max_value: float | None = None,
) -> float:
    tuned_parameters = resolve_tuned_parameters(context, pipeline_config)
    value: Any
    if parameter_name in tuned_parameters:
        value = tuned_parameters.get(parameter_name)
    else:
        strategy = resolve_learning_strategy(context, pipeline_config)
        value = strategy.get(parameter_name, default)

    try:
        normalized_value = float(value)
    except (TypeError, ValueError):
        normalized_value = float(default)

    if min_value is not None:
        normalized_value = max(float(min_value), normalized_value)
    if max_value is not None:
        normalized_value = min(float(max_value), normalized_value)
    return normalized_value


def resolve_learning_flag(
    flag_name: str,
    default: bool,
    context: Mapping[str, Any] | None,
    pipeline_config: Mapping[str, Any] | None = None,
) -> bool:
    if isinstance(context, Mapping) and flag_name in context:
        return bool(context.get(flag_name))

    strategy = resolve_learning_strategy(context, pipeline_config)
    if flag_name in strategy:
        return bool(strategy.get(flag_name))

    default_flag_name = f"default_{flag_name}"
    if default_flag_name in strategy:
        return bool(strategy.get(default_flag_name))

    return bool(default)