"""将 web_console 模块文件替换为从 src.web.ops 重导出的兼容层。"""

import pathlib

shims = {
    "web_console/job_store.py": '''\
"""web_console.job_store 兼容层 — 规范路径: src.web.ops.job_store"""
import warnings as _w
_w.warn(
    "web_console.job_store 已迁移至 src.web.ops.job_store",
    DeprecationWarning,
    stacklevel=2,
)
from src.web.ops.job_store import *            # noqa: F401,F403
from src.web.ops.job_store import PersistentJobStore, SAFE_JOB_ID_PATTERN  # noqa: F401
''',
    "web_console/console_auth.py": '''\
"""web_console.console_auth 兼容层 — 规范路径: src.web.ops.console_auth"""
import warnings as _w
_w.warn(
    "web_console.console_auth 已迁移至 src.web.ops.console_auth",
    DeprecationWarning,
    stacklevel=2,
)
from src.web.ops.console_auth import *         # noqa: F401,F403
from src.web.ops.console_auth import ConsoleAuthService, ConsoleUser  # noqa: F401
''',
    "web_console/job_manager.py": '''\
"""web_console.job_manager 兼容层 — 规范路径: src.web.ops.job_manager"""
import warnings as _w
_w.warn(
    "web_console.job_manager 已迁移至 src.web.ops.job_manager",
    DeprecationWarning,
    stacklevel=2,
)
from src.web.ops.job_manager import *          # noqa: F401,F403
from src.web.ops.job_manager import ResearchJobManager, format_sse  # noqa: F401
''',
}

for path, content in shims.items():
    p = pathlib.Path(path)
    p.write_text(content, encoding="utf-8")
    print(f"  wrote shim: {path} ({len(content)} bytes)")

print("Done.")
