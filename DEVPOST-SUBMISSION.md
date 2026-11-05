# Devpost submission — ShelfClear (PayPal AI Hackathon)
Paste each field into the Devpost submission form. Deadline: 13 Nov 2026, 1:30 a.m. IST.

## Project title
ShelfClear — AI agent that turns dead stock into cash

## Tagline
An AI agent that prices dead stock, negotiates with buyers on its own, and closes the sale through PayPal.

## Description (paste into the main description field)
**Inspiration:** Small online sellers lose money twice: cash locked in products that stopped selling, and hours lost haggling with bargain hunters. I wanted an agent that does the whole job — price it, sell it, collect the money.

**What it does:** ShelfClear is a working web app. The pricing engine scores every item 0–100 (days unsold, category demand, quantity stuck) and sets a clearance price — 10–45% off, never below the seller's floor, with a plain-English reason for each price. Then the negotiation agent chats with buyers: it accepts fair offers, counters low ones (max 2 rounds), holds firm below the floor, or walks away. On agreement it creates a real PayPal order (Orders API v2), the buyer approves, and the app captures the payment. The dashboard shows cash stuck → cash recovered.

**How I built it:** Python 3 standard library only (zero dependencies), SQLite, vanilla JavaScript frontend. PayPal integration uses the official Orders v2 REST API: OAuth2 client-credentials → create order (intent CAPTURE) → buyer approval → capture. A simulator mode runs the identical loop without keys for easy demos — clearly labelled everywhere, never presented as real.

**Challenges:** Making the negotiation agent firm but fair — holding the floor without being rude, and countering at exactly the midpoint. Every number was verified by hand: all pricing and negotiation math double-checked with exact calculations.

**Accomplishments:** A complete working loop: 8 demo items with $2,723.91 stuck, AI pricing on all of them, a full negotiation ($4.00 hold → $7.00 counter at $7.54 → $8.50 accept), and a captured payment with the dashboard's recovered meter moving. 52 automated checks pass.

**What's next:** Real seller catalogs (CSV/Shopify import), multi-currency pricing, and notifications when the agent closes a deal.

## Built with
PayPal Orders API v2, Python, SQLite, JavaScript

## Links
- Code repository (public, MIT licence): https://github.com/sharmapiyush28965-star/shelfclear
- Demo video (1:43, public on YouTube): https://www.youtube.com/watch?v=4OhtQjnSZM8

## Try it out (paste into "How to run / demo instructions")
1. Clone the repo: git clone https://github.com/sharmapiyush28965-star/shelfclear
2. Run: python3 app.py
3. Open http://localhost:8000 — no API keys needed; the app runs in simulator mode (clearly labelled in the UI).
4. Dashboard → see $2,723.91 cash stuck in 8 items. Inventory → see each item's AI price and reason. Storefront → open a deal on the phone case, make offers ($4, $7, $8.50) and watch the agent hold, counter, and accept. Pay with PayPal (simulated) and watch the dashboard's cash-recovered meter move.
5. With real PayPal sandbox keys (PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET env vars), the identical code runs against PayPal's sandbox Orders API v2 — order create → buyer approval → capture.

## Tools disclosure (Devpost "Tools used" / AI disclosure field)
No AI/LLM tools were used to build ShelfClear. The pricing engine, negotiation state machine, and payment loop are real, purpose-built decision code — not a wrapper around a chatbot. The demo video's voiceover was generated with text-to-speech; all numbers shown are real values from the verified test run.
