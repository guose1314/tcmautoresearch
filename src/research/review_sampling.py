"""Phase H / H-4: Review sampling utilities for QC checks.

Provides deterministic sample selection from review queue items so that batch
review operations can be cross-checked without re-doing every assignment.

Public surface:
* :func:`build_review_sample` — filter + deterministic sampling.
* :func:`compute_review_quality_summary` — derive QC metrics from review
  assignments + dispute archive (in-memory; no DB calls).

Both functions are pure: they take normalized list-of-dict inputs and return
plain Python data structures. This keeps them trivially testable and reusable
from API routes, Pydantic adapters, and unit tests.
"""

from __future__ import annotations

import hashlib
import statistics
from typing import Any, Dict, Iterable, List, Optional, Sequence

__all__ = [
    "build_review_sample",
    "compute_review_quality_summary",
]


def _coerce_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _coerce_lower(value: Any) -> str:
    return _coerce_str(value).lower()


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _filter_match(value: Any, expected: Optional[str]) -> bool:
    if expected is None or expected == "":
        return True
    return _coerce_lower(value) == _coerce_lower(expected)


def _stable_sample_key(item: Dict[str, Any], *, seed: str) -> str:
    """Deterministic per-item rank key.

    Combines a stable item identifier (asset_type/asset_key/id) with the seed
    so that different seeds shuffle the order, but the same seed always
    produces the same selection.
    """

    parts = (
        _coerce_str(item.get("id")),
        _coerce_str(item.get("asset_type")),
        _coerce_str(item.get("asset_key")),
        seed,
    )
    digest_source = "|".join(parts).encode("utf-8")
    return hashlib.sha256(digest_source).hexdigest()


def build_review_sample(
    items: Sequence[Dict[str, Any]],
    *,
    sample_size: int = 10,
    seed: str = "",
    reviewer: Optional[str] = None,
    asset_type: Optional[str] = None,
    review_status: Optional[str] = None,
    priority_bucket: Optional[str] = None,
) -> Dict[str, Any]:
    """Build a deterministic review sample from a list of queue items.

    Filters first by reviewer / asset_type / review_status / priority_bucket
    (any of which may be omitted), then deterministically picks up to
    ``sample_size`` items by ranking on ``sha256(item_key | seed)``. Returns a
    dict with the chosen ``items`` plus diagnostic ``summary`` metadata.
    """

    if sample_size < 0:
        raise ValueError("sample_size must be >= 0")
    normalized_items: List[Dict[str, Any]] = []
    for entry in items or []:
        if isinstance(entry, dict):
            normalized_items.append(dict(entry))

    filtered: List[Dict[str, Any]] = []
    for item in normalized_items:
        # Repository serialisations use `assignee` / `queue_status`; tests and
        # ad-hoc callers may use `reviewer` / `review_status`. Accept both so
        # the same sampler works against live data and synthetic fixtures.
        item_reviewer = item.get("reviewer") or item.get("assignee") or item.get("reviewer_label")
        item_status = item.get("review_status") or item.get("queue_status")
        if reviewer and not _filter_match(item_reviewer, reviewer):
            continue
        if asset_type and not _filter_match(item.get("asset_type"), asset_type):
            continue
        if review_status and not _filter_match(item_status, review_status):
            continue
        if priority_bucket and not _filter_match(item.get("priority_bucket"), priority_bucket):
            continue
        filtered.append(item)

    seed_text = _coerce_str(seed)
    ranked = sorted(filtered, key=lambda item: _stable_sample_key(item, seed=seed_text))
    selected = ranked[:sample_size] if sample_size > 0 else []

    return {
        "supported": True,
        "summary": {
            "input_count": len(normalized_items),
            "filtered_count": len(filtered),
            "sample_size": sample_size,
            "selected_count": len(selected),
            "seed": seed_text,
            "filters": {
                "reviewer": _coerce_str(reviewer) or None,
                "asset_type": _coerce_str(asset_type) or None,
                "review_status": _coerce_str(review_status) or None,
                "priority_bucket": _coerce_str(priority_bucket) or None,
            },
        },
        "items": selected,
    }


def _median_or_zero(values: Iterable[float]) -> float:
    values_list = [v for v in values if v is not None]
    if not values_list:
        return 0.0
    try:
        return float(statistics.median(values_list))
    except statistics.StatisticsError:
        return 0.0


def compute_review_quality_summary(
    *,
    review_assignments: Optional[Sequence[Dict[str, Any]]] = None,
    review_disputes: Optional[Sequence[Dict[str, Any]]] = None,
    reviewer: Optional[str] = None,
    asset_type: Optional[str] = None,
) -> Dict[str, Any]:
    """Compute QC metrics from review assignments + dispute archive.

    Metrics:
    * ``agreement_rate`` — of resolved disputes, fraction whose resolution is
      ``accepted`` (i.e. original review decision upheld).
    * ``overturn_rate`` — fraction whose resolution is ``rejected`` or
      ``needs_source`` (original decision overturned).
    * ``recheck_count`` — number of disputes opened (regardless of status).
    * ``overdue_count`` — count of review_assignments where ``is_overdue`` is
      truthy (post-filter).
    * ``median_backlog_age_hours`` — median ``backlog_age_seconds`` of
      assignments, converted to hours.

    Returns ``{"supported": True, ...}`` always; counters are simply zero when
    there is no data so consumers can render a stable shape.
    """

    assignments = [a for a in (review_assignments or []) if isinstance(a, dict)]
    disputes = [d for d in (review_disputes or []) if isinstance(d, dict)]

    def _matches_assignment(entry: Dict[str, Any]) -> bool:
        if reviewer and not _filter_match(entry.get("reviewer") or entry.get("assignee"), reviewer):
            return False
        if asset_type and not _filter_match(entry.get("asset_type"), asset_type):
            return False
        return True

    def _matches_dispute(entry: Dict[str, Any]) -> bool:
        if reviewer:
            arbitrator = _coerce_lower(entry.get("arbitrator"))
            opened_by = _coerce_lower(entry.get("opened_by"))
            if _coerce_lower(reviewer) not in {arbitrator, opened_by}:
                return False
        if asset_type and not _filter_match(entry.get("asset_type"), asset_type):
            return False
        return True

    filtered_assignments = [a for a in assignments if _matches_assignment(a)]
    filtered_disputes = [d for d in disputes if _matches_dispute(d)]

    overdue_count = sum(1 for a in filtered_assignments if bool(a.get("is_overdue")))
    backlog_seconds = [
        _safe_float(a.get("backlog_age_seconds"), 0.0)
        for a in filtered_assignments
    ]
    median_backlog_seconds = _median_or_zero(backlog_seconds)
    median_backlog_age_hours = round(median_backlog_seconds / 3600.0, 3)

    resolved_disputes = [
        d for d in filtered_disputes
        if _coerce_lower(d.get("dispute_status")) == "resolved"
    ]
    accepted = sum(
        1 for d in resolved_disputes
        if _coerce_lower(d.get("resolution")) == "accepted"
    )
    overturned = sum(
        1 for d in resolved_disputes
        if _coerce_lower(d.get("resolution")) in {"rejected", "needs_source"}
    )
    resolved_total = len(resolved_disputes)
    if resolved_total > 0:
        agreement_rate = round(accepted / resolved_total, 3)
        overturn_rate = round(overturned / resolved_total, 3)
    else:
        agreement_rate = 0.0
        overturn_rate = 0.0

    return {
        "supported": True,
        "filters": {
            "reviewer": _coerce_str(reviewer) or None,
            "asset_type": _coerce_str(asset_type) or None,
        },
        "assignment_count": len(filtered_assignments),
        "dispute_count": len(filtered_disputes),
        "resolved_dispute_count": resolved_total,
        "agreement_rate": agreement_rate,
        "overturn_rate": overturn_rate,
        "recheck_count": len(filtered_disputes),
        "overdue_count": overdue_count,
        "median_backlog_age_hours": median_backlog_age_hours,
    }
