"""web_console.console_auth 兼容层 — 规范路径: src.web.ops.console_auth"""
import warnings as _w
_w.warn(
    "web_console.console_auth 已迁移至 src.web.ops.console_auth",
    DeprecationWarning,
    stacklevel=2,
)
from src.web.ops.console_auth import *         # noqa: F401,F403
from src.web.ops.console_auth import ConsoleAuthService, ConsoleUser  # noqa: F401
