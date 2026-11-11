"""
Transactions → CSV for Excel.

Column names match the importer (`name, amount, kind, category_name,
currency, date, tags, note`), so an export can be imported back. Excel opens
the file directly: UTF-8 BOM, and for `uk` the delimiter is `;` with a decimal
comma (what Excel expects under Ukrainian regional settings); `en` uses `,`
and a decimal point.
"""
import csv
import io
from decimal import Decimal
from typing import Iterable

from src.calendar_export.formatting import CATEGORY_NAMES, normalize_lang

HEADER = ["date", "name", "amount", "currency", "kind", "category_name", "category", "tags", "note", "has_receipt"]
KIND_LABELS = {
    "uk": {"EXPENSE": "Витрата", "INCOME": "Дохід", "TRANSFER": "Переказ"},
    "en": {"EXPENSE": "Expense", "INCOME": "Income", "TRANSFER": "Transfer"},
}


def _number(value, decimal_comma: bool) -> str:
    text = f"{Decimal(str(value)):.2f}"
    return text.replace(".", ",") if decimal_comma else text


def transactions_csv(hits: Iterable, lang: str = "uk") -> str:
    """*hits* — SearchHit-like objects (`.tx`, `.has_receipt`)."""
    lang = normalize_lang(lang)
    uk = lang == "uk"
    out = io.StringIO()
    out.write("﻿")  # BOM: Excel detects UTF-8 (Cyrillic) correctly
    writer = csv.writer(out, delimiter=";" if uk else ",", lineterminator="\r\n")
    writer.writerow(HEADER + ["kind_label"])
    for hit in hits:
        tx = hit.tx
        writer.writerow([
            tx.date.strftime("%Y-%m-%d %H:%M") if tx.date else "",
            tx.name,
            _number(tx.amount, uk),
            tx.currency or "",
            tx.kind.name,
            tx.category_name,
            CATEGORY_NAMES[lang].get(tx.category_name, tx.category_name),
            ", ".join(tx.tags or []),
            tx.note or "",
            "1" if hit.has_receipt else "0",
            KIND_LABELS[lang][tx.kind.name],
        ])
    return out.getvalue()
