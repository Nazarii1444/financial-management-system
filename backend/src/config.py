import os
import logging
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse
from dotenv import load_dotenv
from datetime import timedelta

# Load .env from the same directory as this file (src/)
load_dotenv(dotenv_path=Path(__file__).parent / ".env")

# "production" refuses weak secrets and hides the unauthenticated /api/dev routes
APP_ENV: str = os.getenv("APP_ENV", "development").strip().lower()
IS_PRODUCTION: bool = APP_ENV == "production"

SECRET_KEY: str = os.getenv("SECRET_KEY", "secret_key")
# Signs the OAuth session cookie (SessionMiddleware); falls back to SECRET_KEY
SESSION_SECRET: str = os.getenv("SESSION_SECRET") or SECRET_KEY
POSTGRES_USER: str = os.getenv("POSTGRES_USER", default="postgres")
POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", default="postgres")
DB_HOST: str = os.getenv("DB_HOST", default="127.0.0.1")
DB_PORT: int = os.getenv("DB_PORT", default=5432)
DB_NAME: str = os.getenv("DB_NAME", default="annadb")

def _asyncpg_url(url: str) -> str:
    """Turn a hosted-Postgres URL (Neon: postgresql://...?sslmode=require&channel_binding=require)
    into one SQLAlchemy's asyncpg driver accepts: asyncpg takes `ssl`, not `sslmode`/`channel_binding`."""
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query))
    query.pop("channel_binding", None)
    if "sslmode" in query:
        query["ssl"] = query.pop("sslmode")
    return urlunparse(parsed._replace(scheme="postgresql+asyncpg", query=urlencode(query)))


# A full connection string (hosted DBs such as Neon) wins over the separate DB_* settings
DATABASE_URL: str = (
    _asyncpg_url(os.environ["DATABASE_URL"]) if os.getenv("DATABASE_URL")
    else f"postgresql+asyncpg://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)

# Connection pool per worker process (SQLAlchemy default is 5 + 10 overflow).
# Keep workers × (size + overflow) below Postgres max_connections (100 by default): 4 × 20 = 80.
DB_POOL_SIZE: int = int(os.getenv("DB_POOL_SIZE", 15))
DB_MAX_OVERFLOW: int = int(os.getenv("DB_MAX_OVERFLOW", 5))
DB_POOL_TIMEOUT: int = int(os.getenv("DB_POOL_TIMEOUT", 30))

# Behind our own reverse proxy (nginx in docker-compose) the client address comes from
# X-Forwarded-For; never enable this when clients can reach the backend directly.
TRUST_PROXY_HEADERS: bool = os.getenv("TRUST_PROXY_HEADERS", "false").lower() in ("1", "true", "yes")

# Frontend base URL — used for OAuth redirects back to the SPA
FRONTEND_URL: str = os.getenv("FRONTEND_URL", "http://localhost:5173").rstrip("/")

origins = [
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
    FRONTEND_URL,
]

# ===== passkeys (WebAuthn) =====
# The RP id is the site's domain (no scheme / port; IP addresses are not allowed by browsers).
# Passkeys are bound to it: changing it later makes existing passkeys unusable.
WEBAUTHN_RP_ID: str = os.getenv("WEBAUTHN_RP_ID") or (urlparse(FRONTEND_URL).hostname or "localhost")
WEBAUTHN_RP_NAME: str = os.getenv("WEBAUTHN_RP_NAME", "FinanceHub")
# Exact origins the browser may report; default: every known frontend origin on the RP domain
_extra_origins = [o.strip() for o in os.getenv("WEBAUTHN_ORIGINS", "").split(",") if o.strip()]
WEBAUTHN_ORIGINS: list = [
    o.rstrip("/") for o in dict.fromkeys(_extra_origins + origins)
    if (urlparse(o).hostname or "") == WEBAUTHN_RP_ID or (urlparse(o).hostname or "").endswith("." + WEBAUTHN_RP_ID)
]

# ===== logging =====

logging.basicConfig(
    filename='logs.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)


# ===== secrets =====
# Defaults shipped in this repo (.env.example, docker-compose.yml) — fine locally, never in production
_PLACEHOLDER_SECRETS = {"secret_key", "change-me", "change-me-in-production", "super-session-secret"}
_MIN_SECRET_LEN = 32


def secret_problems(name: str, value: str) -> list:
    problems = []
    if not value or value in _PLACEHOLDER_SECRETS:
        problems.append(f"{name} is not set or is a placeholder")
    elif len(value) < _MIN_SECRET_LEN:
        problems.append(f"{name} is shorter than {_MIN_SECRET_LEN} characters")
    return problems


def check_secrets(production: bool) -> None:
    """Raise in production on weak secrets (JWTs and stored Google tokens depend on them); warn otherwise."""
    problems = secret_problems("SECRET_KEY", SECRET_KEY)
    if SESSION_SECRET != SECRET_KEY:
        problems += secret_problems("SESSION_SECRET", SESSION_SECRET)
    if not problems:
        return
    hint = 'generate one with: python -c "import secrets; print(secrets.token_urlsafe(48))"'
    if production:
        raise RuntimeError(f"Refusing to start with APP_ENV=production: {'; '.join(problems)} — {hint}")
    logger.warning("Weak secrets (ok for local development only): %s — %s", "; ".join(problems), hint)


check_secrets(IS_PRODUCTION)


# ===== currencies =====
NBU_API_URL = os.getenv("NBU_API_URL")

# ===== JWT =====
ALGORITHM = os.getenv("ALGORITHM")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES"))
ACCESS_TOKEN_EXPIRES = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

# ===== Google =====
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
JWT_ACCESS_COOKIE_NAME = "access_token"
JWT_REFRESH_COOKIE_NAME = "refresh_token"

# ===== File storage =====
UPLOAD_DIR: str = os.getenv("UPLOAD_DIR", "./uploads")
MAX_UPLOAD_SIZE_MB: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "20"))
# Receipts per user; the oldest must be deleted before uploading more
MAX_RECEIPTS_PER_USER: int = int(os.getenv("MAX_RECEIPTS_PER_USER", "5"))
# "local" → files under UPLOAD_DIR; "database" → bytes in Postgres (receipt_files table),
# for hosts without a persistent disk such as Render's free tier
FILE_STORAGE: str = os.getenv("FILE_STORAGE", "local").strip().lower()

# ===== Github =====
GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")

# ===== Calendar export =====
# Public base URL of this API for calendar subscription links (iPhone / Google
# "From URL" fetch the feed from their servers, so localhost won't work there).
# Defaults to the URL the request came in on.
PUBLIC_API_URL = (os.getenv("PUBLIC_API_URL") or "").rstrip("/")
# Must be registered as an authorised redirect URI of the Google OAuth client.
# Defaults to <API>/api/calendar/google/callback.
GOOGLE_CALENDAR_REDIRECT_URI = os.getenv("GOOGLE_CALENDAR_REDIRECT_URI") or ""
