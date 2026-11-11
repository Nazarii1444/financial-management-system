# Session summary: search performance + security features (2026-10-18)

Repo: `D:\github\financial-management-system` (FastAPI + async SQLAlchemy + PostgreSQL in `backend/`, rules in `backend/AGENTS.md`; React/Vite frontend in `frontend/`). Branch `main`, HEAD `94b8259`. **Nothing from this session is committed.** Other sessions also left uncommitted work in the tree. The user writes in Ukrainian or English; the UI is uk + en.

The previous session (load-test harness, first search step, DB pool settings) is summarised in `side-session-notes/.../session-summary-loadtest-and-search.md`. This one continues from there.

## 1. Search performance (`src/transactions/services/search_service.py`)

- **Step 2:** select plain columns (`_TX_COLUMNS`) instead of ORM entities. `SearchHit.tx` is now a SQLAlchemy `Row` (attribute access works the same for `TransactionOut.model_validate`, the CSV export and totals).
- **Step 3: two queries when `q` is set.**
  1. `GROUP BY name, note, category_name, tags` with `array_agg(id_)`: about 2000 rows become about 240 groups.
  2. Python scores each group once with the unchanged `fuzzy.py`.
  3. Full rows are loaded only for the matched ids (`id_ = ANY(:ids)`).

  Without `q`, it is still a single query.
- **Migration `b9c0d1e2f3a4`:**
  - adds `ix_transactions_user_id_date (user_id, date)` (there was no `user_id` index at all);
  - drops `ix_transactions_id_`, a duplicate of the primary key. Writes are unaffected.
- **Results** (median of 3 runs; files in `backend/loadtest/results/`, `*_search2_*`, `*_search3_*`, `2026-10-18_search{2,3}_compare.md`):

  | text search | RPS | p95 |
  |---|---:|---:|
  | original | 3.3 | 9.9 s |
  | after this session | 143 | 230 ms |

  That is about 43× overall. Write endpoints did not get slower. In a rolled-back test with 500k rows, the index cut the grouping query from 92 to 3.8 ms.
- **Correctness:** output was byte-identical to the previous version on 38 cases (ids, order, scores, page JSON, totals, CSV). The load test's `tx_update` task changes notes, so compare old and new code against the same data, not against old snapshots.

## 2. Passphrase-encrypted exports and import

- **`src/exports/crypto.py`: `.fhx` file format.**
  - Layout: `FHX1` magic, version byte, scrypt parameters (log2 N = 15, r = 8, p = 1, with upper bounds checked on read), 16-byte salt, 12-byte nonce, then AES-256-GCM ciphertext. The header is authenticated as associated data.
  - Functions: `encrypt`, `decrypt`, `is_encrypted`, `validate_passphrase` (8–128 characters).
- **Exports:** an optional `X-Export-Passphrase` header carries the passphrase, percent-encoded so Cyrillic works and never in the URL.
  - PDFs get AES-256 password protection (fpdf2 `set_encryption`, using `_Doc(..., password)`).
  - The CSV becomes `.csv.fhx`. scrypt runs in a thread pool.
- **Import:** `POST /api/transactions/import/statement/preview` accepts a `passphrase` form field. Errors are 422 `passphrase_required`, `wrong_passphrase` or `corrupt_file`.
- **Frontend:** a switch with passphrase fields in `ExportDialog.tsx`, and a passphrase prompt in `ImportDialog.tsx` (accepts `.fhx`).

## 3. Security quick fixes

- `APP_ENV` (default `development`): in `production` the server refuses to start with a placeholder or shorter than 32-character `SECRET_KEY` / `SESSION_SECRET`, and `/api/dev/seed` is not mounted. In development it only logs a warning.
- `SessionMiddleware` uses `SESSION_SECRET` (falls back to `SECRET_KEY`) instead of the hard-coded `"super-session-secret"`.
- **OAuth placeholder bug:** Google and GitHub sign-ups used the literal passwords `__google_oauth__` / `__github_oauth__`, which let anyone log into those accounts. These are now refused in `authenticate_user`, and new OAuth users get `oauth_placeholder_password()` (random).

## 4. Security features (from `docs/security_features_plan.md`)

New package: `src/security/`. Migration `c1d2e3f4a5b6` (applied locally) adds the tables and columns below.

- **SEC-S1, activity history:**
  - Model `SecurityEvent` (`security_events`).
  - `events.record_event(db, user_id, type, request, success=, method=, details=)` commits and never raises. It is called from:
    - login, 2FA completion, passkey login and OAuth callbacks;
    - sign-up, logout, password and email changes, 2FA on/off, passkeys added/removed, and every export (`_logged` in `export_router.py`).
  - Failed logins are recorded only for existing accounts. The client IP comes from `X-Forwarded-For` only when `TRUST_PROXY_HEADERS=true` (set in docker-compose). `describe_user_agent` turns the user agent into a label like "Chrome · Windows".
  - API: `GET /api/security/events`.
- **SEC-S4, password health and policy:**
  - `password_policy.py` follows NIST guidance:
    - length at least 10 characters and at most 72 UTF-8 bytes (bcrypt's limit);
    - zxcvbn score at least 3;
    - no username or email in the password;
    - the bundled common-password lists;
    - HIBP with `Add-Padding`, where `None` means the service was unreachable.

    There are no composition rules.
  - New `User` columns: `password_changed_at`, `password_score`, `password_breached`, `password_checked_at`. They are set at sign-up and password change, and re-checked in the background after a password login at most weekly (`refresh_password_health`, run in its own session).
  - API: `GET /api/security/password-health` and `POST .../check` return a level and recommendation codes. `POST /api/security/password-strength` needs no login and runs the offline checks for the live meter.
  - The error messages are part of the API: `frontend/src/app/lib/errors.ts` maps them by substring.
- **SEC-A1, passkeys:**
  - Built on `webauthn` (py_webauthn 3.0.1). Service in `passkeys.py`, router at `/api/passkeys`:
    - register options and register (logged in);
    - list, rename, delete;
    - `login/options` and `login`, which returns tokens and skips TOTP.
  - Credentials are discoverable and user verification is required. The user handle is a random `User.webauthn_user_handle`.
  - Challenges live in `webauthn_challenges`, are single-use and expire after 5 minutes. Up to 10 passkeys per user.
  - Config: `WEBAUTHN_RP_ID` (default: the `FRONTEND_URL` host, `localhost`; IP addresses don't work), `WEBAUTHN_RP_NAME`, `WEBAUTHN_ORIGINS`.
  - Tests: `tests/security/soft_authenticator.py` is a P-256 software authenticator, used with a fake session in `test_passkeys.py`. It covers replay, a phishing origin, a forged signature, a cloned counter, a wrong user handle, missing user verification, duplicates and the passkey limit.
- **Frontend:**
  - `lib/webauthn.ts`: conversion between JSON and ArrayBuffers, plus `PasskeyCancelled`.
  - `context/AuthContext.tsx`: `loginWithPasskey`.
  - `pages/Login.tsx`: passkey button.
  - `components/security/`: `PasswordStrengthMeter`, `PasswordHealthCard`, `PasskeysCard`, `ActivityCard`. The meter is used on `Register.tsx` (which dropped its old regex) and on Settings → Security, which replaced the "active sessions, coming soon" card.
  - New `security` section in `i18n/translations.ts` (uk/en), including localised zxcvbn durations.

## 5. Verification state

- `backend/.venv/Scripts/python -m pytest tests -q`: **319 passed**.
- A live end-to-end script against `127.0.0.1:8000` passed:
  - weak and personal passwords rejected;
  - events recorded in order;
  - health returned;
  - passkey registration, passwordless login, replay and phishing origin rejected;
  - deletion of the test user.
- In the browser (`localhost:5173`):
  - encrypted CSV and PDF exports;
  - `.fhx` import with wrong and then correct passphrase;
  - the security cards and the meter.
- **Not verified:**
  - a real platform passkey prompt (Windows Hello) — needs the user;
  - the logged-out login page rendering;
  - a TypeScript type check (`tsc` is not installed; `vite build` passes).

## 6. Environment and gotchas

- `.claude/launch.json` has `backend` (uvicorn on port 8000, run from `backend/`) and `frontend` (Vite on 5173, proxies `/api` to 8000) configurations.
- Benchmark server: `.venv/Scripts/python -m uvicorn src.app:app --port 8002 --workers 2 --log-level warning --no-access-log`, then `python -m loadtest.run ...` / `loadtest.compare`. See `backend/loadtest/README.md`.
- The Docker entrypoint creates tables with `scripts.init_db` (`create_all`) and does **not** run Alembic. New tables and the new index appear on a fresh database, but an existing Docker database needs `alembic upgrade head`.
- Frontend files mix CRLF and LF line endings. Keep each file's existing style. Long bash heredocs sometimes fail in this environment, so write scripts to files instead.
- `backend/requirements.txt` gained `webauthn`, `cbor2`, `pyOpenSSL`, `pyasn1_modules` and `zxcvbn`, and `pyasn1` is now 0.6.4.

## 7. Suggested next steps

- **Step-up authentication (SEC-M6):** `PATCH /api/settings/email` changes the email without asking for the password, so a hijacked session can take over the account. Also ask for the password again before unencrypted full exports and account deletion.
- **Rate limiting and lockout (SEC-M3):** there is no brute-force protection. `security_events` already counts failed logins.
- **Real logout and session list (SEC-M1):** JWTs are still not revocable.
- **Password reset:** the frontend calls `/auth/password-reset/*`, which doesn't exist on the backend.
- **Commit housekeeping:** decide what to commit, and whether `backend/loadtest/results/` should be git-ignored.
