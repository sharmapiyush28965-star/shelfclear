"""ShelfClear web server — Python standard library only (no dependencies).

Run:  python3 app.py
Then open http://localhost:8000

Env vars:
  PORT                 port to listen on (default 8000)
  SHELFCLEAR_DB        SQLite file path (default ./data.db)
  PAYPAL_MODE          auto | simulator | sandbox (default auto)
  PAYPAL_CLIENT_ID     sandbox app client id (real sandbox mode)
  PAYPAL_CLIENT_SECRET sandbox app secret (real sandbox mode)
"""
import json
import os
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from shelfclear import negotiate, paypal, pricing, seed, store

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

PAYPAL = paypal.PayPalClient()


def _money(value):
    return round(float(value) + 1e-9, 2)


def _item_view(item):
    return {
        "id": item["id"],
        "name": item["name"],
        "category": item["category"],
        "original_price": item["original_price"],
        "cost_price": item["cost_price"],
        "floor_price": item["floor_price"],
        "qty": item["qty"],
        "days_unsold": item["days_unsold"],
        "status": item["status"],
        "ai_price": item["ai_price"],
        "ai_discount_pct": item["ai_discount_pct"],
        "dead_score": item["dead_score"],
        "ai_reason": item["ai_reason"],
        "stuck_value": _money(item["original_price"] * item["qty"]),
    }


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    # ---- helpers ----
    def _send_json(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path, content_type):
        try:
            with open(path, "rb") as fh:
                body = fh.read()
        except FileNotFoundError:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return {}

    def _base_url(self):
        host = self.headers.get("Host") or f"localhost:{self.server.server_port}"
        return f"http://{host}"

    def log_message(self, fmt, *args):  # keep the console clean
        pass

    # ---- routing ----
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path == "/":
            self._send_file(os.path.join(STATIC_DIR, "index.html"), "text/html")
        elif path == "/api/mode":
            self._send_json(
                {
                    "mode": PAYPAL.mode,
                    "label": (
                        "LIVE SANDBOX — real PayPal sandbox API calls"
                        if PAYPAL.mode == "sandbox"
                        else "SIMULATOR — no PayPal calls, demo mode"
                    ),
                }
            )
        elif path == "/api/dashboard":
            self._send_json(store.dashboard_totals())
        elif path == "/api/items":
            self._send_json([_item_view(i) for i in store.list_items()])
        elif path == "/api/storefront":
            self._send_json([_item_view(i) for i in store.list_items("listed")])
        elif path == "/api/deals":
            deals = []
            for d in store.list_deals():
                payment = store.get_payment_by_deal(d["id"])
                deals.append(
                    {
                        "id": d["id"],
                        "item_id": d["item_id"],
                        "item_name": d["item_name"],
                        "buyer_name": d["buyer_name"],
                        "status": d["status"],
                        "agreed_price": d["agreed_price"],
                        "ask_price": d["ask_price"],
                        "payment": (
                            {
                                "mode": payment["mode"],
                                "status": payment["status"],
                                "paypal_order_id": payment["paypal_order_id"],
                                "capture_id": payment["capture_id"],
                                "amount": payment["amount"],
                            }
                            if payment
                            else None
                        ),
                    }
                )
            self._send_json(deals)
        elif path.startswith("/api/deals/"):
            try:
                deal_id = int(path.split("/")[3])
            except (IndexError, ValueError):
                self._send_json({"error": "bad deal id"}, 400)
                return
            deal = store.get_deal(deal_id)
            if not deal:
                self._send_json({"error": "deal not found"}, 404)
                return
            item = store.get_item(deal["item_id"])
            payment = store.get_payment_by_deal(deal_id)
            approve_url = None
            if payment:
                try:
                    raw = json.loads(payment["raw"] or "{}")
                    for link in raw.get("links", []):
                        if link.get("rel") in ("approve", "payer-action"):
                            approve_url = link["href"]
                except ValueError:
                    approve_url = None
            self._send_json(
                {
                    "deal": {
                        "id": deal["id"],
                        "item_id": deal["item_id"],
                        "item_name": item["name"] if item else "?",
                        "buyer_name": deal["buyer_name"],
                        "status": deal["status"],
                        "agreed_price": deal["agreed_price"],
                        "ask_price": deal["ask_price"],
                    },
                    "messages": store.list_messages(deal_id),
                    "payment": (
                        {
                            "mode": payment["mode"],
                            "status": payment["status"],
                            "paypal_order_id": payment["paypal_order_id"],
                            "capture_id": payment["capture_id"],
                            "amount": payment["amount"],
                            "approve_url": approve_url,
                        }
                        if payment
                        else None
                    ),
                }
            )
        elif path == "/return":
            deal_id = query.get("deal", [""])[0]
            self._send_file(os.path.join(STATIC_DIR, "return.html"), "text/html")
        elif path.startswith("/static/"):
            name = path[len("/static/"):]
            safe = os.path.normpath(name).replace(os.sep, "/")
            if safe.startswith(".."):
                self.send_response(403)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            ctype = "text/plain"
            if safe.endswith(".css"):
                ctype = "text/css"
            elif safe.endswith(".js"):
                ctype = "application/javascript"
            elif safe.endswith(".html"):
                ctype = "text/html"
            self._send_file(os.path.join(STATIC_DIR, safe), ctype)
        else:
            self._send_json({"error": "not found"}, 404)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        body = self._read_json()

        if path == "/api/items":
            try:
                name = str(body["name"]).strip()
                category = str(body.get("category") or "Home").strip()
                original = _money(body["original_price"])
                cost = _money(body["cost_price"])
                floor = _money(body["floor_price"])
                qty = int(body["qty"])
                days = int(body["days_unsold"])
            except (KeyError, TypeError, ValueError):
                self._send_json({"error": "invalid item fields"}, 400)
                return
            if not name or original <= 0 or cost < 0 or floor <= 0 or qty <= 0 or days < 0:
                self._send_json({"error": "invalid item values"}, 400)
                return
            if floor > original:
                self._send_json(
                    {"error": "floor price cannot be above the original price"}, 400
                )
                return
            item_id = store.add_item(name, category, original, cost, floor, qty, days)
            result = pricing.price_item(name, category, original, cost, floor, qty, days)
            store.update_item_pricing(
                item_id, result["ai_price"], result["discount_pct"],
                result["dead_score"], result["reason"],
            )
            self._send_json(_item_view(store.get_item(item_id)), 201)
            return

        if path.startswith("/api/items/") and path.endswith("/reprice"):
            try:
                item_id = int(path.split("/")[3])
            except (IndexError, ValueError):
                self._send_json({"error": "bad item id"}, 400)
                return
            item = store.get_item(item_id)
            if not item:
                self._send_json({"error": "item not found"}, 404)
                return
            result = pricing.price_item(
                item["name"], item["category"], item["original_price"],
                item["cost_price"], item["floor_price"], item["qty"],
                item["days_unsold"],
            )
            store.update_item_pricing(
                item_id, result["ai_price"], result["discount_pct"],
                result["dead_score"], result["reason"],
            )
            self._send_json(_item_view(store.get_item(item_id)))
            return

        if path == "/api/deals":
            try:
                item_id = int(body["item_id"])
                buyer = str(body.get("buyer_name") or "Buyer").strip() or "Buyer"
            except (KeyError, TypeError, ValueError):
                self._send_json({"error": "invalid deal fields"}, 400)
                return
            item = store.get_item(item_id)
            if not item or item["status"] != "listed":
                self._send_json({"error": "item not available"}, 400)
                return
            deal_id = store.create_deal(item_id, buyer, item["ai_price"])
            store.add_message(
                deal_id, "agent", negotiate.agent_greeting(item["name"], item["ai_price"])
            )
            self._send_json({"deal_id": deal_id}, 201)
            return

        if path.startswith("/api/deals/"):
            parts = path.split("/")
            try:
                deal_id = int(parts[3])
                action = parts[4]
            except (IndexError, ValueError):
                self._send_json({"error": "bad deal path"}, 400)
                return
            deal = store.get_deal(deal_id)
            if not deal:
                self._send_json({"error": "deal not found"}, 404)
                return
            item = store.get_item(deal["item_id"])

            if action == "offer":
                if deal["status"] != "negotiating":
                    self._send_json({"error": "deal is closed"}, 400)
                    return
                try:
                    offer = _money(body["offer"])
                except (KeyError, TypeError, ValueError):
                    self._send_json({"error": "invalid offer"}, 400)
                    return
                store.add_message(deal_id, "buyer", f"I'd like to offer ${offer:.2f}.")
                result = negotiate.evaluate_offer(item, deal, offer)
                store.add_message(deal_id, "agent", result["reply"])
                store.update_deal(
                    deal_id,
                    status=result["status"],
                    agreed_price=result["agreed_price"],
                    ask_price=result["new_ask"],
                    counters=result["counters"],
                    below_floor_count=result["below_floor_count"],
                )
                self._send_json(
                    {
                        "action": result["action"],
                        "reply": result["reply"],
                        "status": result["status"],
                        "agreed_price": result["agreed_price"],
                        "ask_price": result["new_ask"],
                    }
                )
                return

            if action == "pay":
                if deal["status"] != "accepted":
                    self._send_json(
                        {"error": "deal must be accepted before payment"}, 400
                    )
                    return
                existing = store.get_payment_by_deal(deal_id)
                if existing and existing["status"] in ("created", "approved", "captured"):
                    self._send_json(
                        {
                            "order_id": existing["paypal_order_id"],
                            "status": existing["status"],
                            "mode": existing["mode"],
                            "approve_url": None,
                            "already_exists": True,
                        }
                    )
                    return
                base = self._base_url()
                try:
                    result = PAYPAL.create_order(
                        deal["agreed_price"],
                        f"ShelfClear clearance: {item['name']}",
                        f"{base}/return?deal={deal_id}",
                        f"{base}/?deal={deal_id}&cancelled=1",
                    )
                except paypal.PayPalError as exc:
                    self._send_json({"error": str(exc)}, 502)
                    return
                except Exception as exc:  # never drop the connection
                    self._send_json({"error": f"PayPal call failed: {exc}"}, 502)
                    return
                store.add_payment(
                    deal_id, result["mode"], deal["agreed_price"],
                    result["order_id"], "created", result["raw"],
                )
                store.add_message(
                    deal_id,
                    "system",
                    f"PayPal order {result['order_id']} created"
                    f" ({result['mode']} mode). Waiting for buyer approval.",
                )
                self._send_json(
                    {
                        "order_id": result["order_id"],
                        "status": result["status"],
                        "mode": result["mode"],
                        "approve_url": result["approve_url"],
                    }
                )
                return

            if action == "approve":
                payment = store.get_payment_by_deal(deal_id)
                if not payment or payment["status"] != "created":
                    self._send_json({"error": "no pending payment to approve"}, 400)
                    return
                try:
                    result = PAYPAL.approve_order(payment["paypal_order_id"])
                except paypal.PayPalError as exc:
                    self._send_json({"error": str(exc)}, 502)
                    return
                except Exception as exc:  # never drop the connection
                    self._send_json({"error": f"PayPal call failed: {exc}"}, 502)
                    return
                store.update_payment(payment["id"], status="approved", raw=result["raw"])
                store.add_message(
                    deal_id, "system",
                    f"Buyer approved the PayPal order ({result['mode']} mode)."
                    " Ready to capture.",
                )
                self._send_json({"status": "approved", "mode": result["mode"]})
                return

            if action == "capture":
                payment = store.get_payment_by_deal(deal_id)
                if not payment or payment["status"] != "approved":
                    self._send_json(
                        {"error": "payment must be approved before capture"}, 400
                    )
                    return
                try:
                    result = PAYPAL.capture_order(payment["paypal_order_id"])
                except paypal.PayPalError as exc:
                    self._send_json({"error": str(exc)}, 502)
                    return
                except Exception as exc:  # never drop the connection
                    self._send_json({"error": f"PayPal call failed: {exc}"}, 502)
                    return
                store.update_payment(
                    payment["id"],
                    status="captured",
                    capture_id=result["capture_id"],
                    raw=result["raw"],
                )
                store.update_deal(deal_id, status="paid")
                store.mark_item_sold(item["id"])
                store.add_message(
                    deal_id,
                    "system",
                    f"Payment captured: ${deal['agreed_price']:.2f}"
                    f" ({result['mode']} mode, capture {result['capture_id']})."
                    " Cash recovered!",
                )
                self._send_json(
                    {
                        "status": "captured",
                        "capture_id": result["capture_id"],
                        "amount": deal["agreed_price"],
                        "mode": result["mode"],
                    }
                )
                return

            self._send_json({"error": "unknown deal action"}, 404)
            return

        self._send_json({"error": "not found"}, 404)


def main():
    store.init_db()
    seeded = seed.seed_if_empty()
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"ShelfClear running on http://localhost:{port}")
    print(f"PayPal mode: {PAYPAL.mode}")
    if seeded:
        print(f"Seeded {seeded} demo items.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
