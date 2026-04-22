"""RLAIF-lite / LoRA 离线微调数据集（Phase M-3）。"""

from .preference_dataset import (  # noqa: F401
    RLAIF_PREFERENCE_DATASET_CONTRACT_VERSION,
    LoRADatasetSpec,
    PreferenceDataset,
    PreferencePair,
    build_dataset_from_fallback_records,
    build_preference_pair,
    export_dataset_to_jsonl,
)
