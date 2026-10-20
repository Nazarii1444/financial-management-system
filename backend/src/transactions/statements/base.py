"""
Common shapes and helpers for bank-statement parsers.

A parser turns a bank export (PDF / CSV / XLSX) into a `ParsedStatement`
— a list of `StatementRow`s plus period / balance metadata — without touching
the DB. Personal data from the statement header (name, tax id, passport,
address, IBAN, card numbers) is deliberately never extracted.
"""
import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import List, Optional

_CENT = Decimal("0.01")
_DASHES = {"—", "–", "-", ""}


@dataclass
class StatementRow:
    date: datetime                       # local wall-clock time from the statement (tz-aware)
    description: str
    amount: Decimal                      # signed, in the account (card) currency: −expense / +income
    currency: str                        # account currency
    mcc: Optional[str] = None
    operation_amount: Optional[Decimal] = None   # signed, in the operation currency
    operation_currency: Optional[str] = None
    rate: Optional[Decimal] = None
    commission: Optional[Decimal] = None
    cashback: Optional[Decimal] = None
    balance_after: Optional[Decimal] = None


@dataclass
class ParsedStatement:
    bank: str                            # "monobank", "generic", …
    bank_name: str
    file_format: str                     # pdf | csv | xlsx
    currency: Optional[str]
    rows: List[StatementRow]
    period_from: Optional[date] = None
    period_to: Optional[date] = None
    opening_balance: Optional[Decimal] = None
    closing_balance: Optional[Decimal] = None
    warnings: List[str] = field(default_factory=list)


def clean_text(value) -> str:
    """NFC, single spaces, no line breaks (PDF cells wrap long descriptions)."""
    text = unicodedata.normalize("NFC", str(value or ""))
    return " ".join(text.split())


def parse_decimal(value) -> Optional[Decimal]:
    """'111 876.61', '-221.0', 4.42, '—' → Decimal | None."""
    if value is None:
        return None
    if isinstance(value, (int, float, Decimal)):
        return Decimal(str(value)).quantize(_CENT)
    text = str(value).strip().replace(" ", "").replace(" ", "").replace("−", "-")
    if text in _DASHES:
        return None
    if "," in text and "." not in text:
        text = text.replace(",", ".")
    try:
        return Decimal(text).quantize(_CENT)
    except InvalidOperation:
        return None


_DATE_RE = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})(?:\s+(\d{2}):(\d{2})(?::(\d{2}))?)?")


def parse_datetime(value, tz) -> Optional[datetime]:
    """'18.10.2026 15:31:58' (or with a line break) → aware datetime in *tz*."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=tz)
    m = _DATE_RE.search(clean_text(value))
    if not m:
        return None
    d, mo, y, h, mi, s = m.groups()
    naive = datetime(int(y), int(mo), int(d), int(h or 0), int(mi or 0), int(s or 0))
    return naive.replace(tzinfo=tz) if not hasattr(tz, "localize") else tz.localize(naive)


def parse_date(value) -> Optional[date]:
    m = _DATE_RE.search(clean_text(value))
    return date(int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else None


def row_ref(bank: str, row: StatementRow) -> str:
    """
    Stable fingerprint of a statement row, identical for the PDF, CSV and XLSX
    export of the same operation — used to skip rows imported before.
    """
    key = "|".join([
        bank,
        row.date.strftime("%Y-%m-%dT%H:%M:%S"),
        f"{row.amount:.2f}",
        clean_text(row.description).casefold(),
        "" if row.balance_after is None else f"{row.balance_after:.2f}",
    ])
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:40]
