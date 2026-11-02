"""SQLite storage for ShelfClear.

Tables:
  items    - dead-stock items added by the seller
  deals    - one negotiation per buyer per item
  messages - chat history inside a deal
  payments - PayPal orders/captures (real sandbox or simulator)
"""
import json
import os
import sqlite3
import threading

DB_PATH = os.environ.get("SHELFCLEAR_DB") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data.db"
)

_LOCK = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    original_price REAL NOT NULL,
    cost_price REAL NOT NULL,
    floor_price REAL NOT NULL,
    qty INTEGER NOT NULL,
    days_unsold INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'listed',
    ai_price REAL,
    ai_discount_pct REAL,
    dead_score REAL,
    ai_reason TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS deals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL REFERENCES items(id),
    buyer_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'negotiating',
    agreed_price REAL,
    ask_price REAL NOT NULL,
    counters INTEGER NOT NULL DEFAULT 0,
    below_floor_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    deal_id INTEGER NOT NULL REFERENCES deals(id),
    sender TEXT NOT NULL,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    deal_id INTEGER NOT NULL REFERENCES deals(id),
    mode TEXT NOT NULL,
    paypal_order_id TEXT,
    status TEXT NOT NULL DEFAULT 'created',
    amount REAL NOT NULL,
    currency TEXT NOT NULL DEFAULT 'USD',
    capture_id TEXT,
    raw TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _LOCK:
        conn = connect()
        try:
            conn.executescript(SCHEMA)
            conn.commit()
        finally:
            conn.close()


def _row_to_dict(row):
    return dict(row) if row is not None else None


def add_item(name, category, original_price, cost_price, floor_price, qty, days_unsold):
    with _LOCK:
        conn = connect()
        try:
            cur = conn.execute(
                "INSERT INTO items (name, category, original_price, cost_price,"
                " floor_price, qty, days_unsold) VALUES (?,?,?,?,?,?,?)",
                (name, category, original_price, cost_price, floor_price, qty, days_unsold),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()


def get_item(item_id):
    conn = connect()
    try:
        return _row_to_dict(
            conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
        )
    finally:
        conn.close()


def list_items(status=None):
    conn = connect()
    try:
        if status:
            rows = conn.execute(
                "SELECT * FROM items WHERE status = ? ORDER BY id", (status,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM items ORDER BY id").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_item_pricing(item_id, ai_price, discount_pct, dead_score, reason):
    with _LOCK:
        conn = connect()
        try:
            conn.execute(
                "UPDATE items SET ai_price=?, ai_discount_pct=?, dead_score=?,"
                " ai_reason=? WHERE id=?",
                (ai_price, discount_pct, dead_score, reason, item_id),
            )
            conn.commit()
        finally:
            conn.close()


def mark_item_sold(item_id):
    with _LOCK:
        conn = connect()
        try:
            conn.execute("UPDATE items SET status='sold' WHERE id=?", (item_id,))
            conn.commit()
        finally:
            conn.close()


def create_deal(item_id, buyer_name, ask_price):
    with _LOCK:
        conn = connect()
        try:
            cur = conn.execute(
                "INSERT INTO deals (item_id, buyer_name, ask_price) VALUES (?,?,?)",
                (item_id, buyer_name, ask_price),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()


def get_deal(deal_id):
    conn = connect()
    try:
        return _row_to_dict(
            conn.execute("SELECT * FROM deals WHERE id = ?", (deal_id,)).fetchone()
        )
    finally:
        conn.close()


def list_deals():
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT d.*, i.name AS item_name FROM deals d"
            " JOIN items i ON i.id = d.item_id ORDER BY d.id DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_deal(deal_id, **fields):
    allowed = {"status", "agreed_price", "ask_price", "counters", "below_floor_count"}
    sets = ", ".join(f"{k}=?" for k in fields if k in allowed)
    vals = [fields[k] for k in fields if k in allowed]
    if not sets:
        return
    with _LOCK:
        conn = connect()
        try:
            conn.execute(f"UPDATE deals SET {sets} WHERE id=?", (*vals, deal_id))
            conn.commit()
        finally:
            conn.close()


def add_message(deal_id, sender, text):
    with _LOCK:
        conn = connect()
        try:
            conn.execute(
                "INSERT INTO messages (deal_id, sender, text) VALUES (?,?,?)",
                (deal_id, sender, text),
            )
            conn.commit()
        finally:
            conn.close()


def list_messages(deal_id):
    conn = connect()
    try:
        rows = conn.execute(
            "SELECT sender, text, created_at FROM messages"
            " WHERE deal_id=? ORDER BY id",
            (deal_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def add_payment(deal_id, mode, amount, paypal_order_id, status, raw):
    with _LOCK:
        conn = connect()
        try:
            cur = conn.execute(
                "INSERT INTO payments (deal_id, mode, amount, paypal_order_id,"
                " status, raw) VALUES (?,?,?,?,?,?)",
                (deal_id, mode, amount, paypal_order_id, status, json.dumps(raw)),
            )
            conn.commit()
            return cur.lastrowid
        finally:
            conn.close()


def get_payment_by_deal(deal_id):
    conn = connect()
    try:
        return _row_to_dict(
            conn.execute(
                "SELECT * FROM payments WHERE deal_id=? ORDER BY id DESC LIMIT 1",
                (deal_id,),
            ).fetchone()
        )
    finally:
        conn.close()


def update_payment(payment_id, **fields):
    allowed = {"status", "capture_id", "raw"}
    sets = ", ".join(f"{k}=?" for k in fields if k in allowed)
    vals = [fields[k] for k in fields if k in allowed]
    if fields.get("raw") is not None and not isinstance(fields.get("raw"), str):
        vals = [
            json.dumps(v) if k == "raw" else v
            for k, v in fields.items()
            if k in allowed
        ]
    if not sets:
        return
    with _LOCK:
        conn = connect()
        try:
            conn.execute(f"UPDATE payments SET {sets} WHERE id=?", (*vals, payment_id))
            conn.commit()
        finally:
            conn.close()


def dashboard_totals():
    conn = connect()
    try:
        stuck = conn.execute(
            "SELECT COALESCE(SUM(original_price * qty), 0) FROM items"
            " WHERE status='listed'"
        ).fetchone()[0]
        stuck_cost = conn.execute(
            "SELECT COALESCE(SUM(cost_price * qty), 0) FROM items"
            " WHERE status='listed'"
        ).fetchone()[0]
        recovered = conn.execute(
            "SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status='captured'"
        ).fetchone()[0]
        sold = conn.execute(
            "SELECT COUNT(*) FROM items WHERE status='sold'"
        ).fetchone()[0]
        listed = conn.execute(
            "SELECT COUNT(*) FROM items WHERE status='listed'"
        ).fetchone()[0]
        active_deals = conn.execute(
            "SELECT COUNT(*) FROM deals WHERE status='negotiating'"
        ).fetchone()[0]
        return {
            "cash_stuck_usd": round(float(stuck), 2),
            "cost_stuck_usd": round(float(stuck_cost), 2),
            "cash_recovered_usd": round(float(recovered), 2),
            "items_sold": int(sold),
            "items_listed": int(listed),
            "active_deals": int(active_deals),
        }
    finally:
        conn.close()
