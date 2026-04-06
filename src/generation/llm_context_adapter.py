from __future__ import annotations

import copy
from typing import Any, Dict, Mapping, Sequence

DEFAULT_LLM_ANALYSIS_MODULE_ALIASES: Dict[str, tuple[str, ...]] = {
    "research_perspectives": ("research_perspectives",),
    "formula_comparisons": ("formula_comparisons",),
    "herb_properties_analysis": ("herb_properties_analysis", "herb_properties"),
    "pharmacology_integration": ("pharmacology_integration",),
    "network_pharmacology": ("network_pharmacology", "network_pharmacology_systems_biology"),
    "supramolecular_physicochemistry": ("supramolecular_physicochemistry",),
    "knowledge_archaeology": ("knowledge_archaeology",),
    "complexity_dynamics": ("complexity_dynamics", "complexity_nonlinear_dynamics"),
    "research_scoring_panel": ("research_scoring_panel",),
    "summary_analysis": ("summary_analysis",),
}


class LLMContextAdapter:
    """Normalize and inject LLM analysis context for zero-touch generator integration."""

    def __init__(
        self,
        module_aliases: Mapping[str, Sequence[str]] | None=None,
        *,
        contract_version: str="llm-analysis-context-v1",
        expose_top_level_analysis_modules: bool=True,
    ) -> None:
        resolved_aliases = module_aliases or DEFAULT_LLM_ANALYSIS_MODULE_ALIASES
        self.module_aliases: Dict[str, tuple[str, ...]] = {
            key: tuple(aliases) for key, aliases in resolved_aliases.items()
        }
        self.contract_version = contract_version
        self.expose_top_level_analysis_modules = expose_top_level_analysis_modules

    def adapt_context(self, context: Mapping[str, Any] | None) -> Dict[str, Any]:
        adapted: Dict[str, Any] = dict(context or {})
        llm_analysis_context = self.build_llm_analysis_context(adapted)
        analysis_modules = llm_analysis_context.get("analysis_modules") or {}

        adapted["llm_analysis_context"] = llm_analysis_context

        analysis_results = adapted.get("analysis_results")
        if isinstance(analysis_results, dict):
            analysis_results_payload = dict(analysis_results)
        else:
            analysis_results_payload = {}
        analysis_results_payload["llm_analysis_context"] = llm_analysis_context
        for module_name, module_value in analysis_modules.items():
            analysis_results_payload.setdefault(module_name, copy.deepcopy(module_value))
        adapted["analysis_results"] = analysis_results_payload

        if self.expose_top_level_analysis_modules:
            adapted["analysis_modules"] = copy.deepcopy(analysis_modules)

        return adapted

    def build_llm_analysis_context(self, context: Mapping[str, Any] | None) -> Dict[str, Any]:
        context_payload = context if isinstance(context, Mapping) else {}
        modules = self._resolve_analysis_modules(context_payload)
        module_presence = {
            module_name: self._has_payload(module_value)
            for module_name, module_value in modules.items()
        }
        populated_modules = [
            module_name
            for module_name, is_present in module_presence.items()
            if is_present
        ]
        return {
            "contract_version": self.contract_version,
            "analysis_modules": modules,
            "module_presence": module_presence,
            "module_count": len(modules),
            "populated_module_count": len(populated_modules),
            "populated_modules": populated_modules,
        }

    def _resolve_analysis_modules(self, context: Mapping[str, Any]) -> Dict[str, Any]:
        llm_context = context.get("llm_analysis_context")
        llm_modules = llm_context.get("analysis_modules") if isinstance(llm_context, dict) else {}

        analysis_results = context.get("analysis_results")
        output_data = context.get("output_data")
        output_analysis_results = output_data.get("analysis_results") if isinstance(output_data, dict) else {}
        research_artifact = context.get("research_artifact")
        research_perspectives = context.get("research_perspectives")

        containers = [
            llm_modules if isinstance(llm_modules, dict) else {},
            context,
            analysis_results if isinstance(analysis_results, dict) else {},
            output_data if isinstance(output_data, dict) else {},
            output_analysis_results if isinstance(output_analysis_results, dict) else {},
            research_artifact if isinstance(research_artifact, dict) else {},
        ]

        resolved: Dict[str, Any] = {}
        for module_name, aliases in self.module_aliases.items():
            module_value = self._resolve_field(containers, aliases)
            if module_name == "research_perspectives" and module_value is None and isinstance(research_perspectives, dict):
                module_value = copy.deepcopy(research_perspectives)
            resolved[module_name] = module_value if module_value is not None else {}
        return resolved

    def _resolve_field(self, containers: Sequence[Mapping[str, Any]], field_names: Sequence[str]) -> Any:
        for container in containers:
            for field_name in field_names:
                if field_name not in container:
                    continue
                value = container.get(field_name)
                if value is None:
                    continue
                return copy.deepcopy(value)
        return None

    def _has_payload(self, value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, (dict, list, tuple, set)):
            return bool(value)
        return True


class LLMContextAdaptedPaperWriter:
    """Proxy paper writer that injects adapted LLM context before execute."""

    def __init__(
        self,
        paper_writer: Any,
        context_adapter: LLMContextAdapter | None=None,
    ) -> None:
        self._paper_writer = paper_writer
        self._context_adapter = context_adapter or LLMContextAdapter()

    @property
    def wrapped_paper_writer(self) -> Any:
        return self._paper_writer

    def initialize(self) -> Any:
        return self._paper_writer.initialize()

    def execute(self, context: Any) -> Any:
        if not isinstance(context, Mapping):
            return self._paper_writer.execute(context)
        adapted_context = self._context_adapter.adapt_context(context)
        return self._paper_writer.execute(adapted_context)

    def cleanup(self) -> Any:
        return self._paper_writer.cleanup()

    def __getattr__(self, item: str) -> Any:
        return getattr(self._paper_writer, item)


def wrap_paper_writer_with_llm_context(
    paper_writer: Any,
    *,
    module_aliases: Mapping[str, Sequence[str]] | None=None,
    contract_version: str="llm-analysis-context-v1",
    expose_top_level_analysis_modules: bool=True,
) -> Any:
    """Wrap a paper writer so execute() always receives adapted LLM context."""

    if paper_writer is None or isinstance(paper_writer, LLMContextAdaptedPaperWriter):
        return paper_writer

    context_adapter = LLMContextAdapter(
        module_aliases=module_aliases,
        contract_version=contract_version,
        expose_top_level_analysis_modules=expose_top_level_analysis_modules,
    )
    return LLMContextAdaptedPaperWriter(
        paper_writer,
        context_adapter=context_adapter,
    )


__all__ = [
    "DEFAULT_LLM_ANALYSIS_MODULE_ALIASES",
    "LLMContextAdapter",
    "LLMContextAdaptedPaperWriter",
    "wrap_paper_writer_with_llm_context",
]
