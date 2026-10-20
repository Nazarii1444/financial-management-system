"""
Template suggestions: spot expenses the user keeps repeating.

Pure functions (no DB) so the grouping rules are unit-testable. The router
loads the last `WINDOW_DAYS` of expenses plus the user's templates/dismissals
and calls `suggest_templates`.

Similarity key = normalised name + category + currency. Within a key the
amounts must be close: transactions further than `AMOUNT_TOLERANCE` from the
group's median are ignored (a one-off big "Coffee" order doesn't count, and
doesn't skew the proposed amount).
"""
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from statistics import median
from typing import Iterable, List, Optional

from src.models import TransactionKind

WINDOW_DAYS = 30
MIN_OCCURRENCES = 5
AMOUNT_TOLERANCE = Decimal("0.25")   # ±25 % of the median

_CENT = Decimal("0.01")
_NON_WORD = re.compile(r"[^\w]+", re.UNICODE)


def normalize_name(name: str) -> str:
    """'  Кава,  Starbucks! ' → 'кава starbucks' (case, punctuation and spacing ignored)."""
    return " ".join(_NON_WORD.sub(" ", (name or "").casefold()).split())


def similarity_key(name: str, category_name: str, currency: Optional[str]) -> str:
    return "|".join((
        normalize_name(name),
        (category_name or "").strip().lower(),
        (currency or "").strip().upper(),
    ))


@dataclass
class Suggestion:
    key: str
    name: str
    amount: Decimal
    kind: TransactionKind
    category_name: str
    currency: str
    count: int
    min_amount: Decimal
    max_amount: Decimal
    last_date: datetime


def _within_tolerance(amount: Decimal, center: Decimal) -> bool:
    if center == 0:
        return amount == 0
    return abs(amount - center) <= center * AMOUNT_TOLERANCE


def proposed_amount(amounts: List[Decimal]) -> Decimal:
    """Most common amount when it covers at least half of the group, otherwise the median."""
    value, freq = Counter(amounts).most_common(1)[0]
    if freq * 2 >= len(amounts):
        return value
    return Decimal(str(median(amounts))).quantize(_CENT, rounding=ROUND_HALF_UP)


def suggest_templates(
        transactions: Iterable,
        existing_keys: Iterable[str] = (),
        dismissed_keys: Iterable[str] = (),
        min_count: int = MIN_OCCURRENCES,
) -> List[Suggestion]:
    """
    *transactions* — objects with name, amount, kind, category_name, currency,
    date (already limited to the analysis window). Only expenses are considered.
    Keys present in *existing_keys* (templates) or *dismissed_keys* are skipped.
    """
    skip = set(existing_keys) | set(dismissed_keys)
    groups: dict = {}
    for tx in transactions:
        if tx.kind != TransactionKind.EXPENSE or not normalize_name(tx.name):
            continue
        key = similarity_key(tx.name, tx.category_name, tx.currency)
        if key not in skip:
            groups.setdefault(key, []).append(tx)

    result = []
    for key, txs in groups.items():
        if len(txs) < min_count:
            continue
        center = Decimal(str(median(Decimal(str(t.amount)) for t in txs)))
        close = [t for t in txs if _within_tolerance(Decimal(str(t.amount)), center)]
        if len(close) < min_count:
            continue

        amounts = [Decimal(str(t.amount)).quantize(_CENT) for t in close]
        latest = max(close, key=lambda t: t.date)
        # Display the spelling the user typed most often (ties → the latest one)
        spellings = Counter(t.name.strip() for t in close)
        top = max(spellings.values())
        name = latest.name.strip() if spellings[latest.name.strip()] == top else spellings.most_common(1)[0][0]

        result.append(Suggestion(
            key=key,
            name=name,
            amount=proposed_amount(amounts),
            kind=TransactionKind.EXPENSE,
            category_name=latest.category_name.strip().lower(),
            currency=(latest.currency or "").strip().upper(),
            count=len(close),
            min_amount=min(amounts),
            max_amount=max(amounts),
            last_date=latest.date,
        ))

    result.sort(key=lambda s: (-s.count, s.name.casefold()))
    return result
