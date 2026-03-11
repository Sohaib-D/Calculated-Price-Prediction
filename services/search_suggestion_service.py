"""
search_suggestion_service.py
AI-assisted search suggestion generation using:
  - previous search trends
  - popular products
  - category relevance
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from collections import Counter, deque
from typing import Any

import requests

logger = logging.getLogger(__name__)

_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_SUGGESTION_MODEL = os.environ.get(
    "SUGGESTION_AI_MODEL",
    os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
)
_SUGGESTION_AI_ENABLED = (
    os.environ.get("SUGGESTION_USE_AI", "true").strip().lower() in {"1", "true", "yes", "on"}
)
_CONNECT_TIMEOUT = float(os.environ.get("SUGGESTION_AI_CONNECT_TIMEOUT_SECONDS", "0.6"))
_READ_TIMEOUT = float(os.environ.get("SUGGESTION_AI_READ_TIMEOUT_SECONDS", "1.2"))

_TREND_HISTORY_MAX = int(os.environ.get("SUGGESTION_TREND_HISTORY_MAX", "1500"))
_TREND_TTL_SECONDS = int(os.environ.get("SUGGESTION_TREND_TTL_SECONDS", "604800"))  # 7 days
_TREND_LOCK = threading.Lock()
_TREND_HISTORY: deque[tuple[float, str]] = deque(maxlen=_TREND_HISTORY_MAX)
_TREND_COUNTS: Counter[str] = Counter()

_CATEGORY_KEYWORDS = {
    "mobile": {
        "iphone",
        "phone",
        "mobile",
        "smartphone",
        "samsung",
        "galaxy",
        "pixel",
        "redmi",
        "redme",
        "realme",
        "infinix",
        "tecno",
        "qmobile",
        "itel",
        "nokia",
        "oneplus",
        "oppo",
        "vivo",
    },
    "laptop": {
        "laptop",
        "notebook",
        "macbook",
        "thinkpad",
        "ideapad",
        "vivobook",
        "inspiron",
        "xps",
        "victus",
        "nitro",
        "rog",
    },
    "tv": {"tv", "smart tv", "television", "oled", "qled", "bravia"},
    "headphone": {"headphone", "headphones", "earbuds", "airpods", "buds"},
    "tablet": {"tablet", "ipad", "tab"},
}

_CATEGORY_SEEDS = {
    "mobile": [
        "iPhone 15",
        "iPhone 14 Pro",
        "Samsung S24",
        "Google Pixel 8",
        "Redmi Note 13 Pro",
        "Realme 9C",
        "Infinix Hot 10 Play",
        "QMobile i6",
        "OnePlus 12",
    ],
    "laptop": [
        "HP Victus Gaming Laptop",
        "ASUS ROG Strix G16",
        "Dell Inspiron 15",
        "Lenovo IdeaPad Slim 5",
        "MacBook Air M3",
    ],
    "tv": [
        "Samsung 55 4K Smart TV",
        "LG OLED TV",
        "TCL QLED 50",
        "Sony Bravia 55",
    ],
    "headphone": [
        "Apple AirPods Pro 2",
        "Samsung Galaxy Buds FE",
        "Sony WH-1000XM5",
        "JBL Tune 770NC",
    ],
    "tablet": [
        "iPad 10th Gen",
        "Samsung Galaxy Tab S9 FE",
        "Xiaomi Pad 6",
    ],
}

_GENERIC_SEEDS = [
    "iPhone 15",
    "Samsung S24",
    "Google Pixel 8",
    "HP Victus Gaming Laptop",
    "ASUS ROG Strix G16",
]

_STOP_WORDS = {
    "official",
    "pta",
    "approved",
    "with",
    "for",
    "the",
    "and",
    "of",
    "new",
    "original",
    "warranty",
    "box",
    "pack",
}

_WORD_CASE_MAP = {
    "iphone": "iPhone",
    "s24": "S24",
    "s23": "S23",
    "s22": "S22",
    "s21": "S21",
    "pixel": "Pixel",
    "qmobile": "QMobile",
    "realme": "Realme",
    "redme": "Redmi",
    "redmi": "Redmi",
    "tv": "TV",
    "oled": "OLED",
    "qled": "QLED",
    "ssd": "SSD",
    "ram": "RAM",
    "ps5": "PS5",
    "xbox": "Xbox",
    "airpods": "AirPods",
    "macbook": "MacBook",
}


def _normalize_text(value: str | None) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _tokens(value: str | None) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9]+", _normalize_text(value)) if token]


def _clean_label(value: str | None) -> str:
    normalized = _normalize_text(value)
    if not normalized:
        return ""

    parts = [token for token in _tokens(normalized) if token not in _STOP_WORDS]
    if not parts:
        parts = _tokens(normalized)

    trimmed = " ".join(parts[:6])
    if not trimmed:
        return ""

    display: list[str] = []
    for token in _tokens(trimmed):
        if token in _WORD_CASE_MAP:
            display.append(_WORD_CASE_MAP[token])
        elif token.isdigit():
            display.append(token)
        else:
            display.append(token.capitalize())
    return " ".join(display)


def _infer_categories(query: str) -> set[str]:
    token_set = set(_tokens(query))
    categories = set()

    for category, keywords in _CATEGORY_KEYWORDS.items():
        if token_set & keywords:
            categories.add(category)

    # Fallback: common single-token cues.
    if "iphone" in token_set or "galaxy" in token_set or "pixel" in token_set:
        categories.add("mobile")

    return categories


def _purge_stale_locked(now_ts: float) -> None:
    cutoff = now_ts - float(_TREND_TTL_SECONDS)
    while _TREND_HISTORY and _TREND_HISTORY[0][0] < cutoff:
        _, old_query = _TREND_HISTORY.popleft()
        _TREND_COUNTS[old_query] -= 1
        if _TREND_COUNTS[old_query] <= 0:
            _TREND_COUNTS.pop(old_query, None)


def track_search_query(query: str) -> None:
    cleaned = _normalize_text(query)
    if not cleaned:
        return

    now_ts = time.time()
    with _TREND_LOCK:
        _purge_stale_locked(now_ts)
        _TREND_HISTORY.append((now_ts, cleaned))
        _TREND_COUNTS[cleaned] += 1


def _trend_candidates(query: str) -> list[tuple[str, float]]:
    query_norm = _normalize_text(query)
    query_tokens = set(_tokens(query_norm))

    with _TREND_LOCK:
        _purge_stale_locked(time.time())
        ranked = _TREND_COUNTS.most_common(80)
        latest_seen: dict[str, int] = {}
        for idx, (_, q) in enumerate(reversed(_TREND_HISTORY)):
            if q not in latest_seen:
                latest_seen[q] = idx

    out: list[tuple[str, float]] = []
    for trend_query, count in ranked:
        trend_tokens = set(_tokens(trend_query))
        if query_tokens:
            overlap = len(query_tokens & trend_tokens)
            if overlap == 0 and query_norm not in trend_query:
                continue
        else:
            overlap = 0

        recency_idx = latest_seen.get(trend_query, 999)
        recency_bonus = max(0.0, 1.0 - (recency_idx / 120.0))
        score = (float(count) * 1.1) + (float(overlap) * 1.8) + recency_bonus
        out.append((trend_query, score))

    return out


def _category_match_score(text: str, categories: set[str]) -> float:
    if not categories:
        return 0.0

    token_set = set(_tokens(text))
    score = 0.0
    for category in categories:
        keywords = _CATEGORY_KEYWORDS.get(category, set())
        if token_set & keywords:
            score += 1.0
    return score


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _product_candidates(query: str, popular_products: list[dict] | None) -> list[tuple[str, float]]:
    items = popular_products or []
    if not items:
        return []

    query_norm = _normalize_text(query)
    query_tokens = set(_tokens(query_norm))
    categories = _infer_categories(query_norm)

    scored: list[tuple[str, float]] = []
    for product in items[:500]:
        raw_name = str(product.get("product") or product.get("name") or "").strip()
        if not raw_name:
            continue
        normalized_name = _normalize_text(raw_name)
        if not normalized_name:
            continue

        name_tokens = set(_tokens(normalized_name))
        overlap = len(query_tokens & name_tokens)
        contains = 1.0 if query_norm and query_norm in normalized_name else 0.0
        category_bonus = _category_match_score(normalized_name, categories)
        rating = min(5.0, max(0.0, _safe_float(product.get("rating"))))
        reviews = max(0.0, _safe_float(product.get("reviews")))
        popularity = (rating * 0.4) + min(2.2, reviews / 120.0)

        if query_tokens:
            if overlap == 0 and contains == 0.0 and category_bonus <= 0:
                continue

        score = (overlap * 2.0) + (contains * 2.2) + category_bonus + popularity
        scored.append((raw_name, score))

    return scored


def _seed_candidates(query: str) -> list[tuple[str, float]]:
    categories = _infer_categories(query)
    out: list[tuple[str, float]] = []
    if categories:
        for category in categories:
            seeds = _CATEGORY_SEEDS.get(category, [])
            for idx, label in enumerate(seeds):
                out.append((label, 4.5 - (idx * 0.18)))
    else:
        for idx, label in enumerate(_GENERIC_SEEDS):
            out.append((label, 2.8 - (idx * 0.1)))
    return out


def _merge_candidates(candidates: list[tuple[str, float]]) -> list[str]:
    bucket: dict[str, tuple[str, float]] = {}
    for raw_label, score in candidates:
        label = _clean_label(raw_label)
        if not label:
            continue
        key = _normalize_text(label)
        prev = bucket.get(key)
        if prev is None or score > prev[1]:
            bucket[key] = (label, score)

    ranked = sorted(bucket.values(), key=lambda row: row[1], reverse=True)
    return [label for label, _ in ranked]


def _extract_json_object(text: str) -> dict | None:
    if not text:
        return None

    payload = text.strip()
    try:
        return json.loads(payload)
    except (json.JSONDecodeError, TypeError):
        pass

    start = payload.find("{")
    end = payload.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None

    try:
        return json.loads(payload[start : end + 1])
    except (json.JSONDecodeError, TypeError):
        return None


def _ai_refine(
    query: str,
    merged_candidates: list[str],
    trend_candidates: list[str],
    limit: int,
) -> list[str] | None:
    if not _SUGGESTION_AI_ENABLED:
        return None

    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        return None

    prompt = (
        "You generate ecommerce search suggestions.\n"
        "Return strict JSON only with key suggestions: {\"suggestions\": [..]}.\n"
        f"User query: {query}\n"
        f"Top trend candidates: {trend_candidates[:12]}\n"
        f"Top product/popularity candidates: {merged_candidates[:20]}\n"
        "Rules:\n"
        "- Keep suggestions concise (2-5 words).\n"
        "- Include both direct and related category suggestions.\n"
        f"- Return at most {limit} suggestions.\n"
        "- No duplicates."
    )

    payload = {
        "model": _SUGGESTION_MODEL,
        "messages": [
            {"role": "system", "content": "You rank search suggestions for shopping queries."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 160,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(
            _GROQ_URL,
            headers=headers,
            json=payload,
            timeout=(max(0.2, _CONNECT_TIMEOUT), max(0.3, _READ_TIMEOUT)),
        )
        response.raise_for_status()
        content = (response.json().get("choices") or [{}])[0].get("message", {}).get("content", "")
        parsed = _extract_json_object(content)
        if not isinstance(parsed, dict):
            return None

        raw_items = parsed.get("suggestions")
        if not isinstance(raw_items, list):
            return None

        cleaned = []
        for item in raw_items:
            label = _clean_label(str(item))
            if label and len(label) <= 60:
                cleaned.append(label)

        if not cleaned:
            return None
        return cleaned[:limit]
    except Exception as exc:
        logger.debug("AI suggestion refinement failed: %s", exc)
        return None


def generate_search_suggestions(
    query: str,
    popular_products: list[dict] | None = None,
    limit: int = 8,
) -> list[str]:
    """
    Generate search suggestions using:
      - previous trend queries
      - popular product list
      - category relevance
      - optional AI re-ranking/refinement
    """
    clean_query = _normalize_text(query)
    limit = max(1, min(12, int(limit or 8)))

    trend_scored = _trend_candidates(clean_query)
    product_scored = _product_candidates(clean_query, popular_products)
    seed_scored = _seed_candidates(clean_query)

    merged = _merge_candidates(trend_scored + product_scored + seed_scored)
    if not merged:
        merged = _merge_candidates(seed_scored) or list(_GENERIC_SEEDS)

    trend_labels = [label for label, _ in sorted(trend_scored, key=lambda row: row[1], reverse=True)]
    ai_ranked = _ai_refine(
        query=clean_query or query,
        merged_candidates=merged,
        trend_candidates=trend_labels,
        limit=limit,
    )

    if ai_ranked:
        # Keep AI order while ensuring candidates remain clean and deduplicated.
        final_bucket: set[str] = set()
        final: list[str] = []
        for item in ai_ranked + merged:
            normalized = _normalize_text(item)
            if not normalized or normalized in final_bucket:
                continue
            final_bucket.add(normalized)
            final.append(item)
            if len(final) >= limit:
                break
        return final

    return merged[:limit]
