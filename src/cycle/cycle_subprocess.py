"""subprocess.run 安全包装器——限定作用域的 encoding/retry 补丁。"""

import subprocess
from contextlib import contextmanager
from typing import Any

_ORIGINAL_RUN = subprocess.run


def _safe_run(*args: Any, **kwargs: Any) -> "subprocess.CompletedProcess[str]":
    """Normalize subprocess text capture outputs (encoding + stdout/stderr retry)."""
    capture_requested = bool(kwargs.get("capture_output")) or kwargs.get("stdout") == subprocess.PIPE
    text_requested = bool(kwargs.get("text")) or bool(kwargs.get("universal_newlines"))
    normalized_kwargs = dict(kwargs)
    if text_requested:
        normalized_kwargs.setdefault("encoding", "utf-8")
        normalized_kwargs.setdefault("errors", "replace")

    completed = _ORIGINAL_RUN(*args, **normalized_kwargs)
    if capture_requested and text_requested and (completed.stdout is None or completed.stderr is None):
        retry_kwargs = dict(normalized_kwargs)
        retry_kwargs.pop("capture_output", None)
        retry_kwargs["stdout"] = subprocess.PIPE
        retry_kwargs["stderr"] = subprocess.PIPE
        retried = _ORIGINAL_RUN(*args, **retry_kwargs)
        return subprocess.CompletedProcess(retried.args, retried.returncode, retried.stdout or "", retried.stderr or "")
    return completed


@contextmanager
def safe_subprocess_run():
    """在 with 块内将 subprocess.run 替换为带 encoding/retry 的安全版本。"""
    original = subprocess.run
    subprocess.run = _safe_run  # type: ignore[assignment]
    try:
        yield
    finally:
        subprocess.run = original  # type: ignore[assignment]
