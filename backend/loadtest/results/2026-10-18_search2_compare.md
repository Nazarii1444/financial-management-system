# Search optimisation, step 2: column rows instead of ORM entities (2026-10-18)

Server: `uvicorn src.app:app --port 8002 --workers 2 --log-level warning --no-access-log`, 20 users, 30 s per endpoint (10 s warm-up).
Three runs each; the table shows the median (runs: `*_search2_before_r1..3`, `*_search2_after_r1..3`).

Change (`src/transactions/services/search_service.py`):
- `select(*Transaction columns, has_receipt)` instead of `select(Transaction, has_receipt)`, so SQLAlchemy returns plain rows and doesn't build ~2000 ORM instances per request.
- The fuzzy score is cached per distinct `(name, note, category, tags)` before the searchable strings are built, so they are built once per distinct combination, not once per row.
- A request without `q` skips the scoring loop.

| request | RPS before | RPS after | RPS × | p50 before → after | p95 before → after | p99 before → after |
|---|---:|---:|---:|---:|---:|---:|
| `GET /search?q` (text) | 29.9 | 48.0 | **1.61×** | 690 → 430 ms | 760 → 560 ms (−26%) | 890 → 580 ms |
| `GET /search?filters` (no text) | 247.8 | 250.2 | 1.01× (noise) | 75 → 76 ms | 150 → 110 ms | 160 → 160 ms |

Per-run RPS for text search: before 30.8 / 29.9 / 29.3, after 49.4 / 43.5 / 48.0.
In-process (`search_transactions` alone, 18 text queries): 64 → 32 ms per call.

Correctness: the output is byte-identical on 38 cases (35 text queries plus filtered, receipt and currency cases). The check covered ids, order, scores, `has_receipt`, the first page as `TransactionOut` JSON, totals and the CSV export. `pytest tests/transactions tests/exports`: 57 passed.

## Both steps together (text search)

| version | RPS | p95 |
|---|---:|---:|
| original | 3.3 | 9900 ms |
| step 1: cached fuzzy matching (`*_search_after`) | 31.8 | 820 ms |
| step 2: column rows (this run) | 48.0 | 560 ms |
| **total** | **≈14.5×** | **−94%** |

Step 1 and step 2 numbers come from different sessions, so compare within a step. The total is approximate.

Remaining cost per text-search request: about 5 ms of fuzzy matching. The rest is transferring and decoding about 2000 rows from Postgres (the ARRAY `tags` column is the most expensive to decode). The next step would be filtering rows in SQL before matching, for example with `pg_trgm`. That needs a DB extension and would change typo/layout behaviour, so it isn't done here.
