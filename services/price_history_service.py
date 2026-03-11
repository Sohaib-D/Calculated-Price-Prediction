"""
price_history_service.py
────────────────────────
Lightweight in-memory price history tracker.
Records timestamped price snapshots per query and provides
trend analysis (rising / falling / stable) for the intelligence engine.

No external DB required — data lives in-process and auto-expires.
"""
from __future__ import annotations

import statistics
import threading
import time
from collections import defaultdict, deque
from typing import Any

_MAX_ENTRIES_PER_QUERY = 50
_EXPIRY_SECONDS = 86_400  # 24 hours

_history: dict[str, deque[dict]] = defaultdict(lambda: deque(maxlen=_MAX_ENTRIES_PER_QUERY))
_lock = threading.Lock()


def record_prices(query: str, prices: list[float]) -> None:
    """
    Store a timestamped snapshot of prices observed for *query*.
    Called after every optimization run so future queries have trend data.
    """
    if not query or not prices:
        return

    key = query.strip().lower()
    snapshot = {
        "ts": time.time(),
        "min": min(prices),
        "max": max(prices),
        "mean": statistics.mean(prices),
        "median": statistics.median(prices),
        "count": len(prices),
    }

    with _lock:
        _history[key].append(snapshot)


def _purge_stale(entries: deque[dict]) -> None:
    """Remove entries older than _EXPIRY_SECONDS."""
    cutoff = time.time() - _EXPIRY_SECONDS
    while entries and entries[0]["ts"] < cutoff:
        entries.popleft()


def get_trend(query: str) -> dict[str, Any]:
    """
    Analyse recent price history and return a trend report.

    Returns
    -------
    dict with keys:
        direction   : "rising" | "falling" | "stable" | "unknown"
        confidence  : float 0-1
        data_points : int — number of snapshots analysed
        avg_price   : float | None
        price_range : dict | None  — {min, max}
    """
    key = query.strip().lower()

    with _lock:
        entries = _history.get(key)
        if not entries:
            return {"direction": "unknown", "confidence": 0.0, "data_points": 0,
                    "avg_price": None, "price_range": None}
        _purge_stale(entries)
        snapshots = list(entries)

    if len(snapshots) < 2:
        snap = snapshots[0] if snapshots else None
        return {
            "direction": "unknown",
            "confidence": 0.0,
            "data_points": len(snapshots),
            "avg_price": snap["mean"] if snap else None,
            "price_range": {"min": snap["min"], "max": snap["max"]} if snap else None,
        }

    # Simple linear regression on mean prices
    means = [s["mean"] for s in snapshots]
    n = len(means)
    x_vals = list(range(n))
    x_mean = statistics.mean(x_vals)
    y_mean = statistics.mean(means)

    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_vals, means))
    denominator = sum((x - x_mean) ** 2 for x in x_vals)

    if denominator == 0:
        slope = 0.0
    else:
        slope = numerator / denominator

    # Normalise slope relative to average price
    relative_slope = slope / y_mean if y_mean else 0.0

    if relative_slope > 0.02:
        direction = "rising"
    elif relative_slope < -0.02:
        direction = "falling"
    else:
        direction = "stable"

    # Confidence based on data points and consistency
    confidence = min(1.0, len(snapshots) / 10) * min(1.0, abs(relative_slope) * 20)
    confidence = round(max(0.1, min(1.0, confidence + 0.3)), 2)

    all_mins = [s["min"] for s in snapshots]
    all_maxs = [s["max"] for s in snapshots]

    return {
        "direction": direction,
        "confidence": confidence,
        "data_points": len(snapshots),
        "avg_price": round(y_mean, 2),
        "price_range": {"min": round(min(all_mins), 2), "max": round(max(all_maxs), 2)},
    }
