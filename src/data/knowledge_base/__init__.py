"""知识库数据加载器 — 从 JSON 文件加载中医知识库数据."""

import json
from functools import lru_cache
from pathlib import Path

_KB_DIR = Path(__file__).parent


@lru_cache(maxsize=None)
def _load_json(filename: str) -> dict:
    filepath = _KB_DIR / filename
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def load_herb_properties() -> dict:
    return _load_json("herb_properties.json")


def load_formula_structures() -> dict:
    return _load_json("formula_structures.json")


def load_herb_targets() -> dict:
    return _load_json("herb_targets.json")


def load_target_pathways() -> dict:
    return _load_json("target_pathways.json")


def load_formula_archive() -> dict:
    return _load_json("formula_archive.json")
