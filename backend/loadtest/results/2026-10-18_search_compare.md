# Before `94b8259` (2026-10-18T18:42:41) → after `94b8259` (2026-10-18T18:45:25)

| endpoint | request | RPS before | RPS after | RPS × | p95 before | p95 after | p95 Δ | err % before → after |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| `tx_search_text` | GET /api/transactions/search?q | 3.3 | 31.8 | 9.64× 🟢 | 9900 | 820 | -92% | 0.0 → 0.0 |
| `tx_search_filtered` | GET /api/transactions/search?filters | 185.9 | 254.1 | 1.37× 🟢 | 220 | 160 | -27% | 0.0 → 0.0 |

🟢 RPS ≥ +10% without p95 regression · 🔴 RPS ≤ −10% or p95 ≥ +20%
