"""
comparison_service.py
AI-assisted product comparison for two user-provided products.
"""
from __future__ import annotations

import json
import math
import os
import re
import statistics
import threading
import time
from difflib import SequenceMatcher
from typing import Any

import requests

from scrapers import fetch_category

_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_AI_MODEL = os.environ.get(
    "COMPARISON_AI_MODEL",
    os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
)
_USE_AI = os.environ.get("COMPARISON_USE_AI", "true").strip().lower() in {"1", "true", "yes", "on"}
_AI_CONNECT_TIMEOUT = float(os.environ.get("COMPARISON_AI_CONNECT_TIMEOUT_SECONDS", "0.8"))
_AI_READ_TIMEOUT = float(os.environ.get("COMPARISON_AI_READ_TIMEOUT_SECONDS", "1.8"))
_CACHE_TTL_SECONDS = int(os.environ.get("COMPARISON_CACHE_TTL_SECONDS", "300"))
_CACHE_MAX_ENTRIES = int(os.environ.get("COMPARISON_CACHE_MAX_ENTRIES", "200"))

_PRODUCT_CACHE: dict[str, tuple[float, list[dict]]] = {}
_CACHE_LOCK = threading.Lock()


def _normalize_text(value: str | None) -> str:
    text = (value or "").strip().lower()
    text = re.sub(r"[^\w\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _tokenize(value: str | None) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", _normalize_text(value)) if t]


def _extract_price(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if number > 0 else None
    text = str(value).replace(",", "")
    match = re.search(r"\d+(?:\.\d+)?", text)
    if not match:
        return None
    number = float(match.group())
    return number if number > 0 else None


def _cache_get(query: str) -> list[dict] | None:
    now = time.time()
    with _CACHE_LOCK:
        cached = _PRODUCT_CACHE.get(query)
        if not cached:
            return None
        expires_at, value = cached
        if expires_at < now:
            _PRODUCT_CACHE.pop(query, None)
            return None
        return list(value)


def _cache_set(query: str, products: list[dict]) -> None:
    with _CACHE_LOCK:
        if len(_PRODUCT_CACHE) >= _CACHE_MAX_ENTRIES:
            oldest_key = min(_PRODUCT_CACHE, key=lambda k: _PRODUCT_CACHE[k][0])
            _PRODUCT_CACHE.pop(oldest_key, None)
        _PRODUCT_CACHE[query] = (time.time() + _CACHE_TTL_SECONDS, list(products))


def _product_name_score(query: str, product_name: str) -> float:
    q_norm = _normalize_text(query)
    p_norm = _normalize_text(product_name)
    if not q_norm or not p_norm:
        return 0.0

    q_tokens = set(_tokenize(q_norm))
    p_tokens = set(_tokenize(p_norm))
    if not q_tokens or not p_tokens:
        return 0.0

    overlap = len(q_tokens & p_tokens) / len(q_tokens)
    jaccard = len(q_tokens & p_tokens) / len(q_tokens | p_tokens)
    sequence = SequenceMatcher(None, q_norm, p_norm).ratio()

    contains_bonus = 0.12 if q_norm in p_norm else 0.0
    return min(1.0, (overlap * 0.45) + (jaccard * 0.2) + (sequence * 0.35) + contains_bonus)


def _retrieve_products(query: str) -> list[dict]:
    query_key = _normalize_text(query)
    cached = _cache_get(query_key)
    if cached is not None:
        return cached

    products = fetch_category("electronics", 1, query=query_key, verbose=False) or []
    if not products:
        # Fallback to general electronics pool if strict query returns empty.
        products = fetch_category("electronics", 1, query=None, verbose=False) or []

    _cache_set(query_key, products)
    return products


def _extract_specs(text: str) -> dict[str, Any]:
    normalized = _normalize_text(text)

    ram_match = re.search(r"(\d{1,3})\s*gb\s*ram", normalized)
    ram_gb = int(ram_match.group(1)) if ram_match else None

    storage_gb = None
    for number_text, unit in re.findall(r"(\d{2,4})\s*(gb|tb)", normalized):
        number = int(number_text)
        size = number * 1024 if unit == "tb" else number
        if size < 16 or size > 8192:
            continue
        if ram_gb is not None and size == ram_gb:
            continue
        if storage_gb is None or size > storage_gb:
            storage_gb = size

    battery_match = re.search(r"(\d{3,5})\s*mah", normalized)
    battery_mah = int(battery_match.group(1)) if battery_match else None

    camera_matches = [int(m) for m in re.findall(r"(\d{1,3})\s*mp", normalized)]
    camera_mp = max(camera_matches) if camera_matches else None

    cpu_tier = 0
    perf_keywords = []

    patterns = [
        (r"\bi9\b|\bryzen\s*9\b|\bm3\s*pro\b|\brtx\s*40", 3, "high-end chipset/gpu"),
        (r"\bi7\b|\bryzen\s*7\b|\bm3\b|\brtx\s*30", 2, "upper-mid chipset/gpu"),
        (r"\bi5\b|\bryzen\s*5\b|\bsnapdragon\s*8\b", 1, "mid-tier chipset"),
    ]
    for pattern, tier, label in patterns:
        if re.search(pattern, normalized):
            cpu_tier = max(cpu_tier, tier)
            perf_keywords.append(label)

    if re.search(r"\b(gaming|ultra|pro|max)\b", normalized):
        perf_keywords.append("performance variant")

    return {
        "ram_gb": ram_gb,
        "storage_gb": storage_gb,
        "battery_mah": battery_mah,
        "camera_mp": camera_mp,
        "cpu_tier": cpu_tier,
        "perf_keywords": perf_keywords,
    }


def _performance_score(specs: dict[str, Any], text: str) -> float:
    score = 3.5
    if specs.get("ram_gb"):
        score += min(3.0, float(specs["ram_gb"]) / 4.0)
    if specs.get("storage_gb"):
        score += min(1.5, float(specs["storage_gb"]) / 256.0)
    score += float(specs.get("cpu_tier") or 0) * 1.6
    if re.search(r"\b(gaming|pro|max|ultra)\b", _normalize_text(text)):
        score += 1.0
    return min(10.0, score)


def _battery_score(specs: dict[str, Any]) -> float:
    battery = specs.get("battery_mah")
    if not battery:
        return 5.0
    return max(2.0, min(10.0, 2.0 + ((float(battery) - 2500.0) / 450.0)))


def _camera_score(specs: dict[str, Any], rating: float | None) -> float:
    score = 5.0
    camera = specs.get("camera_mp")
    if camera:
        score += min(3.0, float(camera) / 50.0)
    if rating:
        score += min(2.0, max(0.0, (rating - 3.5) * 1.1))
    return min(10.0, score)


def _value_score(price: float | None, performance: float, battery: float, camera: float, rating: float | None) -> float:
    if price is None or price <= 0:
        return 0.0
    quality = (performance * 0.45) + (battery * 0.2) + (camera * 0.2) + ((rating or 0.0) * 0.15)
    return quality / max(1.0, math.log10(price))


def _summarize_query_product(query: str) -> dict[str, Any]:
    pool = _retrieve_products(query)
    scored = []

    for product in pool:
        name = str(product.get("product") or "").strip()
        score = _product_name_score(query, name)
        if score > 0.28:
            scored.append((score, product))

    scored.sort(key=lambda item: item[0], reverse=True)
    top = [product for _, product in scored[:25]]

    if not top:
        top = [{"product": query, "price": None, "rating": None, "reviews": None, "source_store": None}]

    prices = [price for price in (_extract_price(item.get("price")) for item in top) if price is not None]
    ratings = [float(item.get("rating")) for item in top if item.get("rating") is not None]
    reviews = [float(item.get("reviews")) for item in top if item.get("reviews") is not None]

    best_name = str(top[0].get("product") or query)
    specs_text = " | ".join([query] + [str(item.get("product") or "") for item in top[:6]])
    specs = _extract_specs(specs_text)

    avg_price = round(statistics.mean(prices), 2) if prices else None
    min_price = round(min(prices), 2) if prices else None
    max_price = round(max(prices), 2) if prices else None
    avg_rating = round(statistics.mean(ratings), 2) if ratings else None
    total_reviews = int(sum(reviews)) if reviews else 0
    store_count = len({str(item.get("source_store") or "").strip().lower() for item in top if item.get("source_store")})

    perf = _performance_score(specs, specs_text)
    batt = _battery_score(specs)
    cam = _camera_score(specs, avg_rating)
    val = _value_score(avg_price, perf, batt, cam, avg_rating)

    return {
        "query": query,
        "best_name": best_name,
        "avg_price": avg_price,
        "min_price": min_price,
        "max_price": max_price,
        "avg_rating": avg_rating,
        "total_reviews": total_reviews,
        "store_count": store_count,
        "specs": specs,
        "scores": {
            "performance": round(perf, 2),
            "battery": round(batt, 2),
            "camera": round(cam, 2),
            "price_value": round(val, 4),
        },
    }


def _winner_text(label: str, a_name: str, b_name: str, a_val: float, b_val: float, high_is_better: bool = True) -> str:
    if a_val is None or b_val is None:
        return "Insufficient comparable data."

    delta = (a_val - b_val) if high_is_better else (b_val - a_val)
    if abs(delta) < (0.08 * max(abs(a_val), abs(b_val), 1.0)):
        return "Both are close on this metric."

    if delta > 0:
        return f"{a_name} has the edge on this metric."
    return f"{b_name} has the edge on this metric."


def _deterministic_comparison(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    a_name = a["best_name"]
    b_name = b["best_name"]

    a_scores = a["scores"]
    b_scores = b["scores"]

    comparison = {
        "performance": _winner_text(
            "performance",
            a_name,
            b_name,
            a_scores["performance"],
            b_scores["performance"],
            True,
        ),
        "battery": _winner_text(
            "battery",
            a_name,
            b_name,
            a_scores["battery"],
            b_scores["battery"],
            True,
        ),
        "camera": _winner_text(
            "camera",
            a_name,
            b_name,
            a_scores["camera"],
            b_scores["camera"],
            True,
        ),
        "price_value": _winner_text(
            "price_value",
            a_name,
            b_name,
            a_scores["price_value"],
            b_scores["price_value"],
            True,
        ),
    }

    points_a = 0
    points_b = 0
    for message in comparison.values():
        if message.startswith(a_name):
            points_a += 1
        elif message.startswith(b_name):
            points_b += 1

    if points_a > points_b:
        winner = a_name
    elif points_b > points_a:
        winner = b_name
    else:
        winner = "tie"

    summary = (
        f"{a_name} vs {b_name}: "
        f"performance {a_scores['performance']:.1f}/{b_scores['performance']:.1f}, "
        f"battery {a_scores['battery']:.1f}/{b_scores['battery']:.1f}, "
        f"camera {a_scores['camera']:.1f}/{b_scores['camera']:.1f}. "
        f"Best value: {'balanced' if winner == 'tie' else winner}."
    )

    return {
        "winner": winner,
        "comparison": comparison,
        "ai_summary": summary,
    }


def _ai_compare(a: dict[str, Any], b: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    if not _USE_AI:
        return fallback

    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        return fallback

    prompt = (
        "Compare product A and product B and return strict JSON only with keys:\n"
        "{winner, comparison:{performance,battery,camera,price_value}, ai_summary}\n"
        "Use concise neutral text. Winner must be one of: product_a, product_b, tie.\n\n"
        f"Product A: {json.dumps(a, ensure_ascii=False)}\n"
        f"Product B: {json.dumps(b, ensure_ascii=False)}\n"
        f"Fallback draft: {json.dumps(fallback, ensure_ascii=False)}"
    )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": _AI_MODEL,
        "messages": [
            {"role": "system", "content": "You are a strict product comparison assistant."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 260,
        "response_format": {"type": "json_object"},
    }

    try:
        response = requests.post(
            _GROQ_URL,
            headers=headers,
            json=payload,
            timeout=(max(0.2, _AI_CONNECT_TIMEOUT), max(0.3, _AI_READ_TIMEOUT)),
        )
        response.raise_for_status()
        raw = (response.json().get("choices") or [{}])[0].get("message", {}).get("content", "")
        parsed = json.loads(raw)

        comparison = parsed.get("comparison") if isinstance(parsed, dict) else None
        if not isinstance(comparison, dict):
            return fallback

        winner_map = {
            "product_a": a["best_name"],
            "product_b": b["best_name"],
            "tie": "tie",
        }
        winner_key = str(parsed.get("winner", "")).strip().lower()
        winner = winner_map.get(winner_key, fallback["winner"])

        result = {
            "winner": winner,
            "comparison": {
                "performance": str(comparison.get("performance") or fallback["comparison"]["performance"]),
                "battery": str(comparison.get("battery") or fallback["comparison"]["battery"]),
                "camera": str(comparison.get("camera") or fallback["comparison"]["camera"]),
                "price_value": str(comparison.get("price_value") or fallback["comparison"]["price_value"]),
            },
            "ai_summary": str(parsed.get("ai_summary") or fallback["ai_summary"]),
        }
        return result
    except Exception:
        return fallback


def compare_products(product_a: str, product_b: str) -> dict[str, Any]:
    """
    1) Retrieve specs and review signals from available product data
    2) Use AI (optional) to analyze differences
    3) Return structured comparison payload
    """
    if not (product_a or "").strip() or not (product_b or "").strip():
        raise ValueError("Both product_a and product_b are required.")

    summary_a = _summarize_query_product(product_a)
    summary_b = _summarize_query_product(product_b)

    fallback = _deterministic_comparison(summary_a, summary_b)
    result = _ai_compare(summary_a, summary_b, fallback)

    return result
