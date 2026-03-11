"""
verify_scrapers.py
Smoke-checks the current electronics scraper pipeline.
"""
import os
import sys

# Add project root to sys.path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from scrapers import fetch_category


def test_scraper(label: str, query: str | None = None) -> bool:
    """Run a basic scrape check for electronics-only mode."""
    print(f"--- Testing {label} ---")
    try:
        products = fetch_category(label if label in ["paints","mobiles"] else "electronics", max_pages=1, query=query)
        print(f"Success! Found {len(products)} products.")
        if products:
            sample = products[0]
            print(f"Sample: {sample['product']} - Rs. {sample['price']}")
            assert "product" in sample
            assert "price" in sample
            assert isinstance(sample["price"], (int, float))
        # category assertion only when default
        if label == "electronics_default":
            assert sample.get("category") == "electronics"
        return True
    except Exception as exc:
        print(f"FAILED: {exc}")
        return False


if __name__ == "__main__":
    checks = [
        ("electronics_default", None),
        ("query_laptop", "laptop"),
        ("query_mobile", "mobile"),
        ("paints", None),
        ("mobiles", None),
    ]

    results = {}
    for label, query in checks:
        results[label] = test_scraper(label, query=query)

    print("\n--- Summary ---")
    all_ok = True
    for label, ok in results.items():
        status = "OK" if ok else "FAILED"
        print(f"{label:20}: {status}")
        if not ok:
            all_ok = False

    if all_ok:
        print("\nAll scraper checks passed.")
        sys.exit(0)

    print("\nSome scraper checks failed.")
    sys.exit(1)
