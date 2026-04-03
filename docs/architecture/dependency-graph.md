# Dependency Graph

This document is generated from internal imports under src/.

## Summary

- Module count: 81
- Module edges: 119
- Package count: 22
- Package edges: 33

## Package Graph

```mermaid
flowchart LR
    src["src"]
    src_analysis["analysis"]
    src_analytics["analytics"]
    src_core["core"]
    src_corpus["corpus"]
    src_cycle["cycle"]
    src_data["data"]
    src_extraction["extraction"]
    src_extractors["extractors"]
    src_hypothesis["hypothesis"]
    src_infra["infra"]
    src_knowledge["knowledge"]
    src_learning["learning"]
    src_llm["llm"]
    src_orchestration["orchestration"]
    src_output["output"]
    src_preprocessor["preprocessor"]
    src_reasoning["reasoning"]
    src_research["research"]
    src_semantic_modeling["semantic_modeling"]
    src_storage["storage"]
    src_test["test"]
    src_analysis --> src_research
    src_corpus --> src_core
    src_cycle --> src_core
    src_data --> src_infra
    src_extraction --> src_knowledge
    src_extraction --> src_semantic_modeling
    src_extractors --> src_core
    src_extractors --> src_data
    src_hypothesis --> src_core
    src_infra --> src_llm
    src_knowledge --> src_semantic_modeling
    src_learning --> src_core
    src_llm --> src_infra
    src_llm --> src_research
    src_orchestration --> src_research
    src_output --> src_core
    src_preprocessor --> src_core
    src_reasoning --> src_core
    src_reasoning --> src_semantic_modeling
    src_research --> src_analytics
    src_research --> src_core
    src_research --> src_corpus
    src_research --> src_extractors
    src_research --> src_hypothesis
    src_research --> src_llm
    src_research --> src_output
    src_research --> src_preprocessor
    src_research --> src_semantic_modeling
    src_semantic_modeling --> src_core
    src_semantic_modeling --> src_extraction
    src_semantic_modeling --> src_knowledge
    src_semantic_modeling --> src_research
    src_test --> src_core
```

## Packages

| Package | In Degree | Out Degree |
|---|---:|---:|
| src | 0 | 0 |
| src.analysis | 0 | 1 |
| src.analytics | 1 | 0 |
| src.core | 11 | 0 |
| src.corpus | 1 | 1 |
| src.cycle | 0 | 1 |
| src.data | 1 | 1 |
| src.extraction | 1 | 2 |
| src.extractors | 1 | 2 |
| src.hypothesis | 1 | 1 |
| src.infra | 2 | 1 |
| src.knowledge | 2 | 1 |
| src.learning | 0 | 1 |
| src.llm | 2 | 2 |
| src.orchestration | 0 | 1 |
| src.output | 1 | 1 |
| src.preprocessor | 1 | 1 |
| src.reasoning | 0 | 2 |
| src.research | 4 | 9 |
| src.semantic_modeling | 4 | 4 |
| src.storage | 0 | 0 |
| src.test | 0 | 1 |
