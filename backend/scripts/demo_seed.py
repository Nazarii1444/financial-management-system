"""
Demo user with realistic Ukrainian data — for manual testing and screenshots.
Everything goes through the public API, so balance, analytics and the security
log fill in the same way they would for a real person (unlike scripts/seed.py,
which writes straight to the database).

    python -m scripts.demo_seed                      # against http://localhost:8000
    python -m scripts.demo_seed --host https://...   # any running server

Log in afterwards as olena.demo@example.com / Kavunova-Hata-2026!

Creates (idempotent per run on an empty DB):
  * olena.demo@example.com — a year of transactions in UAH, recurring payments,
    templates, a template suggestion (coffee), goals, personal + family budget,
    a receipt recognised from a real photo, two items in the trash, calendar feed;
  * andriy.demo@example.com — member of the family budget.
"""
import argparse
import csv
import io
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

DEMO = dict(username="olena_k", email="olena.demo@example.com", password="Kavunova-Hata-2026!")
PARTNER = dict(username="andriy_k", email="andriy.demo@example.com", password="Smerekova-Khata-77!")
RECEIPT = Path(__file__).resolve().parents[1] / "tests/files/fixtures/receipt_mcdonalds_ua.jpg"

EXPENSES = [  # name, category, tags, min, max, times per month
    ("Сільпо", "food", ["продукти"], 250, 1600, 6),
    ("АТБ", "food", ["продукти"], 120, 800, 5),
    ("Обід у Пузатій Хаті", "food", ["обід"], 160, 240, 4),
    ("Метро", "transportation", ["проїзд"], 8, 8, 10),
    ("Uklon", "transportation", ["таксі"], 110, 380, 3),
    ("WOG", "car", ["пальне"], 900, 2000, 2),
    ("Аптека АНЦ", "health", ["аптека"], 90, 700, 1),
    ("Rozetka", "electronics", ["онлайн"], 400, 6000, 0.5),
    ("Zara", "clothing", ["одяг"], 900, 3200, 0.5),
    ("Епіцентр", "home", ["дім"], 300, 2500, 0.7),
    ("Комуналка", "utilities", ["рахунки"], 1800, 3400, 1),
    ("Кінотеатр Multiplex", "entertainment", ["кіно"], 200, 480, 1),
    ("Нова Пошта", "shopping", ["доставка"], 70, 220, 2),
    ("Ветклініка", "pets", ["кіт"], 350, 1200, 0.3),
]


def csv_bytes(rows):
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=["name", "amount", "kind", "category_name", "currency", "date", "tags", "note"])
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue().encode("utf-8")


def row(name, amount, kind, category, when, tags=(), note=""):
    return {"name": name, "amount": f"{amount:.2f}", "kind": kind, "category_name": category, "currency": "UAH",
            "date": when.replace(microsecond=0).isoformat(), "tags": "|".join(tags), "note": note}


def history(now: datetime) -> list[dict]:
    rng = random.Random(2026)
    rows = []
    for m in range(12):
        month_start = (now.replace(day=1) - timedelta(days=31 * m)).replace(day=1, hour=10)
        days = (now - month_start).days if m == 0 else 28
        if days <= 0:
            continue
        if m:  # salary for past months; this month's salary is still upcoming (recurring rule)
            rows.append(row("Зарплата", rng.uniform(40500, 42000), "INCOME", "salary", month_start + timedelta(days=24), ["робота"]))
            rows.append(row("Оренда квартири", 15000, "EXPENSE", "housing", month_start + timedelta(days=14), ["житло"]))
            rows.append(row("Netflix", 250, "EXPENSE", "entertainment", month_start + timedelta(days=19), ["підписка"]))
            rows.append(row("Київстар", 250, "EXPENSE", "phone", month_start + timedelta(days=24), ["зв'язок"]))
        if rng.random() < 0.35:
            rows.append(row("Фриланс: лендінг", rng.uniform(6000, 18000), "INCOME", "freelance",
                            month_start + timedelta(days=rng.randint(1, days)), ["upwork"]))
        for name, cat, tags, lo, hi, per_month in EXPENSES:
            n = int(per_month * days / 28 + rng.random())
            for _ in range(n):
                when = month_start + timedelta(days=rng.uniform(0, days), hours=rng.uniform(0, 10))
                if when > now:
                    continue
                rows.append(row(name, rng.uniform(lo, hi) if lo != hi else lo, "EXPENSE", cat, when, tags,
                                rng.choice(["", "", "", "з друзями", "знижка"])))
    # ~ daily coffee in the last month → the template suggestion on the dashboard
    for d in (1, 3, 4, 6, 8, 10, 13, 15, 17, 20, 22, 24, 27):
        rows.append(row("Кава Aroma Kava", rng.choice([70, 70, 70, 75]), "EXPENSE", "food",
                        now - timedelta(days=d, hours=rng.uniform(0, 3)), ["кава"]))
    return rows


class Api:
    def __init__(self, host):
        self.c = httpx.Client(base_url=host, timeout=300)

    def call(self, method, path, **kw):
        r = self.c.request(method, path, **kw)
        if r.status_code >= 400:
            raise SystemExit(f"{method} {path} -> {r.status_code}: {r.text[:400]}")
        return r.json() if r.content and "json" in r.headers.get("content-type", "") else None

    def signup(self, user):
        r = self.c.post("/api/auth/signup", json=user)
        if r.status_code == 400 and "already" in r.text:
            r = self.c.post("/api/auth/login", json={"email": user["email"], "password": user["password"]})
        r.raise_for_status()
        self.c.headers["Authorization"] = f"Bearer {r.json()['access_token']}"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="http://localhost:8000")
    host = p.parse_args().host
    now = datetime.now(timezone.utc)

    partner = Api(host)
    partner.signup(PARTNER)
    partner.call("PATCH", "/api/settings/currency", json={"default_currency": "UAH"})
    partner.call("POST", "/api/transactions/import", files={"file": ("p.csv", csv_bytes([
        row("Сільпо", 1840.50, "EXPENSE", "food", now - timedelta(days=2), ["продукти"]),
        row("Дитячий садок", 3200, "EXPENSE", "kids", now - timedelta(days=6), ["діти"]),
        row("WOG", 1650, "EXPENSE", "car", now - timedelta(days=4), ["пальне"]),
    ]), "text/csv")})

    api = Api(host)
    httpx.post(f"{host}/api/auth/login", json={"email": DEMO["email"], "password": "wrong-password-1"})  # failed attempt for the log
    api.signup(DEMO)
    api.call("PATCH", "/api/settings/currency", json={"default_currency": "UAH"})
    api.call("PATCH", "/api/settings/profile", json={"timezone": "Europe/Kyiv"})
    api.call("PATCH", "/api/settings/notifications", json={"language": "uk"})

    res = api.call("POST", "/api/transactions/import", files={"file": ("history.csv", csv_bytes(history(now)), "text/csv")})
    print(f"history: imported {res['imported']}, skipped {res['skipped']} {res['errors'][:2]}")

    def next_day(day):  # next occurrence of a day-of-month, at 09:00 UTC
        d = now.replace(day=day, hour=9, minute=0, second=0, microsecond=0)
        return d if d > now else (d.replace(day=1) + timedelta(days=32)).replace(day=day)

    for name, kind, cat, amount, freq, day in [
        ("Оренда квартири", 0, "housing", 15000, "MONTHLY", 15), ("Netflix", 0, "entertainment", 250, "MONTHLY", 20),
        ("Київстар", 0, "phone", 250, "MONTHLY", 25), ("Спортзал", 0, "sports", 900, "MONTHLY", 1),
        ("Зарплата", 1, "salary", 45500, "MONTHLY", 25),
    ]:
        api.call("POST", "/api/transactions/recurring", json={
            "name": name, "kind": kind, "category_name": cat, "amount": amount, "currency": "UAH",
            "frequency": freq, "first_run": next_day(day).isoformat()})

    for name, amount, cat in [("Метро", 8, "transportation"), ("Обід у Пузатій Хаті", 190, "food"), ("Сільпо", 600, "food")]:
        api.call("POST", "/api/templates", json={"name": name, "amount": amount, "kind": 0, "category_name": cat, "currency": "UAH"})

    for name, target, saved, months, desc in [
        ("Відпустка в Карпатах", 30000, 12500, 5, "Тиждень у Яремчі влітку"),
        ("Новий ноутбук", 60000, 21000, 8, "MacBook для роботи"),
        ("Резервний фонд", 20000, 20000, 0, "Три місяці базових витрат"),
    ]:
        goal = api.call("POST", "/api/goals", json={
            "name": name, "target_amount": target, "currency": "UAH", "description": desc,
            "deadline": (now + timedelta(days=30 * months)).isoformat() if months else None})
        api.call("POST", f"/api/goals/{goal['id_']}/deposit", json={"amount": saved})

    api.call("POST", "/api/budgets", json={"name": "Особисті витрати", "type": "PERSONAL", "currency": "UAH", "limit_amount": 9300})
    family = api.call("POST", "/api/budgets", json={"name": "Сімейний бюджет", "type": "FAMILY", "currency": "UAH", "limit_amount": 40000})
    api.call("POST", f"/api/budgets/{family['id_']}/members", json={"email": PARTNER["email"], "role": "EDITOR"})

    receipt = api.call("POST", "/api/files/receipts", params={"auto_create": "true"},
                       files={"file": (RECEIPT.name, RECEIPT.read_bytes(), "image/jpeg")})
    print("receipt:", receipt.get("ocr_result", {}).get("suggested_amount"), receipt.get("transaction_id"))

    for name, amount in [("Таксі Uklon (дубль)", 245), ("Тестова покупка", 99)]:
        tx = api.call("POST", "/api/transactions", json={"name": name, "amount": amount, "kind": 0,
                                                         "category_name": "transportation" if "Uklon" in name else "shopping",
                                                         "currency": "UAH"})
        api.call("DELETE", f"/api/transactions/{tx['id_']}")

    api.call("POST", "/api/calendar/feed")
    me = api.call("GET", "/api/users/me")
    print(f"done: {DEMO['email']} / {DEMO['password']} — balance {me['capital']:.2f} {me['default_currency']}")


if __name__ == "__main__":
    main()
