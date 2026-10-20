"""Locust scenarios for the API.

Two user classes share one registry of endpoint tasks:

* `EndpointUser` — every task is tagged with its endpoint name and its group
  (`read` / `write` / `heavy`), so `--tags tx_list` measures exactly one endpoint.
  `run.py` launches it once per endpoint.
* `MixedUser` — all read/write tasks at once with realistic weights (`mix=`).

Write tasks are create+delete pairs (or symmetric pairs like deposit+withdraw),
so the dataset stays the same size between runs. `heavy` tasks (login/bcrypt,
PDF reports, receipt OCR) only run when asked for explicitly.

Auth: one login per test (outside the stats), the Bearer token is shared.
External services (Google/GitHub OAuth, NBU refresh, Google Calendar) are not touched.
"""
import os
import random
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

import requests
from locust import HttpUser, between, constant, events, tag

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from loadtest.common import (  # noqa: E402
    LOADTEST_EMAIL, LOADTEST_PASSWORD, SEED_BUDGET_NAME, SEED_GOAL_NAMES,
    SEED_TEMPLATE_NAMES, TEMP_PREFIX, auth_headers, login,
)

RECEIPT_FIXTURE = Path(__file__).resolve().parent.parent / "tests" / "files" / "fixtures" / "receipt_mcdonalds_ua.jpg"


class Ctx:
    """Filled once in test_start: token + ids of seeded objects."""
    token: str = ""
    tx_ids: list[int] = []
    budget_id: int = 0
    goal_id: int = 0
    template_id: int = 0


@events.test_start.add_listener
def _prepare(environment, **_):
    host = environment.host
    token = login(host, LOADTEST_EMAIL, LOADTEST_PASSWORD)
    if not token:
        raise SystemExit("Cannot log in as the load-test user — run `python -m loadtest.seed` first")
    h = auth_headers(token)

    def get(path, **params):
        r = requests.get(f"{host}{path}", headers=h, params=params, timeout=60)
        r.raise_for_status()
        return r.json()

    Ctx.token = token
    Ctx.tx_ids = [t["id_"] for t in get("/api/transactions", limit=1000)]
    Ctx.budget_id = next(b["id_"] for b in get("/api/budgets") if b["name"] == SEED_BUDGET_NAME)
    Ctx.goal_id = next(g["id_"] for g in get("/api/goals") if g["name"] == SEED_GOAL_NAMES[0])
    Ctx.template_id = next(t["id_"] for t in get("/api/templates") if t["name"] == SEED_TEMPLATE_NAMES[0])
    if not Ctx.tx_ids:
        raise SystemExit("Load-test user has no transactions — run `python -m loadtest.seed`")


# ── Endpoint registry ─────────────────────────────────────────────────────────

@dataclass
class Endpoint:
    name: str
    group: str  # read | write | heavy
    mix: int    # weight in MixedUser; 0 = not part of the mixed scenario
    fn: Callable


ENDPOINTS: dict[str, Endpoint] = {}


def endpoint(group: str, mix: int = 0):
    def deco(fn):
        ENDPOINTS[fn.__name__] = Endpoint(fn.__name__, group, mix, fn)
        return fn
    return deco


def _ok(resp, *codes):
    """Mark the request failed unless the status is one of `codes`; returns JSON or None."""
    if resp.status_code not in codes:
        resp.failure(f"HTTP {resp.status_code}: {resp.text[:200]}")
        return None
    resp.success()
    try:
        return resp.json()
    except ValueError:
        return None


def _get(u, path, name=None, **params):
    with u.client.get(path, params=params or None, name=name or path, catch_response=True) as r:
        return _ok(r, 200)


def _month_ago():
    return (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()


# ── read ──────────────────────────────────────────────────────────────────────

@endpoint("read", mix=1)
def health(u): _get(u, "/health/")
@endpoint("read", mix=3)
def users_me(u): _get(u, "/api/users/me")
@endpoint("read", mix=1)
def settings_profile(u): _get(u, "/api/settings/profile")
@endpoint("read", mix=1)
def settings_notifications(u): _get(u, "/api/settings/notifications")
@endpoint("read", mix=1)
def settings_subscription(u): _get(u, "/api/settings/subscription")
@endpoint("read", mix=2)
def currencies_list(u): _get(u, "/api/currencies")
@endpoint("read", mix=1)
def tx_categories(u): _get(u, "/api/transactions/categories/list")
@endpoint("read", mix=10)
def tx_list(u): _get(u, "/api/transactions", limit=50)
@endpoint("read", mix=3)
def tx_list_filtered(u):
    _get(u, "/api/transactions", name="/api/transactions?kind&category&date_from",
         limit=50, kind="EXPENSE", category="food", date_from=_month_ago())
@endpoint("read", mix=4)
def tx_get(u):
    _get(u, f"/api/transactions/{random.choice(Ctx.tx_ids)}", name="/api/transactions/{id}")
@endpoint("read", mix=4)
def tx_search_text(u):
    _get(u, "/api/transactions/search", name="/api/transactions/search?q",
         q=random.choice(["сільпо", "кава", "uber", "netflix", "аптека", "ghjv"]), limit=50)
@endpoint("read", mix=3)
def tx_search_filtered(u):
    _get(u, "/api/transactions/search", name="/api/transactions/search?filters",
         kind="EXPENSE", amount_min=100, amount_max=2000, date_from=_month_ago(), limit=50)
@endpoint("read", mix=1)
def trash_list(u): _get(u, "/api/transactions/trash")
@endpoint("read", mix=2)
def recurring_list(u): _get(u, "/api/transactions/recurring")
@endpoint("read", mix=2)
def templates_list(u): _get(u, "/api/templates")
@endpoint("read", mix=2)
def templates_suggestions(u): _get(u, "/api/templates/suggestions")
@endpoint("read", mix=2)
def goals_list(u): _get(u, "/api/goals")
@endpoint("read", mix=2)
def budgets_list(u): _get(u, "/api/budgets")
@endpoint("read", mix=6)
def analytics_overview(u): _get(u, "/api/analytics/overview")
@endpoint("read", mix=3)
def analytics_trends_monthly(u): _get(u, "/api/analytics/trends/monthly", months=12)
@endpoint("read", mix=1)
def analytics_trends_yearly(u): _get(u, "/api/analytics/trends/yearly", years=3)
@endpoint("read", mix=2)
def analytics_comparison(u): _get(u, "/api/analytics/comparison/period", mode="monthly")
@endpoint("read", mix=3)
def analytics_categories(u): _get(u, "/api/analytics/breakdown/categories", kind="EXPENSE")
@endpoint("read", mix=1)
def analytics_tags(u): _get(u, "/api/analytics/breakdown/tags", kind="EXPENSE")
@endpoint("read", mix=6)
def analytics_safe_to_spend(u): _get(u, "/api/analytics/safe-to-spend")
@endpoint("read", mix=1)
def analytics_budget(u):
    _get(u, f"/api/analytics/budgets/{Ctx.budget_id}", name="/api/analytics/budgets/{id}")
@endpoint("read", mix=1)
def export_recurring_json(u): _get(u, "/api/exports/reports/recurring")
@endpoint("read", mix=1)
def export_csv(u): _get(u, "/api/exports/transactions.csv", lang="uk")
@endpoint("read", mix=1)
def calendar_ics(u): _get(u, "/api/calendar/recurring.ics")


# ── write (state-neutral pairs) ───────────────────────────────────────────────

def _delete_tx_and_purge(u, tx_id):
    with u.client.delete(f"/api/transactions/{tx_id}", name="/api/transactions/{id}",
                         catch_response=True) as r:
        body = _ok(r, 200)
    if body:
        with u.client.delete(f"/api/transactions/trash/{body['trash_id']}",
                             name="/api/transactions/trash/{id}", catch_response=True) as r:
            _ok(r, 204)


@endpoint("write", mix=3)
def tx_create_delete(u):
    with u.client.post("/api/transactions", name="/api/transactions", catch_response=True, json={
        "name": f"{TEMP_PREFIX} coffee", "amount": "75.00", "kind": 0,
        "category_name": "food", "tags": ["loadtest"],
    }) as r:
        body = _ok(r, 201)
    if body:
        _delete_tx_and_purge(u, body["id_"])


@endpoint("write", mix=2)
def tx_update(u):
    # note only: does not change amount/kind/currency, so the balance stays put
    with u.client.patch(f"/api/transactions/{random.choice(Ctx.tx_ids)}", name="/api/transactions/{id}",
                        json={"note": random.choice(["з друзями", "знижка", "lt"])}, catch_response=True) as r:
        _ok(r, 200)


@endpoint("write", mix=1)
def recurring_create_delete(u):
    with u.client.post("/api/transactions/recurring", name="/api/transactions/recurring",
                       catch_response=True, json={
                           "name": f"{TEMP_PREFIX} sub", "amount": "99", "kind": 0,
                           "category_name": "entertainment", "frequency": "MONTHLY",
                           # far ahead → the per-minute cron never fires it
                           "first_run": (datetime.now(timezone.utc) + timedelta(days=300)).isoformat(),
                       }) as r:
        body = _ok(r, 201)
    if body:
        with u.client.delete(f"/api/transactions/recurring/{body['id_']}",
                             name="/api/transactions/recurring/{id}", catch_response=True) as r:
            _ok(r, 204)


@endpoint("write", mix=1)
def template_create_delete(u):
    with u.client.post("/api/templates", name="/api/templates", catch_response=True, json={
        "name": f"{TEMP_PREFIX} tpl", "amount": "50", "kind": 0, "category_name": "food",
    }) as r:
        body = _ok(r, 201)
    if body:
        with u.client.delete(f"/api/templates/{body['id_']}", name="/api/templates/{id}",
                             catch_response=True) as r:
            _ok(r, 204)


@endpoint("write", mix=2)
def template_use(u):
    with u.client.post(f"/api/templates/{Ctx.template_id}/use", name="/api/templates/{id}/use",
                       json={}, catch_response=True) as r:
        body = _ok(r, 201)
    if body:
        _delete_tx_and_purge(u, body["id_"])


@endpoint("write", mix=1)
def goal_create_delete(u):
    with u.client.post("/api/goals", name="/api/goals", catch_response=True, json={
        "name": f"{TEMP_PREFIX} goal", "target_amount": "1000", "currency": "UAH",
    }) as r:
        body = _ok(r, 201)
    if body:
        with u.client.delete(f"/api/goals/{body['id_']}", name="/api/goals/{id}",
                             catch_response=True) as r:
            _ok(r, 204)


@endpoint("write", mix=1)
def goal_deposit_withdraw(u):
    for op in ("deposit", "withdraw"):
        with u.client.post(f"/api/goals/{Ctx.goal_id}/{op}", name=f"/api/goals/{{id}}/{op}",
                           json={"amount": "10"}, catch_response=True) as r:
            _ok(r, 200)


@endpoint("write", mix=1)
def budget_create_delete(u):
    with u.client.post("/api/budgets", name="/api/budgets", catch_response=True, json={
        "name": f"{TEMP_PREFIX} budget", "type": "PERSONAL", "currency": "UAH", "limit_amount": "1000",
    }) as r:
        body = _ok(r, 201)
    if body:
        with u.client.delete(f"/api/budgets/{body['id_']}", name="/api/budgets/{id}",
                             catch_response=True) as r:
            _ok(r, 204)


# ── heavy (opt-in: `run.py --groups heavy` or `--only auth_login`) ────────────

@endpoint("heavy")
def auth_login(u):
    # bcrypt is deliberately slow — measures password hashing, not the DB
    with u.client.post("/api/auth/login", name="/api/auth/login", catch_response=True,
                       json={"email": LOADTEST_EMAIL, "password": LOADTEST_PASSWORD}) as r:
        _ok(r, 200)
@endpoint("heavy")
def report_statement_pdf(u): _get(u, "/api/exports/reports/statement.pdf")
@endpoint("heavy")
def report_expenses_pdf(u): _get(u, "/api/exports/reports/expenses.pdf")
@endpoint("heavy")
def report_budgets_pdf(u): _get(u, "/api/exports/reports/budgets.pdf")
@endpoint("heavy")
def report_recurring_pdf(u): _get(u, "/api/exports/reports/recurring.pdf")


@endpoint("heavy")
def receipt_upload_delete(u):
    # Tesseract/OpenCV OCR: CPU-bound for seconds; use few users
    data = RECEIPT_FIXTURE.read_bytes()
    with u.client.post("/api/files/receipts", name="/api/files/receipts", catch_response=True,
                       files={"file": (RECEIPT_FIXTURE.name, data, "image/jpeg")}) as r:
        body = _ok(r, 201, 200)
    if body and body.get("id_"):
        with u.client.delete(f"/api/files/receipts/{body['id_']}", name="/api/files/receipts/{id}",
                             catch_response=True) as r:
            _ok(r, 204)


# ── User classes ──────────────────────────────────────────────────────────────

def _as_task(ep: Endpoint):
    def task(user):
        ep.fn(user)
    task.__name__ = ep.name
    return tag(ep.name, ep.group)(task)


# Think time between requests of one virtual user. 0 = closed-loop max throughput.
_WAIT = float(os.getenv("LOADTEST_WAIT", "0"))


class _Base(HttpUser):
    abstract = True
    wait_time = constant(_WAIT) if _WAIT == 0 else between(_WAIT / 2, _WAIT * 1.5)

    def on_start(self):
        self.client.headers.update(auth_headers(Ctx.token))


class EndpointUser(_Base):
    """Use with --tags <endpoint>; without tags it would hit everything uniformly."""
    tasks = [_as_task(ep) for ep in ENDPOINTS.values()]


class MixedUser(_Base):
    """Realistic blend: dashboard-heavy reads plus a few writes."""
    tasks = {_as_task(ep): ep.mix for ep in ENDPOINTS.values() if ep.mix > 0}
