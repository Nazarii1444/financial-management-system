"""
Unit tests for receipt → transaction creation.

The DB session is a minimal fake and currency conversion is stubbed, so these
tests cover the draft/override merge, linking and error paths only.
"""

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from src.files.schemas import ReceiptTransactionCreate
from src.files.services import ocr_service, receipt_parser
from src.files.services.receipt_transaction_service import build_draft, create_transaction_from_receipt
from src.models import Receipt, TransactionKind
from src.transactions.services import transaction_service
from tests.files import receipt_samples as samples

UTC = timezone.utc
UPLOADED = datetime(2026, 10, 11, 12, 0, tzinfo=UTC)


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


def _receipt(text, transaction_id=None):
    return Receipt(
        id_=7,
        user_id=1,
        transaction_id=transaction_id,
        original_filename="r.jpg",
        stored_filename="x.jpg",
        file_path="1/x.jpg",
        content_type="image/jpeg",
        file_size=10,
        ocr_result={"raw_text": text} if text is not None else None,
        created_at=UPLOADED,
    )


# ── Draft ─────────────────────────────────────────────────────────────────────

def test_draft_from_receipt():
    draft = build_draft(_receipt(samples.UA_ATB), _user())

    assert draft.amount == Decimal("103.38")
    assert draft.name == "АТБ"
    assert draft.category_name == "food"
    assert draft.currency == "UAH"            # not printed → user's default
    assert draft.kind == TransactionKind.EXPENSE
    assert draft.tags == ["receipt"]
    assert draft.is_complete is True
    assert draft.confidence == "high"


def test_draft_without_ocr_has_defaults():
    draft = build_draft(_receipt(None), _user())

    assert draft.amount is None
    assert draft.is_complete is False
    assert draft.name == "Receipt"
    assert draft.category_name == receipt_parser.FALLBACK_CATEGORY
    assert draft.confidence == "none"


# ── Create ────────────────────────────────────────────────────────────────────

@pytest.mark.anyio
async def test_one_click_confirm_uses_draft_and_links_receipt():
    session, user, receipt = _FakeSession(), _user(), _receipt(samples.UA_FUEL)

    tx = await create_transaction_from_receipt(session, user, receipt, ReceiptTransactionCreate())

    assert tx.amount == Decimal("2402.13")
    assert tx.name == "WOG"
    assert tx.category_name == "car"
    assert tx.currency == "UAH"
    assert tx.date == datetime(2026, 10, 5, 12, tzinfo=UTC)
    assert tx.tags == ["receipt"]
    assert receipt.transaction_id == tx.id_
    assert user.capital == pytest.approx(1000.0 - 2402.13)


@pytest.mark.anyio
async def test_user_edits_override_draft():
    session, user, receipt = _FakeSession(), _user(), _receipt(samples.UA_ATB)
    edits = ReceiptTransactionCreate(
        amount=Decimal("99.99"), name="Groceries", category_name="Shopping", tags=["Weekly"], note=None,
    )

    tx = await create_transaction_from_receipt(session, user, receipt, edits)

    assert tx.amount == Decimal("99.99")
    assert tx.name == "Groceries"
    assert tx.category_name == "shopping"
    assert tx.tags == ["weekly"]
    assert tx.date == datetime(2026, 3, 12, 18, 42, 7, tzinfo=UTC)   # untouched → from draft


@pytest.mark.anyio
async def test_explicit_null_for_required_field_keeps_draft_value():
    session, user, receipt = _FakeSession(), _user(), _receipt(samples.UA_ATB)

    tx = await create_transaction_from_receipt(
        session, user, receipt, ReceiptTransactionCreate.model_validate({"amount": None, "date": None}),
    )

    assert tx.amount == Decimal("103.38")
    assert tx.date is None                    # cleared → DB server default (now)


@pytest.mark.anyio
async def test_already_linked_receipt_is_rejected():
    receipt = _receipt(samples.UA_ATB, transaction_id=55)

    with pytest.raises(HTTPException) as exc:
        await create_transaction_from_receipt(_FakeSession(), _user(), receipt, ReceiptTransactionCreate())

    assert exc.value.status_code == 409


@pytest.mark.anyio
async def test_missing_amount_requires_user_input():
    session, user, receipt = _FakeSession(), _user(), _receipt(samples.GARBLED)

    with pytest.raises(HTTPException) as exc:
        await create_transaction_from_receipt(session, user, receipt, ReceiptTransactionCreate())
    assert exc.value.status_code == 422
    assert receipt.transaction_id is None

    tx = await create_transaction_from_receipt(
        session, user, receipt, ReceiptTransactionCreate(amount=Decimal("15.00")),
    )
    assert tx.amount == Decimal("15.00")
    assert tx.name == "Receipt"


@pytest.mark.anyio
async def test_invalid_category_is_rejected():
    with pytest.raises(HTTPException) as exc:
        await create_transaction_from_receipt(
            _FakeSession(), _user(), _receipt(samples.UA_ATB),
            ReceiptTransactionCreate(category_name="salary"),
        )
    assert exc.value.status_code == 422


@pytest.mark.anyio
async def test_unknown_currency_rate_is_a_422_not_a_500():
    with pytest.raises(HTTPException) as exc:
        await create_transaction_from_receipt(
            _FakeSession(), _user(), _receipt(samples.UA_ATB), ReceiptTransactionCreate(currency="JPY"),
        )
    assert exc.value.status_code == 422


def test_draft_uses_every_stored_ocr_pass():
    # Each pass alone is incomplete; the draft re-parses all of them, not only raw_text.
    receipt = _receipt(None)
    receipt.ocr_result = ocr_service.result_from_passes(samples.UA_MCDONALDS_PHOTO2_PASSES, UPLOADED)
    draft = build_draft(receipt, _user())

    assert draft.amount == Decimal("83.00")
    assert draft.name == "McDonald's"
    assert draft.category_name == "food"
    assert draft.date == datetime(2026, 10, 3, 10, 37, tzinfo=UTC)
    assert draft.retake_recommended is False
