"""
AI-powered semantic query parsing for product search.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time

from dotenv import load_dotenv
load_dotenv()

import requests

logger = logging.getLogger(__name__)

_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_GROQ_MODEL = os.environ.get(
    "GROQ_SEMANTIC_MODEL",
    os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
)
_CONNECT_TIMEOUT = float(os.environ.get("GROQ_CONNECT_TIMEOUT_SECONDS", "1.5"))
_READ_TIMEOUT = float(os.environ.get("GROQ_READ_TIMEOUT_SECONDS", "4.0"))
_CACHE_TTL_SECONDS = int(os.environ.get("SEMANTIC_CACHE_TTL_SECONDS", "300"))
_CACHE_MAX_ENTRIES = int(os.environ.get("SEMANTIC_CACHE_MAX_ENTRIES", "256"))

_PARSE_CACHE: dict[str, tuple[float, dict]] = {}
_CACHE_LOCK = threading.Lock()

_SYSTEM_PROMPT = (
    "You extract ecommerce search filters from a single user query for a Pakistani "
    "electronics marketplace.\\n"
    "Return ONLY valid JSON with exactly these keys:\\n"
    "- category: string or null\\n"
    "- budget: integer or null (PKR maximum budget)\\n"
    "- use_case: string or null\\n"
    "Rules:\\n"
    "- Convert shorthand amounts like 200k=200000, 2 lakh=200000, 1.5m=1500000.\\n"
    "- Keep values concise and lowercase when text.\\n"
    "- If unknown, use null.\\n"
    "No markdown. No explanations."
)

_CATEGORY_HINTS = {
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
        "alienware",
    },
    "mobile": {
        "mobile",
        "phone",
        "smartphone",
        "iphone",
        "galaxy",
        "pixel",
        "redmi",
        "oppo",
        "vivo",
        "oneplus",
        "infinix",
        "tecno",
    },
    "tv": {"tv", "television", "oled", "qled", "bravia"},
    "tablet": {"tablet", "ipad", "tab"},
    "headphone": {"headphone", "headphones", "earbuds", "airpods", "buds"},
    "smartwatch": {"watch", "smartwatch", "wearable"},
    "console": {"console", "ps5", "playstation", "xbox"},
}
_CATEGORY_ALIASES = {
    "phone": "mobile",
    "smartphone": "mobile",
    "cellphone": "mobile",
    "cell phone": "mobile",
    "notebook": "laptop",
    "television": "tv",
    "watch": "smartwatch",
    "paint": "paints",
    "paints": "paints",
}
_USE_CASE_HINTS = {
    "gaming": {"gaming", "rtx", "gtx", "gpu", "ps5", "xbox"},
    "office": {"office", "business", "productivity"},
    "study": {"study", "student", "school", "college"},
    "camera": {"camera", "photography", "video", "vlog"},
}
_QUERY_STOPWORDS = {
    "cheap",
    "best",
    "under",
    "below",
    "around",
    "near",
    "official",
    "pta",
    "price",
    "budget",
    "buy",
    "shop",
    "with",
    "for",
    "the",
    "and",
    "or",
}


def _normalize_query(query: str) -> str:
    return " ".join((query or "").strip().lower().split())


def _tokenize_simple(text: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9]+", (text or "").lower()) if token]


def _best_label(tokens: set[str], groups: dict[str, set[str]]) -> str | None:
    best_label = None
    best_score = 0
    for label, words in groups.items():
        score = len(tokens & words)
        if score > best_score:
            best_score = score
            best_label = label
    return best_label


def _extract_budget_from_query(query: str) -> int | None:
    text = _normalize_query(query).replace(",", "")
    if not text:
        return None

    # Budget-intent phrases: "under 200k", "max 2 lakh", "budget 150000"
    intent_match = re.search(
        r"(?:under|below|upto|up to|max|maximum|budget|within|less than)\s*"
        r"(?:rs\.?|pkr|rupees)?\s*(\d+(?:\.\d+)?)\s*(k|m|lakh|lac|crore|cr)?",
        text,
    )
    if intent_match:
        return _coerce_budget(f"{intent_match.group(1)}{intent_match.group(2) or ''}")

    # Explicit currency mention: "rs 250000"
    currency_match = re.search(
        r"(?:rs\.?|pkr|rupees)\s*(\d+(?:\.\d+)?)\s*(k|m|lakh|lac|crore|cr)?",
        text,
    )
    if currency_match:
        return _coerce_budget(f"{currency_match.group(1)}{currency_match.group(2) or ''}")

    # Amounts with compact units can be treated as budget even without explicit words.
    compact_match = re.search(r"\b(\d+(?:\.\d+)?)\s*(k|m|lakh|lac|crore|cr)\b", text)
    if compact_match:
        return _coerce_budget(f"{compact_match.group(1)}{compact_match.group(2)}")

    return None


def _heuristic_parse(query: str) -> dict | None:
    """
    Lightweight offline parser so semantic search still works when Groq is unavailable.
    """
    cleaned = _normalize_query(query)
    if not cleaned:
        return None

    tokens = _tokenize_simple(cleaned)
    token_set = {t for t in tokens if t not in _QUERY_STOPWORDS}

    category = _best_label(token_set, _CATEGORY_HINTS)
    if not category:
        for alias, canonical in _CATEGORY_ALIASES.items():
            alias_tokens = set(_tokenize_simple(alias))
            if alias_tokens and alias_tokens.issubset(token_set):
                category = canonical
                break

    use_case = _best_label(token_set, _USE_CASE_HINTS)
    budget = _extract_budget_from_query(cleaned)

    parsed = {
        "category": category,
        "budget": budget,
        "use_case": use_case,
    }
    return parsed if _has_meaningful_filters(parsed) else None


def _cache_get(query_key: str) -> dict | None:
    now = time.time()
    with _CACHE_LOCK:
        item = _PARSE_CACHE.get(query_key)
        if not item:
            return None
        expires_at, value = item
        if expires_at < now:
            _PARSE_CACHE.pop(query_key, None)
            return None
        return dict(value)


def _cache_set(query_key: str, value: dict) -> None:
    with _CACHE_LOCK:
        if len(_PARSE_CACHE) >= _CACHE_MAX_ENTRIES:
            oldest_key = min(_PARSE_CACHE, key=lambda k: _PARSE_CACHE[k][0])
            _PARSE_CACHE.pop(oldest_key, None)
        _PARSE_CACHE[query_key] = (time.time() + _CACHE_TTL_SECONDS, dict(value))


def _extract_json_object(text: str) -> dict | None:
    if not text:
        return None

    candidate = text.strip()
    try:
        return json.loads(candidate)
    except (json.JSONDecodeError, TypeError):
        pass

    start = candidate.find("{")
    end = candidate.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None

    try:
        return json.loads(candidate[start : end + 1])
    except (json.JSONDecodeError, TypeError):
        return None


def _coerce_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    return text[:64] if text else None


def _coerce_budget(value: object) -> int | None:
    if value is None:
        return None

    if isinstance(value, (int, float)):
        number = int(float(value))
        return number if number > 0 else None

    text = str(value).strip().lower().replace(",", "")
    if not text:
        return None

    direct_digits = re.findall(r"\d+", text)
    if text.isdigit() and direct_digits:
        number = int(text)
        return number if number > 0 else None

    match = re.search(r"(\d+(?:\.\d+)?)\s*(k|m|lakh|lac|crore|cr)?", text)
    if not match:
        if direct_digits:
            number = int("".join(direct_digits))
            return number if number > 0 else None
        return None

    number = float(match.group(1))
    unit = (match.group(2) or "").strip()
    multiplier = 1
    if unit == "k":
        multiplier = 1_000
    elif unit == "m":
        multiplier = 1_000_000
    elif unit in {"lakh", "lac"}:
        multiplier = 100_000
    elif unit in {"crore", "cr"}:
        multiplier = 10_000_000

    value_int = int(number * multiplier)
    return value_int if value_int > 0 else None


def _normalize_structured_output(payload: dict) -> dict:
    return {
        "category": _coerce_text(payload.get("category")),
        "budget": _coerce_budget(payload.get("budget")),
        "use_case": _coerce_text(payload.get("use_case")),
    }


def _has_meaningful_filters(data: dict) -> bool:
    return any(value is not None for value in data.values())


def parse_user_query(query: str) -> dict | None:
    """
    Convert natural language query to structured filters via Groq.
    Returns dict with keys: category, budget, use_case; or None on failure.
    """
    cleaned_query = _normalize_query(query)
    if not cleaned_query:
        return None

    cached = _cache_get(cleaned_query)
    if cached is not None:
        return cached

    heuristic_result = _heuristic_parse(cleaned_query)
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        if heuristic_result:
            _cache_set(cleaned_query, heuristic_result)
            return heuristic_result
        return None

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": _GROQ_MODEL,
        "messages": [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": cleaned_query},
        ],
        "temperature": 0,
        "max_tokens": 96,
        "response_format": {"type": "json_object"},
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
            if heuristic_result:
                _cache_set(cleaned_query, heuristic_result)
            return heuristic_result

        normalized = _normalize_structured_output(parsed)
        if heuristic_result:
            for key, value in heuristic_result.items():
                if normalized.get(key) is None and value is not None:
                    normalized[key] = value

        if not _has_meaningful_filters(normalized):
            if heuristic_result:
                _cache_set(cleaned_query, heuristic_result)
            return heuristic_result

        _cache_set(cleaned_query, normalized)
        return normalized
    except Exception as exc:
        logger.info("Semantic parsing fallback used: %s", exc)
        if heuristic_result:
            _cache_set(cleaned_query, heuristic_result)
        return heuristic_result
