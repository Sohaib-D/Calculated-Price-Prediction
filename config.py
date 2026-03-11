"""
config.py — Pakistan Electronics Intelligence Configuration
─────────────────────────────────────────────────────────────
All 30+ Pakistani electronics stores, coordinates, fuel constants,
and branch data for distance/route optimization.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

_BASE_DIR = Path(__file__).resolve().parent
load_dotenv(_BASE_DIR / ".env")


def _csv_env(name: str, default: str) -> tuple[str, ...]:
    raw = os.environ.get(name, default)
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _float_env(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default

# ── API Keys / AI ─────────────────────────────────────────────────────────────
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()
MAPTILER_API_KEY = os.environ.get("MAPTILER_API_KEY", "").strip()

# Runtime / Security
APP_DEBUG = os.environ.get("APP_DEBUG", "false").strip().lower() in {"1", "true", "yes", "on"}
CORS_ALLOWED_ORIGINS = _csv_env(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:5000,http://127.0.0.1:5000,http://localhost:8000,http://127.0.0.1:8000",
)
SCRAPE_API_KEY = os.environ.get("SCRAPE_API_KEY", "").strip()

# API guardrails
CACHE_TTL_SECONDS = _int_env("CACHE_TTL_SECONDS", 900)
CACHE_MAX_ENTRIES = _int_env("CACHE_MAX_ENTRIES", 64)
MAX_QUERY_LENGTH = _int_env("MAX_QUERY_LENGTH", 80)
MAX_PAGE_FETCH = _int_env("MAX_PAGE_FETCH", 3)
MAX_PRODUCTS_LIMIT = _int_env("MAX_PRODUCTS_LIMIT", 200)
RATE_LIMIT_WINDOW_SECONDS = _int_env("RATE_LIMIT_WINDOW_SECONDS", 60)
RATE_LIMIT_SEARCH_PER_WINDOW = _int_env("RATE_LIMIT_SEARCH_PER_WINDOW", 30)
RATE_LIMIT_SCRAPE_PER_WINDOW = _int_env("RATE_LIMIT_SCRAPE_PER_WINDOW", 3)

# ── OSRM Routing ──────────────────────────────────────────────────────────────
# Public server (no API key).  Switch to "http://localhost:5000" for self-hosted.
OSRM_BASE_URL = os.environ.get("OSRM_BASE_URL", "https://router.project-osrm.org")
ROUTING_PROVIDER = os.environ.get("ROUTING_PROVIDER", "osrm").strip().lower()
OSRM_CONNECT_TIMEOUT_SECONDS = _float_env("OSRM_CONNECT_TIMEOUT_SECONDS", 1.2)
OSRM_READ_TIMEOUT_SECONDS = _float_env("OSRM_READ_TIMEOUT_SECONDS", 2.8)
GOOGLE_MAPS_TIMEOUT_SECONDS = _float_env("GOOGLE_MAPS_TIMEOUT_SECONDS", 8.0)

# ── MapTiler Routing (optional, key-based) ────────────────────────────────────
MAPTILER_BASE_URL = os.environ.get("MAPTILER_BASE_URL", "https://api.maptiler.com").strip()
MAPTILER_PROFILE = os.environ.get("MAPTILER_PROFILE", "driving").strip().lower()
MAPTILER_CONNECT_TIMEOUT_SECONDS = _float_env("MAPTILER_CONNECT_TIMEOUT_SECONDS", 1.2)
MAPTILER_READ_TIMEOUT_SECONDS = _float_env("MAPTILER_READ_TIMEOUT_SECONDS", 2.8)

# ── Location Search (OpenStreetMap Nominatim) ────────────────────────────────
NOMINATIM_BASE_URL = os.environ.get("NOMINATIM_BASE_URL", "https://nominatim.openstreetmap.org").strip()
LOCATION_COUNTRY_CODE = os.environ.get("LOCATION_COUNTRY_CODE", "pk").strip().lower()
LOCATION_SUGGEST_LIMIT = _int_env("LOCATION_SUGGEST_LIMIT", 7)

# ── Delivery Fee Constants (Pakistan market) ──────────────────────────────────
DELIVERY_BASE_FEE = _float_env("DELIVERY_BASE_FEE", 80.0)   # PKR
DELIVERY_PER_KM   = _float_env("DELIVERY_PER_KM",   20.0)   # PKR/km

# ── Fuel / Travel Constants (Pakistan 2024-25) ────────────────────────────────
FUEL_PRICE_PER_LITER = 300.0      # PKR per liter (petrol)
FUEL_EFFICIENCY_KM_PER_L = 12.0   # Average car ~12 km/liter
FUEL_COST_PER_KM = FUEL_PRICE_PER_LITER / FUEL_EFFICIENCY_KM_PER_L   # ~25 PKR/km
TIME_VALUE_PER_HOUR = 500.0       # Opportunity cost PKR/hour
AVG_SPEED_KMH = 30.0             # Average city driving speed in Pakistan

# ── Scraper Settings ──────────────────────────────────────────────────────────
REQUEST_TIMEOUT = _float_env("REQUEST_TIMEOUT", 6.0)
REQUEST_DELAY = _float_env("REQUEST_DELAY", 0.0)
SCRAPER_MAX_WORKERS = _int_env("SCRAPER_MAX_WORKERS", 12)
SCRAPER_CONNECT_TIMEOUT = _float_env("SCRAPER_CONNECT_TIMEOUT", 2.0)
SCRAPER_READ_TIMEOUT = _float_env("SCRAPER_READ_TIMEOUT", 4.0)
PREWARM_PRODUCTS_CACHE = os.environ.get("PREWARM_PRODUCTS_CACHE", "true").strip().lower() in {"1", "true", "yes", "on"}
SCRAPE_SEED_STORES = os.environ.get("SCRAPE_SEED_STORES", "false").strip().lower() in {"1", "true", "yes", "on"}

# ── Category Meta (electronics only) ──────────────────────────────────────────
CATEGORY_META = {
    "electronics": {
        "label": "Electronics",
        "icon": "⚡",
        "description": "All electronics from 30+ Pakistani stores",
    },
}

# ── Store Registry ────────────────────────────────────────────────────────────
# type: "physical" = has a walk-in location, "online" = online-only
# Physical stores have lat/lon for distance calculations

STORES = [
    # ─── Physical Shops (Major Physical & Online Stores) ──────────────────
    {
        "id": "afzal_electronics",
        "name": "Afzal Electronics",
        "url": "https://afzalelectronics.com",
        "type": "physical",
        "city": "Karachi",
        "address": "Electronics Market, Saddar, Karachi",
        "lat": 24.8562,
        "lon": 67.0237,
        "phone": "+92-21-32725555",
    },
    {
        "id": "arduino_pakistan",
        "name": "Arduino Pakistan",
        "url": "https://www.arduinopakistan.com/",
        "type": "physical",
        "city": "Lahore",
        "address": "Hall Road Electronics Market, Lahore",
        "lat": 31.5575,
        "lon": 74.3350,
        "phone": "+92-42-37654321",
    },
    {
        "id": "axis_electronics",
        "name": "Axis Electronics",
        "url": None,
        "type": "physical",
        "city": "Lahore",
        "address": "Hall Road, Lahore",
        "lat": 31.5580,
        "lon": 74.3345,
        "phone": None,
    },
    {
        "id": "chaudhry_electronics",
        "name": "Chaudhry Electronics",
        "url": None,
        "type": "physical",
        "city": "Rawalpindi",
        "address": "Raja Bazaar, Rawalpindi",
        "lat": 33.5972,
        "lon": 73.0479,
        "phone": None,
    },
    {
        "id": "city_electronics",
        "name": "City ElectronicsPk",
        "url": "https://cityelectronics.pk/",
        "type": "physical",
        "city": "Karachi",
        "address": "Tariq Road, Karachi",
        "lat": 24.8704,
        "lon": 67.0631,
        "phone": "+92-21-34556677",
    },
    {
        "id": "college_road",
        "name": "College Road Electronics",
        "url": "https://colgroad.com",
        "type": "physical",
        "city": "Rawalpindi",
        "address": "College Road, Rawalpindi",
        "lat": 33.5961,
        "lon": 73.0518,
        "phone": None,
    },
    {
        "id": "eph",
        "name": "Electronic Power House",
        "url": "https://eph.com.pk",
        "type": "physical",
        "city": "Lahore",
        "address": "Main Boulevard, Lahore",
        "lat": 31.5204,
        "lon": 74.3587,
        "phone": "+92-42-35761234",
    },
    {
        "id": "epro",
        "name": "Electronics Pro",
        "url": "https://www.epro.pk/",
        "type": "physical",
        "city": "Islamabad",
        "address": "Blue Area, Islamabad",
        "lat": 33.7100,
        "lon": 73.0551,
        "phone": None,
    },
    {
        "id": "electronation",
        "name": "Electronation Pakistan",
        "url": "http://www.electronation.pk/",
        "type": "physical",
        "city": "Lahore",
        "address": "Gulberg III, Lahore",
        "lat": 31.5170,
        "lon": 74.3470,
        "phone": None,
    },
    {
        "id": "electrobes",
        "name": "Electrobes",
        "url": "https://electrobes.com",
        "type": "physical",
        "city": "Lahore",
        "address": "Model Town, Lahore",
        "lat": 31.4840,
        "lon": 74.3260,
        "phone": None,
    },
    {
        "id": "evs_electro",
        "name": "EVE-eVision Electronics",
        "url": "https://www.evselectro.com/",
        "type": "physical",
        "city": "Karachi",
        "address": "North Nazimabad, Karachi",
        "lat": 24.9245,
        "lon": 67.0338,
        "phone": None,
    },
    {
        "id": "friends_corp",
        "name": "Friends Corporation",
        "url": "https://friendscorporation.co/",
        "type": "physical",
        "city": "Lahore",
        "address": "Hall Road, Lahore",
        "lat": 31.5578,
        "lon": 74.3342,
        "phone": "+92-42-37231234",
    },
    {
        "id": "galaxy_pk",
        "name": "Galaxy.pk",
        "url": "https://www.galaxy.pk",
        "type": "physical",
        "city": "Karachi",
        "address": "Gulshan-e-Iqbal, Karachi",
        "lat": 24.9215,
        "lon": 67.0935,
        "phone": "+92-21-34821234",
    },
    {
        "id": "hanif_centre",
        "name": "Hanif Centre Electronics",
        "url": "https://hcsupermart.com/",
        "type": "physical",
        "city": "Lahore",
        "address": "Hafeez Centre, Gulberg, Lahore",
        "lat": 31.5175,
        "lon": 74.3505,
        "phone": "+92-42-35761000",
    },
    {
        "id": "homeshopping",
        "name": "Homeshopping.pk",
        "url": "https://www.homeshopping.pk",
        "type": "physical",
        "city": "Karachi",
        "address": "PECHS, Karachi",
        "lat": 24.8659,
        "lon": 67.0651,
        "phone": "0800-SHOPPING",
    },
    {
        "id": "imran_electronics",
        "name": "Imran Electronics",
        "url": "https://imraneshop.com",
        "type": "physical",
        "city": "Lahore",
        "address": "Hall Road Electronics Market, Lahore",
        "lat": 31.5572,
        "lon": 74.3348,
        "phone": None,
    },
    {
        "id": "matrix_electronics",
        "name": "MATRIX Electronics & Communication",
        "url": "http://matrixonline.pk/",
        "type": "physical",
        "city": "Islamabad",
        "address": "Jinnah Super Market, Islamabad",
        "lat": 33.7125,
        "lon": 73.0723,
        "phone": None,
    },
    {
        "id": "mega_pk",
        "name": "Mega.pk",
        "url": "https://www.mega.pk",
        "type": "physical",
        "city": "Karachi",
        "address": "Saddar, Karachi",
        "lat": 24.8565,
        "lon": 67.0230,
        "phone": "+92-21-111-634-263",
    },
    {
        "id": "multan_electronics",
        "name": "Multan Electronics",
        "url": None,
        "type": "physical",
        "city": "Multan",
        "address": "Hussain Agahi, Multan",
        "lat": 30.1984,
        "lon": 71.4734,
        "phone": None,
    },
    {
        "id": "pak_elec_and_electronics",
        "name": "Pakistan Electrical & Electronics",
        "url": None,
        "type": "physical",
        "city": "Karachi",
        "address": "Saddar Electronics Market, Karachi",
        "lat": 24.8555,
        "lon": 67.0235,
        "phone": None,
    },
    {
        "id": "pakistan_electronics",
        "name": "Pakistan Electronics",
        "url": "http://www.pakistanelectronics.com/",
        "type": "physical",
        "city": "Karachi",
        "address": "Gurumandir, Karachi",
        "lat": 24.8700,
        "lon": 67.0315,
        "phone": None,
    },
    {
        "id": "shophive",
        "name": "Shophive.com",
        "url": "https://www.shophive.com",
        "type": "physical",
        "city": "Lahore",
        "address": "Cavalry Ground, Lahore",
        "lat": 31.5125,
        "lon": 74.3595,
        "phone": "0800-746-7484",
    },
    {
        "id": "telemart",
        "name": "Telemart.pk",
        "url": "https://www.telemart.pk",
        "type": "physical",
        "city": "Lahore",
        "address": "Garden Town, Lahore",
        "lat": 31.5152,
        "lon": 74.3345,
        "phone": "042-111-835-362",
    },
    {
        "id": "component_centre",
        "name": "The Component Centre",
        "url": "https://www.thecomponentcentre.com/",
        "type": "physical",
        "city": "Islamabad",
        "address": "I-8 Markaz, Islamabad",
        "lat": 33.6800,
        "lon": 73.0650,
        "phone": None,
    },
    {
        "id": "umar_electronics",
        "name": "Umarelectronics.pk",
        "url": "https://umarelectronics.pk/",
        "type": "physical",
        "city": "Karachi",
        "address": "Bahadurabad, Karachi",
        "lat": 24.8740,
        "lon": 67.0575,
        "phone": None,
    },
    {
        "id": "vmart",
        "name": "VMart.pk",
        "url": "https://www.vmart.pk",
        "type": "physical",
        "city": "Islamabad",
        "address": "F-10 Markaz, Islamabad",
        "lat": 33.6950,
        "lon": 73.0170,
        "phone": None,
    },

    # ─── Online-Only Electronics Stores ───────────────────────────────────
    {
        "id": "art_of_circuits",
        "name": "Art of Circuits",
        "url": "https://artofcircuits.com/shop",
        "type": "online",
        "city": "Online",
        "address": "Online Store — Pakistan-wide delivery",
        "lat": 30.3753,
        "lon": 69.3451,
        "phone": None,
    },
    {
        "id": "chip_pk",
        "name": "Chip.pk",
        "url": "https://chip.pk/",
        "type": "online",
        "city": "Online",
        "address": "Online Store — Pakistan-wide delivery",
        "lat": 30.3753,
        "lon": 69.3451,
        "phone": None,
    },
    {
        "id": "circuit_pk",
        "name": "Circuit.pk",
        "url": "https://circuitpk.enic.pk/",
        "type": "online",
        "city": "Online",
        "address": "Online Store — Pakistan-wide delivery",
        "lat": 30.3753,
        "lon": 69.3451,
        "phone": None,
    },
    {
        "id": "daraz",
        "name": "Daraz.pk",
        "url": "https://www.daraz.pk",
        "type": "online",
        "city": "Online",
        "address": "Pakistan's #1 Online Marketplace",
        "lat": 30.3753,
        "lon": 69.3451,
        "phone": "042-111-132-729",
    },
    {
        "id": "priceoye",
        "name": "PriceOye",
        "url": "https://priceoye.pk",
        "type": "online",
        "city": "Online",
        "address": "Online Store — Pakistan-wide delivery",
        "lat": 30.3753,
        "lon": 69.3451,
        "phone": None,
    },
    {
        "id": "pakmobizone",
        "name": "PakMobiZone",
        "url": "https://www.pakmobizone.pk",
        "type": "online",
        "city": "Online",
        "address": "Online Store — Pakistan-wide delivery",
        "lat": 30.3753,
        "lon": 69.3451,
        "phone": None,
    },
    {
        "id": "mistore",
        "name": "MiStore Pakistan",
        "url": "https://mistore.pk",
        "type": "online",
        "city": "Online",
        "address": "Online Store — Pakistan-wide delivery",
        "lat": 30.3753,
        "lon": 69.3451,
        "phone": None,
    },
    {
        "id": "dcart",
        "name": "Dcart.pk",
        "url": "https://dcart.pk/shop/",
        "type": "online",
        "city": "Online",
        "address": "Online Store — Pakistan-wide delivery",
        "lat": 30.3753,
        "lon": 69.3451,
        "phone": None,
    },
    {
        "id": "digilog",
        "name": "Digilog.pk",
        "url": "https://digilog.pk/",
        "type": "online",
        "city": "Online",
        "address": "Online Store — Pakistan-wide delivery",
        "lat": 30.3753,
        "lon": 69.3451,
        "phone": None,
    },
    {
        "id": "epal",
        "name": "ePal.pk",
        "url": "https://www.epal.pk/",
        "type": "online",
        "city": "Online",
        "address": "Online Store — Pakistan-wide delivery",
        "lat": 30.3753,
        "lon": 69.3451,
        "phone": None,
    },
    {
        "id": "ishopping",
        "name": "iShopping.pk",
        "url": "https://www.ishopping.pk",
        "type": "online",
        "city": "Online",
        "address": "Online Store — Pakistan-wide delivery",
        "lat": 30.3753,
        "lon": 69.3451,
        "phone": None,
    },
    {
        "id": "mreeco",
        "name": "Mreeco.com",
        "url": "https://www.mreeco.com/",
        "type": "online",
        "city": "Online",
        "address": "Online Store — Pakistan-wide delivery",
        "lat": 30.3753,
        "lon": 69.3451,
        "phone": None,
    },
    {
        "id": "rawlix",
        "name": "Rawlix.com",
        "url": "https://www.rawlix.com/",
        "type": "online",
        "city": "Online",
        "address": "Online Store — Pakistan-wide delivery",
        "lat": 30.3753,
        "lon": 69.3451,
        "phone": None,
    },
    {
        "id": "czone",
        "name": "CZone.com.pk",
        "url": "https://www.czone.com.pk",
        "type": "online",
        "city": "Online",
        "address": "Online Store — Pakistan-wide delivery",
        "lat": 30.3753,
        "lon": 69.3451,
        "phone": None,
    },
    {
        "id": "paklap",
        "name": "Paklap.pk",
        "url": "https://www.paklap.pk",
        "type": "online",
        "city": "Online",
        "address": "Online Store — Pakistan-wide delivery",
        "lat": 30.3753,
        "lon": 69.3451,
        "phone": None,
    },
    {
        "id": "computerzone",
        "name": "ComputerZone.com.pk",
        "url": "https://www.computerzone.com.pk",
        "type": "online",
        "city": "Online",
        "address": "Online Store — Pakistan-wide delivery",
        "lat": 30.3753,
        "lon": 69.3451,
        "phone": None,
    },
    {
        "id": "w11stop",
        "name": "W11Stop.com",
        "url": "https://www.w11stop.com",
        "type": "online",
        "city": "Online",
        "address": "Online Store — Pakistan-wide delivery",
        "lat": 30.3753,
        "lon": 69.3451,
        "phone": None,
    },
    {
        "id": "tejar",
        "name": "Tejar.pk",
        "url": "https://www.tejar.pk",
        "type": "online",
        "city": "Online",
        "address": "Online Store — Pakistan-wide delivery",
        "lat": 30.3753,
        "lon": 69.3451,
        "phone": None,
    },
    {
        "id": "myshop",
        "name": "MyShop.pk",
        "url": "https://www.myshop.pk",
        "type": "online",
        "city": "Online",
        "address": "Online Store — Pakistan-wide delivery",
        "lat": 30.3753,
        "lon": 69.3451,
        "phone": None,
    },
]

# ── Build BRANCHES list for distance service (physical stores only) ───────────
# The existing prediction_service.py and decision_service.py expect this format
BRANCHES = []
for store in STORES:
    BRANCHES.append({
        "id": store["id"],
        "name": store["name"],
        "city": store["city"],
        "address": store["address"],
        "lat": store["lat"],
        "lon": store["lon"],
        "phone": store.get("phone", ""),
        "type": store["type"],
        "url": store.get("url", ""),
        # support additional demo categories so search/ranking isnt blank
        "categories": ["electronics", "mobiles", "paints"],
    })

# Helper lookups
STORE_BY_ID = {s["id"]: s for s in STORES}
PHYSICAL_STORES = [s for s in STORES if s["type"] == "physical"]
ONLINE_STORES = [s for s in STORES if s["type"] == "online"]

# ── Seed Stores (optional, not included in core STORES) ───────────────────────
# Enable with SCRAPE_SEED_STORES=true to include these in universal scraper.
SEED_STORES = [
    # Major electronics + multi-brand stores
    {"id": "aysonline", "name": "Ays Online", "url": "https://www.aysonline.pk", "type": "online", "city": "Online", "address": "Online Store - Pakistan-wide delivery", "lat": 30.3753, "lon": 69.3451, "phone": None},
    {"id": "flipzon", "name": "Flipzon", "url": "https://www.flipzon.pk", "type": "online", "city": "Online", "address": "Online Store - Pakistan-wide delivery", "lat": 30.3753, "lon": 69.3451, "phone": None},
    {"id": "zahcomputers", "name": "Zah Computers", "url": "https://www.zahcomputers.pk", "type": "online", "city": "Online", "address": "Online Store - Pakistan-wide delivery", "lat": 30.3753, "lon": 69.3451, "phone": None},
    {"id": "eezeepc", "name": "Eezeepc", "url": "https://www.eezeepc.com", "type": "online", "city": "Online", "address": "Online Store - Pakistan-wide delivery", "lat": 30.3753, "lon": 69.3451, "phone": None},
    {"id": "techsouls", "name": "TechSouls", "url": "https://www.techsouls.pk", "type": "online", "city": "Online", "address": "Online Store - Pakistan-wide delivery", "lat": 30.3753, "lon": 69.3451, "phone": None},
    {"id": "computers_pk", "name": "Computers.pk", "url": "https://www.computers.pk", "type": "online", "city": "Online", "address": "Online Store - Pakistan-wide delivery", "lat": 30.3753, "lon": 69.3451, "phone": None},
    {"id": "pakipc", "name": "PakIPC", "url": "https://www.pakipc.com", "type": "online", "city": "Online", "address": "Online Store - Pakistan-wide delivery", "lat": 30.3753, "lon": 69.3451, "phone": None},
    {"id": "techglobe", "name": "TechGlobe", "url": "https://www.techglobe.pk", "type": "online", "city": "Online", "address": "Online Store - Pakistan-wide delivery", "lat": 30.3753, "lon": 69.3451, "phone": None},
    {"id": "techcity", "name": "TechCity", "url": "https://www.techcity.pk", "type": "online", "city": "Online", "address": "Online Store - Pakistan-wide delivery", "lat": 30.3753, "lon": 69.3451, "phone": None},

    # Mid-size electronics stores
    {"id": "gtstore", "name": "GTStore", "url": "https://www.gtstore.pk", "type": "online", "city": "Online", "address": "Online Store - Pakistan-wide delivery", "lat": 30.3753, "lon": 69.3451, "phone": None},
    {"id": "techmart", "name": "TechMart", "url": "https://www.techmart.pk", "type": "online", "city": "Online", "address": "Online Store - Pakistan-wide delivery", "lat": 30.3753, "lon": 69.3451, "phone": None},
    {"id": "laptopmall", "name": "Laptop Mall", "url": "https://www.laptopmall.pk", "type": "online", "city": "Online", "address": "Online Store - Pakistan-wide delivery", "lat": 30.3753, "lon": 69.3451, "phone": None},
    {"id": "laptopoutlet", "name": "Laptop Outlet", "url": "https://www.laptopoutlet.pk", "type": "online", "city": "Online", "address": "Online Store - Pakistan-wide delivery", "lat": 30.3753, "lon": 69.3451, "phone": None},
    {"id": "smartlink", "name": "SmartLink", "url": "https://www.smartlink.pk", "type": "online", "city": "Online", "address": "Online Store - Pakistan-wide delivery", "lat": 30.3753, "lon": 69.3451, "phone": None},
    {"id": "buyon", "name": "BuyOn", "url": "https://www.buyon.pk", "type": "online", "city": "Online", "address": "Online Store - Pakistan-wide delivery", "lat": 30.3753, "lon": 69.3451, "phone": None},
    {"id": "shopon", "name": "ShopOn", "url": "https://www.shopon.pk", "type": "online", "city": "Online", "address": "Online Store - Pakistan-wide delivery", "lat": 30.3753, "lon": 69.3451, "phone": None},
    {"id": "clicky", "name": "Clicky", "url": "https://www.clicky.pk", "type": "online", "city": "Online", "address": "Online Store - Pakistan-wide delivery", "lat": 30.3753, "lon": 69.3451, "phone": None},
    {"id": "symbios", "name": "Symbios", "url": "https://www.symbios.pk", "type": "online", "city": "Online", "address": "Online Store - Pakistan-wide delivery", "lat": 30.3753, "lon": 69.3451, "phone": None},
    {"id": "yayvo", "name": "Yayvo", "url": "https://www.yayvo.com", "type": "online", "city": "Online", "address": "Online Store - Pakistan-wide delivery", "lat": 30.3753, "lon": 69.3451, "phone": None},

    # Appliance retailers / brand catalogs
    {"id": "haier", "name": "Haier Pakistan", "url": "https://www.haier.com.pk", "type": "online", "city": "Online", "address": "Online Store - Pakistan-wide delivery", "lat": 30.3753, "lon": 69.3451, "phone": None},
    {"id": "pel", "name": "PEL", "url": "https://www.pel.com.pk", "type": "online", "city": "Online", "address": "Online Store - Pakistan-wide delivery", "lat": 30.3753, "lon": 69.3451, "phone": None},
    {"id": "orient", "name": "Orient", "url": "https://www.orient.com.pk", "type": "online", "city": "Online", "address": "Online Store - Pakistan-wide delivery", "lat": 30.3753, "lon": 69.3451, "phone": None},
    {"id": "dawlance", "name": "Dawlance", "url": "https://www.dawlance.com.pk", "type": "online", "city": "Online", "address": "Online Store - Pakistan-wide delivery", "lat": 30.3753, "lon": 69.3451, "phone": None},
    {"id": "gree", "name": "Gree Pakistan", "url": "https://www.gree.com.pk", "type": "online", "city": "Online", "address": "Online Store - Pakistan-wide delivery", "lat": 30.3753, "lon": 69.3451, "phone": None},
    {"id": "boss", "name": "Boss", "url": "https://www.boss.com.pk", "type": "online", "city": "Online", "address": "Online Store - Pakistan-wide delivery", "lat": 30.3753, "lon": 69.3451, "phone": None},
    {"id": "waves", "name": "Waves", "url": "https://www.waves.com.pk", "type": "online", "city": "Online", "address": "Online Store - Pakistan-wide delivery", "lat": 30.3753, "lon": 69.3451, "phone": None},
    {"id": "nasgas", "name": "Nasgas", "url": "https://www.nasgas.com.pk", "type": "online", "city": "Online", "address": "Online Store - Pakistan-wide delivery", "lat": 30.3753, "lon": 69.3451, "phone": None},

    # Hardware, robotics, electronics components
    {"id": "hallroad", "name": "Hall Road", "url": "https://www.hallroad.org", "type": "online", "city": "Online", "address": "Online Store - Pakistan-wide delivery", "lat": 30.3753, "lon": 69.3451, "phone": None},
    {"id": "robotics_pk", "name": "Robotics.pk", "url": "https://www.robotics.pk", "type": "online", "city": "Online", "address": "Online Store - Pakistan-wide delivery", "lat": 30.3753, "lon": 69.3451, "phone": None},
    {"id": "microcontrollershop", "name": "Microcontroller Shop", "url": "https://www.microcontrollershop.pk", "type": "online", "city": "Online", "address": "Online Store - Pakistan-wide delivery", "lat": 30.3753, "lon": 69.3451, "phone": None},
    {"id": "electronicshub", "name": "Electronics Hub", "url": "https://www.electronicshub.pk", "type": "online", "city": "Online", "address": "Online Store - Pakistan-wide delivery", "lat": 30.3753, "lon": 69.3451, "phone": None},
    {"id": "paktronics", "name": "Paktronics", "url": "https://www.paktronics.com", "type": "online", "city": "Online", "address": "Online Store - Pakistan-wide delivery", "lat": 30.3753, "lon": 69.3451, "phone": None},
    {"id": "electroniks", "name": "Electroniks", "url": "https://www.electroniks.pk", "type": "online", "city": "Online", "address": "Online Store - Pakistan-wide delivery", "lat": 30.3753, "lon": 69.3451, "phone": None},
    {"id": "microcontroller", "name": "Microcontroller.pk", "url": "https://www.microcontroller.pk", "type": "online", "city": "Online", "address": "Online Store - Pakistan-wide delivery", "lat": 30.3753, "lon": 69.3451, "phone": None},

    # Laptop + computer focused stores
    {"id": "warcomputer", "name": "War Computer", "url": "https://www.warcomputer.com", "type": "online", "city": "Online", "address": "Online Store - Pakistan-wide delivery", "lat": 30.3753, "lon": 69.3451, "phone": None},
    {"id": "rbtechngames", "name": "RB Tech N Games", "url": "https://www.rbtechngames.com", "type": "online", "city": "Online", "address": "Online Store - Pakistan-wide delivery", "lat": 30.3753, "lon": 69.3451, "phone": None},
    {"id": "gamesngeeks", "name": "Games N Geeks", "url": "https://www.gamesngeeks.com", "type": "online", "city": "Online", "address": "Online Store - Pakistan-wide delivery", "lat": 30.3753, "lon": 69.3451, "phone": None},
    {"id": "ziptech", "name": "ZipTech", "url": "https://www.ziptech.pk", "type": "online", "city": "Online", "address": "Online Store - Pakistan-wide delivery", "lat": 30.3753, "lon": 69.3451, "phone": None},
    {"id": "pcfanatics", "name": "PC Fanatics", "url": "https://www.pcfanatics.pk", "type": "online", "city": "Online", "address": "Online Store - Pakistan-wide delivery", "lat": 30.3753, "lon": 69.3451, "phone": None},
    {"id": "globalcomputers", "name": "Global Computers", "url": "https://www.globalcomputers.pk", "type": "online", "city": "Online", "address": "Online Store - Pakistan-wide delivery", "lat": 30.3753, "lon": 69.3451, "phone": None},
    {"id": "techark", "name": "TechArk", "url": "https://www.techark.pk", "type": "online", "city": "Online", "address": "Online Store - Pakistan-wide delivery", "lat": 30.3753, "lon": 69.3451, "phone": None},
    {"id": "hfstore", "name": "HF Store", "url": "https://www.hfstore.pk", "type": "online", "city": "Online", "address": "Online Store - Pakistan-wide delivery", "lat": 30.3753, "lon": 69.3451, "phone": None},
    {"id": "ascomputer", "name": "AS Computer", "url": "https://www.ascomputer.pk", "type": "online", "city": "Online", "address": "Online Store - Pakistan-wide delivery", "lat": 30.3753, "lon": 69.3451, "phone": None},
    {"id": "techarc", "name": "TechArc", "url": "https://www.techarc.pk", "type": "online", "city": "Online", "address": "Online Store - Pakistan-wide delivery", "lat": 30.3753, "lon": 69.3451, "phone": None},

    # Mobile marketplaces / phone stores
    {"id": "whatmobile", "name": "WhatMobile", "url": "https://www.whatmobile.com.pk", "type": "online", "city": "Online", "address": "Online Store - Pakistan-wide delivery", "lat": 30.3753, "lon": 69.3451, "phone": None},
    {"id": "mobilemall", "name": "MobileMall", "url": "https://www.mobilemall.pk", "type": "online", "city": "Online", "address": "Online Store - Pakistan-wide delivery", "lat": 30.3753, "lon": 69.3451, "phone": None},
    {"id": "babloo", "name": "Babloo", "url": "https://www.babloo.pk", "type": "online", "city": "Online", "address": "Online Store - Pakistan-wide delivery", "lat": 30.3753, "lon": 69.3451, "phone": None},
    {"id": "phonestore", "name": "PhoneStore", "url": "https://www.phonestore.pk", "type": "online", "city": "Online", "address": "Online Store - Pakistan-wide delivery", "lat": 30.3753, "lon": 69.3451, "phone": None},
]
