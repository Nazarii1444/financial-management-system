"""Shared settings for the load-test harness (seed / locustfile / run)."""
import os

import requests

DEFAULT_HOST = os.getenv("LOADTEST_HOST", "http://127.0.0.1:8002")

# Dedicated benchmark account — test values only, never a real user.
LOADTEST_EMAIL = os.getenv("LOADTEST_EMAIL", "loadtest-bench@example.com")
LOADTEST_USERNAME = os.getenv("LOADTEST_USERNAME", "loadtest_bench")
LOADTEST_PASSWORD = os.getenv("LOADTEST_PASSWORD", "Bench#Load2026!x7Q")

# Names used to find seeded objects again (seed.py creates them, locustfile reads them).
SEED_BUDGET_NAME = "LT budget"
SEED_GOAL_NAMES = ("LT laptop", "LT vacation")
SEED_TEMPLATE_NAMES = ("LT coffee", "LT metro", "LT lunch")
# Objects created by write tasks carry this prefix, so leftovers are easy to spot / clean.
TEMP_PREFIX = "lt-tmp"


def login(host: str, email: str = LOADTEST_EMAIL, password: str = LOADTEST_PASSWORD) -> str | None:
    """Access token, or None when the credentials are rejected."""
    r = requests.post(f"{host}/api/auth/login", json={"email": email, "password": password}, timeout=30)
    if r.status_code == 401 or r.status_code == 400:
        return None
    r.raise_for_status()
    body = r.json()
    if body.get("requires_2fa"):
        raise SystemExit("Load-test user has 2FA enabled — disable it or use another account")
    return body["access_token"]


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
