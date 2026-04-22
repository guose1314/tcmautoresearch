"""端到端冒烟测试：模拟浏览器登录 → 创建任务 → 执行阶段 → AI 对话 → 图谱加载。

使用真实 HTTP 端点，覆盖 dashboard 前端实际调用的 API。
"""
from __future__ import annotations

import json
import sys
import time
from typing import Any, Dict

import requests

BASE = "http://127.0.0.1:8765"
USERNAME = "hgk1988"
PASSWORD = "Hgk1989225"


def step(title: str) -> None:
    print(f"\n=== {title} ===", flush=True)


def must(ok: bool, msg: str) -> None:
    if not ok:
        print(f"FAIL: {msg}", flush=True)
        sys.exit(1)
    print(f"  OK: {msg}", flush=True)


def main() -> None:
    s = requests.Session()

    step("登录 /api/auth/login")
    r = s.post(
        f"{BASE}/api/auth/login",
        json={"username": USERNAME, "password": PASSWORD},
        timeout=15,
    )
    must(r.status_code == 200, f"login status={r.status_code} body={r.text[:200]}")
    payload: Dict[str, Any] = r.json()
    token = payload.get("access_token") or payload.get("token") or ""
    must(bool(token), f"token present (keys={list(payload)})")
    s.headers["Authorization"] = f"Bearer {token}"

    step("auth/status")
    r = s.get(f"{BASE}/api/auth/status", timeout=10)
    must(r.status_code == 200, f"status={r.status_code}")
    print(f"  payload={r.json()}", flush=True)

    step("HTMX 片段视觉冒烟（projects/tools/output）")
    for path in ("/api/projects", "/api/analysis/tools", "/api/output"):
        r = s.get(f"{BASE}{path}", timeout=20)
        must(r.status_code == 200, f"GET {path} -> {r.status_code}")
        text = r.text
        must("shell-card" in text or "shell-card-soft" in text,
             f"{path} 包含新外壳类")
        must("bg-white rounded-xl border border-gray-100" not in text,
             f"{path} 不再使用旧白底卡片")

    step("创建研究课题 /api/research/create")
    cycle_name = f"smoke-{int(time.time())}"
    r = s.post(
        f"{BASE}/api/research/create",
        json={
            "cycle_name": cycle_name,
            "description": "联调冒烟",
            "objective": "验证端到端真实 API 链路",
            "scope": "minimum",
            "researchers": ["smoke"],
        },
        timeout=30,
    )
    must(r.status_code in (200, 201), f"create status={r.status_code} body={r.text[:300]}")
    cycle = r.json().get("cycle") or {}
    cycle_id = str(cycle.get("cycle_id") or cycle.get("id") or "")
    must(bool(cycle_id), f"cycle_id present (cycle keys={list(cycle)})")
    print(f"  cycle_id={cycle_id}", flush=True)

    step("执行 observe 阶段 /api/research/{id}/execute")
    r = s.post(
        f"{BASE}/api/research/{cycle_id}/execute",
        json={"phase": "observe", "phase_context": {"raw_text": "桂枝汤主治太阳中风。"}},
        timeout=180,
    )
    print(f"  status={r.status_code}", flush=True)
    if r.status_code != 200:
        print(f"  body[:400]={r.text[:400]}", flush=True)
    # 阶段执行可能因依赖缺失失败，但接口必须可达且非 401/404
    must(r.status_code not in (401, 404), "execute 端点可达且通过鉴权")

    step("AI 对话 /api/assistant/chat")
    r = s.post(
        f"{BASE}/api/assistant/chat",
        json={"message": "你好，请简述桂枝汤。", "session_id": "smoke"},
        timeout=60,
    )
    must(r.status_code == 200, f"chat status={r.status_code} body={r.text[:200]}")
    reply = (r.json() or {}).get("reply", "")
    must(isinstance(reply, str) and reply != "", f"chat reply non-empty (len={len(reply)})")
    print(f"  reply[:80]={reply[:80]!r}", flush=True)

    step("图谱统计 /api/analysis/kg/stats")
    r = s.get(f"{BASE}/api/analysis/kg/stats", timeout=20)
    must(r.status_code == 200, f"kg/stats status={r.status_code}")
    stats = r.json()
    print(f"  keys={list(stats)[:8]}", flush=True)

    step("图谱子图 /api/analysis/kg/subgraph")
    r = s.get(
        f"{BASE}/api/analysis/kg/subgraph",
        params={"graph_type": "herb_relations", "limit": 30},
        timeout=30,
    )
    must(r.status_code == 200, f"kg/subgraph status={r.status_code} body={r.text[:200]}")
    sub = r.json()
    print(f"  keys={list(sub)[:6]}", flush=True)

    step("当前课题图谱 /api/analysis/graph/{id}")
    r = s.get(f"{BASE}/api/analysis/graph/{cycle_id}", timeout=30)
    print(f"  status={r.status_code}", flush=True)
    must(r.status_code in (200, 404), "graph/{id} 端点可达")

    print("\nALL CHECKS PASSED", flush=True)


if __name__ == "__main__":
    main()
