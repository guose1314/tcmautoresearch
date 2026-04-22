"""RLAIF-lite / LoRA 离线微调数据集（Phase M-3）。"""

from .preference_dataset import (  # noqa: F401
    RLAIF_PREFERENCE_DATASET_CONTRACT_VERSION,
    PreferencePair,
    PreferenceDataset,
    LoRADatasetSpec,
    build_preference_pair,
    build_dataset_from_fallback_records,
    export_dataset_to_jsonl,
)
