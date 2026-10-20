"""Pure unit tests for template suggestions (grouping, tolerance, proposed amount)."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

from src.models import TransactionKind
from src.templates.services.suggestions import (
    normalize_name,
    proposed_amount,
    similarity_key,
    suggest_templates,
)

BASE = datetime(2026, 10, 1, 8, 0, tzinfo=timezone.utc)


def _tx(name, amount, day=0, category="food", currency="UAH", kind=TransactionKind.EXPENSE):
    return SimpleNamespace(
        name=name, amount=Decimal(str(amount)), kind=kind,
        category_name=category, currency=currency, date=BASE + timedelta(days=day),
    )


def _coffees(n, amount=65, name="Кава"):
    return [_tx(name, amount, day=i) for i in range(n)]


def test_normalize_name_ignores_case_punctuation_and_spacing():
    assert normalize_name("  Кава,  Starbucks! ") == "кава starbucks"
    assert similarity_key("КАВА", " Food ", "uah") == similarity_key("кава.", "food", "UAH")


def test_five_identical_expenses_make_a_suggestion():
    [s] = suggest_templates(_coffees(5))

    assert s.name == "Кава"
    assert s.amount == Decimal("65.00")
    assert s.count == 5
    assert s.category_name == "food"
    assert s.currency == "UAH"
    assert s.kind == TransactionKind.EXPENSE
    assert s.last_date == BASE + timedelta(days=4)
    assert s.key == "кава|food|UAH"


def test_four_occurrences_are_not_enough():
    assert suggest_templates(_coffees(4)) == []


def test_name_variants_are_grouped():
    txs = [_tx("кава", 65), _tx("Кава ", 65), _tx("КАВА", 65), _tx("Кава!", 65), _tx("Кава", 65, day=9)]

    [s] = suggest_templates(txs)
    assert s.count == 5
    assert s.name == "Кава"   # the most frequent spelling


def test_different_category_or_currency_are_separate_groups():
    txs = _coffees(3) + [_tx("Кава", 65, category="social", day=5 + i) for i in range(3)]
    txs += [_tx("Кава", 2, currency="USD", day=10 + i) for i in range(3)]
    assert suggest_templates(txs) == []


def test_small_spread_is_tolerated_and_median_proposed():
    txs = [_tx("Кава", a, day=i) for i, a in enumerate([60, 62, 65, 68, 70])]

    [s] = suggest_templates(txs)
    assert s.amount == Decimal("65.00")
    assert (s.min_amount, s.max_amount) == (Decimal("60.00"), Decimal("70.00"))


def test_most_common_amount_wins_over_median():
    txs = [_tx("Кава", a, day=i) for i, a in enumerate([65, 65, 65, 70, 72])]
    assert suggest_templates(txs)[0].amount == Decimal("65.00")


def test_outliers_are_ignored_and_can_drop_group_below_threshold():
    txs = _coffees(5) + [_tx("Кава", 400, day=20)]
    [s] = suggest_templates(txs)
    assert s.count == 5
    assert s.max_amount == Decimal("65.00")

    sparse = _coffees(4) + [_tx("Кава", 400, day=20), _tx("Кава", 500, day=21)]
    assert suggest_templates(sparse) == []


def test_income_is_ignored():
    txs = [_tx("Freelance", 100, day=i, category="freelance", kind=TransactionKind.INCOME) for i in range(6)]
    assert suggest_templates(txs) == []


def test_existing_template_and_dismissed_keys_are_skipped():
    txs = _coffees(5) + [_tx("Метро", 8, day=i, category="transportation") for i in range(6)]

    assert [s.name for s in suggest_templates(txs)] == ["Метро", "Кава"]   # sorted by count
    assert [s.name for s in suggest_templates(txs, existing_keys=["кава|food|UAH"])] == ["Метро"]
    assert suggest_templates(txs, existing_keys=["кава|food|UAH"], dismissed_keys=["метро|transportation|UAH"]) == []


def test_proposed_amount_median_is_rounded_to_cents():
    assert proposed_amount([Decimal("1.00"), Decimal("1.01"), Decimal("1.02"), Decimal("1.03")]) == Decimal("1.02")
