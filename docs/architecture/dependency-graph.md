# Dependency Graph

This document is generated from internal imports under src/.

## Summary

- Module count: 54
- Module edges: 59
- Package count: 14
- Package edges: 13

## Package Graph

```mermaid
flowchart LR
    src["src"]
    src_core["core"]
    src_cycle["cycle"]
    src_data["data"]
    src_extractors["extractors"]
    src_learning["learning"]
    src_llm["llm"]
    src_output["output"]
    src_preprocessor["preprocessor"]
    src_reasoning["reasoning"]
    src_research["research"]
    src_semantic_modeling["semantic_modeling"]
    src_storage["storage"]
    src_test["test"]
    src_cycle --> src_core
    src_extractors --> src_core
    src_extractors --> src_data
    src_learning --> src_core
    src_output --> src_core
    src_preprocessor --> src_core
    src_reasoning --> src_core
    src_research --> src_core
    src_research --> src_extractors
    src_research --> src_llm
    src_research --> src_preprocessor
    src_research --> src_semantic_modeling
    src_semantic_modeling --> src_core
```

## Packages

| Package | In Degree | Out Degree |
|---|---:|---:|
| src | 0 | 0 |
| src.core | 8 | 0 |
| src.cycle | 0 | 1 |
| src.data | 1 | 0 |
| src.extractors | 1 | 2 |
| src.learning | 0 | 1 |
| src.llm | 1 | 0 |
| src.output | 0 | 1 |
| src.preprocessor | 1 | 1 |
| src.reasoning | 0 | 1 |
| src.research | 0 | 5 |
| src.semantic_modeling | 1 | 1 |
| src.storage | 0 | 0 |
| src.test | 0 | 0 |
