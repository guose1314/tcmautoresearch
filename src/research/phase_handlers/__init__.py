import importlib as _importlib

_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    "AnalyzePhaseHandler": ("src.research.phase_handlers.analyze_handler", "AnalyzePhaseHandler"),
    "ExperimentPhaseHandler": ("src.research.phase_handlers.experiment_handler", "ExperimentPhaseHandler"),
    "ExperimentExecutionPhaseHandler": ("src.research.phase_handlers.experiment_execution_handler", "ExperimentExecutionPhaseHandler"),
    "HypothesisPhaseHandler": ("src.research.phase_handlers.hypothesis_handler", "HypothesisPhaseHandler"),
    "ObservePhaseHandler": ("src.research.phase_handlers.observe_handler", "ObservePhaseHandler"),
    "PublishPhaseHandler": ("src.research.phase_handlers.publish_handler", "PublishPhaseHandler"),
    "ReflectPhaseHandler": ("src.research.phase_handlers.reflect_handler", "ReflectPhaseHandler"),
}

__all__ = list(_LAZY_IMPORTS.keys())


def __getattr__(name: str):
    if name in _LAZY_IMPORTS:
        module_path, attr = _LAZY_IMPORTS[name]
        mod = _importlib.import_module(module_path)
        val = getattr(mod, attr)
        globals()[name] = val
        return val
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
