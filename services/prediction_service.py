"""
prediction_service.py
Scores every (branch x product) combination for a given user location.
Returns a ranked list with estimated grand total cost.
"""
from __future__ import annotations

import os
import random
import statistics
from collections import defaultdict
from typing import Any

import requests

from config import BRANCHES, CATEGORY_META
from services.deal_detection_service import detect_deal
from services.price_history_service import get_trend, record_prices
from utils.distance import full_trip_analysis

_PREDICTION_AI_REASONING = (
    os.environ.get("PREDICTION_AI_REASONING", "false").strip().lower()
    in {"1", "true", "yes", "on"}
)
_PREDICTION_AI_MODEL = os.environ.get(
    "PREDICTION_AI_MODEL",
    os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
)
_PREDICTION_AI_CONNECT_TIMEOUT = float(
    os.environ.get("PREDICTION_AI_CONNECT_TIMEOUT_SECONDS", "0.7")
)
_PREDICTION_AI_READ_TIMEOUT = float(
    os.environ.get("PREDICTION_AI_READ_TIMEOUT_SECONDS", "1.4")
)
_PREDICTION_AI_MAX_CALLS = int(os.environ.get("PREDICTION_AI_MAX_CALLS", "3"))
_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


def _assign_price_variation(base_price: float, branch_id: str) -> float:
    """
    Different branches may have slightly different prices (+/-10%).
    Uses branch_id as deterministic seed so results stay stable.
    """
    rng = random.Random(hash(branch_id))
    factor = rng.uniform(0.92, 1.08)
    return round(base_price * factor, 2)


def _safe_float(value: Any) -> float | None:
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    return num


def _normalize_category(value: Any) -> str:
    return str(value or "").strip().lower()


def _category_variants(value: str) -> set[str]:
    if not value:
        return set()
    variants = {value}
    if value.endswith("s") and len(value) > 3:
        variants.add(value[:-1])
    elif len(value) > 2:
        variants.add(f"{value}s")
    return variants


def _deal_query_key(product: dict, category: str) -> str:
    name = str(product.get("product") or product.get("name") or category).strip().lower()
    return name or category.strip().lower()


def _demand_signal_score(product_samples: list[dict], store_count: int) -> tuple[float, list[str]]:
    """
    Lightweight demand approximation from available in-run signals.
    Higher score implies stronger upward pressure.
    """
    notes: list[str] = []
    score = 0.0

    ratings = [
        _safe_float(sample.get("rating"))
        for sample in product_samples
        if _safe_float(sample.get("rating")) is not None
    ]
    reviews = [
        _safe_float(sample.get("reviews"))
        for sample in product_samples
        if _safe_float(sample.get("reviews")) is not None
    ]

    avg_rating = statistics.mean(ratings) if ratings else None
    avg_reviews = statistics.mean(reviews) if reviews else None

    if store_count <= 2:
        score += 0.25
        notes.append("limited store availability")
    elif store_count >= 6:
        score -= 0.20
        notes.append("broad store availability")

    if avg_reviews is not None and avg_reviews >= 50:
        score += 0.30
        notes.append("high shopper activity")
    elif avg_reviews is not None and avg_reviews <= 8 and store_count >= 4:
        score -= 0.15
        notes.append("soft shopper activity")

    if avg_rating is not None and avg_rating >= 4.6:
        score += 0.10
    elif avg_rating is not None and avg_rating <= 3.8:
        score -= 0.10

    return score, notes


def _compose_reason(
    label: str,
    history_direction: str,
    data_points: int,
    variation_cv: float,
    demand_notes: list[str],
    price_vs_history: float | None,
) -> str:
    window = max(2, min(7, data_points))

    if label == "likely drop":
        if history_direction == "falling":
            base = f"Price trend decreasing over last {window} observations."
        elif price_vs_history is not None and price_vs_history < 0:
            base = "Current market price is below historical average."
        else:
            base = "Downside pressure detected in recent pricing."
    elif label == "likely increase":
        if history_direction == "rising":
            base = f"Price trend increasing over last {window} observations."
        elif price_vs_history is not None and price_vs_history > 0:
            base = "Current market price is above historical average."
        else:
            base = "Upward pressure detected in recent pricing."
    else:
        base = "Recent trend is mostly stable with limited directional pressure."

    extras: list[str] = []
    if variation_cv >= 0.15:
        extras.append("store prices are highly variable")
    elif variation_cv <= 0.06:
        extras.append("store prices are tightly clustered")
    if demand_notes:
        extras.append(", ".join(demand_notes[:2]))

    if extras:
        return f"{base} Also, {extras[0]}."
    return base


def _maybe_ai_reason(
    prediction_label: str,
    confidence: int,
    fallback_reason: str,
    context: dict[str, Any],
) -> str | None:
    """
    Optional Groq reasoning, used only when enabled and API key is available.
    """
    if not _PREDICTION_AI_REASONING:
        return None

    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        return None

    prompt = (
        "Write one concise sentence (max 22 words) explaining this product price forecast.\n"
        f"Prediction: {prediction_label}\n"
        f"Confidence: {confidence}\n"
        f"Fallback reason: {fallback_reason}\n"
        f"History direction: {context.get('history_direction')}\n"
        f"History points: {context.get('data_points')}\n"
        f"Current mean: {context.get('current_avg')}\n"
        f"Historical mean: {context.get('historical_avg')}\n"
        f"Store variation cv: {context.get('variation_cv')}\n"
        f"Demand notes: {', '.join(context.get('demand_notes') or [])}\n"
        "No markdown."
    )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": _PREDICTION_AI_MODEL,
        "messages": [
            {"role": "system", "content": "You explain ecommerce price forecasts in one sentence."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 60,
    }

    try:
        resp = requests.post(
            _GROQ_URL,
            headers=headers,
            json=payload,
            timeout=(
                max(0.2, _PREDICTION_AI_CONNECT_TIMEOUT),
                max(0.3, _PREDICTION_AI_READ_TIMEOUT),
            ),
        )
        resp.raise_for_status()
        text = (resp.json().get("choices") or [{}])[0].get("message", {}).get("content", "").strip()
        return text or None
    except Exception:
        return None


def _predict_price_direction(
    query_key: str,
    current_prices: list[float],
    product_samples: list[dict],
    ai_calls_used: int,
) -> tuple[dict[str, Any], int]:
    """
    Forecast direction using history + demand + store variation.
    Returns prediction dict and updated AI-call counter.
    """
    if not current_prices:
        return (
            {
                "price_prediction": "likely stable",
                "confidence": 40,
                "reason": "Insufficient current pricing data.",
            },
            ai_calls_used,
        )

    trend = get_trend(query_key)
    history_direction = str(trend.get("direction") or "unknown")
    history_conf = float(_safe_float(trend.get("confidence")) or 0.0)
    data_points = int(trend.get("data_points") or 0)
    historical_avg = _safe_float(trend.get("avg_price"))
    current_avg = statistics.mean(current_prices)

    variation_cv = 0.0
    if len(current_prices) >= 2 and current_avg > 0:
        variation_cv = statistics.pstdev(current_prices) / current_avg

    demand_score, demand_notes = _demand_signal_score(product_samples, len(current_prices))

    momentum = 0.0
    if history_direction == "rising":
        momentum += 0.90 * max(0.35, history_conf)
    elif history_direction == "falling":
        momentum -= 0.90 * max(0.35, history_conf)

    price_vs_history = None
    if historical_avg and historical_avg > 0:
        price_vs_history = (current_avg - historical_avg) / historical_avg
        if price_vs_history >= 0.04:
            momentum += 0.35
        elif price_vs_history <= -0.04:
            momentum -= 0.35

    momentum += demand_score * 0.55

    if momentum <= -0.35:
        label = "likely drop"
    elif momentum >= 0.35:
        label = "likely increase"
    else:
        label = "likely stable"

    confidence = 45.0
    confidence += min(28.0, abs(momentum) * 35.0)
    confidence += min(16.0, history_conf * 20.0)
    confidence += min(10.0, data_points * 1.5)
    confidence += 5.0 if len(current_prices) >= 4 else 0.0
    confidence -= min(18.0, variation_cv * 70.0)
    if label == "likely stable":
        confidence -= 6.0
    confidence_int = int(max(35, min(95, round(confidence))))

    reason = _compose_reason(
        label=label,
        history_direction=history_direction,
        data_points=data_points,
        variation_cv=variation_cv,
        demand_notes=demand_notes,
        price_vs_history=price_vs_history,
    )

    if ai_calls_used < _PREDICTION_AI_MAX_CALLS:
        ai_reason = _maybe_ai_reason(
            prediction_label=label,
            confidence=confidence_int,
            fallback_reason=reason,
            context={
                "history_direction": history_direction,
                "data_points": data_points,
                "current_avg": round(current_avg, 2),
                "historical_avg": round(historical_avg, 2) if historical_avg is not None else None,
                "variation_cv": round(variation_cv, 4),
                "demand_notes": demand_notes,
            },
        )
        if ai_reason:
            reason = ai_reason
            ai_calls_used += 1

    return (
        {
            "price_prediction": label,
            "confidence": confidence_int,
            "reason": reason,
        },
        ai_calls_used,
    )


def rank_branches(
    user_lat: float,
    user_lon: float,
    category: str,
    products: list[dict],
    budget: float | None = None,
    priority: str = "total_cost",   # "total_cost" | "price" | "distance"
) -> list[dict]:
    """
    For each branch that carries `category`, calculate travel cost +
    the cheapest available product price at that branch.

    Returns a list of branch+product dicts, sorted by chosen priority.
    """
    if not products:
        return []

    category_key = _normalize_category(category)
    category_keys = _category_variants(category_key)
    eligible = [
        branch for branch in BRANCHES
        if not category_keys or any(key in branch.get("categories", []) for key in category_keys)
    ]
    if not eligible and category_key and category_key != "electronics":
        eligible = [branch for branch in BRANCHES if "electronics" in branch.get("categories", [])]
    products_by_store: dict[str, list[dict]] = {}

    for product in products:
        product_category = _normalize_category(product.get("category"))
        if category_key and category_key != "electronics":
            if product_category and product_category != "electronics" and product_category not in category_keys:
                continue
        store_name = str(product.get("source_store", "")).strip().lower()
        if not store_name:
            continue
        products_by_store.setdefault(store_name, []).append(product)

    results: list[dict] = []

    for branch in eligible:
        best_product = None
        best_price = float("inf")
        store_products = products_by_store.get(branch["name"].strip().lower(), [])

        for product in store_products:
            try:
                branch_price = float(product["price"])
            except (TypeError, ValueError, KeyError):
                continue
            if branch_price < best_price:
                best_price = branch_price
                best_product = {**product, "price": branch_price}

        if best_product is None:
            continue
        if budget and best_price > budget:
            continue

        trip = full_trip_analysis(
            user_lat,
            user_lon,
            branch["lat"],
            branch["lon"],
            product_price=best_price,
        )

        results.append(
            {
                "branch": branch,
                "best_product": best_product,
                "distance_km": trip["distance_km"],
                "duration_min": trip["duration_min"],
                "fuel_cost": trip["fuel_cost"],
                "time_cost": trip["time_cost"],
                "travel_cost": trip["total_cost"],
                "product_price": best_price,
                "grand_total": trip["grand_total"],
                "via": trip["via"],
                "category_meta": CATEGORY_META.get(category, {}),
                "score": _score(trip, priority),
            }
        )

    if not results:
        return []

    # Group by detected product key for both deal and prediction annotations.
    price_snapshots: dict[str, list[float]] = defaultdict(list)
    product_samples_by_key: dict[str, list[dict]] = defaultdict(list)

    for item in results:
        key = _deal_query_key(item.get("best_product", {}), category)
        price = _safe_float(item.get("product_price"))
        if price is not None and price > 0:
            price_snapshots[key].append(price)
        product_samples_by_key[key].append(item.get("best_product", {}))

    # Compute one forecast per product key, then attach to each ranked row.
    forecast_by_key: dict[str, dict[str, Any]] = {}
    ai_calls_used = 0
    for key, prices in price_snapshots.items():
        forecast, ai_calls_used = _predict_price_direction(
            query_key=key,
            current_prices=prices,
            product_samples=product_samples_by_key.get(key, []),
            ai_calls_used=ai_calls_used,
        )
        forecast_by_key[key] = forecast

    default_forecast = {
        "price_prediction": "likely stable",
        "confidence": 40,
        "reason": "Insufficient data to estimate short-term movement.",
    }

    for item in results:
        key = _deal_query_key(item.get("best_product", {}), category)
        item.update(detect_deal(key, item.get("product_price")))
        item.update(forecast_by_key.get(key, default_forecast))

    # Persist observed prices for next predictions.
    for key, prices in price_snapshots.items():
        record_prices(key, prices)

    sort_key = {
        "total_cost": "grand_total",
        "price": "product_price",
        "distance": "distance_km",
    }.get(priority, "grand_total")

    results.sort(key=lambda row: row[sort_key])
    return results


def _score(trip: dict, priority: str) -> float:
    """Composite score - lower is better."""
    if priority == "price":
        return trip["product_price"]
    if priority == "distance":
        return trip["distance_km"]
    # Weighted: 50% price, 30% fuel, 20% time
    return trip["product_price"] * 0.5 + trip["fuel_cost"] * 0.3 + trip["time_cost"] * 0.2
