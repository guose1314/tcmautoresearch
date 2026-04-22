"""LLM 角色化 prompt 池 + 轻量 KV cache 描述符（J-3）。

设计目标:
  - 提供 5 个中医角色 system_prompt：医经家 / 经方家 / 温病家 / 校勘家 / 训诂家
  - 与 prepare_planned_llm_call(role=...) 协同：把角色 system_prompt 与温度
    在 prompt 阶段透传到 PlannedLLMService.build_prompt
  - 提供 KVCacheDescriptor + KVCacheStore：仅记录 role → 缓存文件路径，不直接
    调用 llama.cpp 内部 API；后续可由 LLMEngine 在加载完模型后读写真实 state

接口:
  - LLMRoleProfile / get_role_profile / list_role_profiles / register_role_profile
  - ROLE_YIJING / ROLE_JINGFANG / ROLE_WENBING / ROLE_JIAOKAN / ROLE_XUNGU
  - KVCacheDescriptor / KVCacheStore
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

# ---------------------------------------------------------------------------
# 角色名常量
# ---------------------------------------------------------------------------
ROLE_YIJING = "医经家"
ROLE_JINGFANG = "经方家"
ROLE_WENBING = "温病家"
ROLE_JIAOKAN = "校勘家"
ROLE_XUNGU = "训诂家"

DEFAULT_ROLE_NAMES: tuple[str, ...] = (
    ROLE_YIJING,
    ROLE_JINGFANG,
    ROLE_WENBING,
    ROLE_JIAOKAN,
    ROLE_XUNGU,
)

ROLE_PROFILE_CONTRACT_VERSION = "llm-role-profile-v1"


def _as_text(value: Any) -> str:
    return str(value or "").strip()


def _clamp(value: float, low: float = 0.0, high: float = 2.0) -> float:
    if value < low:
        return low
    if value > high:
        return high
    return float(value)


@dataclass
class LLMRoleProfile:
    """中医角色化 prompt 配置。

    role_name:        显示名，与 prepare_planned_llm_call(role=...) 入参对齐
    system_prompt:    注入到 LLM system 的角色化前缀
    temperature:      推荐采样温度（0..2）；planner 使用方可选择是否覆盖
    style_tags:       角色风格标签，便于 dashboard / metadata
    kv_cache_key:     与 KVCacheDescriptor 关联的稳定 key
    """

    role_name: str = ""
    system_prompt: str = ""
    temperature: float = 0.3
    style_tags: List[str] = field(default_factory=list)
    kv_cache_key: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "role_name": self.role_name,
            "system_prompt": self.system_prompt,
            "temperature": self.temperature,
            "style_tags": list(self.style_tags),
            "kv_cache_key": self.kv_cache_key,
            "contract_version": ROLE_PROFILE_CONTRACT_VERSION,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "LLMRoleProfile":
        d = dict(data) if isinstance(data, Mapping) else {}
        try:
            temperature = float(d.get("temperature") or 0.3)
        except (TypeError, ValueError):
            temperature = 0.3
        return cls(
            role_name=_as_text(d.get("role_name")),
            system_prompt=_as_text(d.get("system_prompt")),
            temperature=_clamp(temperature),
            style_tags=[_as_text(s) for s in (d.get("style_tags") or []) if _as_text(s)],
            kv_cache_key=_as_text(d.get("kv_cache_key")),
        )


# ---------------------------------------------------------------------------
# 默认角色池
# ---------------------------------------------------------------------------
_DEFAULT_PROFILES: Dict[str, LLMRoleProfile] = {
    ROLE_YIJING: LLMRoleProfile(
        role_name=ROLE_YIJING,
        system_prompt=(
            "你是一位精研《黄帝内经》《难经》的医经家，"
            "回答时优先援引经文原典与历代名家注释，"
            "强调阴阳五行、藏象经络等核心理论框架，"
            "结论需指明所依据的经文出处。"
        ),
        temperature=0.25,
        style_tags=["经典", "理论", "藏象"],
        kv_cache_key="role.yijing.v1",
    ),
    ROLE_JINGFANG: LLMRoleProfile(
        role_name=ROLE_JINGFANG,
        system_prompt=(
            "你是一位经方派临床家，宗仲景学说，"
            "擅以《伤寒论》《金匮要略》方证对应思维分析病机与方药，"
            "回答需明确『方证』『药症』关系，避免泛论。"
        ),
        temperature=0.3,
        style_tags=["方证", "六经", "仲景"],
        kv_cache_key="role.jingfang.v1",
    ),
    ROLE_WENBING: LLMRoleProfile(
        role_name=ROLE_WENBING,
        system_prompt=(
            "你是一位温病学派学者，熟悉叶天士、吴鞠通、薛生白学说，"
            "擅长卫气营血、三焦辨证体系，"
            "回答时区分外感温热与湿热，强调时令与传变。"
        ),
        temperature=0.3,
        style_tags=["温病", "卫气营血", "三焦"],
        kv_cache_key="role.wenbing.v1",
    ),
    ROLE_JIAOKAN: LLMRoleProfile(
        role_name=ROLE_JIAOKAN,
        system_prompt=(
            "你是一位中医文献校勘家，依据目录学、版本学方法，"
            "对古籍异文给出对校、本校、他校、理校四种判断，"
            "回答需注明所对勘的版本与异文位置。"
        ),
        temperature=0.2,
        style_tags=["校勘", "版本", "异文"],
        kv_cache_key="role.jiaokan.v1",
    ),
    ROLE_XUNGU: LLMRoleProfile(
        role_name=ROLE_XUNGU,
        system_prompt=(
            "你是一位训诂学家，长于辨析中医古籍中的字、词、名物，"
            "回答需给出本义、引申义、通假关系与古今异名，"
            "并尽量引证字书、韵书或名家训释。"
        ),
        temperature=0.2,
        style_tags=["训诂", "音韵", "名物"],
        kv_cache_key="role.xungu.v1",
    ),
}


_PROFILE_REGISTRY: Dict[str, LLMRoleProfile] = dict(_DEFAULT_PROFILES)


def list_role_profiles() -> List[LLMRoleProfile]:
    """返回当前注册的所有角色 profile（按角色名排序）。"""
    return [_PROFILE_REGISTRY[name] for name in sorted(_PROFILE_REGISTRY)]


def get_role_profile(role: Any) -> Optional[LLMRoleProfile]:
    """按角色名取得 profile。未知角色返回 None（调用方负责降级）。"""
    name = _as_text(role)
    if not name:
        return None
    return _PROFILE_REGISTRY.get(name)


def register_role_profile(profile: LLMRoleProfile) -> None:
    """注册或覆盖一条角色 profile。"""
    if not isinstance(profile, LLMRoleProfile):
        raise TypeError("profile 必须是 LLMRoleProfile")
    if not profile.role_name:
        raise ValueError("profile.role_name 不能为空")
    _PROFILE_REGISTRY[profile.role_name] = profile


def reset_role_profiles_for_tests() -> None:
    """测试辅助：恢复默认 5 个角色，撤销自定义注册。"""
    _PROFILE_REGISTRY.clear()
    _PROFILE_REGISTRY.update(_DEFAULT_PROFILES)


# ---------------------------------------------------------------------------
# KV cache 描述符 + 轻量持久化
# ---------------------------------------------------------------------------
@dataclass
class KVCacheDescriptor:
    """单条角色 KV cache 文件描述符。

    实际的 llama.cpp prompt cache 由 LLMEngine 在装载模型后写入；
    本描述符只承担"在哪儿、属于谁、是否有效"的元数据职责。
    """

    role_name: str = ""
    kv_cache_key: str = ""
    cache_path: str = ""
    prompt_signature: str = ""
    token_count: int = 0
    valid: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "KVCacheDescriptor":
        d = dict(data) if isinstance(data, Mapping) else {}
        try:
            token_count = int(d.get("token_count") or 0)
        except (TypeError, ValueError):
            token_count = 0
        return cls(
            role_name=_as_text(d.get("role_name")),
            kv_cache_key=_as_text(d.get("kv_cache_key")),
            cache_path=_as_text(d.get("cache_path")),
            prompt_signature=_as_text(d.get("prompt_signature")),
            token_count=max(0, token_count),
            valid=bool(d.get("valid")),
        )


class KVCacheStore:
    """role → KVCacheDescriptor 的最小持久化映射。

    存储格式:
      <root>/index.json  -- 包含 {"role.x.v1": KVCacheDescriptor.to_dict()}
      <root>/<role>.kv   -- 实际 KV cache 二进制（由 LLMEngine 写入；本类不操作）
    """

    INDEX_FILENAME = "index.json"

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._index_path = self._root / self.INDEX_FILENAME
        self._index: Dict[str, KVCacheDescriptor] = {}
        self._load_index()

    def _load_index(self) -> None:
        if not self._index_path.exists():
            return
        try:
            data = json.loads(self._index_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if not isinstance(data, dict):
            return
        for key, payload in data.items():
            if isinstance(payload, Mapping):
                self._index[str(key)] = KVCacheDescriptor.from_dict(payload)

    def _flush_index(self) -> None:
        payload = {k: v.to_dict() for k, v in self._index.items()}
        self._index_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def cache_path_for(self, profile: LLMRoleProfile) -> Path:
        if not profile.kv_cache_key:
            raise ValueError("profile.kv_cache_key 为空，无法定位 KV cache 路径")
        return self._root / f"{profile.kv_cache_key}.kv"

    def get(self, key: str) -> Optional[KVCacheDescriptor]:
        return self._index.get(_as_text(key)) or None

    def upsert(self, descriptor: KVCacheDescriptor) -> None:
        if not descriptor.kv_cache_key:
            raise ValueError("descriptor.kv_cache_key 不能为空")
        self._index[descriptor.kv_cache_key] = descriptor
        self._flush_index()

    def invalidate(self, key: str) -> None:
        norm = _as_text(key)
        descriptor = self._index.get(norm)
        if descriptor is None:
            return
        descriptor.valid = False
        self._flush_index()

    def all_descriptors(self) -> List[KVCacheDescriptor]:
        return [self._index[k] for k in sorted(self._index)]


def normalize_role_profiles(profiles: Iterable[Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for item in profiles or []:
        if isinstance(item, LLMRoleProfile):
            out.append(item.to_dict())
        elif isinstance(item, Mapping):
            out.append(LLMRoleProfile.from_dict(item).to_dict())
    return out


__all__ = [
    "ROLE_YIJING",
    "ROLE_JINGFANG",
    "ROLE_WENBING",
    "ROLE_JIAOKAN",
    "ROLE_XUNGU",
    "DEFAULT_ROLE_NAMES",
    "ROLE_PROFILE_CONTRACT_VERSION",
    "LLMRoleProfile",
    "list_role_profiles",
    "get_role_profile",
    "register_role_profile",
    "reset_role_profiles_for_tests",
    "KVCacheDescriptor",
    "KVCacheStore",
    "normalize_role_profiles",
]
