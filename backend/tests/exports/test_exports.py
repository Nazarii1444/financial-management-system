"""CSV export round-trip, recurring annualisation and PDF rendering (text extracted with pdfplumber)."""

import csv
import io
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pdfplumber
import pytest

from src.exports import crypto, pdf, reports
from src.exports.csv_export import transactions_csv
from src.models import RecurringFrequency, TransactionKind
from src.transactions.import_router import _csv_to_rows, _parse_rows

UTC = timezone.utc


def _tx(name, amount, kind=TransactionKind.EXPENSE, category="repairs", currency="UAH", **kw):
    return SimpleNamespace(name=name, amount=Decimal(amount), kind=kind, category_name=category, currency=currency,
                           tags=kw.get("tags", []), note=kw.get("note"), date=kw.get("date", datetime(2026, 3, 5, 10, tzinfo=UTC)))


def _hit(tx, has_receipt=False):
    return SimpleNamespace(tx=tx, has_receipt=has_receipt)


def _pdf_text(data: bytes) -> str:
    with pdfplumber.open(io.BytesIO(data)) as doc:
        return "\n".join(page.extract_text() or "" for page in doc.pages)


# ── CSV ───────────────────────────────────────────────────────────────────────

def test_csv_uk_is_excel_friendly_and_reimportable():
    hits = [_hit(_tx("Ремонт; ванна", "1234.50", tags=["дім", "дача"], note="плитка"), True),
            _hit(_tx("Зарплата", "25000", TransactionKind.INCOME, "salary"))]
    text = transactions_csv(hits, "uk")

    assert text.startswith("﻿")
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿")), delimiter=";"))
    assert rows[0][:3] == ["date", "name", "amount"]
    assert rows[1][:4] == ["2026-03-05 10:00", "Ремонт; ванна", "1234,50", "UAH"]
    assert rows[1][6] == "Ремонт" and rows[1][9] == "1" and rows[1][10] == "Витрата"

    valid, errors = _parse_rows(_csv_to_rows(text.encode("utf-8")))
    assert errors == []
    assert [(r["name"], r["amount"], r["kind"]) for r in valid] == [
        ("Ремонт; ванна", Decimal("1234.50"), TransactionKind.EXPENSE),
        ("Зарплата", Decimal("25000.00"), TransactionKind.INCOME),
    ]
    assert valid[0]["tags"] == ["дім", "дача"]


def test_csv_en_uses_comma_and_decimal_point():
    text = transactions_csv([_hit(_tx("Repair", "10.5"))], "en")
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿"))))
    assert rows[1][2] == "10.50" and rows[1][6] == "Repairs" and rows[1][10] == "Expense"


# ── Recurring annualisation ───────────────────────────────────────────────────

class _IdentityMoney:
    currency = "UAH"

    def __call__(self, amount, currency):
        return Decimal(str(amount))


def _rule(id_, name, amount, frequency, kind=TransactionKind.EXPENSE, category="entertainment", active=True):
    return SimpleNamespace(id_=id_, name=name, amount=Decimal(amount), frequency=frequency, kind=kind,
                           category_name=category, currency="UAH", is_active=active,
                           next_run=datetime(2026, 11, 1, tzinfo=UTC))


def test_recurring_summary_annualises_by_frequency():
    rules = [
        _rule(1, "Netflix", "299", RecurringFrequency.MONTHLY),
        _rule(2, "Корм", "450", RecurringFrequency.BIWEEKLY, category="pets"),
        _rule(3, "Кава", "65", RecurringFrequency.DAILY, category="food"),
        _rule(4, "Домен", "600", RecurringFrequency.YEARLY, category="electronics"),
        _rule(5, "Paused", "999", RecurringFrequency.MONTHLY, active=False),
        _rule(6, "Зарплата", "25000", RecurringFrequency.MONTHLY, TransactionKind.INCOME, "salary"),
    ]
    data = reports.recurring_summary_from_rules(rules, _IdentityMoney())

    per_year = {r["name"]: r["per_year"] for r in data["expenses"]}
    assert per_year == {"Netflix": Decimal("3588.00"), "Корм": Decimal("11700.00"),
                        "Кава": Decimal("23725.00"), "Домен": Decimal("600.00")}
    assert [r["name"] for r in data["expenses"]][0] == "Кава"          # most expensive first
    assert data["expense_per_year"] == Decimal("39613.00")
    assert data["subscriptions_per_year"] == Decimal("4188.00")         # Netflix + domain (electronics)
    assert data["subscriptions_count"] == 2
    assert data["income_per_year"] == Decimal("300000.00")
    assert data["income_share"] == pytest.approx(13.2, abs=0.05)


def test_month_bounds():
    start, end = reports.month_bounds("2026-02")
    assert (start, end) == (datetime(2026, 2, 1, tzinfo=UTC), datetime(2026, 3, 1, tzinfo=UTC))
    with pytest.raises(ValueError):
        reports.month_bounds("2026/02")


# ── PDF ───────────────────────────────────────────────────────────────────────

@pytest.fixture
def _font_or_skip():
    try:
        pdf.find_fonts()
    except pdf.PdfUnavailable:
        pytest.skip("no TrueType font with Cyrillic on this machine")


def test_recurring_pdf_shows_yearly_cost(_font_or_skip):
    data = reports.recurring_summary_from_rules([
        _rule(1, "Netflix", "299", RecurringFrequency.MONTHLY),
        _rule(2, "Spotify", "169", RecurringFrequency.MONTHLY),
        _rule(3, "Оренда", "9000", RecurringFrequency.MONTHLY, category="housing"),
    ], _IdentityMoney())
    out = pdf.render_recurring(data, "tester", "uk")

    assert out.startswith(b"%PDF")
    text = _pdf_text(out)
    assert "Регулярні платежі" in text
    assert "Netflix" in text and "Оренда" in text
    assert "3 588 ₴" in text.replace(" ", " ")                    # Netflix per year
    assert "113 616 ₴" in text.replace(" ", " ")                  # all expenses per year


def test_statement_pdf_many_rows_paginates(_font_or_skip):
    rows = [{"date": datetime(2026, 3, 1, tzinfo=UTC) + timedelta(hours=i), "name": f"Покупка {i}", "category": "food",
             "kind": TransactionKind.EXPENSE, "amount": Decimal("10"), "currency": "UAH",
             "converted": Decimal("-10"), "note": None} for i in range(80)]
    data = {"month": "2026-03", "start": datetime(2026, 3, 1, tzinfo=UTC), "end": datetime(2026, 3, 31, 23, 59, 59, tzinfo=UTC),
            "currency": "UAH", "opening": Decimal("1800"), "income": Decimal("0"), "expense": Decimal("800"),
            "closing": Decimal("1000"), "count": 80, "rows": rows}
    out = pdf.render_statement(data, "tester", "en")
    with pdfplumber.open(io.BytesIO(out)) as doc:
        assert len(doc.pages) >= 2
    text = _pdf_text(out)
    assert "Monthly statement" in text and "March 2026" in text and "Покупка 79" in text


def test_expenses_and_budgets_pdf_render(_font_or_skip):
    expenses = {"start": datetime(2026, 3, 1, tzinfo=UTC), "end": datetime(2026, 3, 31, 23, 59, 59, tzinfo=UTC),
                "currency": "UAH", "total": Decimal("3000"), "previous_total": Decimal("2000"), "count": 3,
                "categories": [{"category": "repairs", "amount": Decimal("2000"), "count": 1, "share": 66.7,
                                "previous": Decimal("500"), "change": 300.0},
                               {"category": "food", "amount": Decimal("1000"), "count": 2, "share": 33.3,
                                "previous": Decimal("0"), "change": None}],
                "top": [{"date": datetime(2026, 3, 3, tzinfo=UTC), "name": "Плитка", "category": "repairs", "amount": Decimal("2000")}]}
    text = _pdf_text(pdf.render_expenses(expenses, "tester", "uk"))
    assert "Структура витрат" in text and "Ремонт" in text and "Плитка" in text

    budgets = {"month": "2026-03", "start": datetime(2026, 3, 1, tzinfo=UTC), "end": datetime(2026, 3, 31, tzinfo=UTC),
               "budgets": [{"budget_name": "Сім'я", "limit_amount": 10000.0, "actual_spent": 11500.0, "remaining": -1500.0,
                            "utilization_percent": 115.0, "by_category": [{"category": "food", "amount": 11500.0}],
                            "currency": "UAH"}]}
    text = _pdf_text(pdf.render_budgets(budgets, "tester", "uk")).replace(" ", " ")
    assert "Виконання бюджетів" in text and "115%" in text and "−1 500 ₴" in text and "перевищено ліміт" in text


# ── Passphrase-encrypted exports ──────────────────────────────────────────────

def test_encrypted_pdf_needs_the_passphrase(_font_or_skip):
    data = reports.recurring_summary_from_rules([_rule(1, "Netflix", "299", RecurringFrequency.MONTHLY)], _IdentityMoney())
    plain = pdf.render_recurring(data, "tester", "uk")
    locked = pdf.render_recurring(data, "tester", "uk", password="пароль-123")

    assert locked.startswith(b"%PDF") and b"/Encrypt" in locked
    with pytest.raises(Exception):
        _pdf_text(locked)
    with pytest.raises(Exception):
        with pdfplumber.open(io.BytesIO(locked), password="wrong-pass") as doc:
            doc.pages[0].extract_text()
    with pdfplumber.open(io.BytesIO(locked), password="пароль-123") as doc:
        unlocked = "\n".join(page.extract_text() or "" for page in doc.pages)
    # Same content apart from the generation timestamp in the footer
    assert unlocked.split("FinanceHub ·")[0] == _pdf_text(plain).split("FinanceHub ·")[0]


def test_encrypted_csv_reimports_like_plain():
    hits = [_hit(_tx("Ремонт; ванна", "1234.50", tags=["дім"], note="плитка")),
            _hit(_tx("Зарплата", "25000", TransactionKind.INCOME, "salary"))]
    plain = transactions_csv(hits, "uk").encode("utf-8")
    blob = crypto.encrypt(plain, "correct horse")

    assert crypto.is_encrypted(blob) and "Ремонт".encode() not in blob
    assert _parse_rows(_csv_to_rows(crypto.decrypt(blob, "correct horse"))) == _parse_rows(_csv_to_rows(plain))
