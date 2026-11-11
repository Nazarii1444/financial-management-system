"""
Pick the right bank parser for an uploaded file.

The format is sniffed from the bytes (banks don't keep extensions honest:
monobank's ".pdf" is a PKCS#7 container and its ".xls" is XLSX). Each bank
module exposes `parse_pdf` / `parse_csv` / `parse_xlsx` returning a
`ParsedStatement` or None when the file isn't that bank's layout. Add a bank
by writing a module with the same functions and listing it in `PARSERS`.
"""
from typing import Optional

from src.transactions.statements import monobank
from src.transactions.statements.base import ParsedStatement

PARSERS = [monobank]

MAX_FILE_BYTES = 15 * 1024 * 1024


def sniff_format(content: bytes) -> str:
    head = content[:64 * 1024]
    if b"%PDF" in head:
        return "pdf"
    if content.startswith(b"PK\x03\x04"):
        return "xlsx"
    return "csv"


def parse_statement(content: bytes) -> Optional[ParsedStatement]:
    fmt = sniff_format(content)
    for module in PARSERS:
        parser = getattr(module, f"parse_{fmt}", None)
        if parser is None:
            continue
        try:
            statement = parser(content)
        except Exception:   # a malformed file must not break detection of other banks
            statement = None
        if statement is not None:
            return statement
    return None
