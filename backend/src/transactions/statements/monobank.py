"""
monobank (АТ «Універсал Банк») card statement: PDF, CSV and XLSX exports.

All three share the same columns:
    Дата i час операції | Деталі операції | MCC | Сума в валюті картки (UAH) |
    Сума в валюті операції | Валюта | Курс | Сума комісій (UAH) |
    Сума кешбеку (UAH) | Залишок після операції

Quirks handled here:
- The PDF is wrapped in a PKCS#7 (CAdES) signature container — the actual PDF
  is extracted from inside it (`unwrap_pdf`).
- The ".xls" export is really XLSX; the table starts after a header block.
- PDF cells wrap ("18.10.2026\\n15:31:58"); amounts use spaces as thousands
  separators; empty values are "—".
- Times are Kyiv wall-clock time.
"""
import csv
import io
import re
from typing import Dict, List, Optional

from src.transactions.statements.base import (
    ParsedStatement,
    StatementRow,
    clean_text,
    parse_date,
    parse_datetime,
    parse_decimal,
)

BANK = "monobank"
BANK_NAME = "monobank"

# column key → header keywords (matched on the cleaned, lower-cased header)
_COLUMNS = {
    "date": ("дата",),
    "details": ("деталі",),
    "mcc": ("mcc",),
    "amount": ("валюті картки",),
    "op_amount": ("валюті операції",),
    "currency": ("валюта",),
    "rate": ("курс",),
    "commission": ("комісій",),
    "cashback": ("кешбеку",),
    "balance": ("залишок",),
}
_REQUIRED = {"date", "details", "amount"}
_CURRENCY_IN_HEADER = re.compile(r"\(([A-Z]{3})\)")


def _kyiv():
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo("Europe/Kyiv")
    except Exception:
        import pytz
        return pytz.timezone("Europe/Kyiv")


# ── Detection ─────────────────────────────────────────────────────────────────

def looks_like_header(cells) -> bool:
    text = " ".join(clean_text(c).lower() for c in cells if c is not None)
    return "деталі операції" in text and "mcc" in text and "валюті картки" in text


def unwrap_pdf(content: bytes) -> Optional[bytes]:
    """The PDF itself, also when wrapped in a PKCS#7 signature container."""
    if content.startswith(b"%PDF"):
        return content
    start = content.find(b"%PDF", 0, 64 * 1024)
    end = content.rfind(b"%%EOF")
    if start == -1 or end == -1 or end < start:
        return None
    return content[start:end + 5]


# ── Table → rows ──────────────────────────────────────────────────────────────

def _column_map(header) -> Dict[str, int]:
    names = [clean_text(h).lower() for h in header]
    mapping: Dict[str, int] = {}
    for key, keywords in _COLUMNS.items():
        for i, name in enumerate(names):
            if i in mapping.values():
                continue
            if key == "currency" and name != "валюта":
                continue   # "Валюта" exactly — other headers contain "валюті"
            if any(k in name for k in keywords):
                mapping[key] = i
                break
    return mapping


def _currency_from_header(header) -> Optional[str]:
    for cell in header:
        text = clean_text(cell)
        if "картки" in text.lower():
            m = _CURRENCY_IN_HEADER.search(text)
            if m:
                return m.group(1)
    return None


def rows_from_table(header, body, tz, statement: ParsedStatement) -> None:
    cols = _column_map(header)
    if not _REQUIRED <= cols.keys():
        statement.warnings.append("Unrecognised table header")
        return
    statement.currency = statement.currency or _currency_from_header(header) or "UAH"

    def cell(row, key):
        i = cols.get(key)
        return row[i] if i is not None and i < len(row) else None

    for raw in body:
        if not raw or all(c in (None, "") for c in raw):
            continue
        when = parse_datetime(cell(raw, "date"), tz)
        amount = parse_decimal(cell(raw, "amount"))
        if when is None or amount is None:
            continue   # repeated header, page footer, totals …
        op_currency = clean_text(cell(raw, "currency")).upper() or None
        statement.rows.append(StatementRow(
            date=when,
            description=clean_text(cell(raw, "details")) or "—",
            amount=amount,
            currency=statement.currency,
            mcc=clean_text(cell(raw, "mcc")) or None,
            operation_amount=parse_decimal(cell(raw, "op_amount")),
            operation_currency=op_currency if op_currency and len(op_currency) == 3 else None,
            rate=parse_decimal(cell(raw, "rate")),
            commission=parse_decimal(cell(raw, "commission")),
            cashback=parse_decimal(cell(raw, "cashback")),
            balance_after=parse_decimal(cell(raw, "balance")),
        ))


# ── Header block (period / balances only — no personal data) ─────────────────

_PERIOD = re.compile(r"Період:\s*(\d{2}\.\d{2}\.\d{4})\s*[-–—]\s*(\d{2}\.\d{2}\.\d{4})")
_OPENING = re.compile(r"Баланс на початок періоду:\s*([\d\s .,−-]+)\s*([A-Z]{3})")
_CLOSING = re.compile(r"Баланс на кінець періоду:\s*([\d\s .,−-]+)\s*([A-Z]{3})")


def _read_header_block(text: str, statement: ParsedStatement) -> None:
    m = _PERIOD.search(text)
    if m:
        statement.period_from, statement.period_to = parse_date(m.group(1)), parse_date(m.group(2))
    m = _OPENING.search(text)
    if m:
        statement.opening_balance = parse_decimal(m.group(1))
        statement.currency = statement.currency or m.group(2)
    m = _CLOSING.search(text)
    if m:
        statement.closing_balance = parse_decimal(m.group(1))


def _new(file_format: str) -> ParsedStatement:
    return ParsedStatement(bank=BANK, bank_name=BANK_NAME, file_format=file_format, currency=None, rows=[])


# ── Formats ───────────────────────────────────────────────────────────────────

def parse_pdf(content: bytes) -> Optional[ParsedStatement]:
    import pdfplumber

    pdf_bytes = unwrap_pdf(content)
    if pdf_bytes is None:
        return None
    tz = _kyiv()
    statement = _new("pdf")
    header = None
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as doc:
        first_text = (doc.pages[0].extract_text() or "") if doc.pages else ""
        _read_header_block(first_text, statement)
        for page in doc.pages:
            for table in page.extract_tables():
                if not table:
                    continue
                body = table
                if looks_like_header(table[0]):
                    header, body = table[0], table[1:]
                if header is not None:
                    rows_from_table(header, body, tz, statement)
    if header is None:
        return None
    return statement


def _rows_with_header(rows: List[list], text_before: str, file_format: str) -> Optional[ParsedStatement]:
    index = next((i for i, r in enumerate(rows) if looks_like_header(r)), None)
    if index is None:
        return None
    statement = _new(file_format)
    _read_header_block(text_before, statement)
    rows_from_table(rows[index], rows[index + 1:], _kyiv(), statement)
    return statement


def parse_csv(content: bytes) -> Optional[ParsedStatement]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("cp1251", errors="replace")
    first = text.split("\n", 1)[0]
    delimiter = ";" if first.count(";") > first.count(",") else ","
    rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
    return _rows_with_header(rows, "", "csv")


def parse_xlsx(content: bytes) -> Optional[ParsedStatement]:
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    try:
        rows = [list(r) for r in wb.worksheets[0].iter_rows(values_only=True)]
    finally:
        wb.close()
    header_text = "\n".join(str(r[0]) for r in rows if r and r[0] is not None and not looks_like_header(r))
    return _rows_with_header(rows, header_text, "xlsx")
