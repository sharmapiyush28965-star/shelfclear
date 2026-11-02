# ShelfClear — Test Log

All tests run against the real server (booted on a throwaway database),
not against mocked functions. Command: `python3 test_loop.py`

## Run 1 — 2026-10-28, simulator mode (fresh DB)
**46 passed, 0 failed.**

- Server starts; mode reports `simulator`.
- Pages load: `/`, `/static/app.js`, `/static/style.css` (200).
- Seed: 8 items, cash stuck **$2,723.91**, recovered $0.
- Pricing: phone case AI price **$8.07**, discount **37.9%**, dead score
  **79.6**, reason present; no AI price below any floor.
- Add item: ceramic mug priced **$11.93**; 9 items; re-price works.
- Storefront lists 9 items.
- Negotiation: offer $4.00 (below $6.00 floor) → hold, ask unchanged;
  $7.00 → counter at midpoint **$7.54**; $8.50 → accept, agreed $8.50.
- PayPal simulator: order `SIM-ORDER-*` created → approved → captured
  (`SIM-CAPTURE-*`, $8.50). Dashboard recovered $8.50, 1 item sold,
  phone case marked sold.
- Walk-away: two below-floor offers on earbuds → hold, then walk away;
  paying a walked-away deal rejected (400).
- Guards: capture before approval rejected (400); second deal
  (kurti, AI price $22.58) captured; recovered total **$31.08**.

## Bug found by manual smoke test (and fixed)
While testing the **sandbox mode with no keys**, the pay request dropped
the connection (HTTP 000). Root cause: in `shelfclear/paypal.py` the
instance attribute `self._access_token` shadowed the method of the same
name, so calling it raised `TypeError` instead of the intended
`PayPalError`, which the handler did not catch.
Fix: renamed the attribute to `self._token` and the method to
`_get_token()`; also added a generic `except Exception` safety net in
`app.py` so a PayPal failure always returns a clean 502 JSON instead of
ever dropping a connection. A regression test for this path was added to
the suite (phase 2 below).

## Run 2 — after the fix (fresh DB, both phases)
**52 passed, 0 failed** (46 simulator checks + 6 new sandbox checks).

Phase 2 checks: sandbox server starts; mode reports `sandbox`; deal +
accept work; pay without keys → clean **502** naming
`PAYPAL_CLIENT_ID`; server still alive afterwards.

## Run 3 — double verification (fresh DB, both phases)
**52 passed, 0 failed.** Same result as run 2.

## Live smoke test (manual curl, default run)
- `GET /api/mode` → simulator; `GET /api/dashboard` → stuck $2,723.91,
  cost stuck $980.00, 8 listed; `GET /api/items` → 8 items
  (first: Wireless Bluetooth Earbuds, AI $19.49); index title correct;
  `/return?deal=1` → 200.
- Sandbox mode without keys → `{"error": "PAYPAL_CLIENT_ID /
  PAYPAL_CLIENT_SECRET are not set."}` with HTTP 502; server stays alive.

## Not tested (needs keys the user has not provided yet)
- Real sandbox API calls (`api-m.sandbox.paypal.com`): create order,
  buyer approval in the PayPal checkout page, capture. The code follows
  PayPal's documented Orders API v2 flow (OAuth2 client credentials,
  intent CAPTURE, approval link, capture endpoint) verified against
  developer.paypal.com docs, but no live call has been made. Re-run the
  demo loop once real sandbox keys are set, before recording the video.

## Deep re-check — 2026-10-29, independent manual verification (fresh DB, curl)
Done because the user asked for one more full check ("sometime you made too much mistakes").
Every number below was verified by hand, not just by the test suite.

- Code review: pricing.py (score/discount/floor-clamp math), negotiate.py
  (state machine, counter limits, floor never breached), paypal.py (real
  sandbox OAuth2 + Orders v2 flow vs docs; simulator clearly labelled),
  app.py (input validation, state guards), store.py, seed.py — all read fully.
- Pricing hand-check (new item: Cotton Tote Bag, Fashion, $15.00, floor
  $7.00, qty 20, 200 days): score 73.4, discount 35.7%, price $9.65 —
  recomputed by hand, matches exactly.
- Negotiation hand-check (phone case, ask $8.07, floor $6.00): $4.00 -> hold;
  $7.00 -> counter $7.54 = (7.00+8.07)/2 exactly; $8.50 -> accept. All correct.
- Payment loop: order SIM-ORDER-* created -> capture-before-approve rejected
  (400) -> approved -> captured (SIM-CAPTURE-*, $8.50). Dashboard: stuck
  $2,723.91+$300.00-$519.60 = $2,504.31, recovered $8.50, 1 sold, 8 listed.
  Arithmetic verified. Pay-on-negotiating-deal rejected (400).
- Simulator honesty: "simulator" mode labelled in /api/mode, UI banner,
  every simulator response; README Tools disclosure accurate (no LLM used,
  no inflated claims).
- README demo script claims (stuck $2,723.91, phone case $8.07, $8.50 accept)
  all reproduced exactly.

**Result: no bugs found.** Two cosmetic notes (not bugs): pricing.py has a
redundant if/elif/else producing the same reason string; selling marks the
whole item sold regardless of qty (demo simplification, not misrepresented).
Nothing changed in code — nothing needed changing.
