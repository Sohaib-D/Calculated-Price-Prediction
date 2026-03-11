"""
intelligence_service.py
───────────────────────
AI Decision Intelligence Engine.

Transforms raw optimisation results into structured, user-friendly
insights: price predictions, buying advice, cost optimisation
reasoning, savings analysis, and smart tips.

Every recommendation includes explainability — a clear WHY.
"""
from __future__ import annotations

import json
import os
import re
import statistics
from typing import Any

from dotenv import load_dotenv
load_dotenv()

import requests

from services.price_history_service import get_trend
from utils.distance import format_duration

_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_INTELLIGENCE_AI_MODEL = os.environ.get(
    "GROQ_INTELLIGENCE_MODEL",
    os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
)
_INTELLIGENCE_AI_CONNECT_TIMEOUT = float(
    os.environ.get("INTELLIGENCE_AI_CONNECT_TIMEOUT_SECONDS", "0.8")
)
_INTELLIGENCE_AI_READ_TIMEOUT = float(
    os.environ.get("INTELLIGENCE_AI_READ_TIMEOUT_SECONDS", "1.8")
)


def _extract_json_object(text: str) -> dict | None:
    candidate = str(text or "").strip()
    if not candidate:
        return None
    try:
        data = json.loads(candidate)
        return data if isinstance(data, dict) else None
    except (TypeError, ValueError):
        pass
    match = re.search(r"\{.*\}", candidate, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
        return data if isinstance(data, dict) else None
    except (TypeError, ValueError):
        return None


def _maybe_ai_narrative(
    best: dict,
    cheapest: dict,
    nearest: dict,
    query: str,
    options: list[dict],
) -> dict | None:
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        return None
    duration_label = format_duration(best.get("duration_min", 0))

    payload = {
        "model": _INTELLIGENCE_AI_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a professional ecommerce analyst. "
                    "Return only JSON with keys summary and reasoning."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Create a concise recommendation summary and reasoning.\n"
                    f"User query: {query or 'electronics'}\n"
                    f"Compared stores: {len(options)}\n"
                    f"Best store: {best.get('branch_name', '')}\n"
                    f"Best product: {best.get('product', '')}\n"
                    f"Best item price: {best.get('product_price', 0)}\n"
                    f"Best total cost: {best.get('grand_total', 0)}\n"
                    f"Distance km: {best.get('distance_km', 0)}\n"
                    f"Fuel cost: {best.get('fuel_cost', 0)}\n"
                    f"Travel time: {duration_label}\n"
                    f"Cheapest store: {cheapest.get('branch_name', '')} price {cheapest.get('product_price', 0)}\n"
                    f"Nearest store: {nearest.get('branch_name', '')} distance {nearest.get('distance_km', 0)}\n"
                    "Constraints: professional tone, no emoji, no markdown, maximum 2 sentences per field. "
                    "Use the provided travel time label and do not convert time into money."
                ),
            },
        ],
        "temperature": 0.2,
        "max_tokens": 180,
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
            timeout=(
                max(0.2, _INTELLIGENCE_AI_CONNECT_TIMEOUT),
                max(0.3, _INTELLIGENCE_AI_READ_TIMEOUT),
            ),
        )
        response.raise_for_status()
        content = (
            (response.json().get("choices") or [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        parsed = _extract_json_object(content)
        if not parsed:
            return None
        summary = str(parsed.get("summary") or "").strip()
        reasoning = str(parsed.get("reasoning") or "").strip()
        if not summary and not reasoning:
            return None
        return {
            "summary": summary,
            "reasoning": reasoning,
        }
    except Exception:
        return None


# ── Main Entry ───────────────────────────────────────────────────────────────

def generate_intelligence(
    recommendation: dict,
    query: str = "",
    user_prefs: dict | None = None,
) -> dict[str, Any]:
    """
    Main entry point.  Takes a recommendation dict (from decision_service.recommend)
    and enriches it with intelligent analysis.

    Parameters
    ----------
    recommendation : output of decision_service.recommend()
    query          : the product search query
    user_prefs     : optional dict with keys like price_sensitivity, preferred_cities

    Returns
    -------
    dict with keys: summary, best_option, price_prediction, savings_opportunity,
                    ai_reasoning, smart_tips, insights, cost_breakdown
    """
    if recommendation.get("error"):
        return {
            "summary": "I could not find a ranked recommendation for this query yet. Try a broader term or a model family, and check the suggested searches.",
            "best_option": None,
            "price_prediction": None,
            "savings_opportunity": None,
            "ai_reasoning": recommendation["error"],
            "smart_tips": ["Refine the product model name or broaden the query scope."],
            "insights": {},
            "cost_breakdown": None,
        }

    prefs = user_prefs or {}
    options = recommendation.get("all_options", [])
    best = recommendation.get("best_overall", {})
    cheapest = recommendation.get("cheapest_item", {})
    nearest = recommendation.get("nearest_branch", {})

    summary = _build_summary(best, cheapest, nearest, query, options)
    best_option = _build_best_option(best)
    prediction = _build_price_prediction(options, query)
    savings = _build_savings_opportunity(options, best, cheapest, nearest)
    reasoning = _build_reasoning(best, cheapest, nearest, options, prefs)
    ai_narrative = _maybe_ai_narrative(best, cheapest, nearest, query, options)
    if ai_narrative:
        summary = ai_narrative.get("summary") or summary
        reasoning = ai_narrative.get("reasoning") or reasoning
    tips = _build_smart_tips(options, best, cheapest, nearest, query, prefs)
    insights = _build_insights(options, best)
    cost_breakdown = _build_cost_breakdown(best)
    quality = _build_quality_score(best, options, query)
    price_eval = _build_price_evaluation(best, options)
    demand = _build_demand_trend(options, query)
    comparison = _build_model_comparison(options, best)
    risk_warnings = _build_risk_warnings(best, options)
    buying_advice = _build_buying_advice(best, cheapest, nearest, options, query, prefs)

    return {
        "summary": summary,
        "best_option": best_option,
        "price_prediction": prediction,
        "savings_opportunity": savings,
        "ai_reasoning": reasoning,
        "smart_tips": tips,
        "insights": insights,
        "cost_breakdown": cost_breakdown,
        "quality_score": quality,
        "price_evaluation": price_eval,
        "demand_trend": demand,
        "model_comparison": comparison,
        "risk_warnings": risk_warnings,
        "buying_advice": buying_advice,
    }


# ── Summary ──────────────────────────────────────────────────────────────────

def _build_summary(
    best: dict, cheapest: dict, nearest: dict,
    query: str, options: list[dict],
) -> str:
    """Generate a human‑friendly summary.  The output now uses simple markdown
    markers (strong / list items) so that the front end can render rich HTML
    (bold text, bullets, paragraphs).

    The format emphasises **selection** vs **considerations** and always gives
    the numbers users care about.
    """

    store = best.get("branch_name", "Unknown")
    store_type = str(best.get("branch_type", "physical")).lower()
    total = best.get("grand_total", 0)
    price = best.get("product_price", 0)
    dist = best.get("distance_km", 0)
    n_stores = len(options)

    product_label = query or "your product"

    # Build a list of lines that may include bullets (prefixed with "- ").
    lines: list[str] = []
    type_phrase = "online" if store_type == "online" else "a physical"
    lines.append(
        f"**Selection:** {store} ({type_phrase} store) was chosen as the recommended store for {product_label}."
    )
    lines.append(f"- Item price: Rs. {price:,.0f}")
    if store_type != "online":
        lines.append(f"- Travel distance: {dist:.1f} km")
        duration_label = format_duration(best.get("duration_min", 0))
        if duration_label != "0m":
            lines.append(f"- Travel time: {duration_label}")
    lines.append(f"- All‑in total cost: Rs. {total:,.0f}")

    # Compare against cheapest and nearest options if they differ
    if best.get("branch_id") != cheapest.get("branch_id"):
        cheap_price = cheapest.get("product_price", 0)
        lines.append(
            f"**Cheapest item price:** {cheapest.get('branch_name','another store')} has it for Rs. {cheap_price:,.0f}, "
            "but travel-adjusted total made the recommended store better overall."
        )

    if best.get("branch_id") != nearest.get("branch_id"):
        nearest_time = format_duration(nearest.get("duration_min", 0))
        lines.append(
            f"**Nearest option considered:** {nearest.get('branch_name','another store')} "
            f"({nearest.get('distance_km',0):.1f} km, {nearest_time}, "
            f"fuel Rs. {nearest.get('fuel_cost',0):,.0f})."
        )

    lines.append(f"Compared across {n_stores} store{'s' if n_stores != 1 else ''}." )

    return "\n".join(lines)


def _build_best_option(best: dict) -> dict:
    return {
        "store": best.get("branch_name", "Unknown"),
        "city": best.get("city", ""),
        "address": best.get("address", ""),
        "product": best.get("product", ""),
        "item_price": best.get("product_price", 0),
        "travel_cost": best.get("travel_cost", 0),
        "total_cost": best.get("grand_total", 0),
        "distance_km": best.get("distance_km", 0),
        "duration_min": best.get("duration_min", 0),
        "store_type": best.get("branch_type", "physical"),
    }


# ── Price Prediction ────────────────────────────────────────────────────────

def _build_price_prediction(options: list[dict], query: str) -> dict:
    prices = [o.get("product_price", 0) for o in options if o.get("product_price", 0) > 0]
    if not prices:
        return {"direction": "unknown", "probability": 0, "explanation": "Insufficient data."}

    # Check historical trend
    trend = get_trend(query) if query else {"direction": "unknown", "confidence": 0.0}

    # Analyse current price spread
    mean_price = statistics.mean(prices)
    if len(prices) >= 2:
        stdev = statistics.stdev(prices)
        cv = stdev / mean_price if mean_price else 0  # coefficient of variation
    else:
        stdev = 0
        cv = 0

    # Combine historical trend with current market analysis
    historical_dir = trend.get("direction", "unknown")
    historical_conf = trend.get("confidence", 0.0)

    # High CV = volatile market → could go either way
    # Low CV = stable market → prices likely to hold
    if historical_dir != "unknown" and historical_conf > 0.3:
        direction = {"rising": "up", "falling": "down", "stable": "stable"}.get(
            historical_dir, "stable"
        )
        probability = int(min(85, historical_conf * 100))
    elif cv < 0.05:
        direction = "stable"
        probability = 78
    elif cv < 0.15:
        direction = "stable"
        probability = 62
    else:
        # High variance → slight upward bias (products in PK market often increase)
        direction = "up"
        probability = 55

    n_stores = len(prices)

    explanations = {
        "up": (
            f"📈 Prices may **increase** — "
            f"{'historical data shows an upward trend' if historical_dir == 'rising' else 'high price variance across stores suggests market instability'}. "
            f"Based on {n_stores} store prices (avg Rs. {mean_price:,.0f})."
        ),
        "down": (
            f"📉 Prices may **decrease** — "
            f"{'historical data shows a downward trend' if historical_dir == 'falling' else 'competitive pricing across stores indicates downward pressure'}. "
            f"Based on {n_stores} store prices (avg Rs. {mean_price:,.0f})."
        ),
        "stable": (
            f"↔️ Prices are likely **stable** — "
            f"{'consistent pricing observed over time' if historical_dir == 'stable' else f'low variance (±{cv*100:.0f}%) across {n_stores} stores suggests price equilibrium'}. "
            f"Average price: Rs. {mean_price:,.0f}."
        ),
    }

    return {
        "direction": direction,
        "probability": probability,
        "explanation": explanations.get(direction, "Insufficient data for prediction."),
        "avg_price": round(mean_price, 2),
        "price_spread": round(stdev, 2) if stdev else 0,
        "stores_analysed": n_stores,
    }


# ── Savings Opportunity ─────────────────────────────────────────────────────

def _build_savings_opportunity(
    options: list[dict], best: dict, cheapest: dict, nearest: dict,
) -> dict:
    prices = [o.get("product_price", 0) for o in options if o.get("product_price", 0) > 0]
    totals = [o.get("grand_total", 0) for o in options if o.get("grand_total", 0) > 0]

    if not prices or not totals:
        return {"max_savings": 0, "explanation": "No data available."}

    max_price = max(prices)
    min_price = min(prices)
    price_savings = max_price - min_price

    max_total = max(totals)
    min_total = min(totals)
    total_savings = max_total - min_total

    best_total = best.get("grand_total", 0)
    nearest_total = nearest.get("grand_total", 0)
    savings_vs_nearest = nearest_total - best_total

    explanation_parts = []

    if price_savings > 0:
        explanation_parts.append(
            f"💰 Item prices range from Rs. {min_price:,.0f} to Rs. {max_price:,.0f} — "
            f"up to **Rs. {price_savings:,.0f}** difference on item price alone."
        )

    if total_savings > 0 and total_savings != price_savings:
        explanation_parts.append(
            f"🏷️ When including travel costs, the total difference is **Rs. {total_savings:,.0f}** "
            f"between the cheapest and most expensive option."
        )

    if savings_vs_nearest > 500:
        explanation_parts.append(
            f"🚗 By choosing {best.get('branch_name', 'the recommended store')} over the nearest store, "
            f"you save **Rs. {savings_vs_nearest:,.0f}** in total cost."
        )
    elif savings_vs_nearest < -500:
        explanation_parts.append(
            f"📍 The nearest store ({nearest.get('branch_name', '')}) is actually Rs. {abs(savings_vs_nearest):,.0f} cheaper overall — "
            f"sometimes close is best!"
        )

    return {
        "max_savings_on_price": round(price_savings, 2),
        "max_savings_on_total": round(total_savings, 2),
        "savings_vs_nearest": round(savings_vs_nearest, 2),
        "cheapest_store": cheapest.get("branch_name", ""),
        "most_expensive_price": round(max_price, 2),
        "cheapest_price": round(min_price, 2),
        "explanation": " ".join(explanation_parts) if explanation_parts else "Prices are very similar across stores.",
    }


# ── AI Reasoning ─────────────────────────────────────────────────────────────

def _build_reasoning(
    best: dict, cheapest: dict, nearest: dict,
    options: list[dict], prefs: dict,
) -> str:
    """Provide a readable explanation of how the decision was reached.  Output
    lines start with "- " where appropriate so that the frontend can render a
    bullet list automatically.
    """

    lines: list[str] = []

    n_options = len(options)
    lines.append(f"- Compared {n_options} store option{'s' if n_options != 1 else ''} on price, distance, fuel cost, travel time, and reliability.")

    best_store = best.get("branch_name", "the recommended store")
    best_total = best.get("grand_total", 0)
    best_price = best.get("product_price", 0)
    store_type = str(best.get("branch_type", "")).lower()
    fuel_cost = best.get("fuel_cost", 0) or 0
    duration_label = format_duration(best.get("duration_min", 0))
    travel_bits = [f"item Rs. {best_price:,.0f}", f"fuel Rs. {fuel_cost:,.0f}"]
    if store_type != "online" and duration_label != "0m":
        travel_bits.append(f"time {duration_label}")
    lines.append(
        f"- Recommended: {best_store} ({'online' if store_type == 'online' else 'physical'} store) with estimated total Rs. {best_total:,.0f} "
        f"({', '.join(travel_bits)})."
    )
    if store_type == "online":
        lines.append("- Product is available online; no travel cost applies (delivery fees not included).")

    if best.get("branch_id") != cheapest.get("branch_id"):
        lines.append(
            f"- Lowest item price at {cheapest.get('branch_name','another store')}, "
            "but travel-adjusted total made the recommendation more economical."
        )

    if best.get("branch_id") != nearest.get("branch_id"):
        lines.append(
            f"- Nearest store {nearest.get('branch_name','another store')} "
            f"({nearest.get('distance_km',0):.1f} km) offered lower convenience but lower overall value."
        )

    if prefs.get("preferred_cities"):
        cities = ", ".join(str(city) for city in prefs.get("preferred_cities", []) if city)
        if cities:
            lines.append(f"- Preference signal applied: preferred cities ({cities}).")

    if prefs.get("price_sensitivity") == "high":
        lines.append("- Preference signal applied: high price sensitivity increased weight on item price.")

    return "\n".join(lines)


def _build_smart_tips(
    options: list[dict], best: dict, cheapest: dict, nearest: dict,
    query: str, prefs: dict,
) -> list[str]:
    tips = []

    # Tip: Online stores
    online_options = [o for o in options if o.get("branch_type") == "online"]
    if online_options:
        cheapest_online = min(online_options, key=lambda o: o.get("product_price", float("inf")))
        tips.append(
            f"🌐 **Online option available** — {cheapest_online.get('branch_name', 'An online store')} "
            f"has it for Rs. {cheapest_online.get('product_price', 0):,.0f} with no travel cost. "
            f"Check delivery charges separately."
        )

    # Tip: Multi-stop savings
    if len(options) > 3:
        tips.append(
            "🛒 **Buying multiple items?** Use the Multi-Stop Route Planner to optimise "
            "your shopping trip across several stores."
        )

    # Tip: Timing
    best_price = best.get("product_price", 0)
    if best_price > 50_000:
        tips.append(
            "📅 **High-value purchase** — Consider waiting for seasonal sales "
            "(Daraz 11.11, Eid Sales, Black Friday PK) for potential 10-20% discounts."
        )

    # Tip: Travel savings
    fuel = best.get("fuel_cost", 0)
    duration_label = format_duration(best.get("duration_min", 0))
    travel = fuel
    if travel > 500:
        time_note = f" (travel time {duration_label})" if duration_label != "0m" else ""
        tips.append(
            f"⛽ **Fuel costs add up** — Rs. {travel:,.0f} to reach {best.get('branch_name', 'the store')}{time_note}. "
            "Check if they offer delivery to save the trip."
        )

    # Tip: Price comparison
    if len(options) >= 2:
        prices = sorted(set(o.get("product_price", 0) for o in options))
        if len(prices) >= 2 and prices[-1] > 0:
            pct_diff = ((prices[-1] - prices[0]) / prices[-1]) * 100
            if pct_diff > 15:
                tips.append(
                    f"📊 **{pct_diff:.0f}% price variance** across stores — always compare before buying!"
                )

    # Tip: Nearest store is cheapest
    if nearest.get("branch_id") == cheapest.get("branch_id"):
        tips.append(
            f"🎉 **Lucky!** The nearest store ({nearest.get('branch_name', '')}) also has the "
            f"cheapest price. Get there quickly!"
        )

    # Tip: Call ahead
    tips.append(
        "📞 **Pro tip** — Call the store before visiting to confirm stock availability "
        "and exact pricing."
    )

    return tips


# ── Insights ─────────────────────────────────────────────────────────────────

def _build_insights(options: list[dict], best: dict) -> dict:
    prices = [o.get("product_price", 0) for o in options if o.get("product_price", 0) > 0]
    totals = [o.get("grand_total", 0) for o in options if o.get("grand_total", 0) > 0]
    distances = [o.get("distance_km", 0) for o in options]

    insights: dict[str, Any] = {}

    # Price volatility
    if len(prices) >= 2:
        mean_p = statistics.mean(prices)
        stdev_p = statistics.stdev(prices)
        cv = (stdev_p / mean_p * 100) if mean_p else 0
        if cv < 5:
            vol_label = "Very Low"
            vol_emoji = "🟢"
        elif cv < 10:
            vol_label = "Low"
            vol_emoji = "🟢"
        elif cv < 20:
            vol_label = "Moderate"
            vol_emoji = "🟡"
        else:
            vol_label = "High"
            vol_emoji = "🔴"

        insights["price_volatility"] = {
            "label": f"{vol_emoji} {vol_label}",
            "value": f"{cv:.1f}%",
            "detail": f"Price coefficient of variation across {len(prices)} stores",
        }

    # Market competitiveness
    n_stores = len(options)
    if n_stores >= 5:
        comp = "Highly Competitive 🔥"
    elif n_stores >= 3:
        comp = "Moderately Competitive"
    else:
        comp = "Limited Competition"

    insights["market_competition"] = {
        "label": comp,
        "value": f"{n_stores} stores",
        "detail": "Number of stores competing on this product",
    }

    # Hidden costs warning
    travel_costs = [o.get("travel_cost", 0) for o in options]
    avg_travel = statistics.mean(travel_costs) if travel_costs else 0
    if avg_travel > 300:
        insights["hidden_costs"] = {
            "label": "⚠️ Significant Travel Costs",
            "value": f"Avg Rs. {avg_travel:,.0f}",
            "detail": "Average fuel + time cost across all store options",
        }
    else:
        insights["hidden_costs"] = {
            "label": "✅ Low Travel Overhead",
            "value": f"Avg Rs. {avg_travel:,.0f}",
            "detail": "Travel costs are manageable for most options",
        }

    # Best value score
    if totals:
        best_total = best.get("grand_total", 0)
        worst_total = max(totals)
        if worst_total > 0:
            value_score = round((1 - (best_total / worst_total)) * 100, 1)
            insights["value_score"] = {
                "label": f"💎 {value_score}% Better Value",
                "value": f"Rs. {best_total:,.0f}",
                "detail": "How much better the recommended option is vs the worst option",
            }

    # Distance spread
    if distances:
        insights["distance_range"] = {
            "label": "📏 Distance Range",
            "value": f"{min(distances):.1f} — {max(distances):.1f} km",
            "detail": "Spread of store distances from your location",
        }

    return insights


# ── Cost Breakdown ───────────────────────────────────────────────────────────

def _build_cost_breakdown(best: dict) -> dict:
    item_price = best.get("product_price", 0)
    fuel = best.get("fuel_cost", 0)
    duration_min = best.get("duration_min", 0)
    total = best.get("grand_total", 0)

    return {
        "item_price": round(item_price, 2),
        "fuel_cost": round(fuel, 2),
        "time_cost": 0,
        "travel_total": round(fuel, 2),
        "grand_total": round(total, 2),
        "travel_pct": round((fuel / total) * 100, 1) if total else 0,
        "duration_min": duration_min,
        "duration_label": format_duration(duration_min),
    }


# ── Quality Score ────────────────────────────────────────────────────────────

def _build_quality_score(best: dict, options: list[dict], query: str) -> dict:
    """
    Rate the recommended product 1–10 using available quality indicators:
    product rating, store rating, price competitiveness, and market coverage.
    """
    scores: list[tuple[float, float]] = []  # (score, weight)

    # 1. Product rating (from scraper) — weight 3
    product_rating = float(best.get("product_rating", 0))
    if product_rating > 0:
        # Scale 0–5 rating to 0–10
        scores.append((min(product_rating * 2.0, 10.0), 3.0))

    # 2. Store/branch rating — weight 1.5
    store_rating = float(best.get("rating", 0))
    if store_rating > 0:
        scores.append((min(store_rating * 2.0, 10.0), 1.5))

    # 3. Price competitiveness — weight 2
    prices = [o.get("product_price", 0) for o in options if o.get("product_price", 0) > 0]
    best_price = best.get("product_price", 0)
    if prices and best_price > 0:
        min_price = min(prices)
        max_price = max(prices)
        price_range = max_price - min_price
        if price_range > 0:
            position = 1.0 - ((best_price - min_price) / price_range)
            scores.append((max(1.0, min(10.0, position * 10.0)), 2.0))
        else:
            scores.append((7.0, 2.0))  # All same price = fair

    # 4. Market coverage / store count — weight 1
    n_stores = len(options)
    if n_stores >= 5:
        scores.append((9.0, 1.0))
    elif n_stores >= 3:
        scores.append((7.0, 1.0))
    elif n_stores >= 2:
        scores.append((5.0, 1.0))
    else:
        scores.append((3.0, 1.0))

    # 5. Value for money (low travel cost %) — weight 1
    total = best.get("grand_total", 0)
    travel = best.get("travel_cost", 0)
    if total > 0:
        travel_pct = travel / total
        if travel_pct < 0.05:
            scores.append((9.5, 1.0))
        elif travel_pct < 0.15:
            scores.append((8.0, 1.0))
        elif travel_pct < 0.30:
            scores.append((6.0, 1.0))
        else:
            scores.append((4.0, 1.0))

    # Weighted average
    if not scores:
        overall = 5.0
    else:
        total_w = sum(w for _, w in scores)
        overall = sum(s * w for s, w in scores) / total_w if total_w else 5.0

    overall = round(max(1.0, min(10.0, overall)), 1)

    # Build breakdown
    breakdown = []
    if product_rating > 0:
        breakdown.append(f"Product rating: {product_rating:.1f}/5")
    if store_rating > 0:
        breakdown.append(f"Store rating: {store_rating:.1f}/5")
    breakdown.append(f"Price competitiveness: {'excellent' if overall >= 8 else 'good' if overall >= 6 else 'average'}")
    breakdown.append(f"Market coverage: {n_stores} stores")

    if overall >= 8.5:
        verdict = "Excellent"
        emoji = "🌟"
    elif overall >= 7.0:
        verdict = "Very Good"
        emoji = "✅"
    elif overall >= 5.0:
        verdict = "Decent"
        emoji = "👍"
    elif overall >= 3.0:
        verdict = "Below Average"
        emoji = "⚠️"
    else:
        verdict = "Poor"
        emoji = "❌"

    return {
        "score": overall,
        "out_of": 10,
        "verdict": verdict,
        "emoji": emoji,
        "breakdown": breakdown,
        "explanation": f"{emoji} Quality rated **{overall}/10** ({verdict}) based on {', '.join(breakdown[:2])}.",
    }


# ── Price Evaluation ────────────────────────────────────────────────────────

def _build_price_evaluation(best: dict, options: list[dict]) -> dict:
    """
    Determine if the recommended product is a Great Deal, Fair Price, or Overpriced
    using statistical analysis of all available prices.
    """
    prices = [o.get("product_price", 0) for o in options if o.get("product_price", 0) > 0]
    best_price = best.get("product_price", 0)

    if not prices or best_price <= 0:
        return {
            "label": "Unknown",
            "emoji": "❓",
            "confidence": 0,
            "explanation": "Insufficient price data for evaluation.",
        }

    import statistics as stats
    mean_price = stats.mean(prices)
    min_price = min(prices)
    max_price = max(prices)

    if len(prices) >= 2:
        stdev = stats.stdev(prices)
    else:
        stdev = 0

    # Calculate percentile of the best price
    cheaper_count = sum(1 for p in prices if p < best_price)
    percentile = (cheaper_count / len(prices)) * 100

    # Deviation from mean
    deviation_pct = ((best_price - mean_price) / mean_price * 100) if mean_price else 0

    # Classification
    if percentile <= 10 or deviation_pct < -15:
        label = "Great Deal"
        emoji = "🟢"
        color = "green"
        explanation = (
            f"🟢 **Great Deal!** This price (Rs. {best_price:,.0f}) is in the "
            f"bottom {max(1, int(percentile))}% of all {len(prices)} prices found. "
            f"{abs(deviation_pct):.0f}% below average (Rs. {mean_price:,.0f})."
        )
    elif percentile <= 35 or deviation_pct < -5:
        label = "Good Value"
        emoji = "🟢"
        color = "green"
        explanation = (
            f"🟢 **Good Value.** Rs. {best_price:,.0f} is below the market average "
            f"of Rs. {mean_price:,.0f} — you're getting a solid deal."
        )
    elif percentile <= 65 or abs(deviation_pct) < 10:
        label = "Fair Price"
        emoji = "🟡"
        color = "amber"
        explanation = (
            f"🟡 **Fair Price.** Rs. {best_price:,.0f} is near the market average "
            f"(Rs. {mean_price:,.0f}). Not the cheapest, but reasonable."
        )
    elif percentile <= 85:
        label = "Above Average"
        emoji = "🟠"
        color = "amber"
        explanation = (
            f"🟠 **Above Average.** Rs. {best_price:,.0f} is {deviation_pct:.0f}% above "
            f"the market average. Consider cheaper alternatives."
        )
    else:
        label = "Overpriced"
        emoji = "🔴"
        color = "red"
        explanation = (
            f"🔴 **Overpriced.** Rs. {best_price:,.0f} is in the top {100 - int(percentile)}% "
            f"of prices — {deviation_pct:.0f}% above market average (Rs. {mean_price:,.0f}). "
            f"Cheapest available: Rs. {min_price:,.0f}."
        )

    return {
        "label": label,
        "emoji": emoji,
        "color": color,
        "percentile": round(percentile, 1),
        "avg_market_price": round(mean_price, 2),
        "min_price": round(min_price, 2),
        "max_price": round(max_price, 2),
        "deviation_pct": round(deviation_pct, 1),
        "explanation": explanation,
    }


# ── Demand Trend ────────────────────────────────────────────────────────────

def _build_demand_trend(options: list[dict], query: str) -> dict:
    """
    Estimate demand/popularity using store count, price spread, and
    historical data as proxy signals.
    """
    from services.price_history_service import get_trend

    n_stores = len(options)
    prices = [o.get("product_price", 0) for o in options if o.get("product_price", 0) > 0]

    # Get historical trend if available
    trend = get_trend(query) if query else {"direction": "unknown", "data_points": 0}
    historical_dir = trend.get("direction", "unknown")
    data_points = trend.get("data_points", 0)

    # Proxy signals for demand
    # More stores carrying it = higher demand
    # Rising prices = high demand, falling = declining
    # High price variance = active market
    demand_score = 0

    # Store availability signal
    if n_stores >= 8:
        demand_score += 3
    elif n_stores >= 5:
        demand_score += 2
    elif n_stores >= 3:
        demand_score += 1

    # Historical trend signal
    if historical_dir == "rising":
        demand_score += 2
    elif historical_dir == "stable":
        demand_score += 1
    elif historical_dir == "falling":
        demand_score -= 1

    # Price competition signal (tight prices = competitive demand)
    if len(prices) >= 2:
        import statistics as stats
        cv = stats.stdev(prices) / stats.mean(prices) if stats.mean(prices) else 0
        if cv < 0.10:
            demand_score += 1  # Tight pricing = high demand keeping prices competitive
        elif cv > 0.25:
            demand_score -= 1  # Wide variance = fragmented/uncertain market

    # Classify
    if demand_score >= 4:
        level = "High Demand"
        emoji = "🔥"
        color = "green"
    elif demand_score >= 2:
        level = "Stable Demand"
        emoji = "📊"
        color = "blue"
    elif demand_score >= 0:
        level = "Moderate"
        emoji = "➡️"
        color = "amber"
    else:
        level = "Declining"
        emoji = "📉"
        color = "red"

    signals = []
    signals.append(f"Available at {n_stores} store{'s' if n_stores != 1 else ''}")
    if data_points > 0:
        signals.append(f"Price trend: {historical_dir} ({data_points} data points)")
    if len(prices) >= 2:
        import statistics as stats
        cv = stats.stdev(prices) / stats.mean(prices) * 100 if stats.mean(prices) else 0
        signals.append(f"Price variance: {cv:.0f}%")

    return {
        "level": level,
        "emoji": emoji,
        "color": color,
        "score": demand_score,
        "signals": signals,
        "explanation": f"{emoji} **{level}** — {'. '.join(signals)}.",
    }


# ── Model Comparison ─────────────────────────────────────────────────────────

def _build_model_comparison(options: list[dict], best: dict) -> list[dict]:
    """
    Compare the top 3 options side-by-side for easy decision making.
    Shows product name, store, price, distance, total cost, and a value label.
    """
    if len(options) < 2:
        return []

    # Get top options by different criteria
    by_total = sorted(options, key=lambda o: o.get("grand_total", float("inf")))
    by_price = sorted(options, key=lambda o: o.get("product_price", float("inf")))
    by_dist = sorted(options, key=lambda o: o.get("distance_km", float("inf")))

    # Collect unique top options (up to 3)
    seen_ids = set()
    compared = []

    for item in [by_total[0], by_price[0], by_dist[0]]:
        bid = item.get("branch_id", id(item))
        if bid not in seen_ids:
            seen_ids.add(bid)
            compared.append(item)
        if len(compared) >= 3:
            break

    # Fill up to 3 with next-best totals
    for item in by_total[1:]:
        if len(compared) >= 3:
            break
        bid = item.get("branch_id", id(item))
        if bid not in seen_ids:
            seen_ids.add(bid)
            compared.append(item)

    best_id = best.get("branch_id")
    result = []
    for item in compared:
        is_recommended = item.get("branch_id") == best_id

        # Determine tag
        if item.get("branch_id") == by_total[0].get("branch_id"):
            tag = "🏆 Best Overall"
        elif item.get("branch_id") == by_price[0].get("branch_id"):
            tag = "💰 Cheapest"
        elif item.get("branch_id") == by_dist[0].get("branch_id"):
            tag = "📍 Nearest"
        else:
            tag = ""

        result.append({
            "store": item.get("branch_name", "Unknown"),
            "product": item.get("product", ""),
            "item_price": item.get("product_price", 0),
            "travel_cost": item.get("travel_cost", 0),
            "total_cost": item.get("grand_total", 0),
            "distance_km": item.get("distance_km", 0),
            "duration_min": item.get("duration_min", 0),
            "rating": item.get("product_rating", 0),
            "tag": tag,
            "recommended": is_recommended,
        })

    return result


# ── Risk Warnings ────────────────────────────────────────────────────────────

def _build_risk_warnings(best: dict, options: list[dict]) -> list[dict]:
    """
    Identify and flag potential risks to help users avoid bad decisions.
    """
    warnings = []

    # Risk: Very low product rating
    product_rating = float(best.get("product_rating", 0))
    if 0 < product_rating < 3.0:
        warnings.append({
            "level": "high",
            "emoji": "🔴",
            "title": "Low Product Rating",
            "detail": (
                f"This product has a {product_rating:.1f}/5 rating. "
                f"Consider alternatives with better reviews."
            ),
        })
    elif 0 < product_rating < 3.5:
        warnings.append({
            "level": "medium",
            "emoji": "🟠",
            "title": "Below Average Rating",
            "detail": f"Rating is {product_rating:.1f}/5 — check user reviews carefully before buying.",
        })

    # Risk: Store has low rating
    store_rating = float(best.get("rating", 0))
    if 0 < store_rating < 3.0:
        warnings.append({
            "level": "medium",
            "emoji": "🟠",
            "title": "Low Store Rating",
            "detail": (
                f"The recommended store has a {store_rating:.1f}/5 rating. "
                f"Consider buying from a higher-rated store even if slightly pricier."
            ),
        })

    # Risk: Price outlier (recommended price way above cheapest)
    prices = [o.get("product_price", 0) for o in options if o.get("product_price", 0) > 0]
    best_price = best.get("product_price", 0)
    if prices and best_price > 0:
        cheapest = min(prices)
        if cheapest > 0 and ((best_price - cheapest) / cheapest) > 0.30:
            warnings.append({
                "level": "medium",
                "emoji": "🟡",
                "title": "Price Premium",
                "detail": (
                    f"This costs Rs. {best_price:,.0f} vs the cheapest option at "
                    f"Rs. {cheapest:,.0f} ({((best_price - cheapest) / cheapest) * 100:.0f}% more). "
                    f"The difference is justified by lower travel costs."
                ),
            })

    # Risk: Very few store options
    if len(options) <= 1:
        warnings.append({
            "level": "medium",
            "emoji": "🟡",
            "title": "Limited Options",
            "detail": "Only 1 store carries this product. Cannot verify fair pricing — shop cautiously.",
        })

    # Risk: Very high travel cost proportion
    total = best.get("grand_total", 0)
    travel = best.get("travel_cost", 0)
    if total > 0 and (travel / total) > 0.40:
        warnings.append({
            "level": "medium",
            "emoji": "🟡",
            "title": "High Travel Cost",
            "detail": (
                f"Travel costs make up {(travel / total) * 100:.0f}% of your total spend. "
                f"Check if online purchase or delivery is available."
            ),
        })

    return warnings


# ── Buying Advice ────────────────────────────────────────────────────────────

def _build_buying_advice(
    best: dict, cheapest: dict, nearest: dict,
    options: list[dict], query: str, prefs: dict,
) -> dict:
    """
    Generate a human-friendly buying recommendation: Buy Now, Wait, or Switch.
    Combines all analysis signals into a final verdict.
    """
    from services.price_history_service import get_trend
    import statistics as stats

    prices = [o.get("product_price", 0) for o in options if o.get("product_price", 0) > 0]
    best_price = best.get("product_price", 0)
    product_rating = float(best.get("product_rating", 0))
    trend = get_trend(query) if query else {"direction": "unknown"}
    trend_dir = trend.get("direction", "unknown")

    # Decision factors
    buy_score = 0  # Positive = buy now, negative = wait/switch
    reasons = []

    # Factor 1: Price position
    if prices:
        mean_p = stats.mean(prices)
        if best_price <= mean_p * 0.85:
            buy_score += 2
            reasons.append("Price is well below market average")
        elif best_price <= mean_p:
            buy_score += 1
            reasons.append("Price is at or below market average")
        else:
            buy_score -= 1
            reasons.append("Price is above market average")

    # Factor 2: Price trend
    if trend_dir == "falling":
        buy_score -= 1
        reasons.append("Historical prices are trending down — waiting may save money")
    elif trend_dir == "rising":
        buy_score += 2
        reasons.append("Prices are rising — buying sooner is better")
    elif trend_dir == "stable":
        buy_score += 1
        reasons.append("Prices have been stable")

    # Factor 3: Product quality
    if product_rating >= 4.0:
        buy_score += 1
        reasons.append(f"Good product rating ({product_rating:.1f}/5)")
    elif 0 < product_rating < 3.0:
        buy_score -= 2
        reasons.append(f"Poor product rating ({product_rating:.1f}/5) — consider alternatives")

    # Factor 4: Competition
    n_stores = len(options)
    if n_stores >= 5:
        buy_score += 1
        reasons.append(f"Healthy competition ({n_stores} stores)")
    elif n_stores <= 1:
        buy_score -= 1
        reasons.append("Very few options available — hard to verify fair price")

    # Factor 5: Travel efficiency
    total = best.get("grand_total", 0)
    travel = best.get("travel_cost", 0)
    if total > 0 and (travel / total) < 0.10:
        buy_score += 1
        reasons.append("Low travel cost — efficient purchase")

    # Factor 6: User preferences
    if prefs.get("price_sensitivity") == "high" and prices:
        if best_price > stats.mean(prices):
            buy_score -= 1
            reasons.append("You indicated high price sensitivity — look for cheaper options")

    # Build verdict
    if buy_score >= 4:
        action = "Buy Now"
        emoji = "✅"
        color = "green"
        headline = "Strong buy — this is an excellent deal you shouldn't miss!"
    elif buy_score >= 2:
        action = "Buy Now"
        emoji = "👍"
        color = "green"
        headline = "Good time to buy — solid value for your money."
    elif buy_score >= 0:
        action = "Consider Carefully"
        emoji = "🤔"
        color = "amber"
        headline = "Decent option, but weigh the alternatives before deciding."
    elif buy_score >= -2:
        action = "Wait or Compare"
        emoji = "⏳"
        color = "amber"
        headline = "You might benefit from waiting or checking alternatives."
    else:
        action = "Don't Buy"
        emoji = "🚫"
        color = "red"
        headline = "This doesn't look like a good deal. Look elsewhere."

    # Alternative suggestion
    alternative = None
    if best.get("branch_id") != cheapest.get("branch_id"):
        alt_saving = best.get("product_price", 0) - cheapest.get("product_price", 0)
        if alt_saving > 0:
            alternative = {
                "store": cheapest.get("branch_name", ""),
                "price": cheapest.get("product_price", 0),
                "savings": round(alt_saving, 2),
                "note": f"Cheapest at Rs. {cheapest.get('product_price', 0):,.0f} (save Rs. {alt_saving:,.0f} on item price)",
            }

    return {
        "action": action,
        "emoji": emoji,
        "color": color,
        "headline": headline,
        "reasons": reasons,
        "confidence": min(100, abs(buy_score) * 20 + 40),
        "alternative": alternative,
    }



