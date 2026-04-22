"""LLM Tool calling 注册表（Phase M-2）。

把"查图谱 / 查目录 / 查训诂"等能力封装为可调用工具，让小模型用
function-call 风格替代超长 prompt 拼接。

公开 API：
  - TOOL_CALLING_CONTRACT_VERSION
  - ToolSpec / ToolCall / ToolResult / ToolRegistry
  - build_default_tool_registry()
  - render_tool_catalog_for_prompt(registry)

设计原则：
  - 纯契约 + 同步函数，工具实现注入式（callable），便于在测试里替换
  - 默认 registry 注册 query_neo4j / query_catalog / query_exegesis 三个名称
    占位符（实现 callable 由调用方在装配时注入），不强行依赖 Neo4j 运行
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional

TOOL_CALLING_CONTRACT_VERSION = "tool-calling-v1"

ToolHandler = Callable[[Mapping[str, Any]], Any]


@dataclass(frozen=True)
class ToolSpec:
    """工具元数据（可序列化为 LLM prompt / function schema）。"""

    name: str
    description: str
    parameters_schema: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters_schema": dict(self.parameters_schema),
        }


@dataclass
class ToolCall:
    tool_name: str
    arguments: Dict[str, Any] = field(default_factory=dict)
    call_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "arguments": dict(self.arguments),
            "call_id": self.call_id,
        }


@dataclass
class ToolResult:
    tool_name: str
    ok: bool
    output: Any = None
    error: Optional[str] = None
    call_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "ok": self.ok,
            "output": self.output,
            "error": self.error,
            "call_id": self.call_id,
        }


class ToolRegistry:
    """线程不安全（按调用方约定使用）的工具注册表。"""

    def __init__(self) -> None:
        self._specs: Dict[str, ToolSpec] = {}
        self._handlers: Dict[str, Optional[ToolHandler]] = {}

    @property
    def contract_version(self) -> str:
        return TOOL_CALLING_CONTRACT_VERSION

    def register(
        self,
        spec: ToolSpec,
        handler: Optional[ToolHandler] = None,
    ) -> None:
        if spec.name in self._specs:
            raise ValueError(f"工具已注册: {spec.name}")
        self._specs[spec.name] = spec
        self._handlers[spec.name] = handler

    def bind_handler(self, name: str, handler: ToolHandler) -> None:
        if name not in self._specs:
            raise KeyError(f"未注册工具: {name}")
        self._handlers[name] = handler

    def list_specs(self) -> List[ToolSpec]:
        return list(self._specs.values())

    def has(self, name: str) -> bool:
        return name in self._specs

    def invoke(self, call: ToolCall) -> ToolResult:
        if call.tool_name not in self._specs:
            return ToolResult(
                tool_name=call.tool_name,
                ok=False,
                error=f"unknown tool: {call.tool_name}",
                call_id=call.call_id,
            )
        handler = self._handlers.get(call.tool_name)
        if handler is None:
            return ToolResult(
                tool_name=call.tool_name,
                ok=False,
                error=f"tool handler not bound: {call.tool_name}",
                call_id=call.call_id,
            )
        try:
            output = handler(dict(call.arguments))
        except Exception as exc:  # noqa: BLE001 — 工具执行失败封装为 ToolResult
            return ToolResult(
                tool_name=call.tool_name,
                ok=False,
                error=f"{type(exc).__name__}: {exc}",
                call_id=call.call_id,
            )
        return ToolResult(
            tool_name=call.tool_name,
            ok=True,
            output=output,
            call_id=call.call_id,
        )


# ---------------------------------------------------------------------------
# 默认 registry：仅声明 spec，handler 由装配方注入
# ---------------------------------------------------------------------------

_DEFAULT_TOOL_SPECS: List[ToolSpec] = [
    ToolSpec(
        name="query_neo4j",
        description="对 TCM 知识图谱执行只读 Cypher 查询，返回节点/关系列表。",
        parameters_schema={
            "type": "object",
            "properties": {
                "cypher": {"type": "string", "description": "只读 Cypher"},
                "params": {"type": "object", "description": "Cypher 参数"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
            },
            "required": ["cypher"],
        },
    ),
    ToolSpec(
        name="query_catalog",
        description="按书名/作者/朝代检索 CatalogEntry 目录条目。",
        parameters_schema={
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "author": {"type": "string"},
                "dynasty": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
            },
        },
    ),
    ToolSpec(
        name="query_exegesis",
        description="按词目/义项检索训诂条目（ExegesisTerm）。",
        parameters_schema={
            "type": "object",
            "properties": {
                "term": {"type": "string"},
                "sense": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50},
            },
            "required": ["term"],
        },
    ),
]


def build_default_tool_registry() -> ToolRegistry:
    """生成包含 3 个标准工具 spec 的 registry（handler 未绑定）。"""
    registry = ToolRegistry()
    for spec in _DEFAULT_TOOL_SPECS:
        registry.register(spec, handler=None)
    return registry


def render_tool_catalog_for_prompt(registry: ToolRegistry) -> str:
    """把 registry 渲染成给 LLM 的工具目录字符串（function-call 风格）。"""
    lines: List[str] = ["## Available Tools"]
    for spec in registry.list_specs():
        lines.append(f"- {spec.name}: {spec.description}")
    return "\n".join(lines)
