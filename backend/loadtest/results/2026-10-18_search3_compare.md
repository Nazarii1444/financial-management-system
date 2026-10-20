# Search optimisation, step 3: two-step query + `(user_id, date)` index (2026-10-18)

Server: `uvicorn src.app:app --port 8002 --workers 2 --log-level warning --no-access-log`, 20 users, 20 s per endpoint (5 s warm-up).
Three runs each; the table shows the median (runs: `*_search3_before_r1..3`, `*_search3_after_r1..3`).
Write endpoints are included to check whether the new index slows inserts and updates.

## Changes
- `src/transactions/services/search_service.py`: with a text query, step 1 runs `GROUP BY name, note, category_name, tags` with `array_agg(id_)`. This turns about 2000 rows into about 240 groups, and each group is scored once with the unchanged `fuzzy.py`. Step 2 loads full rows only for the matched ids (`id_ = ANY(:ids)`, one array parameter). Requests without a text query still use one query.
- Migration `b9c0d1e2f3a4`:
  - adds `ix_transactions_user_id_date (user_id, date)`. `transactions` had no index on `user_id`, so every per-user query scanned the whole table.
  - drops `ix_transactions_id_`, which duplicated the primary-key index. Each insert still updates the same number of indexes.

## Load test (median of 3)

| endpoint | request | RPS before | RPS after | RPS × | p95 before | p95 after | p95 Δ | runs RPS before → after |
|---|---|---:|---:|---:|---:|---:|---:|---|
| `tx_search_text` | GET /api/transactions/search?q | 43.2 | 143.2 | **3.31×** | 800 | 230 | −71% | 34/50/43 → 150/143/141 |
| `tx_search_filtered` | GET /api/transactions/search?filters | 240.0 | 258.2 | 1.08× | 140 | 110 | −21% | 164/254/240 → 260/257/258 |
| `export_csv` | GET /api/exports/transactions.csv | 24.9 | 29.4 | 1.18× | 1300 | 850 | −35% | 23/25/29 → 30/29/29 |
| `tx_list` | GET /api/transactions | 346.8 | 376.1 | 1.08× | 110 | 110 | +0% | 366/305/347 → 373/376/381 |
| `tx_list_filtered` | GET /api/transactions?kind&category&date_from | 260.1 | 365.1 | 1.40× | 150 | 100 | −33% | 230/321/260 → 367/365/361 |
| `tx_get` | GET /api/transactions/{id} | 554.0 | 641.2 | 1.16× | 50 | 41 | −18% | 415/554/673 → 647/639/641 |
| `analytics_overview` | GET /api/analytics/overview | 34.8 | 36.7 | 1.05× | 850 | 820 | −4% | 33/35/38 → 37/36/37 |
| `tx_create_delete` | POST /api/transactions | 98.1 | 97.7 | 1.00× | 180 | 180 | +0% | 79/98/102 → 97/98/102 |
| `tx_create_delete` | DELETE /api/transactions/{id} | 97.9 | 97.1 | 0.99× | 150 | 150 | +0% | 79/98/101 → 97/97/101 |
| `tx_update` | PATCH /api/transactions/{id} | 353.1 | 364.6 | 1.03× | 110 | 65 | −41% | 353/288/378 → 363/365/379 |
| `template_use` | POST /api/templates/{id}/use | 84.1 | 91.2 | 1.08× | 260 | 240 | −8% | 84/72/94 → 91/88/93 |

The baseline runs were noisier (r1 was slow throughout), so changes under about 10–15% on the non-search endpoints are within noise. The text-search gain is consistent in all three runs. **No write endpoint got slower.**

In-process, `search_transactions` alone over 18 text queries went from 32 to 14.5 ms per call.

## Index at realistic table size

The benchmark table has only about 2,600 rows, so Postgres scans the whole table either way and the index has no effect there. To see its effect at scale, a script added 500,000 rows for 10 other users inside one transaction and then rolled it back. It timed the queries without and with the index (average of 20 runs, benchmark user with 2000 rows):

| query | no index | with index |
|---|---:|---:|
| search step 1 (grouped) | 92.1 ms | 3.8 ms |
| filtered (kind, amount, last 30 days) | 81.8 ms | 0.8 ms |
| all rows of a user + `has_receipt` | 120.5 ms | 89.9 ms |

Without the index, the time for every per-user query grows with the total number of transactions in the database. With it, the time grows only with the user's own transactions. Each insert pays one extra B-tree insert, which dropping the duplicate `id_` index cancels out.

## Correctness
- The old single-query search and the new two-step search were run against the same data in one session. The output was byte-identical on 38 cases (35 text queries plus filtered, `has_receipt` and currency cases). The check covered ids, order, scores, `has_receipt`, the first page as `TransactionOut` JSON, totals and the CSV.
- `pytest tests`: 248 passed.

## Text search, all steps

| version | RPS | p95 |
|---|---:|---:|
| original | 3.3 | 9900 ms |
| step 1: cached fuzzy matching | 31.8 | 820 ms |
| step 2: column rows | 48.0 | 560 ms |
| step 3: two-step query + index | 143.2 | 230 ms |
| **total** | **≈43×** | **−98%** |

Each step was measured in a separate session with its own baseline, so the total is approximate.
