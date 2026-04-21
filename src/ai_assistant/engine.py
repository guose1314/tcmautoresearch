# -*- coding: utf-8 -*-
"""AI 助手引擎 — 对话管理与研究辅助核心。

.. deprecated::
    此模块为向后兼容保留。新代码请使用
    ``from src.ai_assistant.assistant_service import AssistantService``。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class _SimpleAssistantEngine:
    """原始占位实现（无 LLM 调用），仅用于向后兼容。"""

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config = config or {}
        self._history: List[Dict[str, str]] = []

    def chat(self, message: str, *, context: Optional[Dict[str, Any]] = None) -> str:
        self._history.append({"role": "user", "content": message})
        reply = f"[AI 助手] 已收到您的问题：{message}"
        self._history.append({"role": "assistant", "content": reply})
        return reply

    def clear_history(self) -> None:
        self._history.clear()

    @property
    def history(self) -> List[Dict[str, str]]:
        return list(self._history)


class AssistantEngine:
    """AI 助手引擎，委托给 AssistantService（如果可用）。

    向后兼容：``chat()`` 仍返回 ``str``，内部使用 ``AssistantService`` 生成回复。

    Parameters
    ----------
    config : dict | None
        引擎配置，可包含 LLM 参数、知识库路径等。
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config = config or {}
        self._history: List[Dict[str, str]] = []
        self._delegate: Optional[Any] = None

        # 尝试加载完整的 AssistantService
        try:
            from src.ai_assistant.assistant_service import AssistantService
            self._delegate = AssistantService()
            logger.info("AssistantEngine 已委托给 AssistantService")
        except Exception as exc:
            logger.info("AssistantEngine 降级为占位模式: %s", exc)

        logger.info("AssistantEngine 初始化完成")

    def chat(self, message: str, *, context: Optional[Dict[str, Any]] = None) -> str:
        """处理用户消息并返回回复。

        Parameters
        ----------
        message : str
            用户输入。
        context : dict | None
            附加上下文（当前研究项目、选中实体等）。

        Returns
        -------
        str
            助手回复文本。
        """
        self._history.append({"role": "user", "content": message})

        if self._delegate is not None:
            try:
                result = self._delegate.chat(message, context=context or {})
                reply = result.get("reply", "") if isinstance(result, dict) else str(result)
            except Exception as exc:
                logger.warning("AssistantService 调用失败，降级: %s", exc)
                reply = f"[AI 助手] 已收到您的问题：{message}"
        else:
            reply = f"[AI 助手] 已收到您的问题：{message}"

        self._history.append({"role": "assistant", "content": reply})
        return reply

    def clear_history(self) -> None:
        """清空对话历史。"""
        self._history.clear()
        if self._delegate is not None:
            try:
                self._delegate.clear_history()
            except Exception:
                pass

    @property
    def history(self) -> List[Dict[str, str]]:
        """返回对话历史副本。"""
        return list(self._history)
