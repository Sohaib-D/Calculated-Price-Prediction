"""Product model matching and cross-store price unification service."""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from statistics import mean

import requests

logger = logging.getLogger(__name__)

# Fast defaults to avoid slowing down request paths.
_AI_MODEL = os.environ.get(
    "PRODUCT_MATCH_AI_MODEL",
    os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
)
_AI_CONNECT_TIMEOUT = float(os.environ.get("PRODUCT_MATCH_AI_CONNECT_TIMEOUT_SECONDS", "0.7"))
_AI_READ_TIMEOUT = float(os.environ.get("PRODUCT_MATCH_AI_READ_TIMEOUT_SECONDS", "1.5"))
_AI_MAX_CHECKS = int(os.environ.get("PRODUCT_MATCH_MAX_AI_CHECKS", "20"))
_AI_ENABLED = os.environ.get("PRODUCT_MATCH_USE_AI", "true").strip().lower() in {"1", "true", "yes", "on"}

_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

_BRAND_ALIASES = {
    "apple": {"apple", "iphone"},
    "samsung": {"samsung", "galaxy"},
    "xiaomi": {"xiaomi", "redmi", "poco"},
    "oppo": {"oppo"},
    "vivo": {"vivo"},
    "oneplus": {"oneplus", "1plus"},
    "realme": {"realme"},
    "infinix": {"infinix"},
    "tecno": {"tecno"},
    "google": {"google", "pixel"},
    "huawei": {"huawei"},
    "nokia": {"nokia"},
    "motorola": {"motorola", "moto"},
    "sony": {"sony", "xperia"},
    "lenovo": {"lenovo", "thinkpad", "ideapad"},
    "hp": {"hp", "hewlett", "packard"},
    "dell": {"dell", "alienware", "inspiron", "latitude", "xps"},
    "asus": {"asus", "rog", "vivobook", "zenbook"},
    "acer": {"acer", "nitro", "predator"},
    "msi": {"msi"},
}

# Keep product line tokens (e.g., iphone, galaxy, redmi) in model signatures.
_BRAND_REMOVAL_TOKENS = {
    "apple": {"apple"},
    "samsung": {"samsung"},
    "xiaomi": {"xiaomi"},
    "oppo": {"oppo"},
    "vivo": {"vivo"},
    "oneplus": {"oneplus", "1plus"},
    "realme": {"realme"},
    "infinix": {"infinix"},
    "tecno": {"tecno"},
    "google": {"google"},
    "huawei": {"huawei"},
    "nokia": {"nokia"},
    "motorola": {"motorola", "moto"},
    "sony": {"sony"},
    "lenovo": {"lenovo"},
    "hp": {"hp", "hewlett", "packard"},
    "dell": {"dell"},
    "asus": {"asus"},
    "acer": {"acer"},
    "msi": {"msi"},
}

_GENERIC_TOKENS = {
    "official",
    "pta",
    "approved",
    "warranty",
    "new",
    "brand",
    "box",
    "pack",
    "sealed",
    "kit",
    "dual",
    "sim",
    "factory",
    "unlocked",
    "original",
    "global",
    "version",
    "edition",
    "model",
    "mobile",
    "phone",
    "smartphone",
    "with",
    "for",
    "the",
    "and",
    "of",
}

_VARIANT_TOKENS = {"pro", "max", "plus", "ultra", "mini", "fe"}


@dataclass
class ParsedProduct:
    index: int
    raw: dict
    raw_name: str
    normalized_name: str
    tokens: list[str]
    brand: str | None
    storage_gb: int | None
    model_tokens: list[str]
    model_signature: str
    variant_tokens: set[str]


def _normalize_text(text: str) -> str:
    value = (text or "").strip().lower()
    value = value.replace("+", " plus ")
    value = value.replace("-", " ")
    value = value.replace("/", " ")

    # Split glued alpha-numeric patterns: iPhone15 -> iPhone 15, 128GB -> 128 GB
    value = re.sub(r"(?<=[a-z])(?=\d)", " ", value)
    value = re.sub(r"(?<=\d)(?=[a-z])", " ", value)

    value = value.replace("gigabyte", "gb")
    value = value.replace("terabyte", "tb")

    value = re.sub(r"[^a-z0-9\s]", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def _tokenize(text: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9]+", text) if token]


def _extract_brand(tokens: list[str]) -> str | None:
    token_set = set(tokens)
    for brand, aliases in _BRAND_ALIASES.items():
        if token_set & aliases:
            return brand
    return None


def _extract_storage_gb(normalized_name: str) -> int | None:
    matches = re.findall(r"\b(\d{2,4})\s*(gb|tb)\b", normalized_name)
    if not matches:
        return None

    best = None
    for raw_number, unit in matches:
        number = int(raw_number)
        gb_value = number * 1024 if unit == "tb" else number
        if 16 <= gb_value <= 8192:
            best = gb_value if best is None else max(best, gb_value)
    return best


def _normalize_model_tokens(tokens: list[str], brand: str | None, storage_gb: int | None) -> list[str]:
    removal_tokens = _BRAND_REMOVAL_TOKENS.get(brand, set()) if brand else set()
    normalized: list[str] = []
    skip_next = False

    for idx, token in enumerate(tokens):
        if skip_next:
            skip_next = False
            continue

        if token in removal_tokens or token in _GENERIC_TOKENS:
            continue

        # Remove storage fragments like 128 gb / 1 tb from model signature.
        if token.isdigit() and idx + 1 < len(tokens) and tokens[idx + 1] in {"gb", "tb"}:
            skip_next = True
            continue
        if token in {"gb", "tb"}:
            continue

        # Remove plain storage number if it exactly equals extracted storage.
        if storage_gb is not None and token.isdigit() and int(token) == storage_gb:
            continue

        normalized.append(token)

    return normalized[:10]


def _model_signature(model_tokens: list[str]) -> str:
    if not model_tokens:
        return "unknown"
    return " ".join(model_tokens)


def _parse_product(index: int, product: dict) -> ParsedProduct:
    raw_name = str(product.get("product") or product.get("name") or "").strip()
    normalized_name = _normalize_text(raw_name)
    tokens = _tokenize(normalized_name)
    brand = _extract_brand(tokens)
    storage_gb = _extract_storage_gb(normalized_name)
    model_tokens = _normalize_model_tokens(tokens, brand, storage_gb)
    signature = _model_signature(model_tokens)
    variants = set(model_tokens) & _VARIANT_TOKENS

    return ParsedProduct(
        index=index,
        raw=product,
        raw_name=raw_name,
        normalized_name=normalized_name,
        tokens=tokens,
        brand=brand,
        storage_gb=storage_gb,
        model_tokens=model_tokens,
        model_signature=signature,
        variant_tokens=variants,
    )


def _token_jaccard(left: list[str], right: list[str]) -> float:
    left_set = set(left)
    right_set = set(right)
    if not left_set or not right_set:
        return 0.0
    intersection = len(left_set & right_set)
    union = len(left_set | right_set)
    return intersection / union if union else 0.0


def _numeric_model_tokens(model_tokens: list[str]) -> set[str]:
    return {token for token in model_tokens if token.isdigit()}


def _deterministic_match_score(a: ParsedProduct, b: ParsedProduct) -> tuple[float, bool]:
    # Hard mismatches.
    if a.brand and b.brand and a.brand != b.brand:
        return 0.0, False

    if a.storage_gb is not None and b.storage_gb is not None and a.storage_gb != b.storage_gb:
        return 0.0, False

    # Variant-sensitive matching to avoid merging base/pro/max/ultra models.
    if (a.variant_tokens or b.variant_tokens) and a.variant_tokens != b.variant_tokens:
        return 0.0, False

    nums_a = _numeric_model_tokens(a.model_tokens)
    nums_b = _numeric_model_tokens(b.model_tokens)
    if nums_a and nums_b and not (nums_a & nums_b):
        return 0.0, False

    jaccard = _token_jaccard(a.model_tokens, b.model_tokens)
    seq_ratio = SequenceMatcher(None, a.normalized_name, b.normalized_name).ratio()

    score = 0.0
    if a.brand and b.brand and a.brand == b.brand:
        score += 0.35
    elif not a.brand or not b.brand:
        score += 0.10

    if a.storage_gb is not None and b.storage_gb is not None and a.storage_gb == b.storage_gb:
        score += 0.25
    elif a.storage_gb is None or b.storage_gb is None:
        score += 0.10

    score += jaccard * 0.25
    score += seq_ratio * 0.25

    # Strong deterministic acceptance.
    certain = score >= 0.84 or (jaccard >= 0.78 and seq_ratio >= 0.88)
    return score, certain


def _extract_price(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        numeric = float(value)
        return numeric if numeric > 0 else None

    text = str(value).replace(",", "")
    match = re.search(r"\d+(?:\.\d+)?", text)
    if not match:
        return None
    numeric = float(match.group())
    return numeric if numeric > 0 else None


def _pair_key(a: ParsedProduct, b: ParsedProduct) -> tuple[str, str, str, str]:
    left = f"{a.brand or 'na'}|{a.model_signature}|{a.storage_gb or 'na'}"
    right = f"{b.brand or 'na'}|{b.model_signature}|{b.storage_gb or 'na'}"
    return (left, right, a.normalized_name, b.normalized_name) if left <= right else (right, left, b.normalized_name, a.normalized_name)


def _ai_similarity_check(a: ParsedProduct, b: ParsedProduct) -> tuple[bool, float] | None:
    if not _AI_ENABLED:
        return None

    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        return None

    prompt = (
        "Decide if these two product listings are the same exact model variant for price comparison. "
        "Consider brand, model line, storage, and variant terms like pro/max/ultra/plus/mini. "
        "Return strict JSON only: {\"same_model\": true/false, \"confidence\": 0..1}.\n\n"
        f"A: {a.raw_name}\n"
        f"A extracted: brand={a.brand}, model={a.model_signature}, storage_gb={a.storage_gb}\n\n"
        f"B: {b.raw_name}\n"
        f"B extracted: brand={b.brand}, model={b.model_signature}, storage_gb={b.storage_gb}"
    )

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": _AI_MODEL,
        "messages": [
            {"role": "system", "content": "You are a strict product entity matcher."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0,
        "max_tokens": 48,
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

        content = (response.json().get("choices") or [{}])[0].get("message", {}).get("content", "")
        data = json.loads(content)
        same_model = bool(data.get("same_model"))
        confidence = float(data.get("confidence") or 0)
        return same_model, max(0.0, min(1.0, confidence))
    except Exception as exc:
        logger.debug("AI similarity check failed: %s", exc)
        return None


def _should_ai_check(score: float) -> bool:
    return 0.62 <= score < 0.84


def _product_store_name(raw: dict) -> str:
    return str(raw.get("source_store") or raw.get("store") or raw.get("branch_name") or "unknown_store")


def _group_model_id(brand: str | None, signature: str, storage_gb: int | None) -> str:
    safe_brand = (brand or "unknown").strip().lower().replace(" ", "_")
    safe_sig = re.sub(r"[^a-z0-9]+", "_", (signature or "unknown").lower()).strip("_") or "unknown"
    safe_storage = f"{storage_gb}gb" if storage_gb else "nostorage"
    return f"{safe_brand}_{safe_sig}_{safe_storage}"


def _best_group_parse(members: list[ParsedProduct]) -> ParsedProduct:
    def quality(p: ParsedProduct) -> tuple[int, int, int]:
        return (
            1 if p.brand else 0,
            1 if p.storage_gb else 0,
            len(p.model_tokens),
        )

    return sorted(members, key=quality, reverse=True)[0]


def _build_group_output(members: list[ParsedProduct]) -> dict:
    representative = _best_group_parse(members)
    offers_by_store: dict[str, dict] = {}

    for parsed in members:
        raw = parsed.raw
        store_name = _product_store_name(raw)
        price = _extract_price(raw.get("price"))

        candidate_offer = {
            "store": store_name,
            "price": price,
            "product_name": parsed.raw_name,
            "source_url": raw.get("source_url"),
            "store_type": raw.get("store_type"),
        }

        current = offers_by_store.get(store_name)
        if current is None:
            offers_by_store[store_name] = candidate_offer
        else:
            current_price = current.get("price")
            if current_price is None or (price is not None and price < current_price):
                offers_by_store[store_name] = candidate_offer

    offers = sorted(
        offers_by_store.values(),
        key=lambda o: (o.get("price") is None, o.get("price") if o.get("price") is not None else float("inf"), o.get("store", "")),
    )

    prices = [offer["price"] for offer in offers if offer.get("price") is not None]
    min_price = min(prices) if prices else None
    max_price = max(prices) if prices else None
    avg_price = round(mean(prices), 2) if prices else None

    brand = representative.brand
    model = representative.model_signature if representative.model_signature != "unknown" else None
    storage = representative.storage_gb

    canonical_name_parts = []
    if brand:
        canonical_name_parts.append(brand.title())
    if model:
        canonical_name_parts.append(model.upper() if model.isupper() else model)
    if storage:
        canonical_name_parts.append(f"{storage}GB")
    canonical_name = " ".join(canonical_name_parts) if canonical_name_parts else representative.raw_name

    return {
        "model_id": _group_model_id(brand, representative.model_signature, storage),
        "canonical_name": canonical_name,
        "brand": brand,
        "model": model,
        "storage_gb": storage,
        "store_count": len(offers),
        "matched_count": len(members),
        "min_price": min_price,
        "max_price": max_price,
        "avg_price": avg_price,
        "price_spread": round(max_price - min_price, 2) if min_price is not None and max_price is not None else None,
        "offers": offers,
    }


def match_products(product_list: list[dict]) -> list[dict]:
    """
    Group product listings that represent the same model variant.

    Steps:
    1. Normalize names.
    2. Extract brand, model, storage.
    3. Run AI similarity check only for uncertain candidate pairs.
    4. Group identical products.
    5. Return unified entries with per-store prices for comparison.
    """
    if not product_list:
        return []

    parsed_products = [_parse_product(idx, item or {}) for idx, item in enumerate(product_list)]

    groups: list[list[ParsedProduct]] = []
    bucket_to_group_ids: dict[str, set[int]] = {}

    ai_cache: dict[tuple[str, str, str, str], tuple[bool, float]] = {}
    ai_checks_used = 0

    for parsed in parsed_products:
        head_tokens = parsed.model_tokens[:2] if parsed.model_tokens else ["unknown"]
        storage_key = str(parsed.storage_gb) if parsed.storage_gb is not None else "na"

        candidate_keys = {
            f"{parsed.brand or 'unknown'}|{'_'.join(head_tokens)}",
            f"{parsed.brand or 'unknown'}|{storage_key}",
            f"{parsed.model_signature}",
        }

        candidate_group_ids: set[int] = set()
        for key in candidate_keys:
            candidate_group_ids.update(bucket_to_group_ids.get(key, set()))

        best_group_id = None
        best_score = -1.0

        for gid in candidate_group_ids:
            representative = _best_group_parse(groups[gid])
            score, certain = _deterministic_match_score(parsed, representative)

            if score <= 0:
                continue

            matched = certain
            if not matched and _should_ai_check(score):
                pair_key = _pair_key(parsed, representative)
                ai_result = ai_cache.get(pair_key)

                if ai_result is None and ai_checks_used < _AI_MAX_CHECKS:
                    ai_result = _ai_similarity_check(parsed, representative)
                    if ai_result is not None:
                        ai_cache[pair_key] = ai_result
                    ai_checks_used += 1

                if ai_result is not None:
                    matched = ai_result[0] and ai_result[1] >= 0.65

            if matched and score > best_score:
                best_score = score
                best_group_id = gid

        if best_group_id is None:
            groups.append([parsed])
            new_gid = len(groups) - 1
            for key in candidate_keys:
                bucket_to_group_ids.setdefault(key, set()).add(new_gid)
        else:
            groups[best_group_id].append(parsed)
            for key in candidate_keys:
                bucket_to_group_ids.setdefault(key, set()).add(best_group_id)

    unified = [_build_group_output(group_members) for group_members in groups]

    return sorted(
        unified,
        key=lambda item: (
            -int(item.get("store_count") or 0),
            item.get("min_price") if item.get("min_price") is not None else float("inf"),
            item.get("canonical_name") or "",
        ),
    )
