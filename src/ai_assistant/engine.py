# -*- coding: utf-8 -*-
"""AI 助手引擎 — 对话管理与研究辅助核心。"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class AssistantEngine:
    """AI 助手引擎，提供中医科研问答与研究辅助能力。

    Parameters
    ----------
    config : dict | None
        引擎配置，可包含 LLM 参数、知识库路径等。
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config = config or {}
        self._history: List[Dict[str, str]] = []
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
        # TODO: 接入 LLM 推理，当前返回占位回复
        reply = f"[AI 助手] 已收到您的问题：{message}"
        self._history.append({"role": "assistant", "content": reply})
        return reply

    def clear_history(self) -> None:
        """清空对话历史。"""
        self._history.clear()

    @property
    def history(self) -> List[Dict[str, str]]:
        """返回对话历史副本。"""
        return list(self._history)
