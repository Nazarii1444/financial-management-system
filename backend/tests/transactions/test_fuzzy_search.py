"""Pure tests for typo-tolerant search matching and search totals."""

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from src.models import TransactionKind
from src.transactions.services.fuzzy import damerau_levenshtein, match_score, normalize, token_score
from src.transactions.services.search_service import SearchHit, convert, searchable_fields, totals


def _tx(name, note=None, category="repairs", tags=(), amount="100", currency="UAH", kind=TransactionKind.EXPENSE):
    return SimpleNamespace(name=name, note=note, category_name=category, tags=list(tags),
                           amount=Decimal(amount), currency=currency, kind=kind,
                           date=datetime(2026, 3, 10, tzinfo=timezone.utc))


def _matches(query, tx):
    return match_score(query, searchable_fields(tx)) > 0


def test_normalize():
    assert normalize("  Кавʼярня «Львівська», ДНІПРО! ") == "кавярня львівська дніпро"


@pytest.mark.parametrize("a, b, d", [("ремонт", "ремонт", 0), ("ремнот", "ремонт", 1), ("рмонт", "ремонт", 1),
                                     ("ремонтт", "ремонт", 1), ("kitten", "sitting", 3)])
def test_damerau_levenshtein(a, b, d):
    assert damerau_levenshtein(a, b) == d


@pytest.mark.parametrize("query", ["ремонт", "РЕМОНТ", "Ремонт", "ремнот", "рмонт", "ремонту", "ремон", "htvjyn"])
def test_repair_queries_find_the_transaction(query):
    assert _matches(query, _tx("Ремонт ванної", category="home"))


def test_category_display_name_is_searchable():
    # "ремонт" finds a transaction in the "repairs" category even if the name doesn't say so
    assert _matches("ремонт", _tx("Плитка Епіцентр", category="repairs"))
    assert _matches("repairs", _tx("Плитка Епіцентр", category="repairs"))


def test_note_and_tags_are_searchable():
    assert _matches("сантехнік", _tx("Виклик майстра", note="Сантехнік, заміна змішувача", category="home"))
    assert _matches("дача", _tx("Цемент", category="home", tags=["дача"]))


def test_every_word_must_match():
    tx = _tx("Ремонт авто", category="car")
    assert _matches("ремонт авто", tx)
    assert not _matches("ремонт квартири", tx)


def test_short_tokens_need_exact_prefix():
    assert not _matches("рем", _tx("Кава", category="food"))
    assert _matches("кав", _tx("Кава", category="food"))


def test_unrelated_text_does_not_match():
    assert not _matches("ремонт", _tx("Кава", category="food"))
    assert not _matches("зарплата", _tx("Ремонт", category="repairs"))


def test_exact_match_scores_higher_than_typo():
    exact = token_score("ремонт", ["ремонт"])
    typo = token_score("ремнот", ["ремонт"])
    assert exact == 1.0 and 0 < typo < exact


def test_empty_query_matches_everything():
    assert match_score("", searchable_fields(_tx("anything"))) == 1.0


def test_convert_and_totals():
    rates = {"USD": 1.0, "UAH": 41.5, "EUR": 0.92}
    assert convert(Decimal("100"), "USD", "UAH", rates) == Decimal("4150.00")
    assert convert(Decimal("10"), "GBP", "UAH", rates) == Decimal("0")

    user = SimpleNamespace(default_currency="UAH")
    hits = [
        SearchHit(_tx("a", amount="100"), False, 1),
        SearchHit(_tx("b", amount="10", currency="USD"), False, 1),
        SearchHit(_tx("c", amount="1000", kind=TransactionKind.INCOME, category="salary"), False, 1),
        SearchHit(_tx("d", amount="5", kind=TransactionKind.TRANSFER, category="transfer"), False, 1),
    ]
    assert totals(hits, user, rates) == {"expense": 515.0, "income": 1000.0, "net": 485.0, "currency": "UAH"}
