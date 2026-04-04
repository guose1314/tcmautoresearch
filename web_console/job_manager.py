"""web_console.job_manager 兼容层 — 规范路径: src.web.ops.job_manager"""
import warnings as _w
_w.warn(
    "web_console.job_manager 已迁移至 src.web.ops.job_manager",
    DeprecationWarning,
    stacklevel=2,
)
from src.web.ops.job_manager import *          # noqa: F401,F403
from src.web.ops.job_manager import ResearchJobManager, format_sse  # noqa: F401
