"""
decision_service.py
Converts ranked branch options into actionable recommendations.
Adds weighted store-selection intelligence using:
  - product price
  - travel distance and time
  - fuel cost
  - store reliability
"""
from __future__ import annotations

import math

from utils.distance import format_duration


def _safe_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _inverse_norm(values: list[float], value: float) -> float:
    """
    Lower raw value => higher normalized score (0..1).
    """
    if not values:
        return 0.0
    low = min(values)
    high = max(values)
    if math.isclose(high, low):
        return 1.0
    score = 1.0 - ((value - low) / (high - low))
    return max(0.0, min(1.0, score))


def _store_reliability(option: dict) -> float:
    """
    Estimate store reliability on a 0..1 scale.
    Uses branch rating when available, otherwise product quality signals.
    """
    branch = option.get("branch", {})
    product = option.get("best_product", {})

    branch_rating = _safe_float(branch.get("rating"), 0.0)  # expected out of 5
    product_rating = _safe_float(product.get("rating"), 0.0)  # expected out of 5
    reviews = _safe_float(product.get("reviews"), 0.0)
    store_type = str(branch.get("type", "")).strip().lower()

    if branch_rating > 0:
        base = min(1.0, max(0.0, branch_rating / 5.0))
    elif product_rating > 0:
        base = min(1.0, max(0.0, product_rating / 5.0))
    else:
        # Neutral default when no reliability metadata exists.
        base = 0.6

    review_boost = min(0.2, math.log10(max(1.0, reviews + 1.0)) * 0.08)
    type_bonus = 0.04 if store_type == "physical" else 0.0

    reliability = base + review_boost + type_bonus
    return round(max(0.0, min(1.0, reliability)), 4)


def _score_options(ranked: list[dict]) -> list[dict]:
    """
    Apply weighted score:
      price_score * 0.5 +
      distance_score * 0.2 +
      fuel_cost_score * 0.1 +
      store_reliability * 0.2
    """
    if not ranked:
        return []

    prices = [_safe_float(r.get("product_price")) for r in ranked]
    distances = [_safe_float(r.get("distance_km")) for r in ranked]
    durations = [_safe_float(r.get("duration_min")) for r in ranked]
    fuels = [_safe_float(r.get("fuel_cost")) for r in ranked]

    scored_rows = []
    for row in ranked:
        price_raw = _safe_float(row.get("product_price"))
        distance_raw = _safe_float(row.get("distance_km"))
        duration_raw = _safe_float(row.get("duration_min"))
        fuel_raw = _safe_float(row.get("fuel_cost"))

        price_score = _inverse_norm(prices, price_raw)
        distance_norm = _inverse_norm(distances, distance_raw)
        time_norm = _inverse_norm(durations, duration_raw)

        # Include travel time inside distance_score.
        distance_score = (distance_norm * 0.7) + (time_norm * 0.3)
        fuel_cost_score = _inverse_norm(fuels, fuel_raw)
        reliability = _store_reliability(row)

        selection_score = (
            (price_score * 0.5)
            + (distance_score * 0.2)
            + (fuel_cost_score * 0.1)
            + (reliability * 0.2)
        )

        enriched = {**row}
        enriched["price_score"] = round(price_score, 4)
        enriched["distance_score"] = round(distance_score, 4)
        enriched["fuel_cost_score"] = round(fuel_cost_score, 4)
        enriched["store_reliability"] = round(reliability, 4)
        enriched["selection_score"] = round(selection_score, 4)
        scored_rows.append(enriched)

    return scored_rows


def _build_selection_reason(best: dict, objective: str = "weighted intelligence") -> str:
    branch_name = best["branch"]["name"]
    price_score = best.get("price_score", 0.0)
    distance_score = best.get("distance_score", 0.0)
    fuel_score = best.get("fuel_cost_score", 0.0)
    reliability = best.get("store_reliability", 0.0)
    overall = best.get("selection_score", 0.0)

    return (
        f"{branch_name} is the top option for {objective} with weighted score {overall:.2f} "
        f"(price {price_score:.2f}, distance/time {distance_score:.2f}, "
        f"fuel {fuel_score:.2f}, reliability {reliability:.2f})."
    )


def recommend(ranked: list[dict], priority: str = "total_cost") -> dict:
    """
    Given ranked options from prediction_service.rank_branches,
    return a structured recommendation object.
    """
    if not ranked:
        return {"error": "No branches found for this category and location."}

    scored = _score_options(ranked)

    priority_key = str(priority or "total_cost").strip().lower()
    priority_map = {
        "total_cost": ("grand_total", "total cost"),
        "price": ("product_price", "item price"),
        "distance": ("distance_km", "distance"),
    }
    sort_key, objective = priority_map.get(priority_key, ("grand_total", "total cost"))

    # Objective pick selected by user filter.
    best_overall = min(scored, key=lambda x: _safe_float(x.get(sort_key), float("inf")))
    # Weighted pick retained for explainability.
    weighted_best = max(scored, key=lambda x: x.get("selection_score", 0.0))
    cheapest_item = min(scored, key=lambda x: x["product_price"])
    nearest_branch = min(scored, key=lambda x: x["distance_km"])

    savings_vs_nearest = round(
        nearest_branch["grand_total"] - best_overall["grand_total"], 2
    )

    advice_lines = []

    if best_overall["branch"]["id"] == cheapest_item["branch"]["id"]:
        advice_lines.append(
            f"{best_overall['branch']['name']} is both cheapest and strongest by weighted intelligence score."
        )
    else:
        advice_lines.append(
            f"Cheapest item is at {cheapest_item['branch']['name']} "
            f"(Rs. {cheapest_item['product_price']:.0f}), but {best_overall['branch']['name']} "
            f"wins after distance, fuel, and reliability weighting."
        )
        if savings_vs_nearest > 0:
            advice_lines.append(
                f"Choosing {best_overall['branch']['name']} saves "
                f"Rs. {savings_vs_nearest:.0f} overall vs the nearest store."
            )

    if nearest_branch["branch"]["id"] != best_overall["branch"]["id"]:
        duration_label = format_duration(nearest_branch.get("duration_min", 0))
        advice_lines.append(
            f"Nearest store: {nearest_branch['branch']['name']} "
            f"({nearest_branch['distance_km']:.1f} km, "
            f"~{duration_label} drive)."
        )

    reason = _build_selection_reason(best_overall, objective=objective)
    if weighted_best["branch"]["id"] != best_overall["branch"]["id"]:
        reason += (
            f" Weighted-intelligence benchmark favors {weighted_best['branch']['name']} "
            f"(score {weighted_best.get('selection_score', 0.0):.2f})."
        )

    return {
        # New simplified summary fields requested.
        "best_store": best_overall["branch"]["name"],
        "distance_km": best_overall["distance_km"],
        "total_cost": best_overall["grand_total"],
        "reason": reason,
        "selected_priority": priority_key if priority_key in priority_map else "total_cost",

        # Backward-compatible fields.
        "best_overall": _fmt(best_overall),
        "cheapest_item": _fmt(cheapest_item),
        "nearest_branch": _fmt(nearest_branch),
        "all_options": [_fmt(r) for r in scored],
        "advice": advice_lines,
        "total_options": len(scored),
    }


def multi_category_plan(
    category_results: dict[str, list[dict]],
    user_lat: float,
    user_lon: float,
) -> dict:
    """
    Given results for multiple categories, suggest a combined route
    that minimizes total distance and cost.

    Returns an ordered list of stops plus combined cost summary.
    """
    from utils.distance import haversine_km

    stops = []
    total_product_cost = 0.0
    total_travel_cost = 0.0

    for category, ranked in category_results.items():
        if not ranked:
            continue
        best = ranked[0]
        stops.append({
            "category": category,
            "branch": best["branch"],
            "product": best["best_product"]["product"],
            "product_price": best["product_price"],
            "distance_from_user_km": best["distance_km"],
        })
        total_product_cost += best["product_price"]
        total_travel_cost += best["travel_cost"]

    # Greedy nearest-neighbor ordering of stops (starting from user)
    ordered = []
    remaining = stops[:]
    current_lat, current_lon = user_lat, user_lon
    while remaining:
        nearest = min(
            remaining,
            key=lambda s: haversine_km(
                current_lat,
                current_lon,
                s["branch"]["lat"],
                s["branch"]["lon"],
            ),
        )
        ordered.append(nearest)
        current_lat = nearest["branch"]["lat"]
        current_lon = nearest["branch"]["lon"]
        remaining.remove(nearest)

    return {
        "ordered_stops": ordered,
        "total_product_cost": round(total_product_cost, 2),
        "total_travel_cost": round(total_travel_cost, 2),
        "estimated_grand_total": round(total_product_cost + total_travel_cost, 2),
    }


def _fmt(r: dict) -> dict:
    """Return a clean, serializable dict for the API response."""
    return {
        "branch_id": r["branch"]["id"],
        "branch_name": r["branch"]["name"],
        "branch_type": r["branch"].get("type", "physical"),
        "city": r["branch"]["city"],
        "address": r["branch"]["address"],
        "lat": r["branch"]["lat"],
        "lon": r["branch"]["lon"],
        "phone": r["branch"].get("phone", ""),
        "rating": r["branch"].get("rating", 0),
        "product": r["best_product"]["product"],
        "product_price": r["product_price"],
        "product_rating": r["best_product"].get("rating", 0),
        "distance_km": r["distance_km"],
        "duration_min": r["duration_min"],
        "fuel_cost": r["fuel_cost"],
        "time_cost": r["time_cost"],
        "travel_cost": r["travel_cost"],
        "grand_total": r["grand_total"],
        "via": r.get("via", "estimate"),
        "score": r.get("score", 0),
        "price_score": r.get("price_score", 0),
        "distance_score": r.get("distance_score", 0),
        "fuel_cost_score": r.get("fuel_cost_score", 0),
        "store_reliability": r.get("store_reliability", 0),
        "selection_score": r.get("selection_score", 0),
    }
