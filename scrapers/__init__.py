"""
scrapers/__init__.py — Electronics-only scraper dispatcher
──────────────────────────────────────────────────────────
Single entry point: fetch_category('electronics') or fetch_all()
"""
from scrapers.universal_scraper import fetch_all_stores

# Keep SCRAPER_MAP for backward compatibility with app.py
SCRAPER_MAP = {
    "electronics": [fetch_all_stores],
    "paints": [],  # handled specially in fetch_category
}


from scrapers.paints_scraper import fetch_paints
from scrapers.mobiles_scraper import fetch_mobiles

def fetch_category(
    category: str = "electronics",
    max_pages: int = 2,
    query: str = None,
    verbose: bool = True,
) -> list[dict]:
    """
    Fetch products for the given category.
    Dispatches to the appropriate scraper collection.  Currently supports
    "electronics" (the generic universal scraper), "mobiles" (sample phone
    site), and "paints" (fake paint/art supplies).  Additional categories
    can be plugged here as needed.
    """
    cat = (category or "").strip().lower()
    if cat == "paints":
        # paints scraper ignores query but will still reskin items
        return fetch_paints(max_pages)
    if cat in {"mobiles", "mobile", "phones", "mobile phones"}:
        return fetch_mobiles(max_pages)
    # default to electronics for everything else
    return fetch_all_stores(query=query, max_per_store=20, verbose=verbose)
