# ShelfClear — AI agent that turns dead stock into cash

Small online sellers have money stuck on shelves: products that stopped
selling. ShelfClear finds that dead stock, prices it with an AI engine,
negotiates with buyers itself, and closes the sale through PayPal — so
stuck cash becomes recovered cash.

Built for the **PayPal AI Hackathon** (Devpost). Submission deadline:
**12 Nov 2026, 12:00pm Pacific (13 Nov, 1:30am IST)**. Judging 1–15 Dec 2026,
winners announced ~21 Dec 2026.

## The problem

A small seller's unsold inventory is cash locked in a box. A phone case
that hasn't sold in 300 days is not "stock" — it is $500 the seller
cannot spend. Cutting the price by hand is guesswork, and answering
bargain-hunting buyers takes hours the seller doesn't have.

## What ShelfClear does

1. **Seller adds dead-stock items** — name, category, original price, cost,
   floor (minimum) price, quantity, days unsold. 8 realistic demo items are
   pre-loaded.
2. **The AI pricing engine prices each item** — a dead-stock score (0–100)
   from days unsold + category demand + quantity on hand, turned into a
   10–45% clearance discount. The price **never goes below the seller's
   floor**, and every price shows a plain-English reason.
3. **Deals go live on a storefront** — buyers see the AI clearance price.
4. **The AI agent negotiates in chat** — it accepts good offers, counters
   by meeting the buyer halfway (max 2 counters), holds firm at the floor,
   and walks away when the buyer won't come up. It **never** agrees below
   the floor.
5. **PayPal closes the sale** — on agreement the app creates a real PayPal
   Orders API v2 order (intent CAPTURE), the buyer approves it in PayPal
   checkout, and the app captures the payment. The dashboard's
   **cash recovered** total goes up; the item is marked sold.

## Run it (one command)

```sh
python3 app.py
# then open http://localhost:8000
```

Python 3.8+ only. **Zero dependencies** — standard library only, so there
is nothing to install. The app creates `data.db` (SQLite) on first run and
seeds the 8 demo items. Set `PORT` to change the port.

## PayPal modes — read this, it matters

The app has **two modes**, shown in a banner at the top of every page:

| Mode | When | What happens |
|---|---|---|
| **Simulator** (default) | No PayPal keys set | The full loop runs end-to-end — create → approve → capture — with faithful fake responses shaped like PayPal's. Clearly labelled everywhere. **No call is made to PayPal and no money moves.** |
| **Live Sandbox** | `PAYPAL_CLIENT_ID` + `PAYPAL_CLIENT_SECRET` set | Real calls to `api-m.sandbox.paypal.com`: OAuth2 token, create order, buyer approves in the PayPal sandbox checkout page, capture. Still test money only — the sandbox never moves real money. |

Switch to real sandbox mode:

```sh
export PAYPAL_CLIENT_ID="your sandbox app client id"
export PAYPAL_CLIENT_SECRET="your sandbox app secret"
python3 app.py
```

Get the keys free at [developer.paypal.com](https://developer.paypal.com)
(Dashboard → My Apps & Credentials → create a sandbox app). No KYC, no
card, no real money — the sandbox is PayPal's test environment. In sandbox
mode the buyer approves with a **sandbox test buyer account** (created in
the same Developer Dashboard under Sandbox → Accounts).

To force a mode: `PAYPAL_MODE=simulator` or `PAYPAL_MODE=sandbox`.

## What the AI actually does (honest Tools disclosure)

For the Devpost "Tools" field:

- **Pricing engine** (`shelfclear/pricing.py`) — a local, deterministic
  model written for this project. Inputs: days unsold, per-category demand
  index, quantity on hand. Outputs: dead-stock score, discount, clearance
  price, plain-English reason. No API key, no network call, no LLM.
- **Negotiation engine** (`shelfclear/negotiate.py`) — a local, deterministic
  state machine written for this project. It decides accept / counter /
  hold / walk away from the offer, the floor price and the counter rules.
  No LLM.
- **PayPal** — Orders API v2 (`api-m.sandbox.paypal.com`): OAuth2
  client-credentials token, create order (intent CAPTURE), get order,
  capture order. In simulator mode these calls are faithfully mimicked
  locally and labelled as such.
- **No third-party AI model, API or SDK is used.** No LLM API key is
  needed or used anywhere in this project. The AI here is real, purpose-built
  decision code — it makes pricing and negotiation decisions — not a
  wrapper around a chatbot.

## Architecture

```
app.py                    stdlib HTTP server (ThreadingHTTPServer), JSON API
shelfclear/
  store.py                SQLite storage (items, deals, messages, payments)
  pricing.py              AI pricing engine (dead-stock score -> price)
  negotiate.py            AI negotiation engine (accept/counter/hold/walk away)
  paypal.py               PayPal client: real sandbox + simulator, same interface
  seed.py                 8 demo items
static/
  index.html / style.css / app.js / return.html   vanilla frontend
```

Money is always handled as USD with 2-decimal rounding. The PayPal order
amount is the agreed negotiation price.

## Demo script (the 6 steps a judge follows)

1. Open http://localhost:8000 — Dashboard shows $2,723.91 stuck in dead
   stock, $0 recovered. Note the mode banner (Simulator).
2. Inventory — see 8 items with AI prices, dead scores and reasons.
   Add a new item and watch the AI price it instantly.
3. Storefront — open "Floral Phone Case", click "Negotiate with the agent".
4. Negotiate — offer $4.00 (below the $6.00 floor): the agent holds firm.
   Offer $7.00: the agent counters. Offer $8.50: the agent accepts.
5. Pay — click "Create PayPal order", then "Approve", then "Capture
   payment". The capture id appears and the deal is marked paid.
6. Dashboard — cash recovered is now $8.50 and the item is sold.
   The recovery meter moves.

## Test log

See [TEST-LOG.md](TEST-LOG.md) — the full demo loop was run twice against a
fresh database with automated checks at every step (pricing, negotiation
accept/counter/hold/walk-away, order create/approve/capture, dashboard
totals). All checks pass.

## Still to do before submission (not in this phase)

- [ ] Publish this folder as a **public GitHub repo** with the MIT licence
      (already included as `LICENSE`).
- [ ] Record the **demo video (< 3 min)** and upload it to public YouTube.
- [ ] Create the Devpost account, join the hackathon, fill the submission
      form (text description + repo link + demo URL/instructions + video
      link + Tools disclosure from above). The final Submit click is the
      entrant's own step.
- [ ] Optional: switch to real sandbox keys and re-run the demo loop once
      to capture real sandbox order/capture ids for the video.
