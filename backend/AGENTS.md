# AGENTS Guide

## Project Snapshot
- Stack: FastAPI + SQLAlchemy async + PostgreSQL + Alembic.
- App entrypoint is `src/app.py`; routers are mounted under `/api/*` and `/health`.
- DB models live in `src/models.py`; async engine/session in `src/database.py`.

## Architecture And Data Flow
- Request flow is router -> dependency auth -> async DB session -> SQLAlchemy model.
  - Auth gate is `src/dependencies.py::get_current_user` (`HTTPBearer` — `Authorization: Bearer <access_token>`; in Swagger paste the token from `POST /api/auth/login` into "Authorize").
  - Most protected endpoints depend on `get_current_user`.
- Tokens are created in `src/utils/jwt_handlers.py` (async, `PyJWT`) but decoded for auth in `src/utils/security.py` (sync, `python-jose`). Do **not** mix these two libs in the same module.
- Every token created by `jwt_handlers.py` carries a `type` claim: `"access"`, `"refresh"`, or `"2fa_pending"`. `dependencies.py::get_current_user_id_from_token` rejects any token whose `type` is in `_BLOCKED_TOKEN_TYPES = {"refresh", "2fa_pending"}`.
- **2FA login flow**: `POST /api/auth/login` returns `{requires_2fa: true, temp_token}` (no access/refresh tokens) when `twofa_enabled`. The client must then `POST /api/auth/2fa/complete` with `{temp_token, code}` to receive the full `TokenPair`. The `temp_token` is a `2fa_pending` token valid for 5 minutes.
- Currency rates are persisted in `currencies` table and refreshed hourly by startup cron (`src/currencies/currency_router.py::register_currency_cron`).
- Transaction writes update `User.capital` via `src/transactions/currency_converter.py::convert_to_user_currency` (converts source → USD → user's default currency).
- Recurring transactions are fired by a per-minute cron (`src/transactions/recurring_router.py::register_recurring_cron`); each fire creates a real `Transaction` row and advances `next_run` by one frequency step.

## Modules Overview

| Prefix | Router file | Notes |
|---|---|---|
| `/api/auth` | `src/auth/auth_router.py` | `POST /signup`, `POST /login`, `POST /refresh`, `POST /logout`, `PATCH /password`, `POST /2fa/complete`; returns `LoginResponse` or `TokenPair` |
| `/api/transactions` | `src/transactions/transaction_router.py` | CRUD + filters + `GET /categories/list`; `GET /search` (typo/case/keyboard-layout tolerant text over name, note, category uk/en names and tags — pure matcher `services/fuzzy.py`, filters in `services/search_service.py`: amount, currency, period, `has_receipt`; returns `items`, `total`, `totals` in the user's currency). `DELETE /{id}` moves to the trash (no hard delete) |
| `/api/transactions/trash` | `src/transactions/trash_router.py` | list / `POST /{id}/restore` / delete forever / empty. Snapshot in `transaction_trash`; restore re-inserts the same `id_`, re-links receipts and adds back the stored `capital_effect` (exact even if FX moved). Purged after 30 days (`register_trash_cron`). Mounted before `transaction_router` |
| `/api/transactions/recurring` | `src/transactions/recurring_router.py` | CRUD recurring rules + cron |
| `/api/transactions/import` | `src/transactions/import_router.py` | CSV / XLSX bulk import; `POST /statement/preview` (bank statement or app CSV/XLSX → reviewable rows, nothing saved) + `POST /statement/confirm` (`update_balance` flag). Bank parsers in `src/transactions/statements/` (`detect.py` sniffs the bytes — monobank's `.pdf` is a PKCS#7 container, its `.xls` is XLSX; `monobank.py`; MCC → category in `mcc.py`). Rows carry `import_ref` (same for PDF/CSV/XLSX of one operation) → re-imports are skipped |
| `/api/templates` | `src/templates/template_router.py` | one-click transaction presets: CRUD, `POST /{id}/use` (`{amount?, remember_amount?}` → Transaction dated now via `create_user_transaction`), `GET /suggestions` (expenses repeated ≥ 5× in 30 days; pure logic in `src/templates/services/suggestions.py`), `POST /suggestions/dismiss` |
| `/api/calendar` | `src/calendar_export/calendar_router.py` | recurring rules → calendars: `GET /recurring.ics` (one-off file), `/feed` (secret subscription URL, public `GET /feed/{token}.ics` for iPhone `webcal://` / Google "From URL"), `/google/*` (Calendar API sync into an app-created calendar, scope `calendar.app.created`; re-synced in the background after every recurring create/update/delete). Pure iCalendar builder in `ics.py`; series start = earliest fired occurrence ≥ `created_at`, so cron advancing `next_run` keeps events stable |
| `/api/exports` | `src/exports/export_router.py` | `GET /transactions.csv` (same filters as search; `lang=uk` → `;` + decimal comma for Excel, importer accepts it back), PDF reports `/reports/statement.pdf`, `/expenses.pdf`, `/budgets.pdf`, `/recurring.pdf` (+ JSON `/reports/recurring` — monthly/yearly cost of recurring rules). Data in `reports.py`, rendering in `pdf.py` (`fpdf2`, lazy import → 501 if missing; needs a Cyrillic TTF: `PDF_FONT_PATH` or DejaVu/Arial, Dockerfile installs `fonts-dejavu-core`). Optional `X-Export-Passphrase` header (percent-encoded UTF-8, never a query param): PDFs get AES-256 password protection, the CSV becomes an encrypted `.csv.fhx` (`src/exports/crypto.py`: scrypt + AES-256-GCM, KDF params in the header) that `POST /api/transactions/import/statement/preview` opens with the `passphrase` form field (422 `passphrase_required` / `wrong_passphrase` / `corrupt_file`) |
| `/api/budgets` | `src/budgets/budget_router.py` | CRUD budgets + member management |
| `/api/analytics` | `src/analytics/analytics_router.py` | `GET /overview`, `/trends/monthly`, `/trends/yearly`, `/comparison/period`, `/breakdown/categories`, `/breakdown/tags`, `/budgets/{budget_id}`, `/safe-to-spend` (today's allowance: balance + recurring income − recurring payments − goal jars − goal contributions this month, ÷ days left; `left_today` / `per_day_after_today` for the dashboard card) |
| `/api/goals` | `src/goals/goal_router.py` | savings jars |
| `/api/users` | `src/users/users_router.py` | profile, PATCH /me, DELETE /me |
| `/api/currencies` | `src/currencies/currency_router.py` | read-only NBU rates |
| `/api/auth/google/*` | `src/google_oauth/google_router.py` | Google OAuth2 |
| `/api/auth/github/*` | `src/github_oauth/github_oauth.py` | GitHub OAuth2 |
| `/api/2fa` | `src/two_fa/two_fa_router.py` | TOTP setup + verify |
| `/api/security` | `src/security/security_router.py` | `GET /events` login & activity history (`SecurityEvent`, written by `security/events.py::record_event` from login / 2FA / passkey / OAuth / password / email / 2FA / export handlers; failed logins only for existing accounts; IP from `X-Forwarded-For` only with `TRUST_PROXY_HEADERS`), `GET /password-health` + `POST /password-health/check` (age, zxcvbn score, HIBP status snapshots on `User`; re-checked in the background on password login at most weekly), `POST /password-strength` (no auth, offline checks — live meter) |
| `/api/passkeys` | `src/security/passkey_router.py` | WebAuthn via `webauthn` (py_webauthn): register options/verify (logged in), list / rename / delete, `POST /login/options` + `/login` → tokens (discoverable credentials, user verification required, skips TOTP). Challenges single-use in `webauthn_challenges` (5 min). RP: `WEBAUTHN_RP_ID` (default: `FRONTEND_URL` host), `WEBAUTHN_ORIGINS`. Service + tests with a software authenticator: `security/passkeys.py`, `tests/security/soft_authenticator.py` |
| `/api/dev/seed` | `src/for_testing/dev_router.py` | **no auth**, dev-only seeding; not mounted when `APP_ENV=production` |
| `/api/settings` | `src/settings/settings_router.py` | profile, currency, email, notifications, subscription |
| `/api/files` | `src/files/file_router.py` | receipt upload + OCR → transaction draft; `GET /receipts/{id}/draft`, `POST /receipts/{id}/rescan`, `POST /receipts/{id}/transaction` (confirm draft, `{}` = accept as-is); CRUD + linking |

## Conventions That Matter Here
- Password rules live in `src/security/password_policy.py` (NIST-style: ≥ 10 chars, ≤ 72 bytes for bcrypt, zxcvbn score ≥ 3, no username/email, common lists, HIBP with padding) — no composition rules. OAuth-created users get a random unusable password; the old `__google_oauth__` / `__github_oauth__` placeholders are refused at login.
- `APP_ENV=production` (`src/config.py`) refuses to start with a placeholder or < 32-char `SECRET_KEY` / `SESSION_SECRET` and hides `/api/dev`; in development it only logs a warning. `SESSION_SECRET` (OAuth session cookie) falls back to `SECRET_KEY`.
- Primary keys are named `id_` (not `id`) across models/schemas.
- Routers return ORM objects directly with Pydantic `from_attributes=True`.
- Update endpoints follow `payload.model_dump(exclude_unset=True)` partial-update pattern.
- Tags stored as PostgreSQL `ARRAY(String)`, always normalised to lowercase; filter with `Transaction.tags.contains([tag])`.
- Category names are validated against per-kind allowlists in `transaction_router.py`; always stored lowercase.
- Currency codes are validated against `Currencies` enum (uppercase ISO-4217).
- Auth responses return both `access_token` and `refresh_token`.

## Integrations And Boundaries
- NBU exchange rates API via `NBU_API_URL` env var.
- OAuth: Google (`/api/auth/google/*`) and GitHub (`/api/auth/github/*`) via `authlib`.
- 2FA: TOTP + QR code base64 in `src/two_fa/two_fa_router.py` (`pyotp`, `qrcode`).
- File import: `python-multipart` for upload, `openpyxl` for `.xlsx`, stdlib `csv` for `.csv`.
- Receipt OCR: `pytesseract` + `pillow` for images, `pdfplumber` for PDFs (`src/files/services/ocr_service.py`). Both are optional — if Tesseract binary is absent, OCR returns `raw_text=null`/`confidence="none"` but the file is still stored.
- Image pipeline (`src/files/services/image_preprocess.py`, `opencv-python-headless`, optional): find the receipt (most quadrilateral "paper" region across several colour masks) → perspective-warp → decode QR codes (`zxing-cpp` first, then OpenCV, on several image variants) → upscale + shadow-flattening binarisation → multi-pass OCR (`ukr`, `eng`, `ukr`/psm 4; low-confidence lines dropped as noise). `ocr_result.pipeline` records the path taken (`opencv` | `pillow_fallback` …) and startup logs a WARNING per missing OCR dependency — run the server from an interpreter that has `requirements.txt` installed. All passes are stored in `ocr_result.ocr_passes` and the parser lets them vote (`receipt_parser.parse_multi`). A Ukrainian fiscal QR (`cabinet.tax.gov.ua/...&sm=<total>&date=&time=`) sets amount/date exactly (`amount_source="fiscal_qr"`). Without it the total is cross-checked (label / card payment / cash − change / item sum / VAT; confusable digits repaired) — `amount_confirmed=true` when ≥ 2 independent checks agree. Known chains (name, category, tax id, QR host) live in `src/files/services/merchants.py`; OCR-tolerant keyword matching in `receipt_text.py`. No AI/LLM anywhere in this path. Regression photos: `tests/files/fixtures/receipt_mcdonalds_ua*.jpg` (+ `.json` ground truth); accuracy report: `python -m scripts.eval_receipts -v`. Text → fields heuristics live in `src/files/services/receipt_parser.py` (pure, unit-tested); draft building + receipt-driven creation in `receipt_transaction_service.py`, which reuses `src/transactions/services/transaction_service.py::create_user_transaction` (the same path as `POST /api/transactions`).
- Category allowlists live in `src/transactions/categories.py` (re-exported from `transaction_router.py`).
- File storage: `aiofiles` + `LocalStorageService` (`src/files/services/storage_service.py`). Files are stored under `UPLOAD_DIR/<user_id>/<uuid><ext>`. Swap to a cloud backend by subclassing `BaseStorageService` and replacing `_storage` in `file_router.py`.

## Developer Workflow
- Install deps: `pip install -r requirements.txt`.
- `.env` lives in `src/.env` (loaded with `load_dotenv(Path(__file__).parent / ".env")` in `src/config.py`).
- Required env vars: `POSTGRES_*`, `SECRET_KEY`, `ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`, `REFRESH_TOKEN_EXPIRE_DAYS`, `NBU_API_URL`, `GOOGLE_CLIENT_*`, `GITHUB_CLIENT_*`.
- Optional env vars (have defaults): `PUBLIC_API_URL` (public base URL for calendar subscription links — phones/Google can't reach localhost), `GOOGLE_CALENDAR_REDIRECT_URI` (default `<API>/api/calendar/google/callback`; must be an authorised redirect URI of the Google OAuth client, which also needs the Calendar API enabled), `UPLOAD_DIR` (default `./uploads`), `MAX_UPLOAD_SIZE_MB` (default `20`), `TESSERACT_CMD` (tesseract path when not on PATH), `OCR_LANG` (comma-separated passes; default `ukr,eng` if the `ukr` pack is installed, else `eng` — avoid `ukr+eng`, it turns Cyrillic into look-alike Latin).
- Image OCR needs the Tesseract binary on the host (no Docker setup in repo): Windows — UB Mannheim installer, tick "Ukrainian" under additional languages; Debian/Ubuntu — `apt install tesseract-ocr tesseract-ocr-ukr`.
- Run from repo root: `python -m src.app` (NOT `python src/app.py` — relative paths will break).
- Migrations: `alembic upgrade head`. Chain: `b8e9f36a3ab8` (init — users, budgets, goals, transactions) → `e5a8c12f4b76` (tags + recurring) → `f1a2b3c4d5e6` (budget limit_amount) → `a1b2c3d4e5f6` (improve goals) → `b2c3d4e5f6a7` (settings + notifications) → `c3d4e5f6a7b8` (receipts) → `d4e5f6a7b8c9` (transaction templates + suggestion dismissals) → `e5f6a7b8c9d0` (calendar feeds + Google Calendar links) → `f6a7b8c9d0e1` (transaction trash) → `a7b8c9d0e1f2` (transactions.import_ref + counts_in_balance).
- Health check: `GET /health/` → `{"status": "OK"}`.
- Dev seed (no auth): `POST /api/dev/seed`.

## Known Footguns For Agents
- Two overlapping auth stacks: `src/utils/jwt_handlers.py` (async, `PyJWT`) vs `src/utils/security.py` (sync, `python-jose`). Auth gate (`dependencies.py`) uses `security.py::decode_token`. Token **creation** uses `jwt_handlers.py`. Do not cross-wire them.
- Root `src/security.py` is **not** the auth module — it only exports `bearer_scheme = HTTPBearer(...)`. All password hashing and token decoding live in `src/utils/security.py`. Do not edit the root file expecting auth behaviour.
- `src/utils/config.py` calls bare `load_dotenv()` (no path). `jwt_handlers.py` reads `ALGORITHM`, `ACCESS_TOKEN_EXPIRE_MINUTES`, and `REFRESH_TOKEN_EXPIRE_DAYS` from it. When running via `python -m src.app`, this may not find `src/.env`; ensure those three vars are exported in the shell or added to the shell env before startup.
- `TransactionOut` previously had `amount` declared twice — fixed. Do not reintroduce the duplicate.
- `src/utils/getters_services.py::get_user_by_id` references `User.id` (missing underscore) — pre-existing bug; avoid calling it until fixed.
- `Transaction.counts_in_balance = False` marks history imported without touching the balance: `update_transaction`, `move_to_trash` and restore must not change `User.capital` for such rows (already handled — keep it that way in new code paths).
- Real bank statements (`tests/files/fixtures/report_*`) contain personal data and are git-ignored; tests use synthetic statements generated in `tests/transactions/test_statements.py`. Never echo statement header data (name, tax id, passport, IBAN) into API responses or logs.
- Deleted transactions are **not** rows with a flag — they live in `transaction_trash`, so other queries need no `deleted_at` filter. Never hard-delete a `Transaction` from a user-facing endpoint; go through `trash_service.move_to_trash`.
- `update_transaction` does **not** recalculate `User.capital` when `amount` or `kind` changes — known limitation.
- `NotificationPreferences` has no row on signup — it is lazily auto-created by `_get_or_create_prefs` on the first `GET /api/settings/notifications` call. Do not assume the row exists; always go through that helper.
- `POST /api/settings/subscription/upgrade|downgrade` directly sets `subscription_plan` with no payment check — the payment integration is a TODO. Do not add payment logic inline; wire a provider at the router level.

## If You Add Or Change Endpoints
- Add/adjust schema in the feature folder (`src/<feature>/schemas.py`) and keep response models aligned with ORM fields.
- Enforce user scoping with `current_user.id_` in queries (see `_get_user_tx_or_404`, `_get_user_goal_or_404`, `_get_user_rt_or_404`).
- For write operations, commit and refresh objects before returning.
- If model metadata changes, create an Alembic revision and keep `src/models.py` + migration in sync.
- Cron jobs follow `register_*_cron(app: FastAPI)` pattern (see `currency_router.py`, `recurring_router.py`).
- Analytics endpoints use the shared `_ctx` dependency (resolves to `session, user, rates_map, currency`). New analytics metrics should subclass `BaseAnalyticsService` (`src/analytics/services/base.py`) and expose a `.compute()` coroutine; mount with `ctx=Depends(_ctx)` and call `YourService(session, user, rates, currency).compute(...)`.

