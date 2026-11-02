"""ShelfClear negotiation engine.

A deterministic state machine — the agent DECIDES, it does not just
write text. Rules, in order:

  1. Offer >= current ask price            -> ACCEPT at the offer.
  2. Offer >= 95% of ask (and >= floor)    -> ACCEPT at the offer.
  3. Offer >= floor, counters left (< 2)   -> COUNTER at the midpoint
     between the offer and the ask (never below floor).
  4. Offer >= floor, no counters left      -> ACCEPT if the offer is
     within $2 of the ask, otherwise WALK AWAY.
  5. Offer < floor, first time             -> HOLD FIRM at the ask and
     explain the floor.
  6. Offer < floor, second time            -> WALK AWAY politely.

The agent never agrees below the seller's floor price. Ever.
"""

MAX_COUNTERS = 2
ACCEPT_WITHIN_PCT = 0.95
FINAL_ACCEPT_WITHIN_USD = 2.00


def money(value):
    return round(float(value) + 1e-9, 2)


def agent_greeting(item_name, ask_price):
    return (
        f"Hi! I'm the ShelfClear agent for '{item_name}'. "
        f"It's on clearance at ${ask_price:.2f}. "
        f"Make me an offer and I'll see what I can do — I can go lower, "
        f"but I can't go below the seller's minimum price."
    )


def evaluate_offer(item, deal, offer):
    """Evaluate a buyer offer.

    item: dict with ai_price / floor_price / name
    deal: dict with ask_price, counters, below_floor_count
    offer: float, buyer's offered price in USD

    Returns dict: {action, reply, agreed_price, new_ask, counters,
                   below_floor_count, status}
    action is one of: accept, counter, hold, walk_away
    status is one of: negotiating, accepted, walked_away
    """
    floor_price = money(item["floor_price"])
    ask = money(deal["ask_price"])
    counters = int(deal["counters"])
    below_floor = int(deal["below_floor_count"])
    name = item["name"]

    if offer <= 0:
        return {
            "action": "hold",
            "reply": "That offer doesn't work — please enter an amount above $0.",
            "agreed_price": None,
            "new_ask": ask,
            "counters": counters,
            "below_floor_count": below_floor,
            "status": "negotiating",
        }

    # 1-2. Good offer: at ask, or close enough to it.
    if offer >= ask:
        return {
            "action": "accept",
            "reply": (
                f"Deal! ${offer:.2f} works for '{name}'. "
                f"I'll get the PayPal payment ready for you."
            ),
            "agreed_price": money(offer),
            "new_ask": ask,
            "counters": counters,
            "below_floor_count": below_floor,
            "status": "accepted",
        }
    if offer >= floor_price and offer >= ACCEPT_WITHIN_PCT * ask:
        return {
            "action": "accept",
            "reply": (
                f"Deal! ${offer:.2f} is close enough to my ${ask:.2f} — "
                f"'{name}' is yours. I'll get the PayPal payment ready."
            ),
            "agreed_price": money(offer),
            "new_ask": ask,
            "counters": counters,
            "below_floor_count": below_floor,
            "status": "accepted",
        }

    # 5-6. Below the seller's floor: never acceptable.
    if offer < floor_price:
        below_floor += 1
        if below_floor >= 2:
            return {
                "action": "walk_away",
                "reply": (
                    f"I have to stop here — ${offer:.2f} is below the lowest"
                    f" price the seller can accept (${floor_price:.2f}) for"
                    f" '{name}', and I can't go below that. Thanks for"
                    f" your interest!"
                ),
                "agreed_price": None,
                "new_ask": ask,
                "counters": counters,
                "below_floor_count": below_floor,
                "status": "walked_away",
            }
        return {
            "action": "hold",
            "reply": (
                f"${offer:.2f} is below the seller's minimum of"
                f" ${floor_price:.2f} for '{name}', so I can't accept it."
                f" My price stays at ${ask:.2f} — can you come up a bit?"
            ),
            "agreed_price": None,
            "new_ask": ask,
            "counters": counters,
            "below_floor_count": below_floor,
            "status": "negotiating",
        }

    # 3. Fair offer, counters left: meet in the middle.
    if counters < MAX_COUNTERS:
        counter = money((offer + ask) / 2.0)
        if counter < floor_price:
            counter = floor_price
        return {
            "action": "counter",
            "reply": (
                f"${offer:.2f} is a bit low for '{name}' — how about"
                f" ${counter:.2f}? That's halfway between your offer and"
                f" my ${ask:.2f}, and it's a genuine clearance price."
            ),
            "agreed_price": None,
            "new_ask": counter,
            "counters": counters + 1,
            "below_floor_count": below_floor,
            "status": "negotiating",
        }

    # 4. No counters left: accept if within $2, else walk away.
    if offer >= ask - FINAL_ACCEPT_WITHIN_USD:
        return {
            "action": "accept",
            "reply": (
                f"OK, ${offer:.2f} it is — that's close enough to my last"
                f" price of ${ask:.2f} for '{name}'. I'll get the PayPal"
                f" payment ready."
            ),
            "agreed_price": money(offer),
            "new_ask": ask,
            "counters": counters,
            "below_floor_count": below_floor,
            "status": "accepted",
        }
    return {
        "action": "walk_away",
        "reply": (
            f"I've come down as far as I can — my last price was"
            f" ${ask:.2f} and ${offer:.2f} is too far from it for"
            f" '{name}'. Thanks for trying, and the clearance price stays"
            f" at ${ask:.2f} if you change your mind."
        ),
        "agreed_price": None,
        "new_ask": ask,
        "counters": counters,
        "below_floor_count": below_floor,
        "status": "walked_away",
    }
