"""pytest 根 conftest — Phase F-4 known-failure 白名单支持。"""

from __future__ import annotations


def pytest_addoption(parser):
    """注册 --strict-known-failures 命令行选项。"""
    parser.addoption(
        "--strict-known-failures",
        action="store_true",
        default=False,
        help="把 known_failure xfail 标记变为 strict，用于验证已知失败是否已修复。",
    )


def pytest_collection_modifyitems(config, items):
    """当 --strict-known-failures 开启时，将所有 xfail(reason 含 known_failure)
    的标记覆写为 strict=True，让修复后的测试不再被吞掉。"""
    if not config.getoption("--strict-known-failures", default=False):
        return

    import pytest

    for item in items:
        for marker in item.iter_markers("xfail"):
            reason = marker.kwargs.get("reason", "")
            if "known_failure" in reason:
                # 移除旧标记，加上 strict 版本
                item.own_markers = [
                    m for m in item.own_markers if m.name != "xfail"
                ]
                item.add_marker(
                    pytest.mark.xfail(reason=reason, strict=True)
                )
