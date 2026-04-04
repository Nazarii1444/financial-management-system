"""
Transaction import from CSV / Excel (.xlsx).

Expected columns (case-insensitive header):
  name*, amount*, kind* (EXPENSE | INCOME | TRANSFER),
  category_name*, currency, date (ISO-8601), tags (pipe- or comma-separated), note

* required
"""
import csv
import io
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, List, Optional, Tuple

from dateutil import parser as dateutil_parser
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.database import get_db
from src.dependencies import get_current_user
from src.models import Transaction, TransactionKind, User
from src.transactions.currency_converter import convert_to_user_currency
from src.transactions.transaction_router import _validate_category

try:
    import openpyxl
    _OPENPYXL_AVAILABLE = True
except ImportError:
    openpyxl = None          # type: ignore[assignment]
    _OPENPYXL_AVAILABLE = False

import_router = APIRouter()

_REQUIRED_COLUMNS = {"name", "amount", "kind", "category_name"}
_ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}


# ── Parsers ──────────────────────────────────────────────────────────────────

def _parse_kind(raw: str) -> TransactionKind:
    raw = raw.strip().upper()
    mapping = {
        "EXPENSE": TransactionKind.EXPENSE,
        "0": TransactionKind.EXPENSE,
        "INCOME": TransactionKind.INCOME,
        "1": TransactionKind.INCOME,
        "TRANSFER": TransactionKind.TRANSFER,
        "2": TransactionKind.TRANSFER,
    }
    if raw not in mapping:
        raise ValueError(f"Unknown kind '{raw}'; use EXPENSE, INCOME, or TRANSFER")
    return mapping[raw]


def _parse_tags(raw: Optional[str]) -> List[str]:
    if not raw:
        return []
    sep = "|" if "|" in raw else ","
    return [t.strip().lower() for t in raw.split(sep) if t.strip()]


def _parse_date(raw: Optional[str]) -> Optional[datetime]:
    if not raw:
        return None
    try:
        dt = dateutil_parser.parse(str(raw))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _parse_rows(rows: List[Dict[str, Any]]) -> Tuple[List[Dict], List[str]]:
    """Returns (valid_rows, error_messages)."""
    valid: List[Dict] = []
    errors: List[str] = []

    for i, row in enumerate(rows, start=2):          # row 1 = header
        row = {k.strip().lower(): v for k, v in row.items() if k}
        missing = _REQUIRED_COLUMNS - set(row.keys())
        if missing:
            errors.append(f"Row {i}: missing columns {missing}")
            continue

        # amount
        try:
            amount = Decimal(str(row["amount"]).strip())
            if amount <= 0:
                raise ValueError
        except (InvalidOperation, ValueError):
            errors.append(f"Row {i}: invalid amount '{row['amount']}'")
            continue

        # kind
        try:
            kind = _parse_kind(str(row["kind"]))
        except ValueError as e:
            errors.append(f"Row {i}: {e}")
            continue

        name = str(row.get("name", "")).strip()[:64] or "Import"
        category = str(row.get("category_name", "")).strip().lower()
        currency = str(row.get("currency", "")).strip().upper() or None
        date = _parse_date(row.get("date"))
        tags = _parse_tags(str(row.get("tags", "")))
        note_raw = row.get("note")
        note = str(note_raw).strip()[:512] if note_raw else None

        # category validation (soft — errors collected but import still proceeds)
        try:
            _validate_category(kind, category)
        except HTTPException as exc:
            errors.append(f"Row {i}: {exc.detail}")
            continue

        valid.append({
            "name": name,
            "amount": amount,
            "kind": kind,
            "category_name": category,
            "currency": currency,
            "date": date,
            "tags": tags,
            "note": note,
        })

    return valid, errors


def _csv_to_rows(content: bytes) -> List[Dict[str, Any]]:
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    return [dict(r) for r in reader]


def _xlsx_to_rows(content: bytes) -> List[Dict[str, Any]]:
    if not _OPENPYXL_AVAILABLE:
        raise HTTPException(status_code=501, detail="openpyxl not installed; Excel import unavailable")
    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)
    headers = [str(h).strip() if h is not None else "" for h in next(rows_iter)]
    result = []
    for row in rows_iter:
        result.append({headers[j]: row[j] for j in range(len(headers))})
    wb.close()
    return result


# ── Endpoint ─────────────────────────────────────────────────────────────────

@import_router.post("", status_code=status.HTTP_201_CREATED)
async def import_transactions(
    file: UploadFile = File(..., description="CSV or Excel (.xlsx) file"),
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Import transactions from a CSV or Excel file.

    Returns the count of created transactions plus a list of row-level errors
    for rows that were skipped.
    """
    filename = (file.filename or "").lower()
    ext = next((e for e in _ALLOWED_EXTENSIONS if filename.endswith(e)), None)
    if not ext:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported file type. Allowed: {sorted(_ALLOWED_EXTENSIONS)}",
        )

    content = await file.read()

    if ext == ".csv":
        raw_rows = _csv_to_rows(content)
    else:
        raw_rows = _xlsx_to_rows(content)

    if not raw_rows:
        raise HTTPException(status_code=422, detail="File is empty or has no rows after the header")

    valid_rows, parse_errors = _parse_rows(raw_rows)

    created_txs: List[Transaction] = []
    for row in valid_rows:
        currency = row["currency"] or current_user.default_currency
        try:
            val = await convert_to_user_currency(
                session, current_user.default_currency, row["kind"], row["amount"], currency
            )
            current_user.capital = round(float(current_user.capital) + float(val), 2)
        except Exception as exc:
            parse_errors.append(f"Currency conversion failed for row '{row['name']}': {exc}")
            continue

        tx = Transaction(
            user_id=current_user.id_,
            name=row["name"],
            amount=row["amount"],
            kind=row["kind"],
            category_name=row["category_name"],
            currency=row["currency"],
            tags=row["tags"],
            note=row["note"],
            **({"date": row["date"]} if row["date"] else {}),
        )
        session.add(tx)
        created_txs.append(tx)

    if created_txs:
        await session.commit()
        await session.refresh(current_user)

    return {
        "imported": len(created_txs),
        "skipped": len(parse_errors),
        "errors": parse_errors,
        "new_capital": current_user.capital,
    }

