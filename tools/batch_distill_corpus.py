"""批量把 data/*.txt 灌入 /api/analysis/distill。

阶段：
    1. 编码治理：探测 .txt 原始编码，发送前转为标准 UTF-8 文本，不覆盖原文件。
  2. 蒸馏推送：登录 8765，逐文件 POST /api/analysis/distill。
     /distill 内部已串联：preprocess → entity 抽取 → semantic graph →
     LLM 蒸馏（按 1400 字切片）→ 双库持久化（KG SQLite + 业务 ORM）。

注意规模：1602 文件 / 358MB / 7B Q8 GPU 推理约 5-15s/片，全量需要数十天。
默认 --max-bytes 80000 只取每文件前 ~80KB（≈57 片，每文件几分钟）。
用 --max-bytes 0 解除上限。--limit-files 控制处理多少个文件。
默认启用按文件大小 / 字符数的分层限流：大文件会自动降低实际发送字符数，
并在文件间增加冷却，优先压缩 read-timeout 面而不是追求单文件一次送尽。
进度写入 logs/batch_distill_progress.jsonl，可断点续跑（--resume，默认开）。
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

import requests

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.ingestion.corpus_encoding_service import CorpusEncodingService

DATA_DIR = REPO_ROOT / "data"
LOG_PATH = REPO_ROOT / "logs" / "batch_distill_progress.jsonl"

_ENCODING_SERVICE: Optional[CorpusEncodingService] = None

_THROTTLE_PROFILES = {
    "conservative": (
        {
            "name": "tiny",
            "max_source_bytes": 12_000,
            "max_source_chars": 4_000,
            "cap_chars": 0,
            "cooldown_s": 0,
        },
        {
            "name": "small",
            "max_source_bytes": 32_000,
            "max_source_chars": 10_000,
            "cap_chars": 8_000,
            "cooldown_s": 1,
        },
        {
            "name": "medium",
            "max_source_bytes": 96_000,
            "max_source_chars": 30_000,
            "cap_chars": 6_000,
            "cooldown_s": 2,
        },
        {
            "name": "large",
            "max_source_bytes": None,
            "max_source_chars": None,
            "cap_chars": 4_000,
            "cooldown_s": 4,
        },
    ),
    "balanced": (
        {
            "name": "tiny",
            "max_source_bytes": 10_000,
            "max_source_chars": 3_500,
            "cap_chars": 0,
            "cooldown_s": 0,
        },
        {
            "name": "small",
            "max_source_bytes": 24_000,
            "max_source_chars": 8_000,
            "cap_chars": 6_000,
            "cooldown_s": 1,
        },
        {
            "name": "medium",
            "max_source_bytes": 72_000,
            "max_source_chars": 24_000,
            "cap_chars": 4_000,
            "cooldown_s": 3,
        },
        {
            "name": "large",
            "max_source_bytes": None,
            "max_source_chars": None,
            "cap_chars": 2_500,
            "cooldown_s": 6,
        },
    ),
    "aggressive": (
        {
            "name": "tiny",
            "max_source_bytes": 8_000,
            "max_source_chars": 3_000,
            "cap_chars": 0,
            "cooldown_s": 0,
        },
        {
            "name": "small",
            "max_source_bytes": 20_000,
            "max_source_chars": 6_000,
            "cap_chars": 5_000,
            "cooldown_s": 2,
        },
        {
            "name": "medium",
            "max_source_bytes": 48_000,
            "max_source_chars": 16_000,
            "cap_chars": 3_000,
            "cooldown_s": 4,
        },
        {
            "name": "large",
            "max_source_bytes": None,
            "max_source_chars": None,
            "cap_chars": 2_000,
            "cooldown_s": 8,
        },
    ),
}


def _get_encoding_service() -> CorpusEncodingService:
    global _ENCODING_SERVICE  # noqa: PLW0603
    if _ENCODING_SERVICE is None:
        _ENCODING_SERVICE = CorpusEncodingService()
    return _ENCODING_SERVICE


def _file_path_key(path: Path) -> str:
    normalized = str(path.resolve()).lower().replace("\\", "/")
    return hashlib.sha256(normalized.encode("utf-8", errors="replace")).hexdigest()


def _resume_keys_for_file(path: Path) -> set[str]:
    return {path.name, _file_path_key(path)}


def detect_and_normalize_utf8(path: Path) -> Dict[str, Any]:
    """探测并标准化为 UTF-8 文本，不覆盖原始语料文件。"""
    standardized = _get_encoding_service().standardize_file(path)
    report = standardized.encoding_report.to_dict()
    converted = report["decoder_encoding"] not in {"utf-8", "empty"} or bool(
        report.get("normalized_newlines")
    )
    return {
        "converted": converted,
        "encoding": report["decoder_encoding"],
        "size": len(standardized.text.encode("utf-8", errors="replace")),
        "encoding_report": report,
        "canonical_document_identity": standardized.canonical_identity.to_dict(),
    }


def login(base_url: str, username: str, password: str, timeout: int = 60) -> str:
    r = requests.post(
        f"{base_url}/api/auth/login",
        json={"username": username, "password": password},
        timeout=timeout,
    )
    r.raise_for_status()
    return r.json()["access_token"]


def _decode_token_exp(token: str) -> Optional[int]:
    try:
        parts = str(token or "").split(".")
        if len(parts) != 3:
            return None
        payload = parts[1]
        payload += "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload).decode("utf-8"))
        exp = data.get("exp")
        if exp is None:
            return None
        return int(float(exp))
    except Exception:
        return None


def _login_token_state(base_url: str, username: str, password: str) -> Dict[str, Any]:
    token = login(base_url, username, password)
    return {
        "access_token": token,
        "expires_at": _decode_token_exp(token),
    }


def _ensure_fresh_token(
    base_url: str,
    token_state: Dict[str, Any],
    username: str,
    password: str,
    refresh_margin_s: int,
) -> str:
    token = str(token_state.get("access_token") or "")
    expires_at = token_state.get("expires_at")
    now = time.time()
    if token and expires_at is not None and float(expires_at) > now + refresh_margin_s:
        return token
    if token and expires_at is None:
        return token
    if not username or not password:
        return token
    refreshed = _login_token_state(base_url, username, password)
    token_state.update(refreshed)
    refreshed_exp = refreshed.get("expires_at")
    if refreshed_exp is None:
        print("  [token] refreshed exp=unknown")
    else:
        remaining = max(0, int(float(refreshed_exp) - now))
        print(f"  [token] refreshed exp_in={remaining // 60}min")
    return str(token_state.get("access_token") or "")


def _compute_read_timeout(
    chars_sent: int,
    base_timeout: int,
    timeout_per_kchar: int,
    timeout_cap: int,
) -> int:
    units = max(1, (max(0, chars_sent) + 999) // 1000)
    effective_cap = max(int(timeout_cap), int(base_timeout))
    dynamic_timeout = max(int(base_timeout), units * int(timeout_per_kchar))
    return min(dynamic_timeout, effective_cap)


def _select_throttle_rule(
    source_bytes: int,
    source_chars: int,
    profile_name: str,
) -> Dict[str, Any]:
    rules = _THROTTLE_PROFILES.get(profile_name, _THROTTLE_PROFILES["balanced"])
    for rule in rules:
        max_source_bytes = rule.get("max_source_bytes")
        max_source_chars = rule.get("max_source_chars")
        bytes_fit = max_source_bytes is None or source_bytes <= int(max_source_bytes)
        chars_fit = max_source_chars is None or source_chars <= int(max_source_chars)
        if bytes_fit and chars_fit:
            return dict(rule)
    return dict(rules[-1])


def _apply_tiered_limit(
    text: str,
    source_bytes: int,
    requested_max_bytes: int,
    throttle_enabled: bool,
    throttle_profile: str,
) -> Dict[str, Any]:
    source_chars = len(text)
    rule = _select_throttle_rule(source_bytes, source_chars, throttle_profile)
    requested_cap = int(requested_max_bytes)
    requested_active = requested_cap > 0
    tier_cap = int(rule.get("cap_chars") or 0) if throttle_enabled else 0

    effective_cap = 0
    limit_reason = "none"
    if requested_active and tier_cap > 0:
        effective_cap = min(requested_cap, tier_cap)
        limit_reason = "tier+requested"
    elif requested_active:
        effective_cap = requested_cap
        limit_reason = "requested"
    elif tier_cap > 0:
        effective_cap = tier_cap
        limit_reason = "tier"

    truncated = False
    sent_text = text
    if effective_cap > 0 and source_chars > effective_cap:
        sent_text = text[:effective_cap]
        truncated = True

    return {
        "profile": throttle_profile,
        "enabled": bool(throttle_enabled),
        "tier": rule.get("name", "tiny"),
        "source_bytes": int(source_bytes),
        "source_chars": int(source_chars),
        "tier_cap_chars": tier_cap,
        "requested_cap_chars": requested_cap if requested_active else 0,
        "effective_cap_chars": effective_cap,
        "chars_sent": len(sent_text),
        "cooldown_s": int(rule.get("cooldown_s") or 0) if throttle_enabled else 0,
        "truncated": truncated,
        "limit_reason": limit_reason,
        "text": sent_text,
    }


def wait_for_server(base_url: str, max_wait: int = 120, interval: int = 5) -> bool:
    """轮询健康检查端点，直到服务器就绪或超时。返回 True 表示就绪。"""
    deadline = time.time() + max_wait
    while time.time() < deadline:
        try:
            r = requests.get(f"{base_url}/health", timeout=5)
            if r.status_code < 500:
                return True
        except Exception:
            pass
        print(f"  [wait] 服务器尚未就绪，{interval}s 后重试...")
        time.sleep(interval)
    return False


def _resolve_retry_after_seconds(
    response: requests.Response, default_seconds: int
) -> int:
    """解析 Retry-After 头；缺失或不可解析时回退默认值。"""
    header_value = str(response.headers.get("Retry-After") or "").strip()
    if header_value.isdigit():
        return max(1, int(header_value))
    return max(1, int(default_seconds))


def load_done_set() -> set[str]:
    if not LOG_PATH.exists():
        return set()
    done: set[str] = set()
    for line in LOG_PATH.read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            rec = json.loads(line)
            if rec.get("ok"):
                for key in ("file", "original_file", "file_path_key"):
                    value = str(rec.get(key) or "").strip()
                    if value:
                        done.add(value)
        except Exception:
            continue
    return done


def append_log(rec: Dict[str, Any]) -> None:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _extract_research_monitoring(body: Dict[str, Any]) -> Dict[str, Any]:
    enhancement = body.get("research_enhancement") or {}
    knowledge = body.get("knowledge_accumulation") or {}
    topics = list(enhancement.get("community_topics") or [])
    bridges = list(enhancement.get("bridge_entities") or [])
    novelty = list(enhancement.get("novelty_candidates") or [])
    signature = enhancement.get("document_signature") or {}
    graph_rag_trace_ids = _extract_graph_rag_trace_ids(body)
    return {
        "document_key": signature.get("document_key"),
        "topic_count": len(topics),
        "bridge_entity_count": len(bridges),
        "novelty_candidate_count": len(novelty),
        "top_topic_labels": [
            item.get("label") for item in topics[:3] if item.get("label")
        ],
        "bridge_entity_names": [
            item.get("name") for item in bridges[:5] if item.get("name")
        ],
        "orm_statistics": knowledge.get("orm_statistics"),
        "orm_analyses": knowledge.get("orm_analyses"),
        "neo4j_nodes": knowledge.get("neo4j_nodes"),
        "neo4j_edges": knowledge.get("neo4j_edges"),
        "graph_rag_trace_id": graph_rag_trace_ids[0] if graph_rag_trace_ids else None,
        "graph_rag_trace_ids": graph_rag_trace_ids,
    }


def _extract_graph_rag_trace_ids(body: Dict[str, Any]) -> list[str]:
    trace_ids: list[str] = []
    candidates = [
        body.get("graph_rag"),
        body.get("graph_rag_context"),
        (body.get("metadata") or {}).get("graph_rag")
        if isinstance(body.get("metadata"), dict)
        else None,
        (body.get("results") or {}).get("graph_rag")
        if isinstance(body.get("results"), dict)
        else None,
        (body.get("analysis_results") or {}).get("graph_rag")
        if isinstance(body.get("analysis_results"), dict)
        else None,
    ]
    for item in candidates:
        if not isinstance(item, dict):
            continue
        for value in (
            item.get("trace_id"),
            (item.get("retrieval_trace") or {}).get("trace_id")
            if isinstance(item.get("retrieval_trace"), dict)
            else None,
        ):
            text = str(value or "").strip()
            if text and text not in trace_ids:
                trace_ids.append(text)
    direct = body.get("graph_rag_trace_id")
    direct_text = str(direct or "").strip()
    if direct_text and direct_text not in trace_ids:
        trace_ids.insert(0, direct_text)
    return trace_ids


def distill_one(
    base_url: str,
    token_state: Dict[str, Any],
    file_path: Path,
    max_bytes: int,
    timeout: int,
    connect_timeout: int = 30,
    timeout_per_kchar: int = 300,
    timeout_cap: int = 7200,
    token_refresh_margin: int = 300,
    throttle_enabled: bool = True,
    throttle_profile: str = "balanced",
    username: str = "",
    password: str = "",
    server_wait: int = 180,
    rate_limit_retries: int = 2,
    rate_limit_backoff: int = 65,
) -> Dict[str, Any]:
    t0 = time.time()
    try:
        standardized = _get_encoding_service().standardize_file(file_path)
    except Exception as exc:
        return {
            "ok": False,
            "status": 0,
            "error": f"encoding-standardization-failed: {exc}",
            "elapsed_s": round(time.time() - t0, 1),
            "encoding_report": None,
        }

    text = standardized.text
    encoding_report = standardized.encoding_report.to_dict()
    canonical_identity = standardized.canonical_identity.to_dict()
    source_file_for_ingest = str(
        canonical_identity.get("source_file") or file_path.name
    )
    throttle = _apply_tiered_limit(
        text,
        source_bytes=int(
            encoding_report.get("source_size_bytes") or file_path.stat().st_size
        ),
        requested_max_bytes=max_bytes,
        throttle_enabled=throttle_enabled,
        throttle_profile=throttle_profile,
    )
    text = str(throttle.pop("text"))
    truncated = bool(throttle.get("truncated"))
    payload = {
        "raw_text": text,
        "source_file": source_file_for_ingest,
        "metadata": {
            "encoding_report": encoding_report,
            "canonical_document_identity": canonical_identity,
        },
    }
    read_timeout = _compute_read_timeout(
        chars_sent=len(text),
        base_timeout=timeout,
        timeout_per_kchar=timeout_per_kchar,
        timeout_cap=timeout_cap,
    )

    def _failure(status: int, error: str) -> Dict[str, Any]:
        return {
            "ok": False,
            "status": status,
            "error": error,
            "elapsed_s": round(time.time() - t0, 1),
            "source_file": source_file_for_ingest,
            "truncated": truncated,
            "chars_sent": len(text),
            "read_timeout_s": read_timeout,
            "throttle": dict(throttle),
            "encoding_report": encoding_report,
            "canonical_document_identity": canonical_identity,
        }

    if not text.strip():
        return _failure(0, "empty-text-after-normalization")

    def _post(tok: str) -> requests.Response:
        return requests.post(
            f"{base_url}/api/analysis/distill",
            json=payload,
            headers={"Authorization": f"Bearer {tok}"},
            timeout=(connect_timeout, read_timeout),
        )

    try:
        token = _ensure_fresh_token(
            base_url,
            token_state,
            username,
            password,
            refresh_margin_s=token_refresh_margin,
        )
    except Exception as exc:
        return _failure(0, f"token-refresh-failed: {exc}")

    try:
        r = _post(token)
    except requests.exceptions.ReadTimeout:
        print(f"  [超时] {file_path.name} 超过 {read_timeout}s，检查服务状态...")
        if wait_for_server(base_url, max_wait=10, interval=2):
            return _failure(0, f"read-timeout({read_timeout}s)")
        print(f"  [超时恢复] 等待服务器恢复 (最多 {server_wait}s)...")
        if not wait_for_server(base_url, max_wait=server_wait):
            return _failure(0, f"read-timeout({read_timeout}s)-server-not-recovered")
        try:
            token = _ensure_fresh_token(
                base_url,
                token_state,
                username,
                password,
                refresh_margin_s=0,
            )
            r = _post(token)
        except requests.exceptions.ReadTimeout:
            return _failure(0, f"read-timeout({read_timeout}s)-retry")
        except Exception as exc:
            return _failure(0, f"timeout-retry-failed: {exc}")
    except requests.exceptions.ConnectionError:
        # 服务器崩溃——等待 watchdog 将其重启
        print(f"  [连接断开] 等待服务器恢复 (最多 {server_wait}s)...")
        if not wait_for_server(base_url, max_wait=server_wait):
            return _failure(0, "server-not-recovered")
        # 重新登录，重试一次
        try:
            token = _ensure_fresh_token(
                base_url,
                token_state,
                username,
                password,
                refresh_margin_s=0,
            )
            r = _post(token)
        except Exception as exc:
            return _failure(0, f"retry-failed: {exc}")

    elapsed = time.time() - t0

    # 令牌过期，尝试重新登录并重试（一次）
    if r.status_code == 401 and username and password:
        try:
            token_state.update(_login_token_state(base_url, username, password))
            new_token = str(token_state.get("access_token") or "")
            t0 = time.time()
            r = _post(new_token)
            elapsed = time.time() - t0
        except Exception:
            pass  # 重登失败，返回原始 401 响应

    if r.status_code == 429:
        retries = max(0, int(rate_limit_retries))
        for attempt in range(1, retries + 1):
            backoff_s = (
                _resolve_retry_after_seconds(r, rate_limit_backoff) + (attempt - 1) * 5
            )
            print(
                f"  [rate-limit] {file_path.name} 命中 429，"
                f"{backoff_s}s 后重试 {attempt}/{retries}..."
            )
            time.sleep(backoff_s)
            try:
                token = _ensure_fresh_token(
                    base_url,
                    token_state,
                    username,
                    password,
                    refresh_margin_s=0,
                )
                r = _post(token)
                elapsed = time.time() - t0
            except Exception as exc:
                return _failure(0, f"rate-limit-retry-failed: {exc}")
            if r.status_code != 429:
                break

    if r.status_code != 200:
        return {
            **_failure(r.status_code, r.text[:500]),
            "elapsed_s": round(elapsed, 1),
        }
    body = r.json()
    return {
        "ok": True,
        "status": 200,
        "elapsed_s": round(elapsed, 1),
        "source_file": source_file_for_ingest,
        "truncated": truncated,
        "chars_sent": len(text),
        "read_timeout_s": read_timeout,
        "throttle": dict(throttle),
        "encoding_report": encoding_report,
        "canonical_document_identity": canonical_identity,
        "llm": body.get("llm_extracted", {}),
        "llm_gateway": body.get("llm_gateway")
        or body.get("llm_extracted", {}).get("llm_gateway", {}),
        "rule": body.get("rule_extracted", {}),
        "merged": body.get("merged", {}),
        "kg": {
            "new_entities": body.get("knowledge_accumulation", {}).get("new_entities"),
            "new_relations": body.get("knowledge_accumulation", {}).get(
                "new_relations"
            ),
            "total_entities": body.get("knowledge_accumulation", {}).get(
                "total_entities"
            ),
            "total_relations": body.get("knowledge_accumulation", {}).get(
                "total_relations"
            ),
            "orm_entities": body.get("knowledge_accumulation", {}).get("orm_entities"),
            "orm_relations": body.get("knowledge_accumulation", {}).get(
                "orm_relations"
            ),
            "orm_statistics": body.get("knowledge_accumulation", {}).get(
                "orm_statistics"
            ),
            "orm_analyses": body.get("knowledge_accumulation", {}).get("orm_analyses"),
            "neo4j_nodes": body.get("knowledge_accumulation", {}).get("neo4j_nodes"),
            "neo4j_edges": body.get("knowledge_accumulation", {}).get("neo4j_edges"),
        },
        "research": _extract_research_monitoring(body),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8765")
    ap.add_argument("--username", default="hgk1988")
    ap.add_argument("--password", default="Hgk1989225")
    ap.add_argument(
        "--limit-files", type=int, default=0, help="最多处理多少个文件 (0=全部)"
    )
    ap.add_argument(
        "--max-bytes", type=int, default=80000, help="单文件取前 N 字符 (0=不截断)"
    )
    ap.add_argument(
        "--skip-larger-than",
        type=int,
        default=2_000_000,
        help="跳过原始字节数超此值的巨型文件 (0=不跳)",
    )
    ap.add_argument(
        "--timeout",
        type=int,
        default=1800,
        help="基础 read timeout（秒）；长文件会在此基础上自动放大",
    )
    ap.add_argument(
        "--connect-timeout", type=int, default=30, help="HTTP 连接超时（秒）"
    )
    ap.add_argument(
        "--timeout-per-kchar",
        type=int,
        default=300,
        help="按发送字符数动态放大 read timeout：每 1000 字至少分配多少秒",
    )
    ap.add_argument(
        "--timeout-cap", type=int, default=7200, help="动态 read timeout 上限（秒）"
    )
    ap.add_argument(
        "--token-refresh-margin",
        type=int,
        default=300,
        help="JWT 剩余有效期低于此值时，在下一个文件前主动刷新（秒）",
    )
    ap.add_argument(
        "--min-request-interval",
        type=float,
        default=1.1,
        help="两次 /api/analysis 请求起始之间的最小间隔秒数；默认 1.1s 以避开 60/min 限流",
    )
    ap.add_argument(
        "--rate-limit-retries", type=int, default=2, help="命中 429 时最多重试多少次"
    )
    ap.add_argument(
        "--rate-limit-backoff",
        type=int,
        default=65,
        help="命中 429 且无 Retry-After 头时的默认退避秒数",
    )
    ap.add_argument(
        "--no-tiered-throttle",
        action="store_true",
        help="关闭按文件大小/字符数的分层限流与自动降 max-bytes",
    )
    ap.add_argument(
        "--throttle-profile",
        choices=["conservative", "balanced", "aggressive"],
        default="balanced",
        help="分层限流档位：越激进，长文件发送越少、冷却越长",
    )
    ap.add_argument("--no-utf8-fix", action="store_true", help="跳过 UTF-8 归一化阶段")
    ap.add_argument("--no-resume", action="store_true", help="忽略历史进度，从头跑")
    ap.add_argument(
        "--start-after-file",
        default="",
        help="仅处理排序后位于该文件名之后的文件；适合暂停后按安全 no-resume 语义继续",
    )
    ap.add_argument(
        "--sort",
        choices=["asc", "desc", "name"],
        default="asc",
        help="按字节数升 / 降 / 文件名排序",
    )
    args = ap.parse_args()

    files = sorted(DATA_DIR.glob("*.txt"), key=lambda p: p.name)
    if args.sort == "asc":
        files.sort(key=lambda p: p.stat().st_size)
    elif args.sort == "desc":
        files.sort(key=lambda p: -p.stat().st_size)

    if args.skip_larger_than > 0:
        files = [p for p in files if p.stat().st_size <= args.skip_larger_than]

    start_after_file = str(args.start_after_file or "").strip()
    if start_after_file:
        matched_index = next(
            (
                index
                for index, path in enumerate(files)
                if path.name == start_after_file
            ),
            None,
        )
        if matched_index is None:
            raise SystemExit(
                f"--start-after-file 未命中当前文件列表: {start_after_file}"
            )
        files = files[matched_index + 1 :]
        print(f"[resume-from] 从 {start_after_file} 之后继续")

    print(f"[scan] 目标文件数={len(files)} (跳过>{args.skip_larger_than}B 的巨型文件)")

    # 阶段 1: 编码扫描与报告预热（不覆盖原始语料）
    if not args.no_utf8_fix:
        needs_normalization = 0
        for i, p in enumerate(files, 1):
            try:
                info = detect_and_normalize_utf8(p)
                if info["converted"]:
                    needs_normalization += 1
                    if needs_normalization <= 20 or needs_normalization % 50 == 0:
                        print(f"[utf8] {i}/{len(files)} {p.name} <- {info['encoding']}")
            except Exception as exc:
                print(f"[utf8-err] {p.name}: {exc}")
        print(f"[utf8] 完成，需请求前标准化 {needs_normalization} 个文件")

    # 阶段 2: 登录 + 蒸馏
    print(f"[login] {args.base_url}")
    token_state = _login_token_state(args.base_url, args.username, args.password)
    print("[login] OK")
    token_exp = token_state.get("expires_at")
    if token_exp is not None:
        remaining = max(0, int(float(token_exp) - time.time()))
        print(
            f"[login] token_ttl={remaining // 60}min refresh_margin={args.token_refresh_margin}s"
        )
    print(
        f"[throttle] enabled={not args.no_tiered_throttle} profile={args.throttle_profile} "
        f"base_max_bytes={args.max_bytes}"
    )

    done = set() if args.no_resume else load_done_set()
    if done:
        print(f"[resume] 已完成 {len(done)} 个，跳过")

    pending = [p for p in files if not (_resume_keys_for_file(p) & done)]
    if args.limit_files > 0:
        pending = pending[: args.limit_files]
    print(f"[plan] 本次处理 {len(pending)} 个文件")

    ok_n = err_n = 0
    t_start = time.time()
    last_request_started_at = 0.0
    for i, p in enumerate(pending, 1):
        min_interval = max(0.0, float(args.min_request_interval))
        if last_request_started_at > 0.0 and min_interval > 0.0:
            elapsed_since_last_request = time.time() - last_request_started_at
            remaining_interval = min_interval - elapsed_since_last_request
            if remaining_interval > 0:
                time.sleep(remaining_interval)
        last_request_started_at = time.time()
        try:
            res = distill_one(
                args.base_url,
                token_state,
                p,
                args.max_bytes,
                args.timeout,
                connect_timeout=args.connect_timeout,
                timeout_per_kchar=args.timeout_per_kchar,
                timeout_cap=args.timeout_cap,
                token_refresh_margin=args.token_refresh_margin,
                throttle_enabled=not args.no_tiered_throttle,
                throttle_profile=args.throttle_profile,
                username=args.username,
                password=args.password,
                server_wait=300,
                rate_limit_retries=args.rate_limit_retries,
                rate_limit_backoff=args.rate_limit_backoff,
            )
        except Exception as exc:
            res = {
                "ok": False,
                "status": 0,
                "error": f"{type(exc).__name__}: {exc}",
                "encoding_report": None,
            }
        display_file = str(res.get("source_file") or p.name)
        rec = {
            "file": display_file,
            "file_path_key": _file_path_key(p),
            "size": p.stat().st_size,
            **res,
        }
        append_log(rec)
        if res.get("ok"):
            ok_n += 1
            kg = res.get("kg", {})
            research = res.get("research", {})
            throttle = res.get("throttle", {})
            print(
                f"[{i}/{len(pending)}] OK {display_file} "
                f"({res['chars_sent']}字, {res['elapsed_s']}s) "
                f"tier={throttle.get('tier', 'n/a')} cap={throttle.get('effective_cap_chars', 0)} rt={res.get('read_timeout_s', 0)}s "
                f"llm={res['llm']} rule={res['rule']} "
                f"kg_total={kg.get('total_entities')}/{kg.get('total_relations')} "
                f"orm={kg.get('orm_entities')}/{kg.get('orm_relations')} "
                f"topics={research.get('topic_count', 0)} bridges={research.get('bridge_entity_count', 0)} "
                f"analyses={research.get('orm_analyses', 0)} neo4j={research.get('neo4j_nodes', 0)}/{research.get('neo4j_edges', 0)}"
            )
        else:
            err_n += 1
            throttle = res.get("throttle", {})
            print(
                f"[{i}/{len(pending)}] FAIL {display_file} "
                f"tier={throttle.get('tier', 'n/a')} cap={throttle.get('effective_cap_chars', 0)} rt={res.get('read_timeout_s', 0)}s "
                f"status={res.get('status')} {str(res.get('error'))[:200]}"
            )

        cooldown_s = int((res.get("throttle") or {}).get("cooldown_s") or 0)
        if cooldown_s > 0 and i < len(pending):
            print(
                f"  [cooldown] tier={res.get('throttle', {}).get('tier', 'n/a')} sleep={cooldown_s}s"
            )
            time.sleep(cooldown_s)

        # 阶段性总结
        if i % 10 == 0:
            elapsed = time.time() - t_start
            rate = i / elapsed if elapsed else 0
            eta = (len(pending) - i) / rate if rate else 0
            print(
                f"  [stat] ok={ok_n} err={err_n} rate={rate:.2f} f/s eta={eta / 60:.1f}min"
            )

    print(
        f"[done] ok={ok_n} err={err_n} total_time={(time.time() - t_start) / 60:.1f}min"
    )
    return 0 if err_n == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
