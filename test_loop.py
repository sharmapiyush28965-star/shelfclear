"""End-to-end test for ShelfClear — boots the real server on a throwaway
database and walks the full demo loop with HTTP checks at every step.

Run:  python3 test_loop.py
Exit code 0 = all checks pass.
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

WORKDIR = os.path.dirname(os.path.abspath(__file__))
TEST_DB = "/tmp/shelfclear_test.db"
PORT = 8471
BASE = f"http://127.0.0.1:{PORT}"

PASS = 0
FAIL = 0
FAILURES = []


def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        FAILURES.append(name)
        print(f"  FAIL  {name}  {detail}")


def approx(a, b, tol=0.05):
    return abs(float(a) - float(b)) <= tol


def call(method, path, body=None, expect_error=False):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            payload = resp.read().decode()
            try:
                parsed = json.loads(payload) if payload else {}
            except ValueError:
                parsed = {"_html": payload}
            return resp.status, parsed
    except urllib.error.HTTPError as exc:
        payload = exc.read().decode()
        try:
            parsed = json.loads(payload) if payload else {}
        except ValueError:
            parsed = {"_raw": payload}
        if expect_error:
            return exc.code, parsed
        raise


def main():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    env = dict(os.environ)
    env["SHELFCLEAR_DB"] = TEST_DB
    env["PORT"] = str(PORT)
    env["PAYPAL_MODE"] = "simulator"
    env.pop("PAYPAL_CLIENT_ID", None)
    env.pop("PAYPAL_CLIENT_SECRET", None)

    proc = subprocess.Popen(
        [sys.executable, "app.py"], cwd=WORKDIR, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        up = False
        for _ in range(50):
            try:
                call("GET", "/api/mode")
                up = True
                break
            except Exception:
                time.sleep(0.2)
        check("server starts", up)
        if not up:
            return 1

        print("== mode ==")
        _, mode = call("GET", "/api/mode")
        check("mode is simulator", mode.get("mode") == "simulator", str(mode))

        print("== pages ==")
        status, _ = call("GET", "/")
        check("index page loads", status == 200)
        status, _ = call("GET", "/static/app.js")
        check("app.js loads", status == 200)
        status, _ = call("GET", "/static/style.css")
        check("style.css loads", status == 200)

        print("== seed + dashboard ==")
        _, dash = call("GET", "/api/dashboard")
        check("8 items seeded", dash.get("items_listed") == 8, str(dash))
        check("cash stuck is $2723.91",
              approx(dash.get("cash_stuck_usd"), 2723.91, 0.01), str(dash))
        check("nothing recovered yet", dash.get("cash_recovered_usd") == 0)

        print("== pricing ==")
        _, items = call("GET", "/api/items")
        case = next(i for i in items if "Phone Case" in i["name"])
        check("phone case AI price $8.07", approx(case["ai_price"], 8.07, 0.01),
              str(case))
        check("phone case discount 37.9%", approx(case["ai_discount_pct"], 37.9, 0.05),
              str(case))
        check("phone case dead score ~79.6", approx(case["dead_score"], 79.6, 0.5),
              str(case))
        check("phone case has a reason", bool(case.get("ai_reason")))
        check("no AI price below floor",
              all(i["ai_price"] >= i["floor_price"] for i in items))

        print("== add item ==")
        _, new_item = call("POST", "/api/items", {
            "name": "Test Ceramic Mug", "category": "Home",
            "original_price": 15.99, "cost_price": 5.00, "floor_price": 7.00,
            "qty": 5, "days_unsold": 100,
        })
        check("new item priced $11.93", approx(new_item["ai_price"], 11.93, 0.05),
              str(new_item))
        _, items = call("GET", "/api/items")
        check("9 items after add", len(items) == 9)
        _, repriced = call("POST", f"/api/items/{new_item['id']}/reprice", {})
        check("re-price works", approx(repriced["ai_price"], 11.93, 0.05))

        print("== storefront ==")
        _, storefront = call("GET", "/api/storefront")
        check("storefront lists 9", len(storefront) == 9)

        print("== negotiation: hold, counter, accept ==")
        _, deal = call("POST", "/api/deals",
                       {"item_id": case["id"], "buyer_name": "Test Buyer"})
        deal_id = deal["deal_id"]
        check("deal created", isinstance(deal_id, int))
        _, detail = call("GET", f"/api/deals/{deal_id}")
        check("agent greets the buyer",
              any(m["sender"] == "agent" for m in detail["messages"]))

        _, r1 = call("POST", f"/api/deals/{deal_id}/offer", {"offer": 4.00})
        check("offer below floor -> hold", r1["action"] == "hold", str(r1))
        check("still negotiating after hold", r1["status"] == "negotiating")
        check("ask unchanged at $8.07", approx(r1["ask_price"], 8.07, 0.01))

        _, r2 = call("POST", f"/api/deals/{deal_id}/offer", {"offer": 7.00})
        check("fair offer -> counter", r2["action"] == "counter", str(r2))
        check("counter is midpoint $7.54", approx(r2["ask_price"], 7.54, 0.01),
              str(r2))

        _, r3 = call("POST", f"/api/deals/{deal_id}/offer", {"offer": 8.50})
        check("offer above ask -> accept", r3["action"] == "accept", str(r3))
        check("agreed price $8.50", approx(r3["agreed_price"], 8.50, 0.01))
        check("deal accepted", r3["status"] == "accepted")

        print("== PayPal simulator: create, approve, capture ==")
        _, pay = call("POST", f"/api/deals/{deal_id}/pay", {})
        check("order created", str(pay.get("order_id", "")).startswith("SIM-ORDER-"),
              str(pay))
        check("order mode is simulator", pay.get("mode") == "simulator")
        check("approve URL present", bool(pay.get("approve_url")))

        _, appr = call("POST", f"/api/deals/{deal_id}/approve", {})
        check("order approved", appr.get("status") == "approved", str(appr))

        _, cap = call("POST", f"/api/deals/{deal_id}/capture", {})
        check("payment captured", cap.get("status") == "captured", str(cap))
        check("capture id looks right",
              str(cap.get("capture_id", "")).startswith("SIM-CAPTURE-"), str(cap))
        check("captured amount $8.50", approx(cap.get("amount"), 8.50, 0.01))

        _, dash = call("GET", "/api/dashboard")
        check("recovered is $8.50", approx(dash.get("cash_recovered_usd"), 8.50, 0.01),
              str(dash))
        check("1 item sold", dash.get("items_sold") == 1)
        _, items = call("GET", "/api/items")
        case = next(i for i in items if "Phone Case" in i["name"])
        check("phone case marked sold", case["status"] == "sold")

        print("== negotiation: walk away below floor ==")
        buds = next(i for i in items if "Earbuds" in i["name"])
        _, deal2 = call("POST", "/api/deals",
                        {"item_id": buds["id"], "buyer_name": "Lowball Buyer"})
        d2 = deal2["deal_id"]
        _, w1 = call("POST", f"/api/deals/{d2}/offer", {"offer": 5.00})
        check("first below-floor offer -> hold", w1["action"] == "hold", str(w1))
        _, w2 = call("POST", f"/api/deals/{d2}/offer", {"offer": 5.50})
        check("second below-floor offer -> walk away",
              w2["action"] == "walk_away", str(w2))
        check("deal walked away", w2["status"] == "walked_away")
        status, _ = call("POST", f"/api/deals/{d2}/pay", {}, expect_error=True)
        check("cannot pay a walked-away deal", status == 400, f"got {status}")

        print("== guards: capture needs approval ==")
        kurti = next(i for i in items if "Kurti" in i["name"])
        _, deal3 = call("POST", "/api/deals",
                        {"item_id": kurti["id"], "buyer_name": "Quick Buyer"})
        d3 = deal3["deal_id"]
        _, a3 = call("POST", f"/api/deals/{d3}/offer",
                     {"offer": kurti["ai_price"]})
        check("offer at ask accepted", a3["action"] == "accept", str(a3))
        _, pay3 = call("POST", f"/api/deals/{d3}/pay", {})
        check("second order created", str(pay3.get("order_id", "")).startswith("SIM-ORDER-"))
        status, _ = call("POST", f"/api/deals/{d3}/capture", {}, expect_error=True)
        check("capture before approval rejected", status == 400, f"got {status}")
        _, _ = call("POST", f"/api/deals/{d3}/approve", {})
        _, cap3 = call("POST", f"/api/deals/{d3}/capture", {})
        check("second capture works", cap3.get("status") == "captured", str(cap3))
        _, dash = call("GET", "/api/dashboard")
        expected = 8.50 + kurti["ai_price"]
        check(f"recovered is now ${expected:.2f}",
              approx(dash.get("cash_recovered_usd"), expected, 0.01), str(dash))

        print(f"\n{PASS} passed, {FAIL} failed")
        if FAILURES:
            print("Failed checks:", ", ".join(FAILURES))
        return 1 if FAIL else 0
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def run_sandbox_error_path():
    """Phase 2: boot in sandbox mode WITHOUT keys and verify the app
    fails cleanly (502 JSON, server stays alive) instead of dropping
    the connection. This is the regression test for the fixed
    _access_token attribute/method collision."""
    global BASE
    db = "/tmp/shelfclear_test_sandbox.db"
    if os.path.exists(db):
        os.remove(db)
    env = dict(os.environ)
    env["SHELFCLEAR_DB"] = db
    env["PORT"] = "8472"
    env["PAYPAL_MODE"] = "sandbox"
    env.pop("PAYPAL_CLIENT_ID", None)
    env.pop("PAYPAL_CLIENT_SECRET", None)
    proc = subprocess.Popen(
        [sys.executable, "app.py"], cwd=WORKDIR, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    old_base = BASE
    BASE = "http://127.0.0.1:8472"
    try:
        up = False
        for _ in range(50):
            try:
                call("GET", "/api/mode")
                up = True
                break
            except Exception:
                time.sleep(0.2)
        check("sandbox server starts", up)
        if not up:
            return 1
        print("== sandbox mode, no keys ==")
        _, mode = call("GET", "/api/mode")
        check("mode is sandbox", mode.get("mode") == "sandbox", str(mode))
        _, deal = call("POST", "/api/deals",
                       {"item_id": 1, "buyer_name": "Sandbox Buyer"})
        d = deal["deal_id"]
        _, acc = call("POST", f"/api/deals/{d}/offer", {"offer": 19.49})
        check("offer accepted in sandbox mode", acc["action"] == "accept")
        status, err = call("POST", f"/api/deals/{d}/pay", {}, expect_error=True)
        check("pay without keys -> clean 502", status == 502, f"got {status}: {err}")
        check("502 names the missing keys",
              "PAYPAL_CLIENT_ID" in str(err.get("error", "")), str(err))
        _, dash = call("GET", "/api/dashboard")
        check("server still alive after failed pay", dash.get("items_listed") == 8)
        return 0
    finally:
        BASE = old_base
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    code = main()
    print("\n-- phase 2: sandbox error path --")
    code |= run_sandbox_error_path()
    print(f"\nTOTAL: {PASS} passed, {FAIL} failed")
    if FAILURES:
        print("Failed checks:", ", ".join(FAILURES))
    sys.exit(1 if code or FAIL else 0)
