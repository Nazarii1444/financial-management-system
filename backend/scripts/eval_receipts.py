"""
Receipt OCR accuracy — runs the full pipeline on every photo that has a ground-truth file.

Usage (from backend/):
    python -m scripts.eval_receipts                       # tests/files/fixtures
    python -m scripts.eval_receipts path/to/receipts -v   # -v: print mismatches

Each <name>.jpg|png|webp|pdf needs a <name>.json next to it, e.g.
    {"amount": "83.00", "currency": "UAH", "date": "2026-10-03T10:37",
     "merchant": "McDonald's", "category": "food"}
Omitted keys are not scored; "date" is compared up to the given precision.
On Windows set TESSERACT_CMD if tesseract is not on PATH.
"""
from __future__ import annotations

import argparse
import json
import time
from decimal import Decimal
from pathlib import Path

from src.files.services import ocr_service

FIELDS = ("amount", "currency", "date", "merchant", "category")
_CONTENT_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
                  ".webp": "image/webp", ".pdf": "application/pdf"}
_DEFAULT_DIR = Path(__file__).resolve().parent.parent / "tests" / "files" / "fixtures"


def _actual(result: dict) -> dict:
    amount = result.get("suggested_amount")
    return {
        "amount": f"{Decimal(str(amount)):.2f}" if amount is not None else None,
        "currency": result.get("suggested_currency"),
        "date": result.get("suggested_date"),
        "merchant": result.get("merchant"),
        "category": result.get("suggested_category"),
    }


def _matches(field: str, expected, actual) -> bool:
    if field == "date":
        return actual is not None and actual.startswith(expected)
    return expected == actual


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("directory", nargs="?", type=Path, default=_DEFAULT_DIR)
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    cases = sorted(p for p in args.directory.iterdir()
                   if p.suffix.lower() in _CONTENT_TYPES and p.with_suffix(".json").exists())
    if not cases:
        raise SystemExit(f"No receipts with a .json ground truth in {args.directory}")

    print("OCR capabilities:", ocr_service.capabilities())
    correct = {f: 0 for f in FIELDS}
    scored = {f: 0 for f in FIELDS}
    seconds = 0.0

    for path in cases:
        expected = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
        start = time.perf_counter()
        result = ocr_service.analyse(path.read_bytes(), _CONTENT_TYPES[path.suffix.lower()])
        seconds += time.perf_counter() - start
        actual = _actual(result)

        misses = []
        for field in FIELDS:
            if field not in expected:
                continue
            scored[field] += 1
            if _matches(field, expected[field], actual[field]):
                correct[field] += 1
            else:
                misses.append(f"{field}: expected {expected[field]!r}, got {actual[field]!r}")
        status = "OK  " if not misses else "MISS"
        print(f"{status} {path.name}  (amount from {result.get('amount_source')}, "
              f"confirmed={result.get('amount_confirmed')}, confidence={result.get('confidence')})")
        if args.verbose:
            for miss in misses:
                print("       ", miss)

    print()
    print(f"{'field':<10}{'accuracy':>10}")
    for field in FIELDS:
        if scored[field]:
            print(f"{field:<10}{correct[field] / scored[field]:>9.0%}  ({correct[field]}/{scored[field]})")
    print(f"\n{len(cases)} receipts, {seconds / len(cases):.1f} s per receipt")


if __name__ == "__main__":
    main()
