"""
app.py — Pakistan Electronics Intelligence — API Server
────────────────────────────────────────────────────────
Electronics-only. 30+ Pakistani stores. Distance/fuel/route optimization.
"""
from __future__ import annotations

# load environment variables from .env (python-dotenv already in requirements)
from dotenv import load_dotenv
load_dotenv()

import re
import threading
import time
from collections import Counter
from typing import Any

import requests
from flask import Flask, jsonify, request, render_template
from config import BRANCHES, CATEGORY_META, STORES, PHYSICAL_STORES, ONLINE_STORES
from scrapers import fetch_category
from services.prediction_service import rank_branches
from services.decision_service import recommend

app = Flask(__name__)

@app.after_request
def cors_headers(response):
    response.headers['Access-Control-Allow-Origin']  = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-User-Id'
    response.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
    return response

# ─── In-memory product cache  ─────────────────────────────────────────────────
_cache: dict[str, list[dict]] = {}
_cache_lock = threading.Lock()

_STORE_FILTERS = {"all", "physical", "online"}
_NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
_NOMINATIM_REVERSE_URL = "https://nominatim.openstreetmap.org/reverse"
_NOMINATIM_HEADERS = {
    "User-Agent": "price-intelligence/1.0 (location-api)",
    "Accept": "application/json",
}
_IP_GEO_PROVIDERS = [
    {
        "name": "ipapi",
        "url": "https://ipapi.co/json/",
        "lat_key": "latitude",
        "lon_key": "longitude",
        "city_key": "city",
        "region_key": "region",
        "country_key": "country_name",
    },
    {
        "name": "ipinfo",
        "url": "https://ipinfo.io/json",
        "loc_key": "loc",
        "city_key": "city",
        "region_key": "region",
        "country_key": "country",
    },
    {
        "name": "ip-api",
        "url": "http://ip-api.com/json",
        "lat_key": "lat",
        "lon_key": "lon",
        "city_key": "city",
        "region_key": "regionName",
        "country_key": "country",
    },
]
_AI_INSIGHTS_CACHE_TTL_SECONDS = 120
_AI_INSIGHTS_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_AI_INSIGHTS_CACHE_LOCK = threading.Lock()
_DEFAULT_INSIGHTS_LAT = 33.6844
_DEFAULT_INSIGHTS_LON = 73.0479

_CATEGORY_HINTS = {
    "laptop": {"laptop", "notebook", "macbook", "thinkpad", "vivobook", "ideapad", "inspiron", "xps", "nitro", "alienware"},
    "mobile": {"mobile", "phone", "smartphone", "iphone", "galaxy", "redmi", "realme", "qmobile", "oppo", "vivo", "pixel", "infinix", "tecno", "itel", "nokia"},
    "tv": {"tv", "television", "oled", "qled", "bravia", "uhd"},
    "tablet": {"tablet", "ipad", "tab"},
    "headphone": {"headphone", "headphones", "earbuds", "airpods", "buds"},
    "smartwatch": {"watch", "smartwatch", "wearable"},
    "console": {"console", "playstation", "ps5", "xbox"},
}
_CATEGORY_ALIASES = {
    "phone": "mobile",
    "smartphone": "mobile",
    "cellphone": "mobile",
    "cell phone": "mobile",
    "television": "tv",
    "notebook": "laptop",
    "watch": "smartwatch",
    "paint": "paints",
    "paints": "paints",
}
_USE_CASE_HINTS = {
    "gaming": {"gaming", "rtx", "gtx", "playstation", "xbox", "gpu"},
    "office": {"office", "business", "productivity"},
    "study": {"study", "student", "school", "college"},
    "student": {"study", "student", "school", "college"},
}
_SCRAPER_QUERY_STOPWORDS = {
    "cheap",
    "best",
    "under",
    "below",
    "around",
    "for",
    "with",
    "the",
    "and",
    "or",
    "official",
    "pta",
    "price",
    "budget",
    "rs",
    "pkr",
    "buy",
    "shop",
    "near",
    "nearby",
    "closest",
    "me",
    "my",
    "area",
}
_RELEVANCE_IGNORE_TERMS = {
    "cheap",
    "best",
    "latest",
    "new",
    "price",
    "budget",
    "official",
    "pta",
    "under",
    "below",
    "around",
    "near",
    "nearby",
    "nearest",
    "closest",
    "me",
    "my",
    "area",
    "buy",
    "shop",
    "for",
    "with",
    "the",
    "and",
    "or",
    "in",
    "to",
}
_LOCATION_INTENT_PHRASES = {
    "near me",
    "nearby",
    "closest",
    "near",
    "around me",
    "around",
    "in my area",
    "in my city",
    "close to me",
}
_SHORT_CORE_TOKENS = {"tv", "ac", "pc"}


def _get_products(category: str = "electronics", max_pages: int = 2, query: str = None) -> list[dict]:
    category_key = (category or "electronics").strip().lower()
    query_key = " ".join((query or "").strip().lower().split())
    cache_key = f"{category_key}|p{max_pages}|{query_key or 'all'}"
    with _cache_lock:
        if cache_key not in _cache:
            results = fetch_category(category_key, max_pages, query=query)
            # if query-specific scrape returned nothing, try broad fetch
            if (not results or len(results) == 0) and query:
                try:
                    results = fetch_category(category_key, max_pages, query=None)
                except Exception:
                    pass
            _cache[cache_key] = results
        return _cache[cache_key]


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _build_location_label(city: str | None, region: str | None, country: str | None) -> str:
    parts = [p for p in [city, region, country] if p]
    return ", ".join(parts) if parts else ""


def _fetch_ip_geolocation() -> dict | None:
    headers = {
        "User-Agent": "price-intelligence/1.0 (ip-geo)",
        "Accept": "application/json",
    }
    for provider in _IP_GEO_PROVIDERS:
        try:
            response = requests.get(
                provider["url"],
                headers=headers,
                timeout=(0.8, 1.6),
            )
            response.raise_for_status()
            payload = response.json() or {}

            lat = payload.get(provider.get("lat_key")) if provider.get("lat_key") else None
            lon = payload.get(provider.get("lon_key")) if provider.get("lon_key") else None

            if provider.get("loc_key"):
                loc = str(payload.get(provider["loc_key"]) or "")
                if "," in loc:
                    parts = loc.split(",", 1)
                    lat = parts[0].strip()
                    lon = parts[1].strip()

            lat_f = _safe_float(lat)
            lon_f = _safe_float(lon)
            if lat_f is None or lon_f is None:
                continue

            city = str(payload.get(provider.get("city_key")) or "").strip()
            region = str(payload.get(provider.get("region_key")) or "").strip()
            country = str(payload.get(provider.get("country_key")) or "").strip()

            return {
                "lat": lat_f,
                "lon": lon_f,
                "display_name": _build_location_label(city, region, country),
                "source": provider.get("name"),
            }
        except Exception:
            continue
    return None


def _normalize_store_filter(value: str | None) -> str:
    token = str(value or "all").strip().lower()
    return token if token in _STORE_FILTERS else "all"


def _apply_store_filter(options: list[dict], store_filter: str) -> list[dict]:
    selected = _normalize_store_filter(store_filter)
    if selected == "all":
        return list(options)

    return [
        row for row in options
        if str((row.get("branch") or {}).get("type", "")).strip().lower() == selected
    ]


def _popular_products_for_suggestions(max_items: int = 300) -> list[dict]:
    """
    Build a fast product snapshot for suggestion ranking.
    Prefers in-memory cached products; falls back to a small warm fetch.
    """
    items: list[dict] = []
    seen: set[str] = set()

    with _cache_lock:
        cache_batches = list(_cache.values())

    for batch in cache_batches:
        for product in batch:
            name = str(product.get("product") or product.get("name") or "").strip()
            if not name:
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            items.append(product)
            if len(items) >= max_items:
                return items

    if items:
        return items

    try:
        warm = _get_products("electronics", max_pages=1, query=None)
        for product in warm:
            name = str(product.get("product") or product.get("name") or "").strip()
            if not name:
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            items.append(product)
            if len(items) >= max_items:
                break
    except Exception:
        pass

    return items


def _resolve_user_id(payload: dict[str, Any] | None = None) -> str:
    data = payload or {}
    candidates = [
        data.get("user_id"),
        request.headers.get("X-User-Id"),
        request.args.get("user_id"),
    ]
    for candidate in candidates:
        if candidate is None:
            continue
        text = str(candidate).strip()
        if text:
            return text[:128]
    return "anonymous"


def _query_to_scraper_terms(
    query: str,
    explicit_budget: float | None = None,
) -> tuple[str | None, dict | None, float | None]:
    query_text = _strip_location_phrases(query)
    if not query_text:
        return None, None, explicit_budget

    filters = None
    inferred_budget = explicit_budget

    try:
        from services.semantic_search_service import parse_user_query

        filters = parse_user_query(query_text)
    except Exception:
        filters = None

    if filters:
        category = _normalize_label(filters.get("category"), _CATEGORY_ALIASES)
        if category:
            filters["category"] = category

        if inferred_budget is None and filters.get("budget") is not None:
            budget_value = _safe_float(filters.get("budget"))
            if budget_value is not None and budget_value > 0:
                inferred_budget = budget_value

        semantic_query = _build_scraper_query(query_text, filters)
        return semantic_query or query_text, filters, inferred_budget

    return query_text, None, inferred_budget


def _normalize_label(value: str | None, aliases: dict[str, str]) -> str | None:
    if not value:
        return None
    text = " ".join(str(value).strip().lower().split())
    return aliases.get(text, text) or None


def _strip_location_phrases(text: str | None) -> str:
    cleaned = " ".join(str(text or "").strip().split())
    if not cleaned:
        return ""
    lowered = cleaned.lower()
    for phrase in _LOCATION_INTENT_PHRASES:
        if phrase in lowered:
            pattern = re.compile(rf"\b{re.escape(phrase)}\b", re.IGNORECASE)
            lowered = pattern.sub(" ", lowered)
    lowered = re.sub(r"\s+", " ", lowered).strip()
    return lowered


def _tokenize(text: str | None) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(token) >= 2}


def _term_variants(term: str) -> set[str]:
    variants = {term}
    if term.endswith("s") and len(term) > 3:
        variants.add(term[:-1])
    elif len(term) > 2:
        variants.add(f"{term}s")
    return variants


def _query_core_terms(text: str | None, max_terms: int = 3) -> list[str]:
    terms: list[str] = []
    for token in re.findall(r"[a-z0-9]+", (text or "").lower()):
        if token in _SCRAPER_QUERY_STOPWORDS:
            continue
        if token.isdigit():
            continue
        if re.fullmatch(r"\d+(?:k|m|lakh|lac|crore|cr)?", token):
            continue
        if any(ch.isdigit() for ch in token):
            continue
        if len(token) < 3 and token not in _SHORT_CORE_TOKENS:
            continue
        if token not in terms:
            terms.append(token)
        if len(terms) >= max_terms:
            break
    return terms


def _extract_price(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        price = float(value)
        return price if price > 0 else None
    text = str(value).replace(",", "")
    match = re.search(r"\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        price = float(match.group())
        return price if price > 0 else None
    except ValueError:
        return None


def _build_scraper_query(original_query: str, filters: dict | None) -> str:
    cleaned_original = _strip_location_phrases(original_query)
    cleaned_original = " ".join(cleaned_original.split())
    core_terms = _query_core_terms(cleaned_original)
    if core_terms:
        return " ".join(core_terms)

    if not filters:
        return cleaned_original

    category = _normalize_label(filters.get("category"), _CATEGORY_ALIASES)
    use_case = _normalize_label(filters.get("use_case"), {})
    query_terms: list[str] = []
    if use_case:
        query_terms.extend(use_case.split())
    if category:
        query_terms.extend(category.split())

    semantic_query = " ".join(dict.fromkeys(term for term in query_terms if term))
    if semantic_query:
        return semantic_query

    # Fall back to a best-effort short category token so queries like "tv near me"
    # still scrape relevant items.
    category_hint = _guess_query_category(cleaned_original, filters)
    if category_hint and category_hint != "electronics":
        return category_hint

    return cleaned_original


def _semantic_terms(filters: dict | None) -> set[str]:
    if not filters:
        return set()

    terms = set()
    category = _normalize_label(filters.get("category"), _CATEGORY_ALIASES)
    use_case = _normalize_label(filters.get("use_case"), {})

    if category:
        terms.update(_tokenize(category))
        terms.update(_CATEGORY_HINTS.get(category, set()))
    if use_case:
        terms.update(_tokenize(use_case))
        terms.update(_USE_CASE_HINTS.get(use_case, set()))

    return terms


def _query_relevance_terms(text: str) -> set[str]:
    terms: set[str] = set()
    for token in re.findall(r"[a-z0-9]+", (text or "").lower()):
        if token in _RELEVANCE_IGNORE_TERMS:
            continue
        if re.fullmatch(r"\d+(?:k|m|lakh|lac|crore|cr)?", token):
            continue
        if len(token) < 2:
            continue
        terms.add(token)
    return terms


def _filter_relevant_products(
    products: list[dict],
    query: str,
    filters: dict | None,
) -> list[dict]:
    query_text = str(query or "").strip().lower()
    if not query_text:
        return list(products)

    query_terms = _query_relevance_terms(query_text)
    semantic_terms = _semantic_terms(filters)
    category = _normalize_label(filters.get("category"), _CATEGORY_ALIASES) if filters else None

    if not query_terms and not semantic_terms and not category:
        return []

    scored: list[tuple[float, dict]] = []
    for product in products:
        name = str(product.get("product") or product.get("name") or "").strip().lower()
        if not name:
            continue

        name_terms = _tokenize(name)
        if not name_terms:
            continue

        # **STRICT MATCHING**: when query consists of a single token or a
        # phrase, require that token/phrase appears as a standalone word in
        # the product name.  This prevents "tv" from matching "cctv" and keeps
        # results tightly aligned with the user’s intent.
        if query_text and query_terms:
            # word boundary check for single-term queries to avoid "tv" -> "cctv"
            if len(query_terms) == 1:
                term = next(iter(query_terms))
                variants = _term_variants(term)
                if not any(re.search(rf"\b{re.escape(v)}\b", name) for v in variants if v):
                    # if no exact boundary match, skip this product entirely
                    continue

        query_overlap = len(name_terms & query_terms) if query_terms else 0
        semantic_overlap = len(name_terms & semantic_terms) if semantic_terms else 0

        category_match = True
        if category:
            category_match = _infer_product_category(name) == category

        if query_terms and query_overlap == 0 and semantic_overlap == 0:
            continue
        if category and not category_match and semantic_overlap == 0:
            continue

        rating = _safe_float(product.get("rating")) or 0.0
        score = (query_overlap * 3.0) + (semantic_overlap * 2.0) + (1.0 if category_match else 0.0) + (min(rating, 5.0) * 0.1)
        scored.append((score, product))

    if not scored:
        return []

    scored.sort(key=lambda row: row[0], reverse=True)
    return [row[1] for row in scored]


def _apply_budget_filter(products: list[dict], budget: int | float | None) -> list[dict]:
    if budget is None:
        return products

    filtered: list[dict] = []
    for product in products:
        price = _extract_price(product.get("price"))
        if price is None or price <= float(budget):
            filtered.append(product)
    return filtered


def _rank_products(products: list[dict], query: str, filters: dict | None) -> list[dict]:
    products = _filter_relevant_products(products, query, filters)
    query_terms = _tokenize(query)
    semantic_terms = _semantic_terms(filters)
    budget = filters.get("budget") if filters else None

    def score(product: dict) -> float:
        name_terms = _tokenize(product.get("product") or product.get("name"))
        rating = float(product.get("rating") or 0)
        price = _extract_price(product.get("price"))

        query_overlap = len(name_terms & query_terms)
        semantic_overlap = len(name_terms & semantic_terms)

        rank_score = (query_overlap * 2.0) + (semantic_overlap * 3.0) + (min(rating, 5.0) * 0.35)

        if budget is not None and price is not None:
            if price <= float(budget):
                # Encourage results closer to user budget ceiling.
                budget_fit = 1.0 - ((float(budget) - price) / max(float(budget), 1.0))
                rank_score += 1.5 + max(0.0, budget_fit)
            else:
                rank_score -= 2.0

        if price is not None:
            rank_score += max(0.0, 1.2 - (price / 1_000_000.0))

        return rank_score

    return sorted(
        products,
        key=lambda p: (-score(p), _extract_price(p.get("price")) or float("inf")),
    )


def _infer_product_category(product_name: str) -> str:
    tokens = _tokenize(product_name)
    if not tokens:
        return "electronics"

    best_category = "electronics"
    best_score = 0
    for category, keywords in _CATEGORY_HINTS.items():
        score = len(tokens & keywords)
        if score > best_score:
            best_score = score
            best_category = category
    return best_category


def _category_display_name(category: str) -> str:
    label = str(category or "electronics").strip().lower()
    if not label:
        return "Electronics"
    if label == "tv":
        return "TV"
    return label.replace("_", " ").title()


def _guess_query_category(query: str, filters: dict | None) -> str:
    if filters:
        category = _normalize_label(filters.get("category"), _CATEGORY_ALIASES)
        if category:
            return category
    return _infer_product_category(_strip_location_phrases(query) or "")


def _filter_products_by_category(products: list[dict], category: str | None) -> list[dict]:
    if not category or category == "electronics":
        return list(products)
    filtered = []
    for product in products:
        name = str(product.get("product") or product.get("name") or "").strip()
        if not name:
            continue
        if _infer_product_category(name) != category:
            continue
        filtered.append(product)
    return filtered


def _fallback_category_products(
    query: str,
    filters: dict | None,
    budget_value: float | None,
    max_items: int = 8,
) -> tuple[str, list[dict]]:
    category = _guess_query_category(query, filters)
    products = _get_products("electronics", max_pages=1, query=None)
    products = _filter_products_by_category(products, category)
    if budget_value is not None:
        products = _apply_budget_filter(products, budget_value)
    if not products:
        return category, []
    ranked = _rank_products(products, "", {"category": category})
    return category, ranked[:max_items]


def _wiki_suggestions(query: str, limit: int = 4) -> list[str]:
    query = str(query or "").strip()
    if len(query) < 2:
        return []
    try:
        response = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "opensearch",
                "search": query,
                "limit": max(1, min(8, limit)),
                "namespace": 0,
                "format": "json",
            },
            headers={"User-Agent": "price-intelligence/1.0 (wiki-suggest)"},
            timeout=(0.8, 1.6),
        )
        response.raise_for_status()
        payload = response.json() or []
        titles = payload[1] if isinstance(payload, list) and len(payload) > 1 else []
        if not isinstance(titles, list):
            return []
        cleaned = []
        for title in titles:
            label = str(title).strip()
            if label and len(label) <= 80:
                cleaned.append(label)
        return cleaned
    except Exception:
        return []


def _build_search_suggestions(query: str, category: str | None, limit: int = 7) -> list[str]:
    try:
        from services.search_suggestion_service import generate_search_suggestions
    except Exception:
        generate_search_suggestions = None

    suggestions: list[str] = []
    if generate_search_suggestions:
        popular = _popular_products_for_suggestions(max_items=350)
        suggestions = generate_search_suggestions(query=query, popular_products=popular, limit=limit) or []

    wiki = _wiki_suggestions(query, limit=4)
    combined = []
    seen = set()
    for item in suggestions + wiki:
        key = str(item).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        combined.append(str(item).strip())
        if len(combined) >= limit:
            break

    if category and category != "electronics":
        filtered = []
        for item in combined:
            if _infer_product_category(item) == category:
                filtered.append(item)
        combined = filtered or combined

    return combined[:limit]


def _search_scope_message() -> str:
    categories = [
        _category_display_name(cat)
        for cat in sorted(_CATEGORY_HINTS.keys())
        if cat != "electronics"
    ]
    if not categories:
        return "This site focuses on electronics only."
    scope = ", ".join(categories)
    return f"Best results are for: {scope}. You can also try broader electronics searches."


_CHAT_SEARCH_GUIDANCE_PATTERNS = [
    r"\bwhat should i search\b",
    r"\bwhat do i search\b",
    r"\bwhat to search\b",
    r"\bwhat should i type\b",
    r"\bsearch now\b",
    r"\bcopy paste\b",
    r"\bcopy-paste\b",
    r"\bexactly search\b",
    r"\bexact search\b",
]
_CHAT_CASE_MAP = {
    "iphone": "iPhone",
    "ipad": "iPad",
    "macbook": "MacBook",
    "s24": "S24",
    "s23": "S23",
    "s22": "S22",
    "s21": "S21",
    "a15": "A15",
    "a14": "A14",
    "tv": "TV",
    "uhd": "UHD",
    "oled": "OLED",
    "qled": "QLED",
    "4k": "4K",
    "5g": "5G",
    "gb": "GB",
}
_CHAT_QUERY_STOPWORDS = {
    "tell",
    "me",
    "what",
    "should",
    "search",
    "type",
    "exactly",
    "best",
    "results",
    "for",
    "now",
    "please",
    "get",
    "give",
    "copy",
    "paste",
    "recommend",
}


def _split_chat_context(text: str) -> tuple[str, str | None]:
    raw = str(text or "").strip()
    if not raw:
        return "", None
    marker = "\nContext:"
    if marker in raw:
        before, _, after = raw.partition(marker)
        return before.strip(), after.strip() or None
    if "Context:" in raw:
        before, _, after = raw.partition("Context:")
        return before.strip(), after.strip() or None
    return raw, None


def _is_search_guidance_query(text: str) -> bool:
    if not text:
        return False
    lowered = text.strip().lower()
    return any(re.search(pattern, lowered) for pattern in _CHAT_SEARCH_GUIDANCE_PATTERNS)


def _format_query_label(text: str) -> str:
    tokens = [t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if t]
    if not tokens:
        return ""
    out = []
    for token in tokens:
        if token in _CHAT_CASE_MAP:
            out.append(_CHAT_CASE_MAP[token])
        elif token.isdigit():
            out.append(token)
        else:
            out.append(token.capitalize())
    return " ".join(out)


def _extract_product_phrase(text: str) -> str:
    tokens = [t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if t]
    cleaned = []
    for token in tokens:
        if token in _CHAT_QUERY_STOPWORDS:
            continue
        if token in _RELEVANCE_IGNORE_TERMS:
            continue
        cleaned.append(token)
    return " ".join(cleaned).strip()


def _compose_chat_message(
    user_query: str,
    recommended_product: str | None,
    alternatives: list[str],
    reason: str | None,
    suggestions: list[str],
    scope: str | None,
    no_match: bool,
    intent_search: bool,
) -> str:
    cleaned_query = _strip_location_phrases(user_query)
    if intent_search:
        candidates = []
        base_phrase = _extract_product_phrase(cleaned_query)
        if base_phrase:
            formatted = _format_query_label(base_phrase)
            if formatted:
                candidates.append(formatted)
        for item in suggestions:
            if item and item not in candidates:
                candidates.append(item)
        candidates = candidates[:4]
        if candidates:
            quoted = ", ".join(f"\"{item}\"" for item in candidates)
            return f"**Try:** {quoted}."
        return "Try a shorter brand + model name, e.g., \"Samsung A15\" or \"Galaxy A15 128GB\"."

    parts: list[str] = []
    if no_match:
        parts.append("No exact match — showing the closest options.")
    if recommended_product:
        parts.append(f"**Top pick:** {recommended_product}.")
    if reason:
        parts.append(f"**Why:** {str(reason).strip()}")
    if alternatives:
        parts.append("**Other options:** " + "; ".join(alternatives[:3]) + ".")
    if suggestions:
        parts.append("**Try:** " + ", ".join(f"\"{s}\"" for s in suggestions[:4]) + ".")
    if not parts:
        return "I couldn't find enough detail yet. Try a shorter model name or a brand + series."
    return "\n\n".join(parts)


def _avg(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _build_ai_insights_payload(user_lat: float, user_lon: float) -> dict[str, Any]:
    from services.deal_detection_service import detect_deal
    from services.price_history_service import get_trend

    products = _get_products("electronics", max_pages=1, query=None)
    if not products:
        return {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "trending_products": [],
            "biggest_price_drops": [],
            "best_deals_today": [],
            "popular_categories": [],
        }

    product_stats: dict[str, dict[str, Any]] = {}
    for product in products[:600]:
        name = str(product.get("product") or product.get("name") or "").strip()
        if not name:
            continue
        key = " ".join(name.lower().split())
        price = _extract_price(product.get("price"))
        reviews = _safe_float(product.get("reviews")) or 0.0
        rating = _safe_float(product.get("rating")) or 0.0
        category = _infer_product_category(name)

        if key not in product_stats:
            product_stats[key] = {
                "product": name,
                "prices": [],
                "ratings": [],
                "reviews": [],
                "mentions": 0,
                "stores": set(),
                "category": category,
            }

        row = product_stats[key]
        row["mentions"] += 1
        if price is not None:
            row["prices"].append(price)
        if rating > 0:
            row["ratings"].append(rating)
        if reviews > 0:
            row["reviews"].append(reviews)
        store_name = str(product.get("source_store") or "").strip()
        if store_name:
            row["stores"].add(store_name)

    prediction_rows = rank_branches(
        float(user_lat),
        float(user_lon),
        "electronics",
        products,
        budget=None,
        priority="total_cost",
    )

    prediction_by_product: dict[str, dict[str, Any]] = {}
    for row in prediction_rows:
        product_name = str((row.get("best_product") or {}).get("product") or "").strip()
        if not product_name:
            continue
        key = " ".join(product_name.lower().split())
        prediction_by_product[key] = {
            "price_prediction": str(row.get("price_prediction") or ""),
            "confidence": int(row.get("confidence") or 0),
            "reason": str(row.get("reason") or ""),
        }

    ranked_keys = sorted(
        product_stats.keys(),
        key=lambda k: (
            -int(product_stats[k]["mentions"]),
            -float(_avg(product_stats[k]["reviews"]) or 0.0),
            -float(_avg(product_stats[k]["ratings"]) or 0.0),
        ),
    )

    trending_products: list[dict[str, Any]] = []
    drops: list[dict[str, Any]] = []
    popular_categories_counter: Counter[str] = Counter()

    for key in ranked_keys[:140]:
        row = product_stats[key]
        avg_price = _avg(row["prices"])
        if avg_price is None or avg_price <= 0:
            continue

        product_name = row["product"]
        trend = get_trend(key)
        deal = detect_deal(key, avg_price)
        prediction = prediction_by_product.get(key, {})

        trend_direction = str(trend.get("direction") or "unknown")
        trend_conf = int(round(float(trend.get("confidence") or 0) * 100))
        mention_count = int(row["mentions"])
        category = str(row["category"] or "electronics")
        stores_count = len(row["stores"])
        avg_reviews = int(round(_avg(row["reviews"]) or 0.0))

        trend_score = mention_count * 1.0
        trend_score += min(6.0, (avg_reviews / 80.0))
        if trend_direction == "rising":
            trend_score += 3.0
        elif trend_direction == "stable":
            trend_score += 1.0
        elif trend_direction == "falling":
            trend_score -= 1.0
        if str(prediction.get("price_prediction")) == "likely increase":
            trend_score += 1.5

        trending_products.append(
            {
                "product": product_name,
                "trend": trend_direction if trend_direction != "unknown" else "stable",
                "confidence": max(35, trend_conf) if trend_conf else max(35, int(prediction.get("confidence") or 0)),
                "avg_price": round(avg_price, 2),
                "stores": stores_count,
                "_score": round(trend_score, 4),
            }
        )

        if deal.get("deal_detected"):
            drops.append(
                {
                    "product": product_name,
                    "current_price": round(avg_price, 2),
                    "discount_percent": int(deal.get("discount_percent") or 0),
                    "ai_message": str(deal.get("ai_message") or ""),
                }
            )

        popular_categories_counter[category] += mention_count

    trending_products = sorted(
        trending_products,
        key=lambda row: (-(row.get("_score") or 0), row.get("avg_price") or float("inf")),
    )[:6]
    for item in trending_products:
        item.pop("_score", None)

    biggest_price_drops = sorted(
        drops,
        key=lambda row: (-int(row.get("discount_percent") or 0), row.get("current_price") or float("inf")),
    )[:6]

    best_deals_today: list[dict[str, Any]] = []
    for row in prediction_rows:
        if not row.get("deal_detected"):
            continue
        product_name = str((row.get("best_product") or {}).get("product") or "").strip()
        if not product_name:
            continue
        best_deals_today.append(
            {
                "product": product_name,
                "store": str((row.get("branch") or {}).get("name") or ""),
                "price": round(float(row.get("product_price") or 0), 2),
                "discount_percent": int(row.get("discount_percent") or 0),
                "price_prediction": str(row.get("price_prediction") or "likely stable"),
                "confidence": int(row.get("confidence") or 0),
                "ai_message": str(row.get("ai_message") or ""),
            }
        )

    best_deals_today = sorted(
        best_deals_today,
        key=lambda row: (-int(row.get("discount_percent") or 0), row.get("price") or float("inf")),
    )[:6]

    popular_categories = [
        {
            "category": _category_display_name(category),
            "count": count,
        }
        for category, count in popular_categories_counter.most_common(6)
    ]

    return {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "trending_products": trending_products,
        "biggest_price_drops": biggest_price_drops,
        "best_deals_today": best_deals_today,
        "popular_categories": popular_categories,
    }


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/categories")
def api_categories():
    return jsonify({
        "categories": [
            {"id": k, **v} for k, v in CATEGORY_META.items()
        ]
    })


@app.route("/api/branches")
def api_branches():
    return jsonify({"branches": BRANCHES})


@app.route("/api/stores")
def api_stores():
    """List all 30+ stores with type info."""
    return jsonify({
        "total": len(STORES),
        "physical_count": len(PHYSICAL_STORES),
        "online_count": len(ONLINE_STORES),
        "stores": STORES,
    })


@app.route("/ai-insights", methods=["GET"])
@app.route("/api/ai-insights", methods=["GET"])
def api_ai_insights():
    user_lat = _safe_float(request.args.get("user_lat")) or _DEFAULT_INSIGHTS_LAT
    user_lon = _safe_float(request.args.get("user_lon")) or _DEFAULT_INSIGHTS_LON
    refresh = str(request.args.get("refresh") or "").strip().lower() in {"1", "true", "yes", "on"}

    cache_key = f"{round(user_lat, 3)}|{round(user_lon, 3)}"
    now = time.time()

    if not refresh:
        with _AI_INSIGHTS_CACHE_LOCK:
            cached = _AI_INSIGHTS_CACHE.get(cache_key)
            if cached and cached[0] >= now:
                return jsonify(cached[1])

    try:
        payload = _build_ai_insights_payload(user_lat, user_lon)
        with _AI_INSIGHTS_CACHE_LOCK:
            _AI_INSIGHTS_CACHE[cache_key] = (now + float(_AI_INSIGHTS_CACHE_TTL_SECONDS), payload)
        return jsonify(payload)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@app.route("/api/location/suggest")
def api_location_suggest():
    query = (request.args.get("q") or "").strip()
    if len(query) < 2:
        return jsonify({"suggestions": []})

    try:
        limit = int(request.args.get("limit", 7))
    except (TypeError, ValueError):
        limit = 7
    limit = max(1, min(10, limit))

    try:
        # allow optional location bias (lat/lon) so that suggestions are
        # prioritised around the user's current position for local relevance.
        params = {
            "q": query,
            "format": "jsonv2",
            "limit": limit,
            "addressdetails": 1,
            "accept-language": "en",  # always return English-format names
        }
        lat = _safe_float(request.args.get("lat"))
        lon = _safe_float(request.args.get("lon"))
        if lat is not None and lon is not None:
            # create a small viewbox (0.5° ~50km) around coordinates
            delta = 0.5
            params["viewbox"] = f"{lon - delta},{lat + delta},{lon + delta},{lat - delta}"
            params["bounded"] = 1
        response = requests.get(
            _NOMINATIM_SEARCH_URL,
            params=params,
            headers=_NOMINATIM_HEADERS,
            timeout=(0.8, 2.2),
        )
        response.raise_for_status()
        raw_items = response.json() or []
    except Exception:
        return jsonify({"suggestions": []})

    suggestions: list[dict[str, Any]] = []
    for item in raw_items:
        lat = _safe_float(item.get("lat"))
        lon = _safe_float(item.get("lon"))
        if lat is None or lon is None:
            continue
        suggestions.append(
            {
                "display_name": str(item.get("display_name") or "").strip(),
                "lat": round(lat, 7),
                "lon": round(lon, 7),
                "type": str(item.get("type") or "location").strip(),
            }
        )

    return jsonify({"suggestions": suggestions})


@app.route("/api/location/reverse")
def api_location_reverse():
    lat = _safe_float(request.args.get("lat"))
    lon = _safe_float(request.args.get("lon"))
    if lat is None or lon is None:
        return jsonify({"error": "lat and lon are required"}), 400

    display_name = f"{lat:.6f}, {lon:.6f}"
    try:
        response = requests.get(
            _NOMINATIM_REVERSE_URL,
            params={
                "lat": lat,
                "lon": lon,
                "format": "jsonv2",
                "zoom": 16,
            },
            headers=_NOMINATIM_HEADERS,
            timeout=(0.8, 2.2),
        )
        response.raise_for_status()
        payload = response.json() or {}
        candidate = str(payload.get("display_name") or "").strip()
        if candidate:
            display_name = candidate
    except Exception:
        pass

    return jsonify(
        {
            "display_name": display_name,
            "lat": round(lat, 7),
            "lon": round(lon, 7),
        }
    )


@app.route("/api/location/ip")
def api_location_ip():
    payload = _fetch_ip_geolocation()
    if not payload:
        return jsonify({"error": "IP location unavailable"}), 503
    return jsonify(payload)


@app.route("/api/location/route")
def api_location_route():
    start_lat = _safe_float(request.args.get("start_lat"))
    start_lon = _safe_float(request.args.get("start_lon"))
    end_lat = _safe_float(request.args.get("end_lat"))
    end_lon = _safe_float(request.args.get("end_lon"))

    if start_lat is None or start_lon is None or end_lat is None or end_lon is None:
        return jsonify({"error": "start_lat, start_lon, end_lat, and end_lon are required"}), 400

    try:
        from config import OSRM_BASE_URL, OSRM_CONNECT_TIMEOUT_SECONDS, OSRM_READ_TIMEOUT_SECONDS

        base_url = (OSRM_BASE_URL or "").strip().rstrip("/")
        if not base_url:
            raise ValueError("OSRM base URL is not configured")

        url = f"{base_url}/route/v1/driving/{start_lon},{start_lat};{end_lon},{end_lat}"
        params = {"overview": "full", "geometries": "geojson"}
        timeout = (
            max(0.3, float(OSRM_CONNECT_TIMEOUT_SECONDS)),
            max(0.6, float(OSRM_READ_TIMEOUT_SECONDS)),
        )
        response = requests.get(url, params=params, timeout=timeout)
        response.raise_for_status()
        payload = response.json() or {}
        routes = payload.get("routes") or []
        if not routes:
            raise ValueError("OSRM response missing routes")

        route = routes[0] or {}
        geometry = (route.get("geometry") or {}).get("coordinates") or []
        if not geometry:
            raise ValueError("OSRM response missing geometry")

        points = [[lat, lon] for lon, lat in geometry]
        distance_km = float(route.get("distance", 0.0)) / 1000.0
        duration_min = float(route.get("duration", 0.0)) / 60.0
        return jsonify({
            "geometry": points,
            "distance_km": round(distance_km, 2),
            "duration_min": round(duration_min, 1),
            "via": "osrm",
        })
    except Exception:
        from utils.location_utils import calculate_haversine_distance

        fallback = calculate_haversine_distance(start_lat, start_lon, end_lat, end_lon)
        return jsonify({
            "geometry": [[start_lat, start_lon], [end_lat, end_lon]],
            "distance_km": fallback["distance_km"],
            "duration_min": fallback["duration_min"],
            "via": "haversine_estimate",
        })


@app.route("/api/products/electronics")
@app.route("/api/products/<category>")
def api_products(category: str = "electronics"):
    pages = max(1, _safe_int(request.args.get("pages"), 2))
    try:
        products = _get_products("electronics", pages)
        return jsonify({
            "category": "electronics",
            "count":    len(products),
            "products": products,   # Return ALL products, no cap
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/scrape/electronics", methods=["POST"])
@app.route("/api/scrape/<category>", methods=["POST"])
def api_scrape(category: str = "electronics"):
    """Force-refresh the cache."""
    payload = request.get_json(silent=True) or {}
    pages = max(1, _safe_int(payload.get("pages"), 2))
    try:
        with _cache_lock:
            _cache.clear()
            cache_key = f"electronics|p{pages}|all"
            _cache[cache_key] = fetch_category("electronics", pages)
        return jsonify({"status": "ok", "count": len(_cache[cache_key])})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/search/suggestions", methods=["GET"])
@app.route("/api/suggestions", methods=["GET"])
def api_search_suggestions():
    query = (request.args.get("q") or "").strip()
    limit = max(1, min(12, _safe_int(request.args.get("limit"), 8)))

    try:
        from services.search_suggestion_service import (
            generate_search_suggestions,
            track_search_query,
        )

        if query:
            track_search_query(query)

        products = _popular_products_for_suggestions(max_items=350)
        suggestions = generate_search_suggestions(
            query=query,
            popular_products=products,
            limit=limit,
        )

        return jsonify(
            {
                "query": query,
                "suggestions": suggestions,
            }
        )
    except Exception as exc:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@app.route("/api/search", methods=["GET"])
def search_products():
    query = (request.args.get("q") or "").strip()
    if not query:
        return jsonify({"error": "No query provided"}), 400

    try:
        try:
            from services.search_suggestion_service import track_search_query

            track_search_query(query)
        except Exception:
            pass

        from services.semantic_search_service import parse_user_query

        # AI-first parse. If it fails, fallback to plain keyword search.
        filters = parse_user_query(query)
        search_mode = "semantic" if filters else "keyword"

        category = _normalize_label(filters.get("category"), _CATEGORY_ALIASES) if filters else None
        if category:
            filters["category"] = category

        scraper_query = _build_scraper_query(query, filters)
        scrape_cat = category or "electronics"
        results = _get_products(scrape_cat, max_pages=1, query=scraper_query)

        # Try a simpler semantic query before falling back to full raw keyword query.
        if filters and not results and category:
            # still search within same category, not force electronics
            results = _get_products(scrape_cat, max_pages=1, query=category)
            scraper_query = category

        fallback_type = None
        if not results:
            results = _get_products(scrape_cat, max_pages=1, query=query)
            fallback_type = "keyword_search"
            search_mode = "keyword"

        if filters:
            results = _apply_budget_filter(results, filters.get("budget"))

        ranked_results = _rank_products(results, query, filters)

        # if the initial ranking yielded nothing but we did receive raw
        # products (often due to scrapers returning generic data when the
        # query failed), retry with a relaxed match to avoid showing an
        # empty page.  This ensures searches like "mobile phones" still
        # return something even when no product name contains the exact
        # phrase.
        if not ranked_results and results:
            ranked_results = _rank_products(results, "", filters)
            if not fallback_type:
                fallback_type = "loose_matching"

        no_match = False
        category_guess = None
        suggestions: list[str] = []
        category_products: list[dict] = []
        if not ranked_results:
            category_guess, category_products = _fallback_category_products(query, filters, _safe_float(filters.get("budget")) if filters else None)
            if category_products:
                ranked_results = category_products
                fallback_type = fallback_type or "category_alternatives"
                no_match = True
            else:
                no_match = True
            suggestions = _build_search_suggestions(query, category_guess)

        payload = {
            "query": query,
            "count": len(ranked_results),
            "products": ranked_results,
            "search_mode": search_mode,
            "scraper_query": scraper_query,
        }
        if filters:
            payload["semantic_filters"] = filters
        if fallback_type:
            payload["fallback"] = fallback_type
        if no_match:
            payload["no_match"] = True
            payload["category"] = category_guess
            payload["category_label"] = _category_display_name(category_guess)
            payload["suggestions"] = suggestions
            payload["scope"] = _search_scope_message()
            if category_products:
                payload["category_products"] = category_products[:6]
        return jsonify(payload)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/compare", methods=["POST"])
@app.route("/api/compare", methods=["POST"])
def compare_products_api():
    data = request.get_json(silent=True) or {}
    product_a = str(data.get("product_a") or "").strip()
    product_b = str(data.get("product_b") or "").strip()

    if not product_a or not product_b:
        return jsonify({"error": "product_a and product_b are required"}), 400

    try:
        from services.comparison_service import compare_products

        result = compare_products(product_a, product_b)
        return jsonify(result)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@app.route("/api/optimize", methods=["POST"])
def api_optimize():
    """
    Find the best branch + product for a user's location.

    Body JSON:
      user_lat   float  (required)
      user_lon   float  (required)
      category   str    (optional, defaults to 'electronics')
      budget     float  (optional)
      priority   str    "total_cost" | "price" | "distance"  (optional)
      pages      int    (optional, default 2)
    """
    data = request.get_json(silent=True) or {}
    user_lat  = _safe_float(data.get("user_lat"))
    user_lon  = _safe_float(data.get("user_lon"))
    budget    = data.get("budget")
    priority  = data.get("priority", "total_cost")
    query     = str(data.get("query") or "").strip()
    query_clean = _strip_location_phrases(query)
    store_filter = _normalize_store_filter(data.get("store_filter"))
    pages     = max(1, _safe_int(data.get("pages"), 2))

    if user_lat is None or user_lon is None:
        return jsonify({"error": "user_lat and user_lon are required"}), 400

    try:
        if query:
            try:
                from services.search_suggestion_service import track_search_query

                track_search_query(query)
            except Exception:
                pass

        budget_value = _safe_float(budget)
        scraper_query, semantic_filters, budget_value = _query_to_scraper_terms(query_clean, budget_value)

        scrape_cat = semantic_filters.get("category") if semantic_filters else None
        scrape_cat = scrape_cat or "electronics"
        products = _get_products(scrape_cat, pages, query=scraper_query)
        if not products and query and scraper_query != query:
            products = _get_products(scrape_cat, pages, query=query)
        if budget_value is not None:
            products = _apply_budget_filter(products, budget_value)
        products = _filter_relevant_products(products, query_clean, semantic_filters)

        ranked   = rank_branches(
            user_lat, user_lon,
            "electronics", products,
            budget=budget_value,
            priority=priority,
        )
        ranked = _apply_store_filter(ranked, store_filter)

        category_guess = None
        fallback_products: list[dict] = []
        if not ranked:
            category_guess, fallback_products = _fallback_category_products(query_clean, semantic_filters, budget_value)
            if fallback_products:
                ranked = rank_branches(
                    user_lat, user_lon,
                    "electronics", fallback_products,
                    budget=budget_value,
                    priority=priority,
                )
                ranked = _apply_store_filter(ranked, store_filter)

        if not ranked:
            suggestions = _build_search_suggestions(query_clean, category_guess)
            return jsonify({
                "query": query,
                "all_options": [],
                "advice": [
                f"No exact match found for '{query}'.",
                    "Try a broader model name or remove extra keywords.",
                ],
                "no_match": True,
                "category": category_guess,
                "category_label": _category_display_name(category_guess),
                "suggestions": suggestions,
                "scope": _search_scope_message(),
                "category_products": fallback_products[:6] if fallback_products else [],
                "store_filter": store_filter,
            })

        decision = recommend(ranked, priority=priority)

        if semantic_filters:
            decision["semantic_filters"] = semantic_filters
        if scraper_query:
            decision["scraper_query"] = scraper_query
        decision["search_mode"] = "semantic" if semantic_filters else "keyword"
        decision["store_filter"] = store_filter
        decision["query"] = query
        if fallback_products:
            decision["no_match"] = True
            decision["fallback"] = "category_alternatives"
            decision["category"] = category_guess
            decision["category_label"] = _category_display_name(category_guess)
            decision["suggestions"] = _build_search_suggestions(query_clean, category_guess)
            decision["scope"] = _search_scope_message()
            decision["advice"] = (decision.get("advice") or []) + [
                f"No exact match found for '{query}'. Showing similar { _category_display_name(category_guess) } products.",
            ]

        return jsonify(decision)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@app.route("/api/multi-optimize", methods=["POST"])
def api_multi_optimize():
    """
    Multi-store optimization (kept for backward compatibility).
    Since we're electronics-only, this optimizes across stores.
    """
    data       = request.get_json(silent=True) or {}
    user_lat   = _safe_float(data.get("user_lat"))
    user_lon   = _safe_float(data.get("user_lon"))
    priority   = data.get("priority", "total_cost")
    query      = str(data.get("query") or "").strip()
    store_filter = _normalize_store_filter(data.get("store_filter"))

    if user_lat is None or user_lon is None:
        return jsonify({"error": "user_lat and user_lon are required"}), 400

    try:
        if query:
            try:
                from services.search_suggestion_service import track_search_query

                track_search_query(query)
            except Exception:
                pass

        scraper_query, semantic_filters, _ = _query_to_scraper_terms(query, None)
        scrape_cat = semantic_filters.get("category") if semantic_filters else None
        scrape_cat = scrape_cat or "electronics"
        products = _get_products(scrape_cat, 2, query=scraper_query)
        if not products and query and scraper_query != query:
            products = _get_products(scrape_cat, 2, query=query)
        products = _filter_relevant_products(products, query, semantic_filters)
        ranked   = rank_branches(
            user_lat, user_lon,
            "electronics", products, priority=priority,
        )
        ranked = _apply_store_filter(ranked, store_filter)
        decision = recommend(ranked, priority=priority)
        if scraper_query:
            decision["scraper_query"] = scraper_query
        decision["store_filter"] = store_filter
        return jsonify(decision)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@app.route("/api/intelligence", methods=["POST"])
def api_intelligence():
    data = request.get_json(silent=True) or {}
    user_lat = _safe_float(data.get("user_lat"))
    user_lon = _safe_float(data.get("user_lon"))
    if user_lat is None or user_lon is None:
        return jsonify({"error": "user_lat and user_lon are required"}), 400

    query = str(data.get("query") or "").strip()
    priority = str(data.get("priority") or "total_cost")
    store_filter = _normalize_store_filter(data.get("store_filter"))
    pages = max(1, _safe_int(data.get("pages"), 2))
    budget_value = _safe_float(data.get("budget"))
    user_id = _resolve_user_id(data)

    try:
        if query:
            try:
                from services.search_suggestion_service import track_search_query

                track_search_query(query)
            except Exception:
                pass

        from services.intelligence_service import generate_intelligence
        from services.user_profile_service import (
            get_user_preferences,
            track_search_history,
            track_viewed_products,
        )

        scraper_query, semantic_filters, budget_value = _query_to_scraper_terms(query, budget_value)
        scrape_cat = semantic_filters.get("category") if semantic_filters else None
        scrape_cat = scrape_cat or "electronics"
        products = _get_products(scrape_cat, pages, query=scraper_query)
        if not products and query and scraper_query != query:
            products = _get_products(scrape_cat, pages, query=query)
        if budget_value is not None:
            products = _apply_budget_filter(products, budget_value)

        # apply relevance filtering; if nothing remains but we did receive
        # some raw products, fall back to loosened matching so the user at
        # least sees something rather than a blank result set.
        raw_products = list(products)
        products = _filter_relevant_products(products, query, semantic_filters)
        fallback_type = None
        no_match = False
        category_guess = _guess_query_category(query, semantic_filters)

        if not products:
            # Prefer category-specific alternatives over loose matching for
            # category/intention queries (e.g., "tv near me").
            if category_guess and category_guess != "electronics":
                _, fallback_products = _fallback_category_products(query, semantic_filters, budget_value)
                if fallback_products:
                    products = fallback_products
                    fallback_type = "category_alternatives"
                    no_match = True
            # If still empty, use loose matching only for broad electronics queries.
            if not products and raw_products and (not category_guess or category_guess == "electronics"):
                products = raw_products
                fallback_type = "loose_matching"

        if not products:
            category_guess, fallback_products = _fallback_category_products(query, semantic_filters, budget_value)
            if fallback_products:
                products = fallback_products
                fallback_type = fallback_type or "category_alternatives"
                no_match = True
            else:
                no_match = True

        ranked = rank_branches(
            user_lat,
            user_lon,
            scrape_cat,
            products,
            budget=budget_value,
            priority=priority,
        )
        ranked = _apply_store_filter(ranked, store_filter)
        recommendation = recommend(ranked, priority=priority)

        if query:
            track_search_history(user_id, query, budget=budget_value)
        viewed_products = [
            row.get("best_product")
            for row in ranked[:20]
            if isinstance(row.get("best_product"), dict)
        ]
        if viewed_products:
            track_viewed_products(user_id, viewed_products)
        user_prefs = get_user_preferences(user_id)

        intelligence = generate_intelligence(recommendation, query=query, user_prefs=user_prefs)

        response = {
            **intelligence,
            "recommendation": recommendation,
            "user_id": user_id,
            "store_filter": store_filter,
            "search_mode": "semantic" if semantic_filters else "keyword",
        }
        if fallback_type:
            response["fallback"] = fallback_type
        if semantic_filters:
            response["semantic_filters"] = semantic_filters
        if scraper_query:
            response["scraper_query"] = scraper_query
        if no_match:
            response["no_match"] = True
            response["category"] = category_guess
            response["category_label"] = _category_display_name(category_guess)
            response["suggestions"] = _build_search_suggestions(query, category_guess)
            response["scope"] = _search_scope_message()
        return jsonify(response)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@app.route("/ai-chat", methods=["POST"])
@app.route("/api/ai-chat", methods=["POST"])
def api_ai_chat():
    data = request.get_json(silent=True) or {}
    raw_query = str(data.get("query") or data.get("message") or "").strip()
    if not raw_query:
        return jsonify({"error": "query or message is required"}), 400

    user_lat = _safe_float(data.get("user_lat")) or _DEFAULT_INSIGHTS_LAT
    user_lon = _safe_float(data.get("user_lon")) or _DEFAULT_INSIGHTS_LON
    priority = str(data.get("priority") or "total_cost").strip() or "total_cost"
    store_filter = _normalize_store_filter(data.get("store_filter"))
    pages = max(1, min(3, _safe_int(data.get("pages"), 1)))
    budget_value = _safe_float(data.get("budget"))
    user_id = _resolve_user_id(data)

    try:
        from services.intelligence_service import generate_intelligence
        from services.semantic_search_service import parse_user_query
        from services.user_profile_service import (
            get_user_preferences,
            track_search_history,
            track_viewed_products,
        )

        user_query, context_hint = _split_chat_context(raw_query)

        # 1) Parse query using semantic_search_service.
        semantic_filters = parse_user_query(user_query)
        if semantic_filters:
            category = _normalize_label(semantic_filters.get("category"), _CATEGORY_ALIASES)
            if category:
                semantic_filters["category"] = category
            if budget_value is None:
                parsed_budget = _safe_float(semantic_filters.get("budget"))
                if parsed_budget is not None and parsed_budget > 0:
                    budget_value = parsed_budget

        # 2) Fetch products using scrapers.
        scraper_query = _build_scraper_query(user_query, semantic_filters)
        scrape_cat = semantic_filters.get("category") if semantic_filters else None
        scrape_cat = scrape_cat or "electronics"
        products = _get_products(scrape_cat, pages, query=scraper_query)
        if not products and semantic_filters and semantic_filters.get("category"):
            products = _get_products(scrape_cat, pages, query=str(semantic_filters["category"]))
        if not products and scraper_query != user_query:
            products = _get_products(scrape_cat, pages, query=user_query)
        if budget_value is not None:
            products = _apply_budget_filter(products, budget_value)
        products = _filter_relevant_products(products, user_query, semantic_filters)

        no_match = False
        category_guess = None
        if not products:
            category_guess, fallback_products = _fallback_category_products(user_query, semantic_filters, budget_value)
            if fallback_products:
                products = fallback_products
                no_match = True
            else:
                no_match = True

        # 3) Rank using prediction_service.
        ranked = rank_branches(
            user_lat,
            user_lon,
            "electronics",
            products,
            budget=budget_value,
            priority=priority,
        )
        ranked = _apply_store_filter(ranked, store_filter)
        recommendation = recommend(ranked, priority=priority)

        # Track conversational query and viewed products.
        track_search_history(user_id, user_query, budget=budget_value)
        viewed_products = [
            row.get("best_product")
            for row in ranked[:20]
            if isinstance(row.get("best_product"), dict)
        ]
        if viewed_products:
            track_viewed_products(user_id, viewed_products)

        user_prefs = get_user_preferences(user_id)

        # 4) Analyze using intelligence_service.
        intelligence = generate_intelligence(recommendation, query=user_query, user_prefs=user_prefs)

        intent_search = _is_search_guidance_query(user_query)
        if recommendation.get("error"):
            suggestions = _build_search_suggestions(user_query, category_guess)
            message = _compose_chat_message(
                user_query=user_query,
                recommended_product=None,
                alternatives=[],
                reason=recommendation.get("error"),
                suggestions=suggestions,
                scope=_search_scope_message(),
                no_match=no_match,
                intent_search=intent_search,
            )
            return jsonify(
                {
                    "summary": intelligence.get("summary") or "I could not find matching products right now.",
                    "recommended_product": None,
                    "alternatives": [],
                    "reason": recommendation.get("error"),
                    "no_match": no_match,
                    "category": category_guess,
                    "category_label": _category_display_name(category_guess),
                    "suggestions": suggestions,
                    "scope": _search_scope_message(),
                    "message": message,
                }
            )

        best = recommendation.get("best_overall") or {}
        best_product = str(best.get("product") or "").strip()
        best_store = str(best.get("branch_name") or "").strip()
        best_price = _safe_float(best.get("product_price"))

        if best_product:
            if best_price is not None and best_store:
                recommended_product = f"{best_product} (Rs. {best_price:,.0f} at {best_store})"
            elif best_store:
                recommended_product = f"{best_product} at {best_store}"
            else:
                recommended_product = best_product
        else:
            recommended_product = None

        alternatives: list[str] = []
        seen_alt_keys: set[str] = set()
        for option in recommendation.get("all_options", []):
            if best.get("branch_id") and option.get("branch_id") == best.get("branch_id"):
                continue

            alt_product = str(option.get("product") or "").strip()
            if not alt_product:
                continue
            alt_store = str(option.get("branch_name") or "").strip()
            alt_price = _safe_float(option.get("product_price"))

            if alt_price is not None and alt_store:
                line = f"{alt_product} (Rs. {alt_price:,.0f} at {alt_store})"
            elif alt_store:
                line = f"{alt_product} at {alt_store}"
            else:
                line = alt_product

            key = line.lower()
            if key in seen_alt_keys:
                continue
            seen_alt_keys.add(key)
            alternatives.append(line)
            if len(alternatives) >= 3:
                break

        reason = (
            str(intelligence.get("ai_reasoning") or "").strip()
            or str((intelligence.get("buying_advice") or {}).get("headline") or "").strip()
            or str(recommendation.get("reason") or "").strip()
            or str(intelligence.get("summary") or "").strip()
        )
        suggestions = _build_search_suggestions(user_query, category_guess)
        message = _compose_chat_message(
            user_query=user_query,
            recommended_product=recommended_product,
            alternatives=alternatives,
            reason=reason,
            suggestions=suggestions,
            scope=_search_scope_message(),
            no_match=no_match,
            intent_search=intent_search,
        )

        # 5) Return conversational answer.
        response = {
            "summary": intelligence.get("summary")
            or f"For '{user_query}', the best option is {recommended_product or 'currently unavailable'}.",
            "recommended_product": recommended_product,
            "alternatives": alternatives,
            "reason": reason,
            "message": message,
        }
        if no_match:
            response["no_match"] = True
            response["category"] = category_guess
            response["category_label"] = _category_display_name(category_guess)
            response["suggestions"] = suggestions
            response["scope"] = _search_scope_message()
        return jsonify(response)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


@app.route("/api/dashboard", methods=["GET", "POST"])
def api_dashboard():
    data = request.get_json(silent=True) or {}
    user_id = _resolve_user_id(data)
    query = str(data.get("query") or request.args.get("query") or "").strip()
    budget = _safe_float(data.get("budget") or request.args.get("budget"))
    viewed_products = data.get("viewed_products")

    try:
        from services.user_profile_service import (
            generate_recommendations,
            get_user_preferences,
            track_search_history,
            track_viewed_products,
        )

        if query:
            track_search_history(user_id, query, budget=budget)
        if isinstance(viewed_products, list) and viewed_products:
            track_viewed_products(user_id, viewed_products)

        preferences = get_user_preferences(user_id)
        recommendations = generate_recommendations(user_id)

        return jsonify(
            {
                "user_id": user_id,
                "preferences": preferences,
                **recommendations,
            }
        )
    except Exception as exc:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(exc)}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)
