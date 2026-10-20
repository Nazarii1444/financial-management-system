"""
Trash: delete → restore keeps the balance exact even when FX rates change.

The DB session is a small fake; currency conversion uses a mutable rate table
so a test can "move" the rate between delete and restore.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from src.models import Transaction, TransactionKind, TransactionTrash
from src.transactions.services import trash_service

UTC = timezone.utc
NOW = datetime(2026, 10, 18, 12, tzinfo=UTC)
RATES = {"USD": 1.0, "UAH": 40.0, "EUR": 0.9}


class _Result:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return list(self.rows)


class FakeSession:
    def __init__(self, receipts=()):
        self.added, self.deleted = [], []
        self.transactions = {}
        self.receipts = list(receipts)

    def add(self, obj):
        self.added.append(obj)
        if isinstance(obj, Transaction):
            self.transactions[obj.id_] = obj

    async def delete(self, obj):
        self.deleted.append(obj)
        if isinstance(obj, Transaction):
            self.transactions.pop(obj.id_, None)
            for r in self.receipts:
                if r.transaction_id == obj.id_:
                    r.transaction_id = None

    async def flush(self):
        for i, obj in enumerate(self.added, start=500):
            if getattr(obj, "id_", None) is None:
                obj.id_ = i

    async def get(self, model, key):
        return self.transactions.get(key) if model is Transaction else None

    async def execute(self, stmt):
        entity = stmt.column_descriptions[0]
        if entity["name"] == "id_":   # select(Receipt.id_) for the tx being deleted
            tx_ids = set(self.transactions)
            return _Result([r.id_ for r in self.receipts if r.transaction_id in tx_ids])
        return _Result([r for r in self.receipts if r.transaction_id is None])


@pytest.fixture(autouse=True)
def _rates(monkeypatch):
    async def fake_convert(session, user_currency, kind, amount, tx_currency):
        value = Decimal(str(amount)) / Decimal(str(RATES[tx_currency])) * Decimal(str(RATES[user_currency]))
        value = value.quantize(Decimal("0.01"))
        return -value if kind == TransactionKind.EXPENSE else value

    async def fake_rates(session, ensure_usd=True):
        return dict(RATES)

    monkeypatch.setattr(trash_service, "convert_to_user_currency", fake_convert)
    monkeypatch.setattr(trash_service, "get_rates_map", fake_rates)
    original = dict(RATES)
    yield
    RATES.clear()
    RATES.update(original)


def _user(capital=1000.0, currency="UAH"):
    return SimpleNamespace(id_=1, default_currency=currency, capital=capital)


def _tx(**overrides):
    values = dict(id_=42, user_id=1, name="Ремонт", amount=Decimal("10.00"), kind=TransactionKind.EXPENSE,
                  category_name="repairs", currency="USD", tags=["дім"], note="плитка",
                  date=datetime(2026, 3, 5, 10, tzinfo=UTC))
    values.update(overrides)
    return Transaction(**values)


@pytest.mark.anyio
async def test_delete_moves_to_trash_and_reverts_capital():
    session, user, tx = FakeSession(), _user(capital=600.0), _tx()
    session.transactions[42] = tx

    item = await trash_service.move_to_trash(session, user, tx, now=NOW)

    assert isinstance(item, TransactionTrash)
    assert item.capital_effect == Decimal("-400.00")      # 10 USD × 40 = 400 UAH expense
    assert item.capital_currency == "UAH"
    assert item.expires_at == NOW + timedelta(days=30)
    assert item.data["name"] == "Ремонт" and item.data["kind"] == "EXPENSE"
    assert user.capital == 1000.0
    assert 42 not in session.transactions


@pytest.mark.anyio
async def test_restore_returns_exact_balance_even_after_rate_change():
    session, user, tx = FakeSession(), _user(capital=600.0), _tx()
    session.transactions[42] = tx
    item = await trash_service.move_to_trash(session, user, tx, now=NOW)
    assert user.capital == 1000.0

    RATES["UAH"] = 44.0   # hryvnia weakened while the transaction sat in the trash

    restored = await trash_service.restore_from_trash(session, user, item)

    assert user.capital == 600.0                          # not 1000 - 440
    assert restored.id_ == 42
    assert restored.amount == Decimal("10.00")
    assert restored.kind == TransactionKind.EXPENSE
    assert restored.tags == ["дім"] and restored.note == "плитка"
    assert restored.date == datetime(2026, 3, 5, 10, tzinfo=UTC)
    assert item in session.deleted


@pytest.mark.anyio
async def test_restore_relinks_receipts():
    receipt = SimpleNamespace(id_=7, user_id=1, transaction_id=42)
    session, user, tx = FakeSession([receipt]), _user(), _tx()
    session.transactions[42] = tx

    item = await trash_service.move_to_trash(session, user, tx, now=NOW)
    assert item.receipt_ids == [7]
    assert receipt.transaction_id is None

    await trash_service.restore_from_trash(session, user, item)
    assert receipt.transaction_id == 42


@pytest.mark.anyio
async def test_restore_after_default_currency_change_converts_the_stored_effect():
    session, user, tx = FakeSession(), _user(capital=600.0), _tx()
    session.transactions[42] = tx
    item = await trash_service.move_to_trash(session, user, tx, now=NOW)   # effect −400 UAH

    user.default_currency, user.capital = "USD", 25.0                       # user switched to USD
    await trash_service.restore_from_trash(session, user, item)

    assert user.capital == 15.0                                             # 25 − 400/40


@pytest.mark.anyio
async def test_restore_conflict_when_id_is_taken():
    session, user, tx = FakeSession(), _user(), _tx()
    session.transactions[42] = tx
    item = await trash_service.move_to_trash(session, user, tx, now=NOW)
    session.transactions[42] = _tx()

    with pytest.raises(HTTPException) as exc:
        await trash_service.restore_from_trash(session, user, item)
    assert exc.value.status_code == 409


def test_trash_view_shape():
    item = TransactionTrash(id_=3, user_id=1, transaction_id=42, data=trash_service.snapshot(_tx()),
                            receipt_ids=[7], capital_effect=Decimal("-400"), capital_currency="UAH",
                            deleted_at=NOW, expires_at=NOW + timedelta(days=30))
    view = trash_service.trash_view(item)
    assert view["id_"] == 3 and view["transaction_id"] == 42
    assert view["amount"] == Decimal("10.00")
    assert view["has_receipt"] is True


@pytest.mark.anyio
async def test_history_imported_without_balance_never_moves_capital():
    session, user, tx = FakeSession(), _user(capital=600.0), _tx(counts_in_balance=False, import_ref="abc")
    session.transactions[42] = tx

    item = await trash_service.move_to_trash(session, user, tx, now=NOW)
    assert item.capital_effect == Decimal("0.00")
    assert user.capital == 600.0

    restored = await trash_service.restore_from_trash(session, user, item)
    assert user.capital == 600.0
    assert restored.counts_in_balance is False and restored.import_ref == "abc"
