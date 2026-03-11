"""
user_profile_service.py
In-memory user behavior profiling and personalized recommendation generation.
"""
from __future__ import annotations

import math
import re
import threading
import time
from collections import Counter, defaultdict, deque
from statistics import mean
from typing import Any

from scrapers import fetch_category

_SEARCH_HISTORY_MAX = 80
_VIEW_HISTORY_MAX = 160
_BUDGET_HISTORY_MAX = 60
_FETCH_CACHE_TTL_SECONDS = 180
_FETCH_CACHE_MAX = 120

_PROFILE_LOCK = threading.Lock()
_FETCH_LOCK = threading.Lock()

_profiles: dict[str, dict[str, Any]] = {}
_fetch_cache: dict[str, tuple[float, list[dict]]] = {}

_KNOWN_BRANDS = {
    "apple",
    "samsung",
    "xiaomi",
    "redmi",
    "oppo",
    "vivo",
    "oneplus",
    "realme",
    "infinix",
    "tecno",
    "google",
    "pixel",
    "huawei",
    "nokia",
    "motorola",
    "sony",
    "lenovo",
    "hp",
    "dell",
    "asus",
    "acer",
    "msi",
    "haier",
    "dawlance",
    "pel",
    "lg",
    "tcl",
    "canon",
    "epson",
    "jbl",
    "anker",
    "tp",
    "logitech",
}


def _normalize_user_id(user_id: str | None) -> str:
    uid = str(user_id or "").strip()
    return uid if uid else "anonymous"


def _normalize_text(value: str | None) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^\w\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _tokens(value: str | None) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9]+", _normalize_text(value)) if token]


def _extract_brand_tokens(value: str | None) -> set[str]:
    token_set = set(_tokens(value))
    return {token for token in token_set if token in _KNOWN_BRANDS}


def _extract_budget_from_text(value: str | None) -> float | None:
    text = _normalize_text(value)
    if not text:
        return None

    text = text.replace(",", "")
    match = re.search(r"(\d+(?:\.\d+)?)\s*(k|m|lakh|lac|crore|cr)?", text)
    if not match:
        return None

    amount = float(match.group(1))
    unit = (match.group(2) or "").strip()
    multiplier = 1.0
    if unit == "k":
        multiplier = 1_000.0
    elif unit == "m":
        multiplier = 1_000_000.0
    elif unit in {"lakh", "lac"}:
        multiplier = 100_000.0
    elif unit in {"crore", "cr"}:
        multiplier = 10_000_000.0

    budget = amount * multiplier
    return budget if budget > 0 else None


def _extract_price(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        price = float(value)
        return price if price > 0 else None
    text = str(value).replace(",", "")
    match = re.search(r"\d+(?:\.\d+)?", text)
    if not match:
        return None
    price = float(match.group())
    return price if price > 0 else None


def _profile_for_user(user_id: str) -> dict[str, Any]:
    if user_id not in _profiles:
        _profiles[user_id] = {
            "search_history": deque(maxlen=_SEARCH_HISTORY_MAX),
            "viewed_products": deque(maxlen=_VIEW_HISTORY_MAX),
            "preferred_brands": Counter(),
            "budgets": deque(maxlen=_BUDGET_HISTORY_MAX),
            "updated_at": time.time(),
        }
    return _profiles[user_id]


def track_search_history(user_id: str, query: str, budget: float | int | None = None) -> None:
    uid = _normalize_user_id(user_id)
    query_text = _normalize_text(query)
    if not query_text:
        return

    with _PROFILE_LOCK:
        profile = _profile_for_user(uid)
        profile["search_history"].append({"query": query_text, "ts": time.time()})
        for brand in _extract_brand_tokens(query_text):
            profile["preferred_brands"][brand] += 1

        budget_value = None
        if budget is not None:
            try:
                budget_value = float(budget)
            except (TypeError, ValueError):
                budget_value = None
        if budget_value is None:
            budget_value = _extract_budget_from_text(query_text)

        if budget_value is not None and budget_value > 0:
            profile["budgets"].append(float(budget_value))

        profile["updated_at"] = time.time()


def track_viewed_products(user_id: str, products: list[dict] | list[str]) -> None:
    uid = _normalize_user_id(user_id)
    if not products:
        return

    with _PROFILE_LOCK:
        profile = _profile_for_user(uid)

        for item in products:
            if isinstance(item, str):
                name = _normalize_text(item)
                price = None
            else:
                name = _normalize_text(item.get("product") or item.get("name"))
                price = _extract_price(item.get("price"))

            if not name:
                continue

            profile["viewed_products"].append({"product": name, "price": price, "ts": time.time()})
            for brand in _extract_brand_tokens(name):
                profile["preferred_brands"][brand] += 1

        profile["updated_at"] = time.time()


def get_user_preferences(user_id: str) -> dict[str, Any]:
    uid = _normalize_user_id(user_id)

    with _PROFILE_LOCK:
        profile = _profile_for_user(uid)
        searches = list(profile["search_history"])
        viewed = list(profile["viewed_products"])
        brand_counter = Counter(profile["preferred_brands"])
        budgets = [float(v) for v in profile["budgets"]]

    preferred_brands = [brand for brand, _ in brand_counter.most_common(5)]

    budget_range = None
    if budgets:
        budget_range = {
            "min": round(min(budgets), 2),
            "max": round(max(budgets), 2),
            "avg": round(mean(budgets), 2),
        }

    recent_searches = [row["query"] for row in searches[-10:]]
    recent_viewed = [row["product"] for row in viewed[-20:]]

    return {
        "search_history": recent_searches,
        "viewed_products": recent_viewed,
        "preferred_brands": preferred_brands,
        "budget_range": budget_range,
    }


def _cached_fetch(query: str) -> list[dict]:
    now = time.time()
    key = _normalize_text(query)
    with _FETCH_LOCK:
        entry = _fetch_cache.get(key)
        if entry and entry[0] >= now:
            return list(entry[1])

    products = fetch_category("electronics", 1, query=key or None, verbose=False) or []

    if not products and key:
        products = fetch_category("electronics", 1, query=None, verbose=False) or []

    with _FETCH_LOCK:
        if len(_fetch_cache) >= _FETCH_CACHE_MAX:
            oldest_key = min(_fetch_cache, key=lambda k: _fetch_cache[k][0])
            _fetch_cache.pop(oldest_key, None)
        _fetch_cache[key] = (now + _FETCH_CACHE_TTL_SECONDS, list(products))
    return products


def _interest_phrase(pref: dict[str, Any]) -> str:
    searches = pref.get("search_history") or []
    brands = pref.get("preferred_brands") or []

    if searches:
        latest = searches[-1]
        if "gaming" in latest and "laptop" in latest:
            return "gaming laptops"
        if "mobile" in latest or "phone" in latest or "iphone" in latest:
            return "smartphones"
        return latest

    if brands:
        return f"{brands[0]} products"

    return "electronics products"


def _recommendation_query(pref: dict[str, Any]) -> str:
    searches = pref.get("search_history") or []
    brands = pref.get("preferred_brands") or []

    if searches:
        return searches[-1]
    if brands:
        return f"{brands[0]} electronics"
    return "electronics"


def _score_product(product: dict, pref: dict[str, Any]) -> float:
    name = _normalize_text(product.get("product") or product.get("name"))
    price = _extract_price(product.get("price")) or 0.0
    rating = float(product.get("rating") or 0.0)
    reviews = float(product.get("reviews") or 0.0)

    tokens = set(_tokens(name))
    preferred_brands = set(pref.get("preferred_brands") or [])
    searches = pref.get("search_history") or []
    query_tokens = set(_tokens(searches[-1] if searches else ""))

    brand_boost = 1.6 if preferred_brands & tokens else 0.0
    query_overlap = len(tokens & query_tokens) * 0.45
    quality = (min(rating, 5.0) * 0.25) + (min(reviews, 300.0) / 300.0)
    price_component = max(0.0, 1.4 - (price / 1_000_000.0)) if price > 0 else 0.3

    score = brand_boost + query_overlap + quality + price_component

    budget_range = pref.get("budget_range")
    if budget_range and price > 0:
        target = float(budget_range.get("avg") or budget_range.get("max") or 0.0)
        if target > 0:
            diff_ratio = abs(price - target) / max(target, 1.0)
            score += max(0.0, 1.0 - diff_ratio)

    return score


def generate_recommendations(user_id: str) -> dict[str, Any]:
    """
    Return personalized recommendations for the given user.

    Output:
    {
      "recommended_products": [...],
      "reason": "Based on your interest in gaming laptops"
    }
    """
    uid = _normalize_user_id(user_id)
    pref = get_user_preferences(uid)

    query = _recommendation_query(pref)
    products = _cached_fetch(query)

    preferred_brands = set(pref.get("preferred_brands") or [])
    budget_range = pref.get("budget_range")
    budget_cap = float(budget_range.get("max")) if budget_range and budget_range.get("max") else None

    candidates = []
    for product in products:
        name = _normalize_text(product.get("product") or product.get("name"))
        if not name:
            continue

        if preferred_brands and not (preferred_brands & set(_tokens(name))):
            # Keep non-brand matches only if we have too little data.
            if len(products) > 15:
                continue

        price = _extract_price(product.get("price"))
        if budget_cap is not None and price is not None and price > (budget_cap * 1.25):
            continue

        candidates.append(product)

    if not candidates:
        candidates = products[:]

    ranked = sorted(candidates, key=lambda item: _score_product(item, pref), reverse=True)

    seen = set()
    recommended_products = []
    for product in ranked:
        name = str(product.get("product") or product.get("name") or "").strip()
        if not name:
            continue
        key = _normalize_text(name)
        if key in seen:
            continue
        seen.add(key)
        recommended_products.append(
            {
                "product": name,
                "price": _extract_price(product.get("price")),
                "rating": float(product.get("rating") or 0.0),
                "source_store": product.get("source_store"),
                "source_url": product.get("source_url"),
            }
        )
        if len(recommended_products) >= 8:
            break

    reason = f"Based on your interest in {_interest_phrase(pref)}"
    return {
        "recommended_products": recommended_products,
        "reason": reason,
    }

