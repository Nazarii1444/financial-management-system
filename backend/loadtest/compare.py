"""Before/after table for two run.py results.

    python -m loadtest.compare loadtest/results/A.json loadtest/results/B.json [-o diff.md]

RPS × > 1 and a negative p95 Δ are improvements. Rows present in only one file are listed too.
"""
import argparse
import json
import sys
from pathlib import Path


def _rows(result: dict) -> dict:
    """(section, endpoint, request) -> row."""
    out = {}
    for ep in result.get("endpoints", []):
        for r in ep["rows"]:
            if r["name"] != "Aggregated":
                out[(ep["endpoint"], r["name"])] = r
    if result.get("mixed"):
        for r in result["mixed"]["rows"]:
            out[("mixed", "total" if r["name"] == "Aggregated" else r["name"])] = r
    return out


def _ratio(a, b):
    return f"{b / a:.2f}×" if a else "—"


def _pct(a, b):
    if not a:
        return "—"
    d = (b - a) / a * 100
    return f"{d:+.0f}%"


def _mark(rps_a, rps_b, p95_a, p95_b):
    """Flag changes beyond ~10%, the usual run-to-run noise on a laptop."""
    if rps_a and p95_a:
        if rps_b / rps_a >= 1.1 and p95_b <= p95_a * 1.05:
            return " 🟢"
        if rps_b / rps_a <= 0.9 or p95_b >= p95_a * 1.2:
            return " 🔴"
    return ""


def compare(before: dict, after: dict) -> str:
    a, b = _rows(before), _rows(after)
    ma, mb = before["meta"], after["meta"]
    lines = [
        f"# Before `{ma['git_sha']}` ({ma['started_at']}) → after `{mb['git_sha']}` ({mb['started_at']})",
        "",
    ]
    if (ma["users"], ma["duration_s"], ma.get("wait_s")) != (mb["users"], mb["duration_s"], mb.get("wait_s")):
        lines += [f"> ⚠ Different settings: {ma['users']} users/{ma['duration_s']} s vs "
                  f"{mb['users']} users/{mb['duration_s']} s — numbers are not directly comparable.", ""]
    lines += [
        "| endpoint | request | RPS before | RPS after | RPS × | p95 before | p95 after | p95 Δ | err % before → after |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for key in list(a) + [k for k in b if k not in a]:
        ep, name = key
        ra, rb = a.get(key), b.get(key)
        if ra and rb:
            lines.append(
                f"| `{ep}` | {name} | {ra['rps']} | {rb['rps']} | {_ratio(ra['rps'], rb['rps'])}"
                f"{_mark(ra['rps'], rb['rps'], ra['p95_ms'], rb['p95_ms'])} | {ra['p95_ms']:.0f} | "
                f"{rb['p95_ms']:.0f} | {_pct(ra['p95_ms'], rb['p95_ms'])} | {ra['error_pct']} → {rb['error_pct']} |")
        else:
            r = ra or rb
            side = "only before" if ra else "only after"
            lines.append(f"| `{ep}` | {name} ({side}) | {r['rps'] if ra else '—'} | {r['rps'] if rb else '—'} | — | "
                         f"{r['p95_ms'] if ra else '—'} | {r['p95_ms'] if rb else '—'} | — | {r['error_pct']} |")

    max_a = {s["label"]: s for s in before.get("max_rps", [])}
    max_b = {s["label"]: s for s in after.get("max_rps", [])}
    common = [k for k in max_a if k in max_b]
    if common:
        lines += ["", "| max RPS | before | after | × |", "|---|---:|---:|---:|"]
        for k in common:
            x, y = max_a[k]["max_rps"], max_b[k]["max_rps"]
            lines.append(f"| {k} | {x} ({max_a[k]['at_users']} u) | {y} ({max_b[k]['at_users']} u) | "
                         f"{_ratio(x, y) if x and y else '—'} |")
    lines += ["", "🟢 RPS ≥ +10% without p95 regression · 🔴 RPS ≤ −10% or p95 ≥ +20%"]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("before")
    p.add_argument("after")
    p.add_argument("-o", "--output", help="also write the table to this file")
    args = p.parse_args(argv)
    md = compare(*(json.loads(Path(f).read_text(encoding="utf-8")) for f in (args.before, args.after)))
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(md)
    if args.output:
        Path(args.output).write_text(md, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
