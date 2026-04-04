"""web_console.job_store 兼容层 — 规范路径: src.web.ops.job_store"""
import warnings as _w
_w.warn(
    "web_console.job_store 已迁移至 src.web.ops.job_store",
    DeprecationWarning,
    stacklevel=2,
)
from src.web.ops.job_store import *            # noqa: F401,F403
from src.web.ops.job_store import PersistentJobStore, SAFE_JOB_ID_PATTERN  # noqa: F401
