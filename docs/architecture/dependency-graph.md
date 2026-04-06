# Dependency Graph

This document is generated from internal imports under src/.

## Summary

- Module count: 205
- Module edges: 432
- Package count: 28
- Package edges: 66

## Package Graph

```mermaid
flowchart LR
    src["src"]
    src_ai_assistant["ai_assistant"]
    src_analysis["analysis"]
    src_analytics["analytics"]
    src_api["api"]
    src_collector["collector"]
    src_common["common"]
    src_core["core"]
    src_cycle["cycle"]
    src_data["data"]
    src_extraction["extraction"]
    src_extractors["extractors"]
    src_generation["generation"]
    src_infra["infra"]
    src_infrastructure["infrastructure"]
    src_knowledge["knowledge"]
    src_learning["learning"]
    src_llm["llm"]
    src_orchestration["orchestration"]
    src_output["output"]
    src_quality["quality"]
    src_reasoning["reasoning"]
    src_research["research"]
    src_semantic_modeling["semantic_modeling"]
    src_storage["storage"]
    src_test["test"]
    src_visualization["visualization"]
    src_web["web"]
    src_ai_assistant --> src_llm
    src_analysis --> src_core
    src_analysis --> src_data
    src_analysis --> src_extraction
    src_analysis --> src_knowledge
    src_analysis --> src_research
    src_analysis --> src_semantic_modeling
    src_api --> src_analysis
    src_api --> src_collector
    src_api --> src_core
    src_api --> src_extraction
    src_api --> src_infrastructure
    src_api --> src_web
    src_collector --> src_common
    src_collector --> src_core
    src_collector --> src_knowledge
    src_core --> src_generation
    src_cycle --> src_analysis
    src_cycle --> src_core
    src_cycle --> src_generation
    src_cycle --> src_infrastructure
    src_cycle --> src_test
    src_data --> src_infra
    src_extraction --> src_knowledge
    src_extraction --> src_semantic_modeling
    src_extractors --> src_analysis
    src_generation --> src_core
    src_infra --> src_infrastructure
    src_infra --> src_llm
    src_infrastructure --> src_core
    src_knowledge --> src_semantic_modeling
    src_knowledge --> src_storage
    src_learning --> src_core
    src_llm --> src_infra
    src_llm --> src_research
    src_orchestration --> src_research
    src_output --> src_core
    src_output --> src_generation
    src_quality --> src_collector
    src_quality --> src_core
    src_quality --> src_research
    src_reasoning --> src_analysis
    src_research --> src_analysis
    src_research --> src_analytics
    src_research --> src_collector
    src_research --> src_core
    src_research --> src_generation
    src_research --> src_infra
    src_research --> src_llm
    src_research --> src_quality
    src_research --> src_semantic_modeling
    src_research --> src_storage
    src_semantic_modeling --> src_analysis
    src_semantic_modeling --> src_data
    src_semantic_modeling --> src_research
    src_storage --> src_infrastructure
    src_storage --> src_knowledge
    src_storage --> src_semantic_modeling
    src_test --> src_core
    src_web --> src_ai_assistant
    src_web --> src_analysis
    src_web --> src_api
    src_web --> src_infrastructure
    src_web --> src_knowledge
    src_web --> src_orchestration
    src_web --> src_research
```

## Packages

| Package | In Degree | Out Degree |
|---|---:|---:|
| src | 0 | 0 |
| src.ai_assistant | 1 | 1 |
| src.analysis | 7 | 6 |
| src.analytics | 1 | 0 |
| src.api | 1 | 6 |
| src.collector | 3 | 3 |
| src.common | 1 | 0 |
| src.core | 11 | 1 |
| src.cycle | 0 | 5 |
| src.data | 2 | 1 |
| src.extraction | 2 | 2 |
| src.extractors | 0 | 1 |
| src.generation | 4 | 1 |
| src.infra | 3 | 2 |
| src.infrastructure | 5 | 1 |
| src.knowledge | 5 | 2 |
| src.learning | 0 | 1 |
| src.llm | 3 | 2 |
| src.orchestration | 1 | 1 |
| src.output | 0 | 2 |
| src.quality | 1 | 3 |
| src.reasoning | 0 | 1 |
| src.research | 6 | 10 |
| src.semantic_modeling | 5 | 3 |
| src.storage | 2 | 3 |
| src.test | 1 | 1 |
| src.visualization | 0 | 0 |
| src.web | 1 | 7 |
