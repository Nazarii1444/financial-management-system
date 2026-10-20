# Financial Management System — Feature Development Plan

> Focus: powerful, user-facing features that fit naturally into the existing
> FastAPI + PostgreSQL + SQLAlchemy (async) backend. Emphasis on user value and
> presentation impact over refactoring. Each feature notes how it plugs into the
> current modules.

---

## Guiding principles

The current backend already has several pieces that are **modeled but dead** — the
plan deliberately activates them, which is both fast to build and reads very well
in a thesis defense ("we designed for this from the start"):

- `SubscriptionPlan` enum (`FREE` / `PRO`) exists on `User` but **nothing enforces limits**.
- `Receipt.ocr_result` (JSON) is **stored but never used** to create transactions.
- `NotificationPreferences` and `Notification` tables exist but **nothing sends anything**.
- `import_router` exists but there is **no export**.
- `Budget.limit_amount` is stored but **never enforced or alerted on**.

Everything below is chosen to reuse the existing feature-based module layout
(`src/<module>/{router,schemas,services}`), the analytics `BaseAnalyticsService`
pattern, and the pluggable `BaseStorageService`.

---

## Feature Catalog

### F1. Receipt / OCR Scanner → auto-created transaction ⭐ flagship

**1. What the user can do**
Upload or photograph a receipt. The system stores the image (already works), runs
OCR (already works), then **parses** the OCR text into structured fields —
`amount`, `date`, `merchant`, suggested `category` — and returns a **transaction
draft**. The user confirms (or edits) and the transaction is created and linked to
the receipt automatically. A "confidence" score tells the UI how much to trust the draft.

**2. Why it provides value**
This is the single highest-"wow" feature: snap a photo, get a categorized
transaction. It removes the most tedious part of expense tracking.

**3. Integration with current system**
- `files/` already does upload + OCR (`ocr_service.analyse` → `Receipt.ocr_result`).
- Add a **parsing layer** (`files/services/receipt_parser.py`) that turns raw OCR
  text into `{amount, date, merchant, category_guess, confidence}`.
- New endpoints: `POST /api/files/receipts/{id}/suggest-transaction` (returns a
  draft) and `POST /api/files/receipts/{id}/create-transaction` (creates + links,
  reusing the existing `capital` update + `convert_to_user_currency` logic from
  `transaction_router`).
- Category guessing maps merchant keywords → the existing `ALLOWED_*_CATEGORIES`.

**4. Main backend components**
- `receipt_parser.py`: regex/heuristics for totals (`TOTAL`, `AMOUNT DUE`, currency
  symbols), date extraction via `python-dateutil` (already a dependency),
  merchant = top line / longest capitalized token.
- Merchant→category dictionary (seeded, extensible).
- Shared transaction-creation service extracted from `transaction_router` (so both
  manual and receipt-driven creation share one code path).

**5. Complexity:** Medium. (OCR + storage already exist; parsing heuristics are the new work.)

---

### F2. PDF Reports & Statements ⭐

**1. What the user can do**
Generate a polished **monthly / custom-period statement**: balance summary,
income vs expenses, category breakdown (table + optional chart), and a transaction
list. Download as PDF, or receive it by email (see F4).

**2. Why it provides value**
Tangible artifact for records, taxes, or sharing — the kind of output that makes a
demo feel like a finished product.

**3. Integration with current system**
- **Reuses the analytics services directly** — `OverviewService`,
  `CategoryBreakdownService`, `TrendsService` already produce exactly the numbers a
  statement needs. The PDF layer is a *renderer* on top of existing computations.
- New module `reports/` with `report_router.py` + `services/pdf_report_service.py`.
- Endpoint: `GET /api/reports/statement?date_from&date_to&format=pdf`.

**4. Main backend components**
- PDF engine: `reportlab` (pure-Python, no system deps — safest) or `weasyprint`
  (HTML→PDF, prettier). Recommend `reportlab` for portability.
- `ReportService` orchestrating the analytics services → a document model → PDF bytes.
- Charts: render with `matplotlib`→PNG embedded, or draw simple bars in reportlab.

**5. Complexity:** Medium.

---

### F3. Data Export + Custom Backup / Restore format ⭐

**1. What the user can do**
- **Export** all transactions to CSV/Excel (mirror of the existing import).
- **Full backup**: download a single application-specific file (`.fmsbackup`) that
  contains *everything* — profile, transactions, recurring rules, budgets +
  members, goals, categories, settings — as versioned JSON (optionally zipped with
  a manifest + checksum).
- **Restore**: re-upload the backup to rebuild the account state.

**2. Why it provides value**
Data ownership and portability; disaster recovery; account migration. The custom
format is a genuinely interesting engineering artifact to present.

**3. Integration with current system**
- CSV/Excel export lives in `transactions/import_router.py`'s sibling
  `export_router.py`, reusing `openpyxl` (already an optional dep).
- Backup: new `backup/` module. Serialize each ORM model via its Pydantic schema →
  a top-level envelope `{schema_version, exported_at, user, data:{...}}`.
- Restore validates `schema_version`, wraps the whole rebuild in **one transaction**
  (all-or-nothing), remaps old IDs → new IDs, and recomputes `capital`.

**4. Main backend components**
- `backup_service.py` (export/serialize) and `restore_service.py` (validate +
  transactional rebuild + ID remapping).
- A `schema_version` constant and a small migration path for older backups (great
  thesis talking point about forward/backward compatibility).
- Checksum (`hashlib`) + optional `zipfile` packaging.

**5. Complexity:** Medium (CSV/Excel Low; backup/restore Medium–High due to ID remap + integrity).

---

### F4. Email Sending + Notification Engine ⭐

**1. What the user can do**
Receive emails for: password reset, budget-limit alerts, recurring-transaction
reminders, goal milestones (25/50/75/100 %), and an end-of-month summary. Toggle
each via the settings that **already exist** (`NotificationPreferences`).

**2. Why it provides value**
Turns a passive ledger into a proactive assistant — the reason people keep using
finance apps. Also unlocks password reset, a currently missing essential flow.

**3. Integration with current system**
- `NotificationPreferences` (email/push toggles + per-event flags) and the
  `Notification` table are **already modeled and unused** — this feature activates them.
- A `notifications/` module with a pluggable channel interface
  (`EmailChannel` first, `PushChannel` later) — mirrors the `BaseStorageService`
  strategy pattern already used in `files/`.
- Event hooks: budget alert checked on transaction create; goal milestone checked on
  goal update; recurring reminder + monthly digest driven by cron
  (reuse the `@repeat_every` mechanism already in `app.py`).

**4. Main backend components**
- `email_service.py` using `aiosmtplib` (async) + Jinja2 HTML templates.
- `notification_dispatcher.py`: given an event + user prefs, decide + send + record
  a `Notification` row.
- Config: SMTP creds via env (`BaseSettings`).

**5. Complexity:** Medium.

---

### F5. Cash-Flow Forecasting & Anomaly Detection ⭐

**1. What the user can do**
- **Forecast**: "Projected end-of-month balance: X" and a short forward curve,
  derived from active recurring transactions + historical category averages.
- **Anomalies**: automatic flags like "This $420 grocery spend is unusually high"
  or "Spending in *entertainment* is up 3× vs your 3-month average".

**2. Why it provides value**
Predictive insight is what separates a "tracker" from a "financial assistant" —
the most modern, impressive-sounding capability in the deck.

**3. Integration with current system**
- New analytics services subclassing the existing `BaseAnalyticsService`
  (`forecast_service.py`, `anomaly_service.py`) → drop-in endpoints under
  `/api/analytics/*`, matching the current one-service-per-metric pattern.
- Forecast combines `RecurringTransaction.next_run` projections with historical
  monthly means already computed by `TrendsService`.
- Anomaly detection: per-category rolling mean + standard deviation; flag
  transactions beyond `mean + k·σ` (statistical, no ML infra needed). Optional
  upgrade: seasonal/EWMA or an isolation-forest variant for a "future work" slide.

**4. Main backend components**
- `forecast_service.py`: expand recurring rules across the horizon; sum with trend baseline.
- `anomaly_service.py`: SQL group-by for per-category stats + z-score scan.
- Endpoints: `GET /api/analytics/forecast?horizon_days=30`,
  `GET /api/analytics/anomalies?lookback_months=3`.

**5. Complexity:** Medium (heuristic) → High (ML variant, optional).

---

### F6. Free vs Premium (subscription limits) ⭐

**1. What the user can do**
Free tier gets meaningful caps; PRO unlocks the powerful features. Example matrix
(tunable):

| Capability | FREE | PRO |
|---|---|---|
| Active transactions | up to 200 | unlimited |
| Recurring rules | 3 | unlimited |
| Budgets | 1 personal | unlimited + family/business |
| Receipt OCR scans / month | 10 | unlimited |
| PDF reports & full backup | ❌ | ✅ |
| Forecasting & anomaly detection | ❌ | ✅ |
| Multi-currency analytics override | ❌ | ✅ |

**2. Why it provides value**
Demonstrates real product thinking and monetization; a clean way to show system
design (feature-gating, quotas, upgrade flow) in a presentation.

**3. Integration with current system**
- `User.subscription_plan` (`FREE`/`PRO`) **already exists** — this feature gives it teeth.
- Implement as a **reusable FastAPI dependency** `require_plan(...)` and a
  `check_quota(user, resource)` helper, applied to the relevant routers — minimal,
  centralized, non-invasive.
- An upgrade/downgrade endpoint in `settings/` (mock payment for the thesis; real
  Stripe integration as optional "future work").

**4. Main backend components**
- `subscription/` module: `limits.py` (the plan→limits matrix as data),
  `guards.py` (`require_plan`, `enforce_quota`), and a `plan_router.py` for
  upgrade/status.
- Quota counts via cheap `COUNT(*)` queries (add the missing `transactions.user_id`
  index so these stay fast).
- A `402 Payment Required` / clear error contract when a free user hits a cap.

**5. Complexity:** Low–Medium (the gating framework is small; value is high).

---

### F7. Password reset via email (essential companion to F4)

**1. What the user can do** Request a reset link → receive a time-limited token by
email → set a new password.
**2. Value** Currently there's no recovery path; this is table-stakes for a "complete product".
**3. Integration** Reuses the JWT infra (a `reset` token type alongside
`access`/`refresh`/`2fa_pending`) and F4's email service. Endpoints in `auth/`.
**4. Components** `POST /api/auth/password/forgot`, `POST /api/auth/password/reset`;
short-lived signed token; reuse `check_password_strength`.
**5. Complexity:** Low (once F4 exists).

---

### F8. Smart auto-categorization (nice complement to F1)

**1. What the user can do** New transactions get a suggested category from the
merchant/name/past behavior, learned from the user's own history.
**2. Value** Less manual tagging; gets smarter over time.
**3. Integration** A `categorization_service.py` used by both manual create and F1;
starts as a keyword map, upgrades to "most frequent category for this merchant".
**4. Components** history lookup query + keyword dictionary; optional lightweight
Naive Bayes over transaction names for a "future work" slide.
**5. Complexity:** Low (heuristic) → Medium (learned).

---

## Prioritized Roadmap — the 5–10 to implement next

Ordered to maximize demo impact per unit of effort, and sequenced so dependencies
come first.

### 🥇 Tier 1 — build these (highest value, strong dependencies for the rest)

1. **F6 — Free vs Premium limits.** *Low–Medium.* Small framework, activates an
   existing field, and becomes the backbone that gates F2/F3/F5. Build first so
   every later feature can be plan-gated.
2. **F1 — Receipt/OCR → transaction.** *Medium.* The flagship demo moment; reuses
   the working upload+OCR pipeline.
3. **F4 — Email + notification engine.** *Medium.* Activates dead
   `NotificationPreferences`; unlocks F7 and monthly reports.
4. **F2 — PDF reports/statements.** *Medium.* Pure win — reuses analytics services;
   produces a tangible deliverable to show.
5. **F5 — Forecasting & anomaly detection.** *Medium.* The most "modern/AI-ish"
   headline feature; slots into the existing analytics pattern.

### 🥈 Tier 2 — build if time allows

6. **F3 — Export + custom backup/restore.** *Medium–High.* Technically the most
   interesting (versioned format, transactional restore, ID remap) — great for the
   engineering-depth part of the defense.
7. **F7 — Password reset via email.** *Low.* Cheap once F4 exists; completes the
   product.
8. **F8 — Smart auto-categorization.** *Low–Medium.* Amplifies F1; good "future
   work → done" story.

### Suggested build order (dependency-aware)

```
F6 (limits framework)
   └── F4 (email/notifications) ──┬── F7 (password reset)
                                  └── enables monthly digest
F1 (receipt → transaction) ── F8 (auto-categorization shares the code path)
F2 (PDF reports) ── reuses analytics
F5 (forecast/anomaly) ── reuses analytics
F3 (export/backup) ── standalone, do when Tier 1 is stable
```

### One-line pitch for each (presentation slide)
- **F1:** "Photograph a receipt — the app fills in the transaction."
- **F2:** "One click → a professional PDF financial statement."
- **F3:** "Export everything, or back up and restore your entire account."
- **F4:** "Proactive email alerts for budgets, goals, and monthly summaries."
- **F5:** "Predicts your month-end balance and flags unusual spending."
- **F6:** "Free vs Premium tiers with real, enforced limits."

---

## Notes on prerequisites (kept minimal, per the 'features over refactoring' focus)

Only two small technical items materially help these features and are worth doing
*inline* as part of them (not as a separate refactor phase):

- **Add `transactions.user_id` / `(user_id, date)` index** — F6 quota counts and F2/F5
  analytics all filter on it.
- **Config via `BaseSettings` + env** — needed anyway to hold SMTP creds (F4) and to
  stop shipping a `"secret_key"` default. Do it when F4 lands.

Everything else (multi-account model, full auth consolidation, token revocation)
stays out of scope for this feature-focused phase.
