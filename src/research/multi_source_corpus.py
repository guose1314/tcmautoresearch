"""兼容层 — 已迁移至 src.collector.multi_source_corpus"""
from src.collector.multi_source_corpus import *  # noqa: F401,F403
from src.collector.multi_source_corpus import (  # noqa: F401
    SourceWitness,
    build_source_collection_plan,
    build_witnesses_from_records,
    cross_validate_witnesses,
    load_source_registry,
    recognize_classical_format,
)
