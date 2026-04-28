"""LLMDiskCache.make_llm_key 的 extra_keys 扩展点回归测试。

目的：保证未来 prompt_version / schema_version 等语义版本号被注入后，
即使 prompt 文本完全相同，缓存键也会按版本隔离；同时验证默认 None 时
键与历史实现完全一致，避免一次性失效全量旧缓存。
"""

from src.infra.cache_service import LLMDiskCache

_PROMPT = "请分析《伤寒论》太阳病提纲。"
_SYS = "你是一位中医文献研究助手。"
_MODEL = "local:./models/qwen.gguf"
_TEMP = 0.3
_MAX = 1024


def test_make_llm_key_default_matches_legacy_signature() -> None:
    """不传 extra_keys 时，键必须与历史 5 参形式一致，避免缓存全失效。"""

    legacy = LLMDiskCache.make_llm_key(_PROMPT, _SYS, _MODEL, _TEMP, _MAX)
    explicit_none = LLMDiskCache.make_llm_key(
        _PROMPT, _SYS, _MODEL, _TEMP, _MAX, extra_keys=None
    )
    empty = LLMDiskCache.make_llm_key(
        _PROMPT, _SYS, _MODEL, _TEMP, _MAX, extra_keys={}
    )

    assert legacy == explicit_none
    assert legacy == empty


def test_make_llm_key_isolates_by_extra_keys() -> None:
    """提供不同 extra_keys（如 prompt_version）时，键必须不同。"""

    base = LLMDiskCache.make_llm_key(_PROMPT, _SYS, _MODEL, _TEMP, _MAX)
    v1 = LLMDiskCache.make_llm_key(
        _PROMPT, _SYS, _MODEL, _TEMP, _MAX, extra_keys={"prompt_version": "v1"}
    )
    v2 = LLMDiskCache.make_llm_key(
        _PROMPT, _SYS, _MODEL, _TEMP, _MAX, extra_keys={"prompt_version": "v2"}
    )

    assert base != v1
    assert v1 != v2


def test_make_llm_key_is_order_independent() -> None:
    """extra_keys 内键值对顺序不影响最终缓存键。"""

    a = LLMDiskCache.make_llm_key(
        _PROMPT,
        _SYS,
        _MODEL,
        _TEMP,
        _MAX,
        extra_keys={"prompt_version": "v1", "schema_version": "s1"},
    )
    b = LLMDiskCache.make_llm_key(
        _PROMPT,
        _SYS,
        _MODEL,
        _TEMP,
        _MAX,
        extra_keys={"schema_version": "s1", "prompt_version": "v1"},
    )

    assert a == b


def test_make_key_alias_supports_extra_keys() -> None:
    """make_key 别名也必须接受 extra_keys，并与 make_llm_key 等价。"""

    via_alias = LLMDiskCache.make_key(
        _PROMPT, _SYS, _MODEL, _TEMP, _MAX, extra_keys={"prompt_version": "v3"}
    )
    via_llm = LLMDiskCache.make_llm_key(
        _PROMPT, _SYS, _MODEL, _TEMP, _MAX, extra_keys={"prompt_version": "v3"}
    )

    assert via_alias == via_llm
