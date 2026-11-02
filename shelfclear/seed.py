"""Seed data: 8 realistic dead-stock items for a small online seller.

Prices in USD — the seller sells to international buyers and gets paid
through PayPal (the realistic PayPal use case for an Indian seller).
Each item has a believable original price, cost, floor price, quantity
and days unsold.
"""
from . import pricing, store

SEED_ITEMS = [
    # name, category, original, cost, floor, qty, days_unsold
    ("Wireless Bluetooth Earbuds", "Electronics", 29.99, 12.00, 16.00, 14, 210),
    ("Handloom Cotton Kurti (Size M)", "Fashion", 34.00, 14.00, 18.00, 9, 180),
    ("Leather Sneakers (UK 8)", "Footwear", 59.99, 26.00, 32.00, 6, 260),
    ("Floral Phone Case (iPhone 13)", "Accessories", 12.99, 3.50, 6.00, 40, 300),
    ("Brass Diya Set (Pack of 4)", "Home", 24.99, 9.00, 12.00, 12, 150),
    ("Stainless Steel Bottle 1L", "Home", 18.99, 6.50, 9.00, 18, 120),
    ("Kids' Wooden Building Blocks", "Toys", 27.99, 11.00, 14.00, 8, 200),
    ("Herbal Face Serum 30ml", "Beauty", 22.99, 7.00, 11.00, 11, 170),
]


def seed_if_empty():
    if store.list_items():
        return 0
    count = 0
    for name, category, original, cost, floor, qty, days in SEED_ITEMS:
        item_id = store.add_item(name, category, original, cost, floor, qty, days)
        result = pricing.price_item(name, category, original, cost, floor, qty, days)
        store.update_item_pricing(
            item_id,
            result["ai_price"],
            result["discount_pct"],
            result["dead_score"],
            result["reason"],
        )
        count += 1
    return count
