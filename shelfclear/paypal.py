"""PayPal client for ShelfClear — real sandbox mode + simulator mode.

REAL SANDBOX MODE (used only when PAYPAL_CLIENT_ID and
PAYPAL_CLIENT_SECRET are set in the environment):
  * OAuth2 client-credentials flow against api-m.sandbox.paypal.com
  * POST /v2/checkout/orders (intent CAPTURE, payment_source paypal)
    -> returns a real PayPal order id + approval URL
  * GET  /v2/checkout/orders/{id} to check approval status
  * POST /v2/checkout/orders/{id}/capture -> real sandbox capture
  No real money ever moves: sandbox is PayPal's test environment.

SIMULATOR MODE (default when keys are absent):
  Runs the exact same steps — create -> approve -> capture — with
  faithful, clearly labelled fake responses shaped like PayPal's.
  Simulator results are NEVER presented as real PayPal calls: every
  response carries mode="simulator" and the UI shows a banner.

Mode selection: PAYPAL_MODE env var (auto | simulator | sandbox).
auto (default) = sandbox when both credentials are present, else simulator.
"""
import base64
import json
import os
import random
import string
import urllib.error
import urllib.request

SANDBOX_BASE = "https://api-m.sandbox.paypal.com"


class PayPalError(Exception):
    pass


def _env_mode():
    mode = os.environ.get("PAYPAL_MODE", "auto").strip().lower()
    if mode in ("simulator", "sandbox", "auto"):
        return mode
    return "auto"


def active_mode():
    """Return 'sandbox' or 'simulator' — the mode actually in use."""
    mode = _env_mode()
    if mode == "sandbox":
        return "sandbox"
    if mode == "simulator":
        return "simulator"
    # auto
    if os.environ.get("PAYPAL_CLIENT_ID") and os.environ.get("PAYPAL_CLIENT_SECRET"):
        return "sandbox"
    return "simulator"


def _fake_id(prefix, length=12):
    alphabet = string.ascii_uppercase + string.digits
    return prefix + "".join(random.choice(alphabet) for _ in range(length))


class PayPalClient:
    def __init__(self, mode=None):
        self.mode = mode or active_mode()
        self.client_id = os.environ.get("PAYPAL_CLIENT_ID", "")
        self.client_secret = os.environ.get("PAYPAL_CLIENT_SECRET", "")
        self._token = None

    # ---- public API (identical in both modes) ----

    def create_order(self, amount, description, return_url, cancel_url):
        """Create a CAPTURE order. Returns dict with order_id, status,
        approve_url, raw response and mode."""
        amount_str = f"{float(amount):.2f}"
        if self.mode == "sandbox":
            return self._create_order_real(amount_str, description, return_url, cancel_url)
        raw = {
            "id": _fake_id("SIM-ORDER-"),
            "intent": "CAPTURE",
            "status": "CREATED",
            "purchase_units": [
                {
                    "reference_id": "shelfclear-deal",
                    "description": description,
                    "amount": {"currency_code": "USD", "value": amount_str},
                }
            ],
            "links": [
                {
                    "href": "https://www.sandbox.paypal.com/checkoutnow?token=SIMULATED",
                    "rel": "approve",
                    "method": "GET",
                }
            ],
            "simulator": True,
            "note": (
                "SIMULATOR response — no call was made to PayPal. "
                "Set PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET to use the real sandbox."
            ),
        }
        return {
            "order_id": raw["id"],
            "status": raw["status"],
            "approve_url": raw["links"][0]["href"],
            "raw": raw,
            "mode": "simulator",
        }

    def approve_order(self, order_id):
        """Mark an order approved (simulator) or check its live status (sandbox).

        In real sandbox flow the buyer approves in the PayPal checkout
        page; this call verifies the order is APPROVED before capture.
        """
        if self.mode == "sandbox":
            order = self._get_order_real(order_id)
            status = order.get("status", "")
            if status != "APPROVED":
                raise PayPalError(
                    f"Order {order_id} is '{status}', not APPROVED yet."
                    " The buyer must approve it in PayPal checkout first."
                )
            return {"order_id": order_id, "status": "APPROVED", "raw": order, "mode": "sandbox"}
        raw = {
            "id": order_id,
            "status": "APPROVED",
            "simulator": True,
            "note": "SIMULATOR approval — the buyer approval step was simulated.",
        }
        return {"order_id": order_id, "status": "APPROVED", "raw": raw, "mode": "simulator"}

    def capture_order(self, order_id):
        """Capture an approved order. Returns capture details."""
        if self.mode == "sandbox":
            return self._capture_order_real(order_id)
        capture_id = _fake_id("SIM-CAPTURE-")
        raw = {
            "id": order_id,
            "status": "COMPLETED",
            "purchase_units": [
                {
                    "payments": {
                        "captures": [
                            {
                                "id": capture_id,
                                "status": "COMPLETED",
                                "amount": {"currency_code": "USD", "value": "see-deal"},
                            }
                        ]
                    }
                }
            ],
            "simulator": True,
            "note": "SIMULATOR capture — no money moved and no call was made to PayPal.",
        }
        return {
            "order_id": order_id,
            "status": "COMPLETED",
            "capture_id": capture_id,
            "raw": raw,
            "mode": "simulator",
        }

    # ---- real sandbox implementation ----

    def _http(self, method, path, body=None, headers=None):
        url = SANDBOX_BASE + path
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        for key, value in (headers or {}).items():
            req.add_header(key, value)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            raise PayPalError(f"PayPal {method} {path} failed ({exc.code}): {detail}")

    def _get_token(self):
        if self._token:
            return self._token
        if not self.client_id or not self.client_secret:
            raise PayPalError("PAYPAL_CLIENT_ID / PAYPAL_CLIENT_SECRET are not set.")
        creds = base64.b64encode(
            f"{self.client_id}:{self.client_secret}".encode("utf-8")
        ).decode("ascii")
        req = urllib.request.Request(
            SANDBOX_BASE + "/v1/oauth2/token",
            data=b"grant_type=client_credentials",
            method="POST",
        )
        req.add_header("Authorization", f"Basic {creds}")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise PayPalError(
                f"PayPal OAuth failed ({exc.code}): "
                f"{exc.read().decode('utf-8', 'replace')}"
            )
        self._token = payload["access_token"]
        return self._token

    def _auth_headers(self):
        return {"Authorization": f"Bearer {self._get_token()}"}

    def _create_order_real(self, amount_str, description, return_url, cancel_url):
        body = {
            "intent": "CAPTURE",
            "purchase_units": [
                {
                    "reference_id": "shelfclear-deal",
                    "description": description[:120],
                    "amount": {"currency_code": "USD", "value": amount_str},
                }
            ],
            "payment_source": {
                "paypal": {
                    "experience_context": {
                        "brand_name": "ShelfClear",
                        "user_action": "PAY_NOW",
                        "return_url": return_url,
                        "cancel_url": cancel_url,
                    }
                }
            },
        }
        raw = self._http("POST", "/v2/checkout/orders", body, self._auth_headers())
        approve_url = None
        for link in raw.get("links", []):
            if link.get("rel") in ("approve", "payer-action"):
                approve_url = link["href"]
        return {
            "order_id": raw["id"],
            "status": raw.get("status", "CREATED"),
            "approve_url": approve_url,
            "raw": raw,
            "mode": "sandbox",
        }

    def _get_order_real(self, order_id):
        return self._http("GET", f"/v2/checkout/orders/{order_id}", None, self._auth_headers())

    def _capture_order_real(self, order_id):
        raw = self._http(
            "POST", f"/v2/checkout/orders/{order_id}/capture", {}, self._auth_headers()
        )
        capture_id = None
        try:
            capture_id = raw["purchase_units"][0]["payments"]["captures"][0]["id"]
        except (KeyError, IndexError, TypeError):
            capture_id = None
        return {
            "order_id": order_id,
            "status": raw.get("status", "COMPLETED"),
            "capture_id": capture_id,
            "raw": raw,
            "mode": "sandbox",
        }
