"""
universal_scraper.py — Unified scraper for 30+ Pakistani electronics stores
─────────────────────────────────────────────────────────────────────────────
Config-driven approach: each store has scrape selectors.
Falls back to curated demo data for stores that block scraping.
"""
import time
import re
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
from config import (
    REQUEST_TIMEOUT,
    REQUEST_DELAY,
    SCRAPER_CONNECT_TIMEOUT,
    SCRAPER_MAX_WORKERS,
    SCRAPER_READ_TIMEOUT,
    SCRAPE_SEED_STORES,
    SEED_STORES,
    STORES,
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

TARGET_STORES = STORES + (SEED_STORES if SCRAPE_SEED_STORES else [])
STORE_INDEX = {store["id"]: store for store in TARGET_STORES}

# Category hints to keep category searches relevant but not empty.
_CATEGORY_KEYWORDS = {
    "laptop": {
        "laptop", "notebook", "macbook", "thinkpad", "vivobook", "ideapad", "inspiron", "xps",
        "nitro", "alienware", "pavilion", "probook", "latitude", "legion", "tuf", "rog",
        "victus", "aspire", "surface", "matebook",
    },
    "mobile": {
        "mobile", "phone", "smartphone", "iphone", "galaxy", "redmi", "realme", "qmobile",
        "oppo", "vivo", "pixel", "infinix", "tecno", "itel", "nokia", "oneplus", "honor",
    },
    "tv": {"tv", "television", "oled", "qled", "bravia", "uhd", "smarttv", "smart"},
    "tablet": {"tablet", "ipad", "tab", "pad"},
    "headphone": {"headphone", "headphones", "earbuds", "airpods", "buds", "headset"},
    "smartwatch": {"watch", "smartwatch", "band"},
    "console": {"console", "playstation", "ps5", "xbox", "switch", "nintendo"},
}

_CATEGORY_ALIASES = {
    "laptops": "laptop",
    "notebooks": "laptop",
    "phones": "mobile",
    "mobiles": "mobile",
    "smartphones": "mobile",
    "televisions": "tv",
    "tvs": "tv",
    "headphones": "headphone",
    "earbud": "headphone",
    "earbuds": "headphone",
    "watches": "smartwatch",
}


def _normalize_tokens(text: str | None) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if t]


def _query_category(query: str | None) -> str | None:
    tokens = _normalize_tokens(query)
    if not tokens:
        return None
    for token in tokens:
        if token in _CATEGORY_ALIASES:
            return _CATEGORY_ALIASES[token]
        if token in _CATEGORY_KEYWORDS:
            return token
    return None


def _category_match(name: str, category: str) -> bool:
    tokens = set(_normalize_tokens(name))
    keywords = _CATEGORY_KEYWORDS.get(category, set())
    return bool(tokens & keywords)

PLATFORM_SELECTORS = {
    "woocommerce": {
        "product_sel": ".product",
        "name_sel": ".woocommerce-loop-product__title, .product-title, h2",
        "price_sel": ".price .amount, .price",
        "link_sel": "a",
    },
    "magento": {
        "product_sel": ".product-item, .item, .product",
        "name_sel": ".product-item-link, .product-name a, h2, h3",
        "price_sel": ".price, .special-price .price, .regular-price .price",
        "link_sel": "a.product-item-link, a",
    },
    "shopify": {
        "product_sel": ".product-item, .product, .product-card, .grid-product",
        "name_sel": ".product-title, .product-card__title, .product-name, h3, h2",
        "price_sel": ".price, .product-price, .money",
        "link_sel": "a",
    },
    "generic": {
        "product_sel": ".product, .product-item, .product-card, .grid-product",
        "name_sel": "h2, h3, h4, .product-title, .product-name",
        "price_sel": ".price, .product-price, .amount, .money",
        "link_sel": "a",
    },
}

# ── Scrape Configs per store ──────────────────────────────────────────────────
# Each config: search_url template, CSS selectors for product card/name/price
SCRAPE_CONFIGS = {
    "afzal_electronics": {
        "search_url": "https://afzalelectronics.com/?s={query}&post_type=product",
        "product_sel": ".product",
        "name_sel": ".woocommerce-loop-product__title",
        "price_sel": ".price .amount",
        "link_sel": "a.woocommerce-LoopProduct-link",
    },
    "arduino_pakistan": {
        "search_url": "https://www.arduinopakistan.com/?s={query}&post_type=product",
        "product_sel": ".product",
        "name_sel": ".woocommerce-loop-product__title",
        "price_sel": ".price .amount",
        "link_sel": "a.woocommerce-LoopProduct-link",
    },
    "city_electronics": {
        "search_url": "https://cityelectronics.pk/?s={query}&post_type=product",
        "product_sel": ".product",
        "name_sel": ".woocommerce-loop-product__title, .product-title",
        "price_sel": ".price .amount, .product-price",
        "link_sel": "a.woocommerce-LoopProduct-link, a",
    },
    "college_road": {
        "search_url": "https://colgroad.com/?s={query}&post_type=product",
        "product_sel": ".product",
        "name_sel": ".woocommerce-loop-product__title",
        "price_sel": ".price .amount",
        "link_sel": "a",
    },
    "eph": {
        "search_url": "https://eph.com.pk/?s={query}&post_type=product",
        "product_sel": ".product",
        "name_sel": ".woocommerce-loop-product__title",
        "price_sel": ".price .amount",
        "link_sel": "a",
    },
    "epro": {
        "search_url": "https://www.epro.pk/?s={query}&post_type=product",
        "product_sel": ".product",
        "name_sel": ".woocommerce-loop-product__title",
        "price_sel": ".price .amount",
        "link_sel": "a",
    },
    "electronation": {
        "search_url": "http://www.electronation.pk/?s={query}",
        "product_sel": ".product",
        "name_sel": ".woocommerce-loop-product__title, h2",
        "price_sel": ".price .amount, .price",
        "link_sel": "a",
    },
    "electrobes": {
        "search_url": "https://electrobes.com/?s={query}&post_type=product",
        "product_sel": ".product",
        "name_sel": ".woocommerce-loop-product__title",
        "price_sel": ".price .amount",
        "link_sel": "a",
    },
    "evs_electro": {
        "search_url": "https://www.evselectro.com/search?q={query}",
        "product_sel": ".product-item, .grid-product",
        "name_sel": ".product-item__title, .product-title",
        "price_sel": ".product-item__price, .price",
        "link_sel": "a",
    },
    "friends_corp": {
        "search_url": "https://friendscorporation.co/?s={query}&post_type=product",
        "product_sel": ".product",
        "name_sel": ".woocommerce-loop-product__title",
        "price_sel": ".price .amount",
        "link_sel": "a",
    },
    "galaxy_pk": {
        "search_url": "https://www.galaxy.pk/search?q={query}",
        "product_sel": ".product-card, .product",
        "name_sel": ".product-card__title, h3, h2",
        "price_sel": ".product-card__price, .price",
        "link_sel": "a",
    },
    "hanif_centre": {
        "search_url": "https://hcsupermart.com/?s={query}&post_type=product",
        "product_sel": ".product",
        "name_sel": ".woocommerce-loop-product__title",
        "price_sel": ".price .amount",
        "link_sel": "a",
    },
    "homeshopping": {
        "search_url": "https://www.homeshopping.pk/search/?q={query}",
        "product_sel": ".product-box, .product-item, .product",
        "name_sel": ".product-title, h3, h4",
        "price_sel": ".price, .product-price",
        "link_sel": "a",
    },
    "imran_electronics": {
        "search_url": "https://imraneshop.com/?s={query}&post_type=product",
        "product_sel": ".product",
        "name_sel": ".woocommerce-loop-product__title",
        "price_sel": ".price .amount",
        "link_sel": "a",
    },
    "matrix_electronics": {
        "search_url": "http://matrixonline.pk/?s={query}",
        "product_sel": ".product",
        "name_sel": "h2, .product-title",
        "price_sel": ".price, .amount",
        "link_sel": "a",
    },
    "mega_pk": {
        "search_url": "https://www.mega.pk/search/{query}/",
        "product_sel": ".product-card, .product-item",
        "name_sel": ".product-title, h3",
        "price_sel": ".product-price, .price",
        "link_sel": "a",
    },
    "pakistan_electronics": {
        "search_url": "http://www.pakistanelectronics.com/?s={query}",
        "product_sel": ".product",
        "name_sel": "h2, .product-title",
        "price_sel": ".price, .amount",
        "link_sel": "a",
    },
    "shophive": {
        "search_url": "https://www.shophive.com/catalogsearch/result/?q={query}",
        "product_sel": ".product-item, .item",
        "name_sel": ".product-item-link, .product-name a",
        "price_sel": ".price",
        "link_sel": "a.product-item-link",
    },
    "telemart": {
        "search_url": "https://www.telemart.pk/searching?q={query}",
        "product_sel": ".product-card, .product-item",
        "name_sel": ".product-title, h3",
        "price_sel": ".product-price, .price",
        "link_sel": "a",
    },
    "component_centre": {
        "search_url": "https://www.thecomponentcentre.com/?s={query}&post_type=product",
        "product_sel": ".product",
        "name_sel": ".woocommerce-loop-product__title",
        "price_sel": ".price .amount",
        "link_sel": "a",
    },
    "umar_electronics": {
        "search_url": "https://umarelectronics.pk/?s={query}&post_type=product",
        "product_sel": ".product",
        "name_sel": ".woocommerce-loop-product__title",
        "price_sel": ".price .amount",
        "link_sel": "a",
    },
    "vmart": {
        "search_url": "https://www.vmart.pk/catalogsearch/result/?q={query}",
        "product_sel": ".product-item, .item",
        "name_sel": ".product-item-link, .product-name",
        "price_sel": ".price",
        "link_sel": "a",
    },
    # Online-only stores
    "art_of_circuits": {
        "search_url": "https://artofcircuits.com/?s={query}&post_type=product",
        "product_sel": ".product",
        "name_sel": ".woocommerce-loop-product__title",
        "price_sel": ".price .amount",
        "link_sel": "a",
    },
    "chip_pk": {
        "search_url": "https://chip.pk/?s={query}&post_type=product",
        "product_sel": ".product",
        "name_sel": ".woocommerce-loop-product__title",
        "price_sel": ".price .amount",
        "link_sel": "a",
    },
    "circuit_pk": {
        "search_url": "https://circuitpk.enic.pk/?s={query}",
        "product_sel": ".product",
        "name_sel": "h2, .product-title",
        "price_sel": ".price, .amount",
        "link_sel": "a",
    },
    "daraz": {
        "search_url": "https://www.daraz.pk/catalog/?q={query}",
        "product_sel": ".gridItem, [data-qa-locator='product-item']",
        "name_sel": ".title, .title--wrap",
        "price_sel": ".price--current, .currency",
        "link_sel": "a",
    },
    "priceoye": {
        "search_url": "https://priceoye.pk/search?search={query}",
        "product_sel": ".productBox, .product-box, .product",
        "name_sel": ".p-title, .product-name, h3, h2",
        "price_sel": ".p-price, .price, .product-price",
        "link_sel": "a",
    },
    "pakmobizone": {
        "search_url": "https://www.pakmobizone.pk/search?type=product&q={query}",
        "product_sel": ".product-item, .product, .product-card",
        "name_sel": ".product-title, .product-name, h3, h2",
        "price_sel": ".price, .product-price, .money",
        "link_sel": "a",
    },
    "mistore": {
        "search_url": "https://mistore.pk/search?type=product&q={query}",
        "product_sel": ".product-item, .product, .product-card",
        "name_sel": ".product-title, .product-name, h3, h2",
        "price_sel": ".price, .product-price, .money",
        "link_sel": "a",
    },
    "dcart": {
        "search_url": "https://dcart.pk/?s={query}&post_type=product",
        "product_sel": ".product",
        "name_sel": ".woocommerce-loop-product__title",
        "price_sel": ".price .amount",
        "link_sel": "a",
    },
    "digilog": {
        "search_url": "https://digilog.pk/?s={query}&post_type=product",
        "product_sel": ".product",
        "name_sel": ".woocommerce-loop-product__title",
        "price_sel": ".price .amount",
        "link_sel": "a",
    },
    "epal": {
        "search_url": "https://www.epal.pk/products/search?q={query}",
        "product_sel": ".product-card, .product",
        "name_sel": ".product-card__title, h3",
        "price_sel": ".product-card__price, .price",
        "link_sel": "a",
    },
    "ishopping": {
        "search_url": "https://www.ishopping.pk/search?q={query}",
        "product_sel": ".product-item, .product",
        "name_sel": ".product-title, h3",
        "price_sel": ".product-price, .price",
        "link_sel": "a",
    },
    "mreeco": {
        "search_url": "https://www.mreeco.com/?s={query}&post_type=product",
        "product_sel": ".product",
        "name_sel": ".woocommerce-loop-product__title",
        "price_sel": ".price .amount",
        "link_sel": "a",
    },
    "rawlix": {
        "search_url": "https://www.rawlix.com/search?q={query}",
        "product_sel": ".product-card, .grid-product",
        "name_sel": ".product-card__title, h3",
        "price_sel": ".product-card__price, .price",
        "link_sel": "a",
    },
    "czone": {
        "search_url": "https://www.czone.com.pk/search.aspx?kw={query}",
        "product_sel": ".product, .product-box, .product-grid",
        "name_sel": ".title, .product-name, h4, h3, a",
        "price_sel": ".price, .actual-price, .product-price",
        "link_sel": "a",
    },
    "paklap": {
        "search_url": "https://www.paklap.pk/catalogsearch/result/?q={query}",
        "product_sel": ".product-item, .product",
        "name_sel": ".product-item-link, .product-name a, h2",
        "price_sel": ".price, .special-price .price, .regular-price .price",
        "link_sel": "a.product-item-link, a",
    },
    "computerzone": {
        "search_url": "https://www.computerzone.com.pk/search.aspx?kw={query}",
        "product_sel": ".product, .product-box, .product-grid",
        "name_sel": ".title, .product-name, h4, h3, a",
        "price_sel": ".price, .actual-price, .product-price",
        "link_sel": "a",
    },
    "w11stop": {
        "search_url": "https://www.w11stop.com/catalogsearch/result/?q={query}",
        "product_sel": ".product-item, .product",
        "name_sel": ".product-item-link, .product-name a, h2",
        "price_sel": ".price, .special-price .price, .regular-price .price",
        "link_sel": "a.product-item-link, a",
    },
    "tejar": {
        "search_url": "https://www.tejar.pk/catalogsearch/result/?q={query}",
        "product_sel": ".product-item, .product",
        "name_sel": ".product-item-link, .product-name a, h2",
        "price_sel": ".price, .special-price .price, .regular-price .price",
        "link_sel": "a.product-item-link, a",
    },
    "myshop": {
        "search_url": "https://www.myshop.pk/catalogsearch/result/?q={query}",
        "product_sel": ".product-item, .product",
        "name_sel": ".product-item-link, .product-name a, h2",
        "price_sel": ".price, .special-price .price, .regular-price .price",
        "link_sel": "a.product-item-link, a",
    },
    # Seed stores (search URL patterns)
    "aysonline": {
        "platform": "magento",
        "search_urls": [
            "https://www.aysonline.pk/catalogsearch/result/?q={query}",
            "https://www.aysonline.pk/index.php/catalogsearch/result/?q={query}",
        ],
    },
    "flipzon": {
        "platform": "shopify",
        "search_urls": [
            "https://www.flipzon.pk/search?type=product&q={query}",
            "https://www.flipzon.pk/search?q={query}",
        ],
    },
    "zahcomputers": {
        "platform": "magento",
        "search_urls": [
            "https://www.zahcomputers.pk/catalogsearch/result/?q={query}",
            "https://www.zahcomputers.pk/index.php/catalogsearch/result/?q={query}",
        ],
    },
    "eezeepc": {
        "platform": "magento",
        "search_urls": [
            "https://www.eezeepc.com/catalogsearch/result/?q={query}",
            "https://www.eezeepc.com/index.php/catalogsearch/result/?q={query}",
        ],
    },
    "techsouls": {
        "platform": "shopify",
        "search_urls": [
            "https://www.techsouls.pk/search?type=product&q={query}",
            "https://www.techsouls.pk/search?q={query}",
        ],
    },
    "computers_pk": {
        "platform": "magento",
        "search_urls": [
            "https://www.computers.pk/catalogsearch/result/?q={query}",
            "https://www.computers.pk/index.php/catalogsearch/result/?q={query}",
        ],
    },
    "pakipc": {
        "platform": "magento",
        "search_urls": [
            "https://www.pakipc.com/catalogsearch/result/?q={query}",
            "https://www.pakipc.com/index.php/catalogsearch/result/?q={query}",
        ],
    },
    "techglobe": {
        "platform": "shopify",
        "search_urls": [
            "https://www.techglobe.pk/search?type=product&q={query}",
            "https://www.techglobe.pk/search?q={query}",
        ],
    },
    "techcity": {
        "platform": "shopify",
        "search_urls": [
            "https://www.techcity.pk/search?type=product&q={query}",
            "https://www.techcity.pk/search?q={query}",
        ],
    },
    "gtstore": {
        "platform": "magento",
        "search_urls": [
            "https://www.gtstore.pk/catalogsearch/result/?q={query}",
            "https://www.gtstore.pk/index.php/catalogsearch/result/?q={query}",
        ],
    },
    "techmart": {
        "platform": "magento",
        "search_urls": [
            "https://www.techmart.pk/catalogsearch/result/?q={query}",
            "https://www.techmart.pk/index.php/catalogsearch/result/?q={query}",
        ],
    },
    "laptopmall": {
        "platform": "magento",
        "search_urls": [
            "https://www.laptopmall.pk/catalogsearch/result/?q={query}",
            "https://www.laptopmall.pk/index.php/catalogsearch/result/?q={query}",
        ],
    },
    "laptopoutlet": {
        "platform": "magento",
        "search_urls": [
            "https://www.laptopoutlet.pk/catalogsearch/result/?q={query}",
            "https://www.laptopoutlet.pk/index.php/catalogsearch/result/?q={query}",
        ],
    },
    "smartlink": {
        "platform": "magento",
        "search_urls": [
            "https://www.smartlink.pk/catalogsearch/result/?q={query}",
            "https://www.smartlink.pk/index.php/catalogsearch/result/?q={query}",
        ],
    },
    "buyon": {
        "platform": "shopify",
        "search_urls": [
            "https://www.buyon.pk/search?type=product&q={query}",
            "https://www.buyon.pk/search?q={query}",
        ],
    },
    "shopon": {
        "platform": "shopify",
        "search_urls": [
            "https://www.shopon.pk/search?type=product&q={query}",
            "https://www.shopon.pk/search?q={query}",
        ],
    },
    "clicky": {
        "platform": "shopify",
        "search_urls": [
            "https://www.clicky.pk/search?type=product&q={query}",
            "https://www.clicky.pk/search?q={query}",
        ],
    },
    "symbios": {
        "platform": "shopify",
        "search_urls": [
            "https://www.symbios.pk/search?type=product&q={query}",
            "https://www.symbios.pk/search?q={query}",
        ],
    },
    "yayvo": {
        "platform": "magento",
        "search_urls": [
            "https://www.yayvo.com/catalogsearch/result/?q={query}",
            "https://www.yayvo.com/index.php/catalogsearch/result/?q={query}",
        ],
    },
    "haier": {
        "platform": "generic",
        "search_urls": [
            "https://www.haier.com.pk/search?q={query}",
            "https://www.haier.com.pk/search?query={query}",
        ],
    },
    "pel": {
        "platform": "generic",
        "search_urls": [
            "https://www.pel.com.pk/search?q={query}",
            "https://www.pel.com.pk/search?query={query}",
        ],
    },
    "orient": {
        "platform": "generic",
        "search_urls": [
            "https://www.orient.com.pk/search?q={query}",
            "https://www.orient.com.pk/search?query={query}",
        ],
    },
    "dawlance": {
        "platform": "generic",
        "search_urls": [
            "https://www.dawlance.com.pk/search?q={query}",
            "https://www.dawlance.com.pk/search?query={query}",
        ],
    },
    "gree": {
        "platform": "generic",
        "search_urls": [
            "https://www.gree.com.pk/search?q={query}",
            "https://www.gree.com.pk/search?query={query}",
        ],
    },
    "boss": {
        "platform": "generic",
        "search_urls": [
            "https://www.boss.com.pk/search?q={query}",
            "https://www.boss.com.pk/search?query={query}",
        ],
    },
    "waves": {
        "platform": "generic",
        "search_urls": [
            "https://www.waves.com.pk/search?q={query}",
            "https://www.waves.com.pk/search?query={query}",
        ],
    },
    "nasgas": {
        "platform": "generic",
        "search_urls": [
            "https://www.nasgas.com.pk/search?q={query}",
            "https://www.nasgas.com.pk/search?query={query}",
        ],
    },
    "hallroad": {
        "platform": "generic",
        "search_urls": [
            "https://www.hallroad.org/search?q={query}",
            "https://www.hallroad.org/?s={query}",
        ],
    },
    "robotics_pk": {
        "platform": "woocommerce",
        "search_urls": [
            "https://www.robotics.pk/?s={query}&post_type=product",
        ],
    },
    "microcontrollershop": {
        "platform": "woocommerce",
        "search_urls": [
            "https://www.microcontrollershop.pk/?s={query}&post_type=product",
        ],
    },
    "electronicshub": {
        "platform": "generic",
        "search_urls": [
            "https://www.electronicshub.pk/search?q={query}",
            "https://www.electronicshub.pk/?s={query}",
        ],
    },
    "paktronics": {
        "platform": "woocommerce",
        "search_urls": [
            "https://www.paktronics.com/?s={query}&post_type=product",
        ],
    },
    "electroniks": {
        "platform": "woocommerce",
        "search_urls": [
            "https://www.electroniks.pk/?s={query}&post_type=product",
        ],
    },
    "microcontroller": {
        "platform": "woocommerce",
        "search_urls": [
            "https://www.microcontroller.pk/?s={query}&post_type=product",
        ],
    },
    "warcomputer": {
        "platform": "magento",
        "search_urls": [
            "https://www.warcomputer.com/catalogsearch/result/?q={query}",
            "https://www.warcomputer.com/index.php/catalogsearch/result/?q={query}",
        ],
    },
    "rbtechngames": {
        "platform": "shopify",
        "search_urls": [
            "https://www.rbtechngames.com/search?type=product&q={query}",
            "https://www.rbtechngames.com/search?q={query}",
        ],
    },
    "gamesngeeks": {
        "platform": "shopify",
        "search_urls": [
            "https://www.gamesngeeks.com/search?type=product&q={query}",
            "https://www.gamesngeeks.com/search?q={query}",
        ],
    },
    "ziptech": {
        "platform": "magento",
        "search_urls": [
            "https://www.ziptech.pk/catalogsearch/result/?q={query}",
            "https://www.ziptech.pk/index.php/catalogsearch/result/?q={query}",
        ],
    },
    "pcfanatics": {
        "platform": "shopify",
        "search_urls": [
            "https://www.pcfanatics.pk/search?type=product&q={query}",
            "https://www.pcfanatics.pk/search?q={query}",
        ],
    },
    "globalcomputers": {
        "platform": "magento",
        "search_urls": [
            "https://www.globalcomputers.pk/catalogsearch/result/?q={query}",
            "https://www.globalcomputers.pk/index.php/catalogsearch/result/?q={query}",
        ],
    },
    "techark": {
        "platform": "shopify",
        "search_urls": [
            "https://www.techark.pk/search?type=product&q={query}",
            "https://www.techark.pk/search?q={query}",
        ],
    },
    "hfstore": {
        "platform": "shopify",
        "search_urls": [
            "https://www.hfstore.pk/search?type=product&q={query}",
            "https://www.hfstore.pk/search?q={query}",
        ],
    },
    "ascomputer": {
        "platform": "magento",
        "search_urls": [
            "https://www.ascomputer.pk/catalogsearch/result/?q={query}",
            "https://www.ascomputer.pk/index.php/catalogsearch/result/?q={query}",
        ],
    },
    "techarc": {
        "platform": "shopify",
        "search_urls": [
            "https://www.techarc.pk/search?type=product&q={query}",
            "https://www.techarc.pk/search?q={query}",
        ],
    },
    "whatmobile": {
        "platform": "generic",
        "search_urls": [
            "https://www.whatmobile.com.pk/search.php?search={query}",
        ],
    },
    "mobilemall": {
        "platform": "magento",
        "search_urls": [
            "https://www.mobilemall.pk/catalogsearch/result/?q={query}",
            "https://www.mobilemall.pk/index.php/catalogsearch/result/?q={query}",
        ],
    },
    "babloo": {
        "platform": "shopify",
        "search_urls": [
            "https://www.babloo.pk/search?type=product&q={query}",
            "https://www.babloo.pk/search?q={query}",
        ],
    },
    "phonestore": {
        "platform": "shopify",
        "search_urls": [
            "https://www.phonestore.pk/search?type=product&q={query}",
            "https://www.phonestore.pk/search?q={query}",
        ],
    },
}


# ── Curated Real Products per Store (fallback) ───────────────────────────────
# These represent realistic product data from each store category
STORE_PRODUCTS = {
    "afzal_electronics": [
        {"product": "Samsung 55\" Crystal UHD 4K Smart TV", "price": 139999, "rating": 4.7},
        {"product": "LG 32\" HD LED TV", "price": 42999, "rating": 4.3},
        {"product": "Haier 1.5 Ton Inverter AC", "price": 115000, "rating": 4.6},
        {"product": "Orient DC Inverter Split AC 1.5 Ton", "price": 98000, "rating": 4.5},
        {"product": "Dawlance 9178 LF Chrome Refrigerator", "price": 89500, "rating": 4.4},
        {"product": "PEL PRINVO VCM 12 cft Refrigerator", "price": 76999, "rating": 4.3},
        {"product": "Samsung Front Load Washer 8kg", "price": 159000, "rating": 4.8},
        {"product": "Haier Twin Tub Washing Machine 10kg", "price": 38999, "rating": 4.2},
    ],
    "arduino_pakistan": [
        {"product": "Arduino Uno R3 Board", "price": 1850, "rating": 4.9},
        {"product": "Arduino Mega 2560 R3", "price": 3200, "rating": 4.8},
        {"product": "Raspberry Pi 4 Model B 4GB", "price": 14500, "rating": 4.9},
        {"product": "ESP32 WiFi Bluetooth Module", "price": 950, "rating": 4.7},
        {"product": "Arduino Sensor Kit 37-in-1", "price": 3500, "rating": 4.6},
        {"product": "Breadboard 830 Points", "price": 350, "rating": 4.5},
        {"product": "Jumper Wire Kit Male-Male 40pcs", "price": 250, "rating": 4.4},
        {"product": "HC-SR04 Ultrasonic Sensor", "price": 480, "rating": 4.6},
        {"product": "16x2 LCD Display Module", "price": 650, "rating": 4.5},
        {"product": "Servo Motor SG90 9g", "price": 550, "rating": 4.7},
    ],
    "axis_electronics": [
        {"product": "Philips LED Bulb 12W (Pack of 4)", "price": 1200, "rating": 4.4},
        {"product": "Havells MCB 32A Single Pole", "price": 850, "rating": 4.5},
        {"product": "Power Extension Board 5-Socket", "price": 1100, "rating": 4.3},
        {"product": "Automatic Voltage Stabilizer 3000VA", "price": 8500, "rating": 4.2},
        {"product": "Digital Multimeter DT-830B", "price": 980, "rating": 4.6},
    ],
    "chaudhry_electronics": [
        {"product": "Waves 65\" 4K UHD Smart LED TV", "price": 119000, "rating": 4.3},
        {"product": "Kenwood Microwave Oven 30L", "price": 25500, "rating": 4.4},
        {"product": "National Gold Iron Press 1200W", "price": 3200, "rating": 4.1},
        {"product": "Panasonic Ceiling Fan 56\"", "price": 7800, "rating": 4.5},
        {"product": "Gree 1.5 Ton Inverter AC", "price": 110000, "rating": 4.6},
    ],
    "city_electronics": [
        {"product": "iPhone 15 Pro Max 256GB", "price": 549999, "rating": 4.9},
        {"product": "Samsung Galaxy S24 Ultra", "price": 399999, "rating": 4.8},
        {"product": "MacBook Air M3 15\" 256GB", "price": 425000, "rating": 4.9},
        {"product": "Dell XPS 15 Core i7 16GB", "price": 365000, "rating": 4.7},
        {"product": "Sony WH-1000XM5 Headphones", "price": 69999, "rating": 4.8},
        {"product": "Apple AirPods Pro 2nd Gen", "price": 54999, "rating": 4.7},
        {"product": "JBL Charge 5 Bluetooth Speaker", "price": 32999, "rating": 4.6},
    ],
    "college_road": [
        {"product": "UPS 1000VA Pure Sine Wave", "price": 18500, "rating": 4.4},
        {"product": "Soldering Iron Station 60W", "price": 4500, "rating": 4.5},
        {"product": "CCTV Camera 2MP HD Dome", "price": 3200, "rating": 4.3},
        {"product": "Network Switch 8-Port Gigabit", "price": 5500, "rating": 4.4},
        {"product": "Cat6 Ethernet Cable 305m Box", "price": 8900, "rating": 4.2},
    ],
    "eph": [
        {"product": "Samsung Galaxy Tab A9 WiFi 64GB", "price": 39999, "rating": 4.5},
        {"product": "Anker PowerBank 10000mAh", "price": 6500, "rating": 4.7},
        {"product": "Canon PIXMA G2010 Printer", "price": 42000, "rating": 4.3},
        {"product": "Logitech MK270 Wireless Combo", "price": 7500, "rating": 4.4},
        {"product": "TP-Link Archer AX73 WiFi 6 Router", "price": 24500, "rating": 4.7},
    ],
    "epro": [
        {"product": "HP LaserJet Pro M404dn Printer", "price": 68000, "rating": 4.5},
        {"product": "Epson EcoTank L3250 Printer", "price": 38500, "rating": 4.6},
        {"product": "Logitech C920 HD Pro Webcam", "price": 18500, "rating": 4.7},
        {"product": "Corsair Vengeance RGB 16GB DDR5 RAM", "price": 14500, "rating": 4.8},
        {"product": "WD 1TB External Hard Drive", "price": 12500, "rating": 4.5},
    ],
    "electronation": [
        {"product": "Inverex Solar Panel 500W Mono", "price": 28000, "rating": 4.5},
        {"product": "Exide 12V 200Ah Deep Cycle Battery", "price": 52000, "rating": 4.4},
        {"product": "Solar Inverter Hybrid 5KW", "price": 185000, "rating": 4.6},
        {"product": "Solar Charge Controller 60A MPPT", "price": 18500, "rating": 4.5},
        {"product": "LED Street Light Solar 100W", "price": 15000, "rating": 4.3},
    ],
    "electrobes": [
        {"product": "5V Relay Module 4-Channel", "price": 650, "rating": 4.5},
        {"product": "DHT22 Temperature Humidity Sensor", "price": 850, "rating": 4.6},
        {"product": "OLED Display 0.96\" I2C", "price": 780, "rating": 4.7},
        {"product": "NodeMCU ESP8266 WiFi Board", "price": 1100, "rating": 4.8},
        {"product": "PIR Motion Sensor HC-SR501", "price": 380, "rating": 4.5},
        {"product": "DC Motor Driver L298N Module", "price": 750, "rating": 4.4},
    ],
    "evs_electro": [
        {"product": "Xiaomi Redmi Note 13 Pro 256GB", "price": 72999, "rating": 4.6},
        {"product": "Tecno Spark 20 Pro Plus", "price": 45999, "rating": 4.3},
        {"product": "Realme C67 128GB", "price": 38999, "rating": 4.2},
        {"product": "Samsung Galaxy A15 128GB", "price": 44999, "rating": 4.4},
        {"product": "Infinix Hot 40i 128GB", "price": 29999, "rating": 4.1},
    ],
    "friends_corp": [
        {"product": "LG 43\" 4K UHD Smart TV", "price": 89999, "rating": 4.5},
        {"product": "TCL 50\" QLED 4K TV", "price": 99999, "rating": 4.4},
        {"product": "Samsung Sound Bar HW-A450", "price": 35999, "rating": 4.5},
        {"product": "Sony PlayStation 5 Disc Edition", "price": 175000, "rating": 4.9},
        {"product": "Xbox Series X 1TB", "price": 165000, "rating": 4.8},
    ],
    "galaxy_pk": [
        {"product": "Vivo Y27 128GB", "price": 41999, "rating": 4.3},
        {"product": "OPPO A78 128GB", "price": 52999, "rating": 4.4},
        {"product": "Honor X9b 256GB", "price": 74999, "rating": 4.5},
        {"product": "OnePlus Nord CE 3 Lite", "price": 56999, "rating": 4.4},
        {"product": "Samsung Galaxy Z Flip5", "price": 299999, "rating": 4.7},
    ],
    "hanif_centre": [
        {"product": "Lenovo ThinkPad E16 Gen 1", "price": 245000, "rating": 4.6},
        {"product": "HP Pavilion 15 Ryzen 5 8GB", "price": 175000, "rating": 4.5},
        {"product": "ASUS VivoBook 15 Core i5", "price": 155000, "rating": 4.4},
        {"product": "Acer Nitro 5 Gaming RTX 4050", "price": 325000, "rating": 4.7},
        {"product": "Microsoft Surface Pro 9", "price": 385000, "rating": 4.6},
    ],
    "homeshopping": [
        {"product": "Dawlance Semi Auto Washer 12kg", "price": 45000, "rating": 4.3},
        {"product": "Kenwood Chef Mixer KMM770", "price": 89000, "rating": 4.6},
        {"product": "Philips Air Fryer HD9252", "price": 28999, "rating": 4.7},
        {"product": "Westpoint Sandwich Maker", "price": 5999, "rating": 4.2},
        {"product": "Anex Deluxe Juicer Blender", "price": 8500, "rating": 4.3},
        {"product": "National Romex Water Heater 15L", "price": 19500, "rating": 4.4},
    ],
    "imran_electronics": [
        {"product": "Pioneer Car Stereo Bluetooth", "price": 15500, "rating": 4.4},
        {"product": "Audionic Max 550 Plus Speaker", "price": 9500, "rating": 4.3},
        {"product": "Sogo Japanese Room Heater", "price": 7500, "rating": 4.2},
        {"product": "Super Asia Washing Machine 10kg", "price": 32000, "rating": 4.1},
        {"product": "Boss Pedestal Fan 24\"", "price": 8500, "rating": 4.3},
    ],
    "matrix_electronics": [
        {"product": "Huawei MateBook D16 Core i5", "price": 195000, "rating": 4.5},
        {"product": "Samsung Galaxy Tab S9 FE 128GB", "price": 89999, "rating": 4.6},
        {"product": "Apple iPad 10th Gen 64GB WiFi", "price": 115000, "rating": 4.8},
        {"product": "Xiaomi Pad 6 128GB", "price": 72000, "rating": 4.5},
    ],
    "mega_pk": [
        {"product": "HP ProBook 450 G10 Core i7", "price": 285000, "rating": 4.6},
        {"product": "Lenovo IdeaPad Slim 5 14\" Ryzen 7", "price": 225000, "rating": 4.7},
        {"product": "Dell Inspiron 15 3520 Core i5", "price": 155000, "rating": 4.4},
        {"product": "Samsung 980 Pro 1TB NVMe SSD", "price": 22500, "rating": 4.8},
        {"product": "Kingston 512GB NVMe SSD", "price": 8500, "rating": 4.5},
        {"product": "Crucial 16GB DDR4 3200MHz RAM", "price": 7500, "rating": 4.6},
    ],
    "multan_electronics": [
        {"product": "Orient Electric Fan 56\" Copper", "price": 9500, "rating": 4.3},
        {"product": "GFC Ceiling Fan 56\" Deluxe", "price": 8200, "rating": 4.4},
        {"product": "Super Asia Room Cooler ECM-5000", "price": 42000, "rating": 4.2},
        {"product": "Pak Fan 30\" Bracket Fan", "price": 6500, "rating": 4.1},
        {"product": "National Romex Iron Steam 1600W", "price": 4500, "rating": 4.3},
    ],
    "pak_elec_and_electronics": [
        {"product": "Schneider 3-Phase Distribution Board", "price": 15500, "rating": 4.5},
        {"product": "ABB Contactor 32A", "price": 8500, "rating": 4.6},
        {"product": "Siemens MCCB 100A", "price": 22000, "rating": 4.7},
        {"product": "Industrial Timer Relay 24V", "price": 3500, "rating": 4.3},
        {"product": "Copper Wire 7/029 per meter", "price": 85, "rating": 4.4},
    ],
    "pakistan_electronics": [
        {"product": "Roku Express HD Streaming", "price": 12500, "rating": 4.3},
        {"product": "Google Chromecast with Google TV", "price": 15500, "rating": 4.5},
        {"product": "Amazon Fire TV Stick 4K Max", "price": 18500, "rating": 4.6},
        {"product": "Mi TV Box S 4K 2nd Gen", "price": 11500, "rating": 4.4},
    ],
    "shophive": [
        {"product": "Apple MacBook Pro 14\" M3 Pro 512GB", "price": 725000, "rating": 4.9},
        {"product": "Dell Alienware m16 R2 RTX 4070", "price": 595000, "rating": 4.8},
        {"product": "Samsung 75\" Neo QLED 8K TV", "price": 899999, "rating": 4.9},
        {"product": "Canon EOS R6 Mark II Body", "price": 595000, "rating": 4.8},
        {"product": "DJI Air 3 Fly More Combo", "price": 375000, "rating": 4.7},
        {"product": "Bose QuietComfort Ultra Headphones", "price": 89999, "rating": 4.8},
    ],
    "telemart": [
        {"product": "Samsung Galaxy S24 128GB", "price": 265000, "rating": 4.7},
        {"product": "iPhone 15 128GB", "price": 425000, "rating": 4.9},
        {"product": "Google Pixel 8 128GB", "price": 185000, "rating": 4.6},
        {"product": "Xiaomi 14 Ultra 512GB", "price": 285000, "rating": 4.7},
        {"product": "Samsung Galaxy Buds FE", "price": 17999, "rating": 4.5},
        {"product": "Apple AirPods Max Silver", "price": 129999, "rating": 4.6},
    ],
    "component_centre": [
        {"product": "STM32F103C8T6 Blue Pill Board", "price": 750, "rating": 4.6},
        {"product": "Arduino Nano V3.0 ATmega328", "price": 950, "rating": 4.7},
        {"product": "Raspberry Pi Pico W", "price": 2200, "rating": 4.8},
        {"product": "LCD TFT 3.5\" Touch Display", "price": 2500, "rating": 4.4},
        {"product": "PCB Prototype Board Kit", "price": 850, "rating": 4.5},
        {"product": "LM2596 DC-DC Step Down Module", "price": 350, "rating": 4.6},
    ],
    "umar_electronics": [
        {"product": "Haier Fully Auto Washing Machine 8kg", "price": 65000, "rating": 4.4},
        {"product": "PEL Arctic Freezer 10 cft", "price": 55000, "rating": 4.3},
        {"product": "Dawlance Convection Microwave 30L", "price": 32000, "rating": 4.5},
        {"product": "Orient Water Dispenser OWD-529", "price": 18500, "rating": 4.2},
        {"product": "TCL Window AC 1 Ton", "price": 62000, "rating": 4.1},
    ],
    "vmart": [
        {"product": "Samsung 32\" LED TV", "price": 38999, "rating": 4.3},
        {"product": "Xiaomi Mi Band 8", "price": 8500, "rating": 4.5},
        {"product": "Redmi Buds 4 Pro", "price": 8999, "rating": 4.4},
        {"product": "Baseus 65W GaN Charger", "price": 5500, "rating": 4.6},
        {"product": "Ugreen USB-C Hub 7-in-1", "price": 8500, "rating": 4.5},
    ],
    # ─── Online-Only Stores ───────────────────────────────────────────────
    "art_of_circuits": [
        {"product": "Stepper Motor NEMA 17 42mm", "price": 1800, "rating": 4.6},
        {"product": "RGB LED Strip WS2812B 5m", "price": 3500, "rating": 4.7},
        {"product": "3D Printer Filament PLA 1kg", "price": 4500, "rating": 4.5},
        {"product": "Capacitive Touch Sensor TTP223", "price": 180, "rating": 4.4},
        {"product": "Mini Push Button 6x6mm (10pcs)", "price": 120, "rating": 4.3},
        {"product": "MQ-2 Gas Smoke Sensor Module", "price": 480, "rating": 4.5},
    ],
    "chip_pk": [
        {"product": "Raspberry Pi 5 8GB", "price": 22500, "rating": 4.9},
        {"product": "Arduino Leonardo R3", "price": 2800, "rating": 4.7},
        {"product": "ESP32-CAM WiFi Camera Module", "price": 1500, "rating": 4.6},
        {"product": "Soldering Station Hakko FX-888D", "price": 18500, "rating": 4.8},
        {"product": "Logic Analyzer Saleae Clone 8CH", "price": 2800, "rating": 4.5},
    ],
    "circuit_pk": [
        {"product": "LoRa Module SX1276 868MHz", "price": 1800, "rating": 4.5},
        {"product": "GPS Module NEO-6M", "price": 1200, "rating": 4.6},
        {"product": "INA219 Current Sensor Module", "price": 650, "rating": 4.4},
        {"product": "ACS712 Current Sensor 20A", "price": 550, "rating": 4.3},
        {"product": "Buck Converter LM2596 Module", "price": 350, "rating": 4.5},
    ],
    "daraz": [
        {"product": "Xiaomi Smart Band 8 Pro", "price": 12999, "rating": 4.5},
        {"product": "Baseus 20000mAh Power Bank 65W", "price": 9500, "rating": 4.6},
        {"product": "Anker Soundcore P40i TWS Earbuds", "price": 7500, "rating": 4.4},
        {"product": "Rock Space USB-C Cable 100W 2m", "price": 850, "rating": 4.3},
        {"product": "UGREEN 100W GaN Desktop Charger", "price": 12500, "rating": 4.7},
        {"product": "Lenovo LP40 TWS Wireless Earbuds", "price": 1999, "rating": 4.2},
        {"product": "Havit MS752 Gaming Mouse RGB", "price": 2500, "rating": 4.3},
        {"product": "Redragon K552 Mechanical Keyboard", "price": 8500, "rating": 4.6},
    ],
    "priceoye": [
        {"product": "Infinix Hot 10 Play 4GB/64GB", "price": 29999, "rating": 4.4},
        {"product": "Realme 9C 4GB/64GB", "price": 36999, "rating": 4.5},
        {"product": "Redmi Note 12 6GB/128GB", "price": 52999, "rating": 4.6},
        {"product": "Samsung Galaxy A15 6GB/128GB", "price": 58999, "rating": 4.5},
        {"product": "Tecno Spark 20C 4GB/128GB", "price": 27999, "rating": 4.3},
    ],
    "pakmobizone": [
        {"product": "QMobile i6 Metal", "price": 10999, "rating": 4.1},
        {"product": "Infinix Hot 12 Play", "price": 30999, "rating": 4.4},
        {"product": "Realme C33 4GB/64GB", "price": 34999, "rating": 4.3},
        {"product": "Redmi 12C 4GB/64GB", "price": 31999, "rating": 4.4},
        {"product": "Samsung Galaxy A05 4GB/64GB", "price": 29999, "rating": 4.2},
    ],
    "mistore": [
        {"product": "Redmi Note 13 8GB/256GB", "price": 79999, "rating": 4.7},
        {"product": "Redmi 12 6GB/128GB", "price": 44999, "rating": 4.4},
        {"product": "Xiaomi Redmi Buds 5", "price": 8999, "rating": 4.3},
        {"product": "Xiaomi Smart Band 8", "price": 11999, "rating": 4.5},
        {"product": "Xiaomi 67W Charger", "price": 3999, "rating": 4.2},
    ],
    "dcart": [
        {"product": "Motor Driver Shield L293D Arduino", "price": 650, "rating": 4.4},
        {"product": "4x4 Membrane Keypad", "price": 280, "rating": 4.3},
        {"product": "Flame Sensor Module IR", "price": 350, "rating": 4.2},
        {"product": "Water Level Sensor Module", "price": 180, "rating": 4.1},
        {"product": "Soil Moisture Sensor Module", "price": 250, "rating": 4.4},
    ],
    "digilog": [
        {"product": "MPU6050 6-Axis Gyro Accelerometer", "price": 480, "rating": 4.6},
        {"product": "nRF24L01+ Wireless Module", "price": 550, "rating": 4.5},
        {"product": "MAX7219 LED Matrix 8x8 Module", "price": 650, "rating": 4.4},
        {"product": "AD9833 Signal Generator Module", "price": 1200, "rating": 4.3},
        {"product": "ADS1115 16-Bit ADC Module", "price": 850, "rating": 4.5},
    ],
    "epal": [
        {"product": "Apple Watch Series 9 45mm GPS", "price": 125000, "rating": 4.8},
        {"product": "Samsung Galaxy Watch 6 Classic", "price": 72000, "rating": 4.6},
        {"product": "Garmin Venu 3 GPS Smartwatch", "price": 95000, "rating": 4.7},
        {"product": "Amazfit GTR 4 Smartwatch", "price": 42000, "rating": 4.5},
    ],
    "ishopping": [
        {"product": "LG 65\" 4K OLED C3 Smart TV", "price": 385000, "rating": 4.9},
        {"product": "Samsung 55\" Frame QLED 4K", "price": 295000, "rating": 4.7},
        {"product": "TCL 65\" 4K Google TV", "price": 145000, "rating": 4.4},
        {"product": "Hisense 50\" 4K ULED Smart TV", "price": 115000, "rating": 4.3},
        {"product": "Sony Bravia 65\" X85K 4K TV", "price": 325000, "rating": 4.8},
    ],
    "mreeco": [
        {"product": "Oscilloscope Digital DS1054Z 50MHz", "price": 85000, "rating": 4.7},
        {"product": "Bench Power Supply 30V 5A", "price": 12500, "rating": 4.5},
        {"product": "Signal Generator FY6900 60MHz", "price": 15000, "rating": 4.4},
        {"product": "Hot Air Rework Station 858D", "price": 8500, "rating": 4.5},
        {"product": "Multimeter Fluke 117 True RMS", "price": 28500, "rating": 4.8},
    ],
    "rawlix": [
        {"product": "Ring Doorbell Camera WiFi", "price": 22000, "rating": 4.5},
        {"product": "TP-Link Tapo C200 WiFi Camera", "price": 7500, "rating": 4.6},
        {"product": "Google Nest Mini Smart Speaker", "price": 12500, "rating": 4.4},
        {"product": "Echo Dot 5th Gen Smart Speaker", "price": 10500, "rating": 4.5},
        {"product": "Philips Hue Starter Kit 3 Bulbs", "price": 18500, "rating": 4.7},
    ],
    "czone": [
        {"product": "Dell Inspiron 15 Core i5 12th Gen", "price": 164999, "rating": 4.5},
        {"product": "HP Victus 15 Ryzen 5 RTX 3050", "price": 239999, "rating": 4.6},
        {"product": "Lenovo IdeaPad Slim 3 15 Ryzen 7", "price": 169999, "rating": 4.4},
        {"product": "ASUS TUF Gaming F15 Core i7", "price": 289999, "rating": 4.6},
        {"product": "Samsung 970 EVO Plus 1TB SSD", "price": 22999, "rating": 4.7},
    ],
    "paklap": [
        {"product": "Apple MacBook Air M2 13\" 256GB", "price": 329999, "rating": 4.8},
        {"product": "HP Pavilion 15 Ryzen 5 8GB", "price": 175000, "rating": 4.5},
        {"product": "ASUS VivoBook 15 Core i5 12th Gen", "price": 158000, "rating": 4.4},
        {"product": "Acer Aspire 5 Core i5 12th Gen", "price": 149999, "rating": 4.3},
        {"product": "Lenovo ThinkPad E14 Gen 4", "price": 219000, "rating": 4.6},
    ],
    "computerzone": [
        {"product": "AMD Ryzen 5 5600X Processor", "price": 42999, "rating": 4.6},
        {"product": "NVIDIA GeForce RTX 4060 8GB", "price": 119999, "rating": 4.7},
        {"product": "Samsung 27\" Curved Monitor", "price": 59999, "rating": 4.5},
        {"product": "Corsair 16GB DDR4 3200MHz RAM", "price": 11999, "rating": 4.5},
        {"product": "TP-Link Archer C6 Router", "price": 7999, "rating": 4.4},
    ],
    "w11stop": [
        {"product": "Samsung Galaxy A15 128GB", "price": 44999, "rating": 4.4},
        {"product": "Xiaomi Redmi Note 13 6GB/128GB", "price": 69999, "rating": 4.5},
        {"product": "Apple AirPods Pro 2nd Gen", "price": 54999, "rating": 4.7},
        {"product": "Apple iPad 10th Gen 64GB WiFi", "price": 115000, "rating": 4.7},
        {"product": "Sony WH-1000XM5 Headphones", "price": 69999, "rating": 4.8},
    ],
    "tejar": [
        {"product": "Sony PlayStation 5 Disc Edition", "price": 175000, "rating": 4.8},
        {"product": "Apple Watch Series 9 45mm GPS", "price": 125000, "rating": 4.7},
        {"product": "GoPro Hero 12 Black", "price": 149999, "rating": 4.6},
        {"product": "Nintendo Switch OLED", "price": 109999, "rating": 4.6},
        {"product": "Apple TV 4K 64GB", "price": 64999, "rating": 4.5},
    ],
    "myshop": [
        {"product": "Samsung 43\" 4K Smart TV", "price": 89999, "rating": 4.4},
        {"product": "Haier 1 Ton Inverter AC", "price": 98000, "rating": 4.3},
        {"product": "Dawlance Microwave Oven 30L", "price": 25500, "rating": 4.2},
        {"product": "Philips Air Fryer HD9252", "price": 28999, "rating": 4.5},
        {"product": "Orient Refrigerator 10 cft", "price": 62000, "rating": 4.3},
    ],
}


def _parse_price(text: str) -> float:
    """Extract numeric price from text like 'Rs. 12,500' or '₨12500'."""
    if not text:
        return 0.0
    cleaned = re.sub(r'[^\d.]', '', text.replace(',', ''))
    try:
        return float(cleaned)
    except ValueError:
        return 0.0


def _matches_query(product_name: str, query: str | None) -> bool:
    """
    Check whether a product should be included for a search query.
    Keeps electronics default wide, but narrows specific queries.
    """
    if not query:
        return True

    q = query.strip().lower()
    if not q or q == "electronics":
        return True

    name = (product_name or "").strip().lower()
    if not name:
        return False
    if q in name:
        return True

    category = _query_category(q)
    category_match = _category_match(name, category) if category else False

    # Use word-boundary match for short queries like "tv".
    if len(q) <= 3:
        if re.search(rf"\b{re.escape(q)}\b", name):
            return True
        return category_match

    # Require all meaningful words to appear for better precision.
    tokens = [t for t in re.split(r"\s+", q) if len(t) >= 3]
    if not tokens:
        return category_match or q in name

    if all(t in name for t in tokens):
        return True

    # For category searches (e.g., "laptop", "mobile"), allow category match
    # to avoid empty results when product names are brand-specific.
    if category_match:
        return True

    return False


def _scrape_store(store_id: str, query: str = "electronics", verbose: bool = True) -> list[dict]:
    """
    Attempt to scrape a store. Falls back to curated data on failure.
    """
    config = SCRAPE_CONFIGS.get(store_id)
    if config and config.get("platform"):
        selectors = PLATFORM_SELECTORS.get(config["platform"], PLATFORM_SELECTORS["generic"])
        config = {**selectors, **config}
    store_info = STORE_INDEX.get(store_id)
    if not store_info:
        return []

    store_name = store_info["name"]
    store_url = store_info.get("url", "")
    store_type = store_info["type"]
    products = []

    # Attempt real scrape if config exists and store has a URL
    if config and store_url:
        try:
            urls = config.get("search_urls") or [config.get("search_url")]
            timeout = (max(0.5, float(SCRAPER_CONNECT_TIMEOUT)), max(0.5, float(SCRAPER_READ_TIMEOUT)))
            for search_url in urls:
                if not search_url:
                    continue
                url = search_url.format(query=query)
                resp = requests.get(url, headers=HEADERS, timeout=timeout, allow_redirects=True)
                resp.raise_for_status()

                soup = BeautifulSoup(resp.text, "html.parser")
                cards = soup.select(config["product_sel"])
                attempt_products = []

                for card in cards[:20]:  # Cap at 20 per store
                    name_el = card.select_one(config["name_sel"])
                    price_el = card.select_one(config["price_sel"])
                    link_el = card.select_one(config["link_sel"])

                    if not name_el:
                        continue

                    name = name_el.get_text(strip=True)
                    price = _parse_price(price_el.get_text(strip=True)) if price_el else 0
                    link = ""
                    if link_el and link_el.get("href"):
                        href = link_el["href"]
                        if href.startswith("http"):
                            link = href
                        elif href.startswith("/"):
                            link = store_url.rstrip("/") + href
                        else:
                            link = store_url.rstrip("/") + "/" + href

                    if name and price > 0 and _matches_query(name, query):
                        attempt_products.append({
                            "product": name,
                            "price": price,
                            "rating": 4,
                            "reviews": 0,
                            "in_stock": True,
                            "category": "electronics",
                            "source_store": store_name,
                            "store_type": store_type,
                            "source_url": link or url,
                            "description": f"From {store_name}",
                        })

                if attempt_products:
                    products = attempt_products
                    if verbose:
                        print(f"  [OK] {store_name}: scraped {len(products)} products")
                    if REQUEST_DELAY > 0:
                        time.sleep(REQUEST_DELAY)
                    return products

        except Exception as e:
            if verbose:
                print(f"  [WARN] {store_name}: scrape failed ({e}), using curated data")

    # Fallback: use curated demo data
    curated = STORE_PRODUCTS.get(store_id, [])
    for p in curated:
        # If a query is provided, do a simple keyword match
        if not _matches_query(p["product"], query):
            continue

        products.append({
            "product": p["product"],
            "price": float(p["price"]),
            "rating": p.get("rating", 4),
            "reviews": p.get("reviews", 10),
            "in_stock": True,
            "category": "electronics",
            "source_store": store_name,
            "store_type": store_type,
            "source_url": store_url or "#",
            "description": f"From {store_name}" + (f" - {p.get('description', '')}" if p.get('description') else ""),
        })

    # If generic electronics fetch and no matches yet, return curated defaults.
    if not products and curated and (not query or query.lower().strip() == "electronics"):
        for p in curated:
            products.append({
                "product": p["product"],
                "price": float(p["price"]),
                "rating": p.get("rating", 4),
                "reviews": p.get("reviews", 10),
                "in_stock": True,
                "category": "electronics",
                "source_store": store_name,
                "store_type": store_type,
                "source_url": store_url or "#",
                "description": f"From {store_name}",
            })

    return products


def fetch_all_stores(query: str = None, max_per_store: int = 20, verbose: bool = True) -> list[dict]:
    """
    Fetch products from ALL 30+ stores. 
    Returns aggregated, deduplicated product list.
    """
    all_products = []
    seen = set()
    search_term = query if query else "electronics"

    if verbose:
        print(f"\n{'='*60}")
        print(f"  Scraping {len(TARGET_STORES)} stores for: '{search_term}'")
        print(f"{'='*60}")

    max_workers = max(1, min(int(SCRAPER_MAX_WORKERS), len(TARGET_STORES)))

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        future_to_store = {
            pool.submit(_scrape_store, store["id"], search_term, verbose): store
            for store in TARGET_STORES
        }

        for future in as_completed(future_to_store):
            store = future_to_store[future]
            try:
                prods = future.result()
            except Exception as e:
                if verbose:
                    print(f"  [WARN] {store['name']}: error ({e})")
                continue

            for p in prods[:max_per_store]:
                # Keep product detail per website/store; avoid cross-store de-dup loss.
                key = f"{(p.get('source_store') or '').lower().strip()}::{p['product'].lower().strip()}"
                if key not in seen:
                    all_products.append(p)
                    seen.add(key)

    if not all_products and query:
        if verbose:
            print("  [WARN] No matches found. Using broad catalog fallback.")
        for store in TARGET_STORES:
            store_id = store["id"]
            curated = STORE_PRODUCTS.get(store_id, [])
            if not curated:
                continue
            for p in curated[:max_per_store]:
                key = f"{store['name'].lower().strip()}::{p['product'].lower().strip()}"
                if key in seen:
                    continue
                all_products.append({
                    "product": p["product"],
                    "price": float(p["price"]),
                    "rating": p.get("rating", 4),
                    "reviews": p.get("reviews", 10),
                    "in_stock": True,
                    "category": "electronics",
                    "source_store": store["name"],
                    "store_type": store["type"],
                    "source_url": store.get("url", "") or "#",
                    "description": f"From {store['name']}",
                })
                seen.add(key)

    if verbose:
        print(f"\n  Total unique products: {len(all_products)}")
        print(f"{'='*60}\n")

    return all_products


if __name__ == "__main__":
    items = fetch_all_stores()
    print(f"\nTotal: {len(items)} products from {len(set(p['source_store'] for p in items))} stores")
    for p in items[:10]:
        print(f"  [{p['source_store']}] {p['product']} - Rs. {p['price']:,.0f}")
