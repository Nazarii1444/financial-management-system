# import os
# import sys
import time

import uvicorn

# sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi_utilities import repeat_every
from starlette.middleware.sessions import SessionMiddleware

from src.health.routers import health_router
from src.auth.auth_router import auth_router
from src.transactions.transaction_router import transaction_router
from src.for_testing.dev_router import dev_router
from src.users.users_router import users_router
from src.currencies.currency_router import currency_router, register_currency_cron
from src.goals.goal_router import goal_router
from src.google_oauth.google_router import google_oauth_router
from src.github_oauth.github_oauth import github_oauth_router
from src.two_fa.two_fa_router import two_fa_router
from src.budgets.budget_router import budget_router
from src.transactions.recurring_router import recurring_router, register_recurring_cron
from src.transactions.import_router import import_router
from src.analytics.analytics_router import analytics_router
from src.settings.settings_router import settings_router
from src.files.file_router import file_router

from src.database import get_db
from src.config import origins

app = FastAPI(title="Financial API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
register_currency_cron(app)
register_recurring_cron(app)

@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.perf_counter()
    response = await call_next(request)
    process_time = time.perf_counter() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    return response

app.add_middleware(SessionMiddleware, secret_key="super-session-secret")

app.include_router(health_router, prefix="/health", tags=["Health Check"])
app.include_router(auth_router, prefix="/api/auth", tags=["Auth"])
app.include_router(transaction_router, prefix="/api/transactions", tags=["Transactions"])
app.include_router(recurring_router, prefix="/api/transactions/recurring", tags=["Recurring Transactions"])
app.include_router(import_router, prefix="/api/transactions/import", tags=["Import"])
app.include_router(dev_router, prefix="/api/dev")
app.include_router(users_router, prefix="/api/users", tags=["Users"])
app.include_router(currency_router, prefix="/api/currencies", tags=["Currencies"])
app.include_router(google_oauth_router, prefix="/api", tags=["Google OAuth"])
app.include_router(github_oauth_router, prefix="/api", tags=["Github OAuth"])
app.include_router(goal_router, prefix="/api/goals", tags=["Goals"])
app.include_router(two_fa_router, prefix="/api/2fa", tags=["2FA"])
app.include_router(budget_router, prefix="/api/budgets", tags=["Budgets"])
app.include_router(analytics_router, prefix="/api/analytics", tags=["Analytics"])
app.include_router(settings_router, prefix="/api/settings", tags=["Settings"])
app.include_router(file_router, prefix="/api/files", tags=["Files"])

if __name__ == '__main__':
    get_db()
    uvicorn.run("src.app:app", host="127.0.0.1", port=8000, reload=True, workers=4)
