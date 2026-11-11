"""
Unit tests for template → transaction creation.

The DB session is a minimal fake and currency conversion is stubbed, so these
tests cover the amount override, date, capital update and error paths only.
"""

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from src.models import TransactionKind, TransactionTemplate
from src.templates.services.template_service import normalize_currency, use_template
from src.transactions.services import transaction_service

UTC = timezone.utc
NOW = datetime(2026, 10, 18, 8, 30, tzinfo=UTC)


class _FakeSession:
    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        for i, obj in enumerate(self.added, start=1):
            if getattr(obj, "id_", None) is None:
                obj.id_ = 100 + i


@pytest.fixture(autouse=True)
def _stub_converter(monkeypatch):
    async def fake_convert(session, user_currency, kind, amount, tx_currency):
        if tx_currency not in {"UAH", "USD", "EUR"}:
            raise ValueError(f"Rate for source currency '{tx_currency}' not found")
        value = Decimal(str(amount))
        return -value if kind == TransactionKind.EXPENSE else value

    monkeypatch.setattr(transaction_service, "convert_to_user_currency", fake_convert)


def _user():
    return SimpleNamespace(id_=1, default_currency="UAH", capital=1000.0)


def _template(**overrides):
    values = dict(
        id_=5, user_id=1, name="Кава", amount=Decimal("65.00"), kind=TransactionKind.EXPENSE,
        category_name="food", currency="UAH", tags=["coffee"], note="ранкова", use_count=0,
    )
    values.update(overrides)
    return TransactionTemplate(**values)


@pytest.mark.anyio
async def test_use_template_creates_transaction_dated_now():
    session, user, template = _FakeSession(), _user(), _template()

    tx = await use_template(session, user, template, now=NOW)

    assert session.added == [tx]
    assert tx.id_ is not None
    assert tx.user_id == 1
    assert tx.name == "Кава"
    assert tx.amount == Decimal("65.00")
    assert tx.kind == TransactionKind.EXPENSE
    assert tx.category_name == "food"
    assert tx.currency == "UAH"
    assert tx.tags == ["coffee"]
    assert tx.note == "ранкова"
    assert tx.date == NOW
    assert user.capital == pytest.approx(935.0)
    assert template.use_count == 1
    assert template.last_used_at == NOW


@pytest.mark.anyio
async def test_default_date_is_current_time():
    before = datetime.now(UTC)
    tx = await use_template(_FakeSession(), _user(), _template())
    assert before <= tx.date <= datetime.now(UTC)


@pytest.mark.anyio
async def test_amount_override_does_not_touch_template_by_default():
    user, template = _user(), _template()

    tx = await use_template(_FakeSession(), user, template, amount=Decimal("72.50"), now=NOW)

    assert tx.amount == Decimal("72.50")
    assert user.capital == pytest.approx(927.5)
    assert template.amount == Decimal("65.00")


@pytest.mark.anyio
async def test_amount_override_can_be_remembered():
    template = _template()
    await use_template(_FakeSession(), _user(), template, amount=Decimal("72.50"), now=NOW, remember_amount=True)
    assert template.amount == Decimal("72.50")


@pytest.mark.anyio
async def test_income_template_increases_capital():
    user = _user()
    template = _template(name="Зарплата", amount=Decimal("500"), kind=TransactionKind.INCOME, category_name="salary")

    await use_template(_FakeSession(), user, template, now=NOW)

    assert user.capital == pytest.approx(1500.0)


@pytest.mark.anyio
async def test_invalid_category_is_rejected_without_side_effects():
    session, user, template = _FakeSession(), _user(), _template(category_name="salary")

    with pytest.raises(HTTPException) as exc:
        await use_template(session, user, template, now=NOW)

    assert exc.value.status_code == 422
    assert session.added == []
    assert user.capital == 1000.0
    assert template.use_count == 0


@pytest.mark.anyio
async def test_missing_rate_is_422():
    session, template = _FakeSession(), _template(currency="PLN")

    with pytest.raises(HTTPException) as exc:
        await use_template(session, _user(), template, now=NOW)

    assert exc.value.status_code == 422
    assert session.added == []


def test_normalize_currency():
    user = _user()
    assert normalize_currency(None, user) == "UAH"
    assert normalize_currency(" usd ", user) == "USD"
    with pytest.raises(HTTPException) as exc:
        normalize_currency("BTC", user)
    assert exc.value.status_code == 422
