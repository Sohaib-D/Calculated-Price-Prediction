<![CDATA[# ⚡ Pakistan Electronics Price Intelligence

A full-stack price comparison and route optimization platform for Pakistani electronics stores. Scrapes real-time product data from **30+ stores**, calculates travel costs (fuel + time), and recommends the best deal factoring in both **product price and physical distance**.

---

## ✨ Key Features

| Feature | Description |
|---|---|
| 🔍 **Multi-Store Scraping** | Aggregates products from 12 specialized scrapers covering CZone, Telemart, PriceOye, Daraz, iShopping, Homeshopping, and more |
| 📍 **Distance & Route Optimization** | Calculates real road distances via Google Maps API (with Haversine fallback) |
| ⛽ **Fuel & Time Cost Estimation** | Factors in PKR fuel prices and opportunity cost to compute true total cost |
| 🏆 **Smart Recommendations** | Ranks stores by best overall deal, cheapest item, or nearest location |
| 🗺️ **Multi-Stop Planning** | Greedy nearest-neighbour routing for shopping across multiple stores |
| 🔎 **Product Search** | Query-based search across all supported stores simultaneously |
| 🌐 **Web Dashboard** | Interactive frontend with Google Maps integration |

---

## 🏗️ Project Structure

```
price_intelligence/
├── app.py                  # Flask API server (all routes)
├── config.py               # 30+ store registry, fuel constants, API keys
├── demo_data.py             # Sample product data for offline/demo mode
├── requirements.txt         # Python dependencies
├── verify_scrapers.py       # Scraper health-check utility
│
├── scrapers/                # Web scrapers for each store
│   ├── __init__.py          # Dispatcher — fetch_category() entry point
│   ├── universal_scraper.py # Aggregator across all stores
│   ├── czone_scraper.py     # CZone.com.pk
│   ├── telemart_scraper.py  # Telemart.pk
│   ├── priceoye_scraper.py  # PriceOye.pk
│   ├── daraz_scraper.py     # Daraz.pk
│   ├── homeshopping_scraper.py
│   ├── ishopping_scraper.py
│   ├── electronics_scraper.py
│   ├── laptops_scraper.py
│   ├── mobiles_scraper.py
│   ├── books_scraper.py
│   └── paints_scraper.py
│
├── services/                # Business logic
│   ├── prediction_service.py  # Branch × product ranking engine
│   └── decision_service.py    # Recommendation & multi-stop route planner
│
├── utils/
│   └── distance.py          # Google Maps + Haversine distance calculations
│
├── templates/
│   └── index.html           # Web dashboard template
│
└── static/
    ├── style.css            # Frontend styles
    └── script.js            # Frontend logic & map integration
```

---

## 🚀 Getting Started

### Prerequisites

- **Python 3.10+**
- **(Optional)** A [Google Maps API Key](https://developers.google.com/maps/documentation/distance-matrix/get-api-key) for real road-distance calculations

### Installation

```bash
# Clone the repository
git clone https://github.com/a-hananop/Price-Predictor.git
cd Price-Predictor

# Install dependencies
pip install -r requirements.txt
```

### Configuration

Edit `config.py` to add your Google Maps API key:

```python
GOOGLE_MAPS_API_KEY = "YOUR_ACTUAL_KEY_HERE"
```

> **Note:** The app works without an API key — it falls back to Haversine (straight-line) distance estimates with a 1.3× road-distance multiplier.

### Running the Server

```bash
python app.py
```

The app starts at **http://localhost:5000**.

---

## 📡 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/` | Web dashboard |
| `GET` | `/api/categories` | List supported categories |
| `GET` | `/api/branches` | List all store branches with coordinates |
| `GET` | `/api/stores` | Full store registry (physical + online counts) |
| `GET` | `/api/products/electronics` | Fetch scraped product listings |
| `GET` | `/api/search?q=<query>` | Search products across all stores |
| `POST` | `/api/scrape/electronics` | Force-refresh the product cache |
| `POST` | `/api/optimize` | Find the best store for your location |
| `POST` | `/api/multi-optimize` | Multi-store route optimization |

### Example — Optimize Request

```json
POST /api/optimize
{
  "user_lat": 31.5204,
  "user_lon": 74.3587,
  "budget": 50000,
  "priority": "total_cost"
}
```

**Priority options:** `total_cost` (default), `price`, `distance`

---

## 🏪 Supported Stores

### Physical Stores (26)

Stores with walk-in locations across Karachi, Lahore, Islamabad, Rawalpindi, and Multan — including Afzal Electronics, CZone, Telemart, Mega.pk, Shophive, HomeShopping, Galaxy.pk, and more.

### Online-Only Stores (10)

Daraz.pk, iShopping.pk, Chip.pk, Digilog.pk, ePal.pk, Rawlix.com, and others offering Pakistan-wide delivery.

---

## 🧠 How It Works

```
User Location + Product Query
            │
            ▼
   ┌─────────────────┐
   │  Web Scrapers    │  ← Scrape 30+ stores in parallel
   └────────┬────────┘
            ▼
   ┌─────────────────┐
   │ Prediction Svc   │  ← Score every (branch × product) pair
   │  • Price ±10%    │     with location-based price variation
   │  • Distance calc │
   │  • Travel cost   │
   └────────┬────────┘
            ▼
   ┌─────────────────┐
   │  Decision Svc    │  ← Pick best overall, cheapest, nearest
   │  • Recommend     │     with human-readable advice
   │  • Multi-stop    │
   └────────┬────────┘
            ▼
     JSON API Response
```

### Cost Calculation

| Parameter | Value |
|-----------|-------|
| Fuel price | Rs. 300/liter |
| Fuel efficiency | 12 km/liter |
| Fuel cost/km | ~Rs. 25/km |
| Time value | Rs. 500/hour |
| Avg city speed | 30 km/h |

**Grand Total = Product Price + Fuel Cost + Time Cost**

---

## 🧪 Verifying Scrapers

Run the built-in verification script to test all scrapers:

```bash
python verify_scrapers.py
```

---

## 🛠️ Tech Stack

- **Backend:** Flask, Gunicorn
- **Scraping:** Requests, BeautifulSoup4, lxml
- **Distance:** Google Maps Distance Matrix API / Haversine
- **Frontend:** HTML, CSS, JavaScript, Google Maps JS API

---

## 📄 License

This project is for educational and research purposes.
]]>
