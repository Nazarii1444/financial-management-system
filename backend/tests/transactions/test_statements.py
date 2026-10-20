"""
Bank-statement import: monobank PDF / CSV / XLSX parsing, MCC classification,
row fingerprints and the confirm step.

Fixtures are synthetic (fake people / numbers) and generated in the test.
Real statements contain personal data and are never committed; if someone
drops one into tests/files/fixtures/report_* locally, `test_real_statements_*`
cross-checks the three formats against each other.
"""
import glob
import io
import os
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import openpyxl
import pytest

from src.exports import pdf as pdf_module
from src.models import Transaction, TransactionKind
from src.transactions.statements import monobank, service
from src.transactions.statements.base import parse_decimal, row_ref
from src.transactions.statements.detect import parse_statement, sniff_format
from src.transactions.statements.mcc import category_for_mcc, classify
from src.transactions.statements.schemas import StatementImportRow
from src.transactions.services import transaction_service

HEADER = ["Дата i час операції", "Деталі операції", "MCC", "Сума в валюті картки (UAH)", "Сума в валюті операції",
          "Валюта", "Курс", "Сума комісій (UAH)", "Сума кешбеку (UAH)", "Залишок після операції"]
ROWS = [
    ["17.03.2026 19:05:11", "Сільпо", "5411", "-845.30", "-845.30", "UAH", "—", "—", "8.45", "15 154.70"],
    ["16.03.2026 12:00:00", "Steam", "5816", "-415.00", "-10.00", "USD", "41.5000", "—", "—", "16 000.00"],
    ["15.03.2026 09:30:00", "Від: Тестовий Платник", "4829", "1000.00", "1000.00", "UAH", "—", "—", "—", "16 415.00"],
    ["14.03.2026 08:00:00", "Укрзалізниця", "4112", "-585.00", "-585.00", "UAH", "—", "10.00", "—", "15 415.00"],
    ["13.03.2026 18:20:00", "На чорну картку", "4829", "-1000.00", "-1000.00", "UAH", "—", "—", "—", "16 000.00"],
    ["12.03.2026 10:00:00", "Зарплата за лютий ТОВ Ромашка", "4829", "20000.00", "20000.00", "UAH", "—", "—", "—", "17 000.00"],
]
HEADER_BLOCK = ["Клієнт: Тестовий Клієнт", "Період: 12.03.2026 – 17.03.2026",
                "Баланс на початок періоду: 0.00 UAH", "Баланс на кінець періоду: 15 154.70 UAH"]


def _csv_bytes() -> bytes:
    def q(v):
        return f'"{v}"'
    lines = [",".join(q(h) for h in HEADER)] + [",".join(q(c) for c in r) for r in ROWS]
    return ("\n".join(lines) + "\n").encode("utf-8")


def _xlsx_bytes() -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    for line in HEADER_BLOCK:
        ws.append([line])
        ws.append([])
    ws.append(HEADER)
    for r in ROWS:
        ws.append([r[0], r[1], r[2], float(parse_decimal(r[3])), float(parse_decimal(r[4])), r[5], r[6],
                   r[7], float(parse_decimal(r[8])) if r[8] != "—" else "—", float(parse_decimal(r[9]))])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _pdf_bytes() -> bytes:
    from fpdf import FPDF

    regular, bold = pdf_module.find_fonts()
    doc = FPDF(orientation="L")
    doc.add_font("Main", "", regular)
    doc.add_font("Main", "B", bold)
    doc.set_font("Main", size=7)
    doc.add_page()
    for line in HEADER_BLOCK:
        doc.cell(0, 5, line, new_x="LMARGIN", new_y="NEXT")
    with doc.table(col_widths=(26, 50, 12, 24, 24, 14, 16, 20, 20, 26)) as table:
        table.row(HEADER)
        for r in ROWS:
            table.row([r[0].replace(" ", "\n", 1), *r[1:]])
    # monobank wraps the PDF into a PKCS#7 signature container
    return b"0\x82\x03\x00\x06\t*\x86H\x86\xf7\r\x01\x07\x02" + bytes(doc.output()) + b"\x00signature"


@pytest.fixture
def _font_or_skip():
    try:
        pdf_module.find_fonts()
    except pdf_module.PdfUnavailable:
        pytest.skip("no TrueType font with Cyrillic on this machine")


# ── Parsing ───────────────────────────────────────────────────────────────────

def _check(statement):
    assert statement.bank == "monobank"
    assert statement.currency == "UAH"
    assert len(statement.rows) == 6
    first = statement.rows[0]
    assert first.description == "Сільпо"
    assert first.amount == Decimal("-845.30")
    assert first.mcc == "5411"
    assert first.cashback == Decimal("8.45")
    assert first.balance_after == Decimal("15154.70")
    assert first.date.strftime("%Y-%m-%d %H:%M:%S") == "2026-03-17 19:05:11"
    assert first.date.utcoffset().total_seconds() == 2 * 3600       # Kyiv, winter time
    steam = statement.rows[1]
    assert (steam.operation_amount, steam.operation_currency, steam.rate) == (Decimal("-10.00"), "USD", Decimal("41.50"))
    assert statement.rows[3].commission == Decimal("10.00")


def test_parse_csv():
    content = _csv_bytes()
    assert sniff_format(content) == "csv"
    _check(parse_statement(content))


def test_parse_xlsx_with_header_block():
    statement = parse_statement(_xlsx_bytes())
    assert statement.file_format == "xlsx"
    _check(statement)
    assert str(statement.period_from) == "2026-03-12" and str(statement.period_to) == "2026-03-17"
    assert statement.closing_balance == Decimal("15154.70")


def test_parse_pdf_inside_pkcs7_container(_font_or_skip):
    content = _pdf_bytes()
    assert not content.startswith(b"%PDF") and sniff_format(content) == "pdf"
    statement = parse_statement(content)
    assert statement.file_format == "pdf"
    _check(statement)
    assert statement.opening_balance == Decimal("0.00")


def test_same_operation_has_the_same_fingerprint_in_every_format(_font_or_skip):
    refs = [[row_ref("monobank", r) for r in parse_statement(c).rows] for c in (_csv_bytes(), _xlsx_bytes(), _pdf_bytes())]
    assert refs[0] == refs[1] == refs[2]
    assert len(set(refs[0])) == 6


def test_unknown_files_are_not_mistaken_for_monobank():
    assert parse_statement(b"name,amount,kind,category_name\nCoffee,10,EXPENSE,food\n") is None
    assert monobank.unwrap_pdf(b"no pdf here") is None


@pytest.mark.skipif(not glob.glob(os.path.join(os.path.dirname(__file__), "..", "files", "fixtures", "report_*")),
                    reason="real statements are local-only")
def test_real_statements_agree_across_formats():
    files = glob.glob(os.path.join(os.path.dirname(__file__), "..", "files", "fixtures", "report_*"))
    parsed = [parse_statement(open(f, "rb").read()) for f in files]
    assert all(p is not None and p.bank == "monobank" and p.rows for p in parsed)
    refs = {tuple(sorted(row_ref("monobank", r) for r in p.rows)) for p in parsed}
    assert len(refs) == 1


# ── Classification ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("mcc, category", [("5411", "food"), ("5814", "food"), ("4111", "transportation"),
                                           ("5542", "car"), ("5912", "health"), ("5816", "entertainment"),
                                           ("4814", "phone"), ("0742", "pets"), ("9999", None), (None, None)])
def test_category_for_mcc(mcc, category):
    assert category_for_mcc(mcc) == category


def test_classify_rows():
    assert classify(-1, "5411", "Сільпо") == (TransactionKind.EXPENSE, "food")
    assert classify(-1, "6011", "Банкомат") == (TransactionKind.TRANSFER, "transfer")
    assert classify(-1, "4829", "На чорну картку") == (TransactionKind.TRANSFER, "transfer")
    assert classify(1, "4829", "Зарплата за лютий") == (TransactionKind.INCOME, "salary")
    assert classify(1, None, "Виведення кешбеку") == (TransactionKind.INCOME, "bonus")
    assert classify(1, "4829", "Від: Тестовий Платник") == (TransactionKind.INCOME, "other")
    assert classify(-1, None, "Щось незрозуміле") == (TransactionKind.EXPENSE, "shopping")


def test_preview_rows_suggest_name_kind_category_and_note():
    rows = service.preview_rows(parse_statement(_csv_bytes()))
    silpo, steam, income, train, own, salary = rows
    assert (silpo["kind"], silpo["category_name"], silpo["amount"]) == (TransactionKind.EXPENSE, "food", Decimal("845.30"))
    assert silpo["note"] == "кешбек 8.45 UAH; MCC 5411"
    assert steam["note"] == "10.00 USD за курсом 41.50; MCC 5816"
    assert train["note"].startswith("комісія 10.00 UAH")
    assert (income["kind"], own["kind"], salary["category_name"]) == (TransactionKind.INCOME, TransactionKind.TRANSFER, "salary")


# ── Confirm ───────────────────────────────────────────────────────────────────

class _Result:
    def __init__(self, rows):
        self.rows = rows

    def scalars(self):
        return self

    def all(self):
        return list(self.rows)


class FakeSession:
    def __init__(self, existing_refs=()):
        self.added = []
        self.existing_refs = list(existing_refs)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        pass

    async def execute(self, stmt):
        return _Result(self.existing_refs)


def _row(ref, amount="100", kind=TransactionKind.EXPENSE, category="food", currency="UAH"):
    return StatementImportRow(ref=ref, date=datetime(2026, 3, 17, 19, 5), name="Сільпо", amount=Decimal(amount),
                              currency=currency, kind=kind, category_name=category)


def _user():
    return SimpleNamespace(id_=1, default_currency="UAH", capital=500.0)


@pytest.mark.anyio
async def test_confirm_history_only_keeps_balance_and_skips_duplicates():
    session, user = FakeSession(existing_refs=["old"]), _user()
    result = await service.confirm_import(session, user, "monobank", [_row("new1"), _row("old"), _row("new1"), _row("new2")], False)

    assert result == {"imported": 2, "skipped_duplicates": 2, "errors": []}
    assert user.capital == 500.0
    tx = session.added[0]
    assert isinstance(tx, Transaction)
    assert tx.counts_in_balance is False
    assert tx.import_ref == "new1"
    assert tx.tags == ["import", "monobank"]


@pytest.mark.anyio
async def test_confirm_with_balance_update_goes_through_create_user_transaction(monkeypatch):
    async def fake_convert(session, user_currency, kind, amount, tx_currency):
        return -Decimal(str(amount)) if kind == TransactionKind.EXPENSE else Decimal(str(amount))

    monkeypatch.setattr(transaction_service, "convert_to_user_currency", fake_convert)
    session, user = FakeSession(), _user()
    result = await service.confirm_import(session, user, "monobank", [_row("a", "100"), _row("b", "1000", TransactionKind.INCOME, "salary")], True)

    assert result["imported"] == 2
    assert user.capital == 1400.0
    assert all(tx.counts_in_balance is not False for tx in session.added)


@pytest.mark.anyio
async def test_confirm_reports_bad_rows_without_aborting():
    session = FakeSession()
    result = await service.confirm_import(session, _user(), "monobank",
                                          [_row("a", category="salary"), _row("b", currency="BTC"), _row("c")], False)
    assert result["imported"] == 1
    assert len(result["errors"]) == 2
