# Financial Management System — Security Features Plan

> Security treated as a **user-facing product feature**, not just internal hardening.
> Each feature builds on the current auth stack:
> - JWT access + refresh tokens with rotation (`utils/jwt_handlers.py`) — but **no revocation**, and `logout` is a no-op.
> - TOTP 2FA already implemented (`two_fa/`) — but **no backup codes, no trusted devices**.
> - Password strength rules + **HaveIBeenPwned** k-anonymity check (`auth/password_validator.py`).
> - Google/GitHub OAuth2.
> - `NotificationPreferences` table **modeled but dead** — several features below activate it.
> - **Missing today:** rate limiting, account lockout, login history, session management, password reset, audit log.

Complexity: **Low** (days) · **Medium** (1–2 weeks) · **High** (multi-week / research-flavored).

---

## 1. Simple

### SEC-S1. Login & Activity History — ✅ implemented (`src/security/events.py`, `/api/security/events`)
- **What the user experiences:** A "Recent activity" page: timestamp, IP, approximate location, device/browser, and outcome (success / failed / 2FA challenge) for every login and sensitive action.
- **Security problem solved:** Lets users spot unauthorized access themselves — the first line of defense.
- **Fits the system:** A `login_events` (or broader `security_events`) table written from the existing `login`, `refresh`, `2fa/complete`, and password-change handlers in `auth_router.py`.
- **Backend components:** `security_events` model; a small `record_event()` helper; IP + `User-Agent` parsing (`user-agents` lib); optional offline IP→city (GeoLite2).
- **Complexity:** Low.
- **Presentation value:** Instantly demoable ("here's every login to my account"); foundation for SEC-M3 and SEC-M2.

### SEC-S2. Security Notifications (activate the dead table)
- **What the user experiences:** Email alerts on security-relevant events: new-device login, password changed, 2FA enabled/disabled, email changed. Each has a "This wasn't me — secure my account" link.
- **Security problem solved:** Turns silent account changes into detectable events; early breach warning.
- **Fits the system:** `NotificationPreferences` already models these toggles; this gives them behavior. Fires from the same auth handlers as SEC-S1.
- **Backend components:** Email service (`aiosmtplib` + templates); a dispatcher keyed off event type + user prefs.
- **Complexity:** Low–Medium (needs an email sender configured).
- **Presentation value:** "The app emails you the instant someone logs in" — very product-credible.

### SEC-S3. Privacy Mode / Balance Masking
- **What the user experiences:** A toggle that hides balances and amounts by default (shown as ••••), revealed on tap; useful in public/shoulder-surfing situations.
- **Security problem solved:** Visual/physical privacy of sensitive financial data.
- **Fits the system:** A `privacy_mode` flag in user settings; API can optionally return a `masked` hint; mostly a settings + client concern with a server-stored preference.
- **Backend components:** One settings field + endpoint.
- **Complexity:** Low.
- **Presentation value:** Small but thoughtful; shows attention to real usage contexts.

### SEC-S4. Password Health & Age — ✅ implemented (`/api/security/password-health`, policy in `src/security/password_policy.py`)
- **What the user experiences:** "Your password was last changed 8 months ago", a strength indicator on change, and a warning if it appears in new breaches.
- **Security problem solved:** Encourages rotation of stale/compromised passwords.
- **Fits the system:** Add `password_changed_at` to `User`; reuse the existing `check_password_strength` + HIBP check for on-demand re-evaluation.
- **Backend components:** Timestamp column; a `GET /api/security/password-health` endpoint.
- **Complexity:** Low.
- **Presentation value:** Reuses the impressive HIBP integration you already built, surfaced to the user.

### SEC-S5. Configurable Session Timeout
- **What the user experiences:** Choose how long a session stays valid (e.g. 15 min / 2 h / 30 days) and toggle "log me out on browser close".
- **Security problem solved:** Reduces exposure window on shared/lost devices.
- **Fits the system:** Access token lifetime is already env-driven; make it a per-user preference applied at token creation.
- **Backend components:** Preference field; use it in `create_access_token`.
- **Complexity:** Low.
- **Presentation value:** Simple, but signals mature session thinking.

---

## 2. Medium

### SEC-M1. Device & Session Management + Real Logout ⭐
- **What the user experiences:** "Active sessions" screen listing every logged-in device (browser, OS, location, last-seen, current-device marker) with **"Log out"** per session and **"Log out everywhere"**.
- **Security problem solved:** The current biggest gap — JWTs can't be revoked, so a stolen/leaked token stays valid until expiry, and `logout` does nothing.
- **Fits the system:** Introduce a server-side **refresh-token registry** (DB table or Redis): each login creates a session row (jti, device info, expiry, revoked flag). Refresh checks the registry; revoking a session invalidates its refresh token. Access tokens stay short-lived so revocation propagates quickly (optionally add a short access-token denylist for instant kill).
- **Backend components:** `sessions` table keyed by token `jti`; modify `create_refresh_token`/`refresh`/`logout`; a `sessions_router` (list/revoke/revoke-all).
- **Complexity:** Medium.
- **Presentation value:** High — this is the feature that makes the app feel like a real platform, and it directly fixes a documented weakness (great defense narrative).

### SEC-M2. Suspicious / New-Device Login Detection ⭐
- **What the user experiences:** Logging in from an unrecognized device/location triggers an email alert and (optionally) an extra verification step (email code or 2FA) before access is granted.
- **Security problem solved:** Stops credential-stuffing and stolen-password logins even without 2FA enabled.
- **Fits the system:** Uses the SEC-S1 event history to fingerprint "known" devices (hashed UA + IP subnet / geo); unknown → challenge + SEC-S2 notification.
- **Backend components:** Device-fingerprint hashing; a "known devices" table; a risk check in the login flow; email verification-code issuance.
- **Complexity:** Medium.
- **Presentation value:** Very impressive — "the system noticed I logged in from a new country and challenged me."

### SEC-M3. Rate Limiting & Account Lockout
- **What the user experiences:** After several failed logins, progressive delays, a temporary lockout, and an email alert; abusive clients are throttled across auth endpoints.
- **Security problem solved:** Brute-force and credential-stuffing protection — currently entirely absent.
- **Fits the system:** Middleware/dependency on `auth/*` endpoints; counters in Redis (or in-DB for a simpler build). Ties into SEC-S2 for the lockout email.
- **Backend components:** `slowapi` or a custom Redis token-bucket; a `failed_attempts` counter + lockout window on `User`.
- **Complexity:** Medium.
- **Presentation value:** Demonstrable with a scripted brute-force that gets blocked — clear before/after.

### SEC-M4. 2FA Backup Codes + Trusted Devices ⭐
- **What the user experiences:** On enabling 2FA, receive 10 one-time **recovery codes** to store safely (for when the phone is lost); and a **"trust this device for 30 days"** option so 2FA isn't demanded every login.
- **Security problem solved:** Removes the two biggest 2FA pain points — lockout on lost device, and prompt fatigue (which drives users to disable 2FA).
- **Fits the system:** Extends the existing `two_fa/` module. Backup codes stored **hashed** (like passwords); trusted devices reuse the SEC-M1 session/device registry.
- **Backend components:** `twofa_backup_codes` table (hashed, single-use); a "trusted device" flag on sessions; verification endpoints.
- **Complexity:** Medium.
- **Presentation value:** Rounds out the 2FA you already have into a complete, production-grade flow.

### SEC-M5. Password Reset & Account Recovery
- **What the user experiences:** "Forgot password" → emailed time-limited link → set a new password; recovery still requires 2FA if enabled.
- **Security problem solved:** There is **no recovery path today**; also a secure, non-enumerable reset flow (always responds "if the email exists…").
- **Fits the system:** Reuses JWT infra with a new `reset` token type and the SEC-S2 email service; reuses `check_password_strength`.
- **Backend components:** `password/forgot` + `password/reset` endpoints; single-use reset tokens (registry or signed + jti); anti-enumeration responses.
- **Complexity:** Medium.
- **Presentation value:** Essential for a "complete product"; pairs naturally with the email work.

### SEC-M6. Step-Up (Re-)Authentication for Sensitive Operations ⭐
- **What the user experiences:** High-risk actions — delete account, change email/password, export all data, bulk-delete transactions, add a budget member — require re-entering the password or a fresh 2FA code, even in an active session.
- **Security problem solved:** Limits damage from a hijacked but already-authenticated session; protects the "keys to the kingdom" actions.
- **Fits the system:** A reusable `require_recent_auth` FastAPI dependency that checks for a short-lived "sudo" token minted by a `/api/auth/verify` step; applied to the sensitive endpoints.
- **Backend components:** Sudo-token issuance/verification; a dependency decorator; apply to chosen routes.
- **Complexity:** Medium.
- **Presentation value:** A recognizable pattern from GitHub/Google ("confirm your password to continue") — signals real security design.

### SEC-M7. Encrypted Backup / Export
- **What the user experiences:** When exporting data or downloading a full account backup, optionally set a password; the file is AES-encrypted and can only be opened/restored with that password.
- **Security problem solved:** Financial data leaving the system (in a file, email, or cloud drive) is protected at rest.
- **Fits the system:** Wraps the export/backup feature; uses `cryptography` (already a dependency) with a password-derived key (PBKDF2/scrypt) + authenticated encryption (AES-GCM).
- **Backend components:** Envelope encryptor; a decrypt-on-restore path; clear KDF parameters in the file header.
- **Complexity:** Medium.
- **Presentation value:** Concrete applied cryptography — a strong, self-contained thesis section.

### SEC-M8. Account Freeze / Panic Button ⭐ creative
- **What the user experiences:** A one-tap **"Freeze my account"** that immediately revokes all sessions, blocks new logins (except a secure unfreeze flow), and disables data export — for when a device is lost or compromise is suspected.
- **Security problem solved:** Gives users an emergency kill-switch instead of waiting for support.
- **Fits the system:** A `frozen` state on `User` checked in `get_current_user`; reuses SEC-M1 revoke-all; unfreeze requires email + 2FA/step-up.
- **Backend components:** Account-state flag + guard in the auth dependency; freeze/unfreeze endpoints; notification.
- **Complexity:** Medium.
- **Presentation value:** Memorable, finance-specific, and genuinely useful — the kind of feature examiners remember.

---

## 3. Advanced

### SEC-A1. Passkeys / WebAuthn (FIDO2) — passwordless & phishing-proof ⭐⭐ — ✅ implemented (`/api/passkeys`)
- **What the user experiences:** Register a passkey (Face ID / Touch ID / Windows Hello / hardware key) and log in with no password — or use it as a phishing-resistant second factor.
- **Security problem solved:** Eliminates password phishing and credential reuse entirely; the modern gold standard for auth.
- **Fits the system:** Adds a new credential type alongside the existing password + TOTP; slots into the login flow as an alternative/added factor.
- **Backend components:** `py_webauthn` for registration/assertion ceremonies; a `webauthn_credentials` table (public key, sign count); challenge storage.
- **Complexity:** High.
- **Presentation value:** Top-tier — passwordless biometric login is a genuine "wow" and shows command of cutting-edge auth standards.

### SEC-A2. Risk-Based / Adaptive Authentication ⭐
- **What the user experiences:** The app silently scores each login/action (new device, odd hour, impossible travel, unusual amount) and only escalates to a challenge when risk is high — invisible when safe, protective when not.
- **Security problem solved:** Balances security and friction; catches account takeover that static rules miss.
- **Fits the system:** Consumes SEC-S1 history + device data; a scoring service gates login (SEC-M2) and step-up (SEC-M6).
- **Backend components:** A `risk_engine` (weighted heuristics or a lightweight model); "impossible travel" via geo velocity; decision → allow / challenge / block.
- **Complexity:** High.
- **Presentation value:** Sophisticated and modern; a clear systems-thinking demonstration.

### SEC-A3. Tamper-Evident Audit Log (hash-chained) ⭐
- **What the user experiences:** A complete, exportable, verifiable history of every action on the account, with a guarantee it hasn't been altered.
- **Security problem solved:** Non-repudiation and integrity — critical for financial data; detects insider/DB tampering.
- **Fits the system:** Extends SEC-S1 into an append-only `audit_log` where each row stores `hash = H(prev_hash + entry)`; a verify endpoint replays the chain.
- **Backend components:** Append-only writer; hash-chain (SHA-256); a `verify_integrity` endpoint; optional periodic anchoring.
- **Complexity:** High.
- **Presentation value:** Advanced and finance-appropriate; the "prove the log wasn't tampered with" demo is compelling and academically strong.

### SEC-A4. Field-Level Encryption of Sensitive Data (envelope encryption)
- **What the user experiences:** Sensitive fields (notes, merchant, receipts, maybe amounts) are encrypted at rest; even a database dump reveals nothing readable.
- **Security problem solved:** Protects data at rest against DB compromise/backups leaking.
- **Fits the system:** Encrypt selected columns with per-user data keys wrapped by a master key (KMS-style); decrypt in the service layer transparently.
- **Backend components:** `cryptography` (AES-GCM); a key-management service (per-user DEK + master KEK); encrypt/decrypt hooks in SQLAlchemy types.
- **Complexity:** High.
- **Presentation value:** Serious applied crypto and key-management design — strong for a security-focused thesis. (Note the searchability tradeoff — a good discussion point.)

### SEC-A5. Compromised-Credential & Breach Monitoring
- **What the user experiences:** Periodic background checks; if the user's email/password appears in a new breach, they get an alert and a forced password change.
- **Security problem solved:** Proactive defense against credential reuse after third-party breaches.
- **Fits the system:** Reuses the existing HIBP integration, run on a schedule (`@repeat_every` cron already in use) + SEC-S2 notifications.
- **Backend components:** Scheduled HIBP breach-check job; a "force password change" flag enforced in the auth dependency.
- **Complexity:** Medium–High.
- **Presentation value:** Elevates the one-time HIBP check into an ongoing protection service.

---

## Top Recommendations (5–10 to implement)

Balanced on user value, effort, technical depth, presentation impact, and fit.
Sequenced so shared infrastructure comes first.

| # | Feature | Tier | Rationale |
|---|---------|------|-----------|
| 1 | **SEC-S1 — Login & Activity History** | Low | Foundation for M1/M2/A2/A3; cheap; instantly demoable |
| 2 | **SEC-S2 — Security Notifications** | Low–Med | Activates the dead `NotificationPreferences`; high perceived value |
| 3 | **SEC-M1 — Device & Session Management + real logout** | Med | Fixes the #1 gap (no revocation); makes it feel like a real platform |
| 4 | **SEC-M3 — Rate Limiting & Account Lockout** | Med | Closes brute-force exposure; clean before/after demo |
| 5 | **SEC-M4 — 2FA Backup Codes + Trusted Devices** | Med | Completes the 2FA you already built; removes real friction |
| 6 | **SEC-M5 — Password Reset & Recovery** | Med | Essential missing flow; reuses the email service |
| 7 | **SEC-M2 — Suspicious/New-Device Detection** | Med | Impressive, protective, builds on S1+S2 |
| 8 | **SEC-M6 — Step-Up Auth for Sensitive Ops** | Med | Recognizable pattern; protects the dangerous actions |
| 9 | **SEC-A1 — Passkeys / WebAuthn** | High | The showstopper; modern passwordless auth |
| 10 | **SEC-A3 — Tamper-Evident Audit Log** | High | Advanced, finance-appropriate; extends S1 naturally |

### If you want a tight, coherent bundle
**S1 → S2 → M1 → M3 → M4/M5**, then one advanced headline (**A1 Passkeys** *or* **A3 Audit Log**).

This order builds one piece of shared plumbing at a time:
- **S1 (event history)** feeds M1, M2, A2, A3.
- **S2 (email/notifications)** feeds M2, M3, M5, A5.
- **M1 (session/device registry)** feeds M2, M4 (trusted devices), M8 (freeze).

The result covers detection (history + alerts), prevention (rate limit + step-up + sessions), recovery (reset + backup codes), and one flagship advanced feature — a complete, defensible security story rather than a grab-bag of controls.

---

## Deliberately not prioritized (and why)
- **SEC-A4 field-level encryption** — high effort and it breaks searching/filtering/analytics on encrypted columns; great to *discuss* as future work, heavy to fully build now.
- **SEC-A2 adaptive auth** — powerful but overlaps M2; only pursue if you want a dedicated risk-engine chapter.
- **SEC-S3 privacy mode / SEC-S5 session timeout** — nice touches, but mostly client-side; include as small polish, not headline features.
