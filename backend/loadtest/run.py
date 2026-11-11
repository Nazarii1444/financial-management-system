"""Run Locust headless per endpoint (+ a mixed scenario) and save the results.

    python -m loadtest.run                                  # read + write groups, 20 users, 30 s each
    python -m loadtest.run --only tx_list,tx_search_text    # just these endpoints
    python -m loadtest.run --groups heavy --users 4         # opt-in heavy endpoints
    python -m loadtest.run --step --skip-endpoints          # find max RPS of the mixed scenario
    python -m loadtest.run --list                           # show endpoint names / groups

Output: loadtest/results/<YYYY-MM-DD_HHMM>_<git-sha>.json and .md next to it.
The server must already run (see loadtest/README.md) and be seeded (python -m loadtest.seed).
"""
import argparse
import csv
import json
import math
import os
import platform
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent
RESULTS = HERE / "results"
LOCUSTFILE = HERE / "locustfile.py"

sys.path.insert(0, str(BACKEND))
from loadtest.common import DEFAULT_HOST  # noqa: E402


def _git(*args) -> str:
    try:
        return subprocess.run(["git", *args], cwd=BACKEND, capture_output=True, text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def _endpoints() -> dict:
    """name -> (group, mix) without importing locust's monkey-patched runtime here."""
    import ast
    tree = ast.parse(LOCUSTFILE.read_text(encoding="utf-8"))
    out = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            for d in node.decorator_list:
                if isinstance(d, ast.Call) and getattr(d.func, "id", "") == "endpoint":
                    group = d.args[0].value
                    mix = next((k.value.value for k in d.keywords if k.arg == "mix"), 0)
                    out[node.name] = (group, mix)
    return out


def _f(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def run_locust(host: str, user_class: str, users: int, spawn_rate: float, duration: int,
               tags: list[str] | None, label: str, reset_stats: bool = True) -> list[dict]:
    """One headless Locust run; returns per-request rows (+ 'Aggregated')."""
    ramp = math.ceil(users / spawn_rate) + 1
    with tempfile.TemporaryDirectory() as tmp:
        prefix = os.path.join(tmp, "stats")
        cmd = [sys.executable, "-m", "locust", "-f", str(LOCUSTFILE), user_class,
               "--headless", "--host", host, "-u", str(users), "-r", str(spawn_rate),
               "-t", f"{duration + ramp}s", "--stop-timeout", "5",
               "--csv", prefix, "--only-summary", "--loglevel", "WARNING"]
        if reset_stats:
            cmd.append("--reset-stats")  # drop the ramp-up phase from the stats
        if tags:
            cmd += ["--tags", *tags]
        print(f"  [{label}] {users} users, {duration}s ...", end=" ", flush=True)
        proc = subprocess.run(cmd, cwd=BACKEND, capture_output=True, text=True,
                              encoding="utf-8", errors="replace")
        stats_file = Path(prefix + "_stats.csv")
        if not stats_file.exists():
            print("FAILED")
            sys.stderr.write(proc.stderr[-3000:])
            raise SystemExit(f"Locust produced no stats for {label} (exit {proc.returncode})")
        with stats_file.open(encoding="utf-8") as fh:
            rows = list(csv.DictReader(fh))
    out = []
    for r in rows:
        n = int(_f(r["Request Count"]))
        fails = int(_f(r["Failure Count"]))
        out.append({
            "name": f"{r['Type']} {r['Name']}" if r["Type"] else r["Name"],
            "requests": n,
            "failures": fails,
            "error_pct": round(100 * fails / n, 2) if n else 0.0,
            "rps": round(_f(r["Requests/s"]), 1),
            "avg_ms": round(_f(r["Average Response Time"]), 1),
            "p50_ms": _f(r["50%"]),
            "p95_ms": _f(r["95%"]),
            "p99_ms": _f(r["99%"]),
            "max_ms": _f(r["Max Response Time"]),
        })
    agg = next((r for r in out if r["name"] == "Aggregated"), None)
    if agg:
        print(f"{agg['rps']} rps, p95 {agg['p95_ms']:.0f} ms, errors {agg['error_pct']}%")
    else:
        print("no requests")
    return out


def find_max(host: str, user_class: str, tags, args, label: str) -> dict:
    """Increase users until p95 > threshold or errors > max; report the best passing step."""
    steps, users, best = [], args.step_start, None
    while users <= args.step_max_users:
        rows = run_locust(host, user_class, users, users, args.step_duration, tags, f"{label} step")
        agg = next((r for r in rows if r["name"] == "Aggregated"), None)
        if not agg or agg["requests"] == 0:
            break
        ok = agg["p95_ms"] <= args.p95_threshold and agg["error_pct"] <= args.max_error_pct
        steps.append({"users": users, "rps": agg["rps"], "p95_ms": agg["p95_ms"],
                      "error_pct": agg["error_pct"], "ok": ok})
        if not ok:
            break
        if best is None or agg["rps"] > best["rps"]:
            best = steps[-1]
        users = int(users * args.step_factor)
    return {"label": label, "p95_threshold_ms": args.p95_threshold, "max_error_pct": args.max_error_pct,
            "max_rps": best["rps"] if best else None, "at_users": best["users"] if best else None,
            "steps": steps}


def to_markdown(result: dict) -> str:
    m = result["meta"]
    lines = [
        f"# Load test {m['started_at']} — `{m['git_sha']}`{' (dirty)' if m['git_dirty'] else ''}",
        "",
        f"Host `{m['host']}` · {m['users']} users · {m['duration_s']} s per endpoint · "
        f"think time {m['wait_s']} s · {m['machine']}",
    ]
    if result["endpoints"]:
        lines += ["", "| endpoint | request | RPS | p50 ms | p95 ms | p99 ms | error % | requests |",
                  "|---|---|---:|---:|---:|---:|---:|---:|"]

    def row(ep, r):
        return (f"| {ep} | {r['name']} | {r['rps']} | {r['p50_ms']:.0f} | {r['p95_ms']:.0f} | "
                f"{r['p99_ms']:.0f} | {r['error_pct']} | {r['requests']} |")

    for ep in result["endpoints"]:
        reqs = [r for r in ep["rows"] if r["name"] != "Aggregated"]
        for r in reqs:
            lines.append(row(f"`{ep['endpoint']}` ({ep['group']})", r))
    if result.get("mixed"):
        agg = next(r for r in result["mixed"]["rows"] if r["name"] == "Aggregated")
        lines += ["", f"## Mixed scenario ({result['mixed']['users']} users)", "",
                  "| request | RPS | p50 ms | p95 ms | p99 ms | error % | requests |",
                  "|---|---:|---:|---:|---:|---:|---:|"]
        for r in sorted(result["mixed"]["rows"], key=lambda r: (r["name"] == "Aggregated", -r["requests"])):
            name = "**total**" if r["name"] == "Aggregated" else r["name"]
            lines.append(f"| {name} | {r['rps']} | {r['p50_ms']:.0f} | {r['p95_ms']:.0f} | "
                         f"{r['p99_ms']:.0f} | {r['error_pct']} | {r['requests']} |")
        lines += ["", f"Mixed total: **{agg['rps']} RPS**, p95 {agg['p95_ms']:.0f} ms"]
    for s in result.get("max_rps", []):
        lines += ["", f"## Max RPS — {s['label']} (p95 ≤ {s['p95_threshold_ms']} ms, errors ≤ {s['max_error_pct']}%)",
                  "", "| users | RPS | p95 ms | error % | ok |", "|---:|---:|---:|---:|:---:|"]
        lines += [f"| {st['users']} | {st['rps']} | {st['p95_ms']:.0f} | {st['error_pct']} | {'✓' if st['ok'] else '✗'} |"
                  for st in s["steps"]]
        lines += ["", f"**Max sustainable: {s['max_rps']} RPS at {s['at_users']} users**" if s["max_rps"]
                  else "**No step met the threshold**"]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--host", default=DEFAULT_HOST)
    p.add_argument("--users", type=int, default=20)
    p.add_argument("--spawn-rate", type=float, default=None, help="default: all users within 1 s")
    p.add_argument("--duration", type=int, default=30, help="measured seconds per endpoint")
    p.add_argument("--warmup", type=int, default=10, help="seconds of mixed load before measuring (0 = off)")
    p.add_argument("--groups", default="read,write", help="comma list of read,write,heavy")
    p.add_argument("--only", default="", help="comma list of endpoint names (overrides --groups)")
    p.add_argument("--skip-endpoints", action="store_true", help="no per-endpoint runs")
    p.add_argument("--skip-mixed", action="store_true")
    p.add_argument("--mixed-duration", type=int, default=None, help="default: 2 × --duration")
    p.add_argument("--step", action="store_true", help="also find max RPS (mixed scenario by default)")
    p.add_argument("--step-endpoints", default="", help="comma list: find max RPS for these endpoints too")
    p.add_argument("--step-start", type=int, default=5)
    p.add_argument("--step-factor", type=float, default=2.0)
    p.add_argument("--step-max-users", type=int, default=320)
    p.add_argument("--step-duration", type=int, default=20)
    p.add_argument("--p95-threshold", type=float, default=500.0, help="ms")
    p.add_argument("--max-error-pct", type=float, default=1.0)
    p.add_argument("--wait", type=float, default=float(os.getenv("LOADTEST_WAIT", "0")),
                   help="think time per virtual user, s (0 = max throughput)")
    p.add_argument("--label", default="", help="suffix for the result file name, e.g. 'baseline'")
    p.add_argument("--list", action="store_true", help="print endpoints and exit")
    args = p.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    eps = _endpoints()
    if args.list:
        for name, (group, mix) in eps.items():
            print(f"{group:6} {name:28} mix={mix}")
        return 0

    os.environ["LOADTEST_WAIT"] = str(args.wait)  # read by locustfile in the child process
    spawn = args.spawn_rate or args.users
    if args.only:
        selected = [n.strip() for n in args.only.split(",") if n.strip()]
        unknown = [n for n in selected if n not in eps]
        if unknown:
            raise SystemExit(f"Unknown endpoints: {unknown}. See --list")
    else:
        groups = {g.strip() for g in args.groups.split(",")}
        selected = [n for n, (g, _) in eps.items() if g in groups]

    import requests
    try:
        requests.get(f"{args.host}/health/", timeout=5).raise_for_status()
    except Exception as exc:
        raise SystemExit(f"Server at {args.host} is not reachable: {exc}")

    started = datetime.now()
    sha = _git("rev-parse", "--short", "HEAD") or "nogit"
    result = {
        "meta": {
            "started_at": started.isoformat(timespec="seconds"),
            "git_sha": sha,
            "git_dirty": bool(_git("status", "--porcelain")),
            "host": args.host, "users": args.users, "spawn_rate": spawn, "duration_s": args.duration,
            "warmup_s": args.warmup, "wait_s": args.wait,
            "machine": f"{platform.system()} {platform.release()}, {os.cpu_count()} CPU, Python {platform.python_version()}",
            "label": args.label,
        },
        "endpoints": [], "mixed": None, "max_rps": [],
    }
    t0 = time.time()

    if args.warmup:
        print("Warm-up (mixed, not recorded)")
        run_locust(args.host, "MixedUser", args.users, spawn, args.warmup, None, "warm-up")

    if not args.skip_endpoints:
        print(f"Per-endpoint runs: {len(selected)}")
        for name in selected:
            rows = run_locust(args.host, "EndpointUser", args.users, spawn, args.duration, [name], name)
            result["endpoints"].append({"endpoint": name, "group": eps[name][0], "rows": rows})

    if not args.skip_mixed:
        print("Mixed scenario")
        dur = args.mixed_duration or args.duration * 2
        result["mixed"] = {"users": args.users, "duration_s": dur,
                           "rows": run_locust(args.host, "MixedUser", args.users, spawn, dur, None, "mixed")}

    if args.step:
        print("Max-RPS search")
        result["max_rps"].append(find_max(args.host, "MixedUser", None, args, "mixed"))
    for name in [n.strip() for n in args.step_endpoints.split(",") if n.strip()]:
        result["max_rps"].append(find_max(args.host, "EndpointUser", [name], args, name))

    result["meta"]["elapsed_s"] = round(time.time() - t0)
    RESULTS.mkdir(exist_ok=True)
    stem = f"{started:%Y-%m-%d_%H%M}_{sha}" + (f"_{args.label}" if args.label else "")
    (RESULTS / f"{stem}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    md = to_markdown(result)
    (RESULTS / f"{stem}.md").write_text(md, encoding="utf-8")
    print()
    print(md)
    print(f"Saved {RESULTS / (stem + '.json')} and .md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
