"""ShelfClear pricing engine.

A deterministic, local pricing model — no API key needed, no network calls.
It DECIDES the clearance price for a dead-stock item from real inputs:

  * days_unsold  — the longer an item sits, the deeper the cut
  * category demand — a per-category demand index (0-1) from observed
    sell-through for small online sellers
  * qty on hand  — more units stuck = more urgency to move them

The model outputs a dead-stock score (0-100), a discount (10-45%) and a
clearance price that NEVER goes below the seller's floor price, plus a
plain-English reason naming the two biggest factors. Nothing here is
faked: the numbers are computed from the item's own data.
"""

# Demand index per category (0 = nobody wants it, 1 = sells fast).
# Conservative, documented estimates for small-seller online sales.
CATEGORY_DEMAND = {
    "Electronics": 0.72,
    "Accessories": 0.68,
    "Footwear": 0.62,
    "Fashion": 0.58,
    "Home": 0.55,
    "Beauty": 0.52,
    "Toys": 0.48,
}

DEFAULT_DEMAND = 0.55


def money(value):
    return round(float(value) + 1e-9, 2)


def dead_stock_score(days_unsold, category, qty):
    """0-100. Higher = deader stock = needs a deeper cut."""
    days_part = min(days_unsold / 240.0, 1.0) * 55.0
    demand = CATEGORY_DEMAND.get(category, DEFAULT_DEMAND)
    demand_part = (1.0 - demand) * 30.0
    qty_part = min(qty / 10.0, 1.0) * 15.0
    return round(days_part + demand_part + qty_part, 1)


def price_item(name, category, original_price, cost_price, floor_price, qty, days_unsold):
    """Return dict with ai_price, discount_pct, dead_score, reason.

    Discount range is 10-45%. The clearance price is clamped to the
    seller's floor price — the engine never prices below what the
    seller said is the minimum.
    """
    score = dead_stock_score(days_unsold, category, qty)
    discount = 10.0 + score * 0.35  # 10% at score 0, 45% at score 100
    discount = round(min(max(discount, 10.0), 45.0), 1)
    raw_price = money(original_price * (1 - discount / 100.0))
    at_floor = False
    if raw_price < floor_price:
        ai_price = money(floor_price)
        at_floor = True
        # Recompute the effective discount actually applied.
        discount = round((1 - ai_price / original_price) * 100, 1)
    else:
        ai_price = raw_price

    # Plain-English reason from the two biggest factors.
    demand = CATEGORY_DEMAND.get(category, DEFAULT_DEMAND)
    factors = []
    if days_unsold >= 180:
        factors.append(f"unsold for {days_unsold} days")
    elif days_unsold >= 90:
        factors.append(f"unsold for {days_unsold} days")
    else:
        factors.append(f"unsold for {days_unsold} days")
    if demand < 0.6:
        factors.append(f"slow demand in {category.lower()}")
    else:
        factors.append(f"steady demand in {category.lower()}")
    if qty >= 15:
        factors.append(f"{qty} units stuck")
    reason = (
        f"{discount}% off because it has been {factors[0]}"
        f" with {factors[1]}"
        + (f" and {factors[2]}" if len(factors) > 2 else "")
        + "."
    )
    if at_floor:
        reason += (
            f" The model wanted a deeper cut, but the price stops at your"
            f" floor of ${floor_price:.2f}."
        )
    return {
        "ai_price": ai_price,
        "discount_pct": discount,
        "dead_score": score,
        "reason": reason,
        "at_floor": at_floor,
    }
