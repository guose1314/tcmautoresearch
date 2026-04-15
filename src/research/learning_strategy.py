from __future__ import annotations

from typing import Any, Dict, Mapping


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