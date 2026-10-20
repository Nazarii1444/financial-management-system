"""
Unit tests for receipt_parser — the OCR text → structured fields heuristics.
"""

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from src.files.services import ocr_service, receipt_parser
from src.files.services.receipt_parser import parse, parse_amounts
from tests.files import receipt_samples as samples

UTC = timezone.utc
REF = datetime(2026, 10, 11, 12, 0, tzinfo=UTC)


# ── Full receipts ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "text, amount, currency, date, merchant, category",
    [
        (samples.UA_ATB, "103.38", "UAH", datetime(2026, 3, 12, 18, 42, 7, tzinfo=UTC), "АТБ", "food"),
        (samples.UA_FUEL, "2402.13", "UAH", datetime(2026, 10, 5, 12, tzinfo=UTC), "WOG", "car"),
        (samples.EN_SUPERMARKET, "11.43", "USD", datetime(2026, 10, 4, 9, 15, tzinfo=UTC),
         "FRESH MART SUPERMARKET", "food"),
        (samples.EN_THOUSANDS, "1259.50", "USD", datetime(2026, 9, 30, 12, tzinfo=UTC), "Comfy", "electronics"),
        (samples.CAFE_SPLIT_TOTAL, "120.00", None, datetime(2026, 10, 11, 8, 5, tzinfo=UTC),
         "Aroma Kava", "food"),
    ],
    ids=["ua-atb", "ua-fuel", "en-supermarket", "en-thousands", "cafe-split-total"],
)
def test_parses_sample_receipts(text, amount, currency, date, merchant, category):
    r = parse(text, REF)

    assert r.amount == Decimal(amount)
    assert r.currency == currency
    assert r.date == date
    assert r.merchant == merchant
    assert r.category == category
    assert r.confidence_label == "high"


def test_garbled_text_yields_nothing():
    r = parse(samples.GARBLED, REF)

    assert r.amount is None and r.date is None and r.merchant is None and r.category is None
    assert r.confidence_score == 0
    assert r.confidence_label == "none"


@pytest.mark.parametrize("text", [None, "", "   \n  "])
def test_empty_input(text):
    r = parse(text, REF)
    assert r.amount is None
    assert r.confidence_label == "none"


# ── Amounts ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "text, expected",
    [
        ("25.50", ["25.50"]),
        ("1234,50", ["1234.50"]),
        ("1,234.50", ["1234.50"]),          # used to be read as 234.00
        ("1.234,50", ["1234.50"]),
        ("2 402,13 грн", ["2402.13"]),
        ("12.03.2026 18:42", []),           # dates are not amounts
        ("2.000 X 19,99", ["19.99"]),       # quantity with 3 decimals is ignored
        ("12,345", []),                      # no 2-digit fraction → not money
    ],
)
def test_amount_formats(text, expected):
    assert parse_amounts(text) == [Decimal(e) for e in expected]


def test_subtotal_and_tax_lines_are_not_the_total():
    text = "SUBTOTAL 50.00\nTAX 9.00\nTOTAL 59.00\nCASH 100.00\nCHANGE 41.00"
    r = parse(text, REF)
    assert r.amount == Decimal("59.00")
    assert r.amount_confirmed                       # cash 100.00 − change 41.00 = 59.00
    assert r.field_confidence["amount"] == pytest.approx(0.97)


def test_strong_label_beats_weak_label():
    text = "СУМА 300,00\nДО СПЛАТИ 270,00"
    assert parse(text, REF).amount == Decimal("270.00")


def test_fallback_to_largest_amount_ignores_cash_tendered():
    text = "Item A 12.00\nItem B 30.00\nГОТІВКА 100.00"
    r = parse(text, REF)
    assert r.amount == Decimal("30.00")
    assert r.field_confidence["amount"] == pytest.approx(0.4)


# ── Dates ─────────────────────────────────────────────────────────────────────

def test_future_and_very_old_dates_are_rejected():
    text = "01.01.2030\n01.01.2020\n05.10.2026"
    assert parse(text, REF).date == datetime(2026, 10, 5, 12, tzinfo=UTC)


def test_iso_date():
    assert parse("Paid 2026-09-01", REF).date == datetime(2026, 9, 1, 12, tzinfo=UTC)


def test_day_first_unless_usd():
    assert parse("04/10/2026", REF).date.month == 10
    assert parse("$5.00\n04/10/2026", REF).date.month == 4
    assert parse("$5.00\n25/09/2026", REF).date == datetime(2026, 9, 25, 12, tzinfo=UTC)


def test_reference_controls_date_window():
    old_ref = datetime(2025, 1, 1, tzinfo=UTC)
    assert parse("05.10.2026", old_ref).date is None


# ── Merchant / category ───────────────────────────────────────────────────────

def test_merchant_skips_address_and_tax_id_lines():
    text = "ПН 123456789012\nм. Київ, вул. Січових Стрільців 5\nФОП Іваненко\nХліб 20,00"
    assert parse(text, REF).merchant == "Іваненко"


def test_category_uses_word_boundaries():
    # "bar" inside "barcode" must not count; there is no other signal.
    merchant, conf = receipt_parser.guess_category("barcode 1234567", None)
    assert merchant is None and conf == 0


def test_cyrillic_keywords_match_inflections():
    category, _ = receipt_parser.guess_category("Товари з аптеки", None)
    assert category == "health"


def test_categories_are_allowed_expense_categories():
    from src.transactions.categories import ALLOWED_EXPENSE_CATEGORIES

    used = set(receipt_parser._BRAND_CATEGORIES) | set(receipt_parser._KEYWORD_CATEGORIES)
    assert used <= ALLOWED_EXPENSE_CATEGORIES
    assert receipt_parser.FALLBACK_CATEGORY in ALLOWED_EXPENSE_CATEGORIES


# ── Stored OCR JSON ───────────────────────────────────────────────────────────

def test_result_from_text_shape_is_json_friendly():
    result = ocr_service.result_from_text(samples.UA_FUEL, REF)

    assert result["suggested_amount"] == 2402.13
    assert result["suggested_currency"] == "UAH"
    assert result["suggested_date"] == "2026-10-05T12:00:00+00:00"
    assert result["suggested_category"] == "car"
    assert result["merchant"] == "WOG"
    assert result["confidence"] == "high"
    assert result["parser_version"] == receipt_parser.PARSER_VERSION
    assert all(isinstance(a, float) for a in result["amounts"])


# ── Fiscal QR (Ukrainian receipts) ────────────────────────────────────────────

@pytest.mark.parametrize(
    "payload, amount, date",
    [
        (samples.UA_MCDONALDS_QR[0], "83.00", datetime(2026, 10, 3, 10, 37, tzinfo=UTC)),
        ("https://cabinet.tax.gov.ua/cashregs/check?fn=1&id=2&sm=1234,5&date=20260101&time=235959",
         "1234.50", datetime(2026, 1, 1, 23, 59, 59, tzinfo=UTC)),
        ("https://cabinet.tax.gov.ua/cashregs/check?sm=10.00", "10.00", None),
    ],
)
def test_fiscal_qr_is_parsed(payload, amount, date):
    info = receipt_parser.parse_fiscal_qr([payload])
    assert info.amount == Decimal(amount)
    assert info.date == date


@pytest.mark.parametrize(
    "payload",
    [
        "https://cabinet.tax.gov.ua/cashregs/check?id=1&fn=2",          # no total
        "https://cabinet.tax.gov.ua/cashregs/check?sm=abc",
        "https://evil.example.com/cashregs/check?sm=83.00",             # not the tax office
        "not a url",
    ],
)
def test_invalid_fiscal_qr_is_ignored(payload):
    assert receipt_parser.parse_fiscal_qr([payload]) is None


def test_fiscal_qr_overrides_ocr_amount_and_date():
    misread = samples.UA_MCDONALDS_OCR.replace("Сума 83.00", "Сума 93.00")
    r = parse(misread, REF, qr_codes=samples.UA_MCDONALDS_QR)

    assert r.amount == Decimal("83.00")
    assert r.amount_source == "fiscal_qr"
    assert r.field_confidence["amount"] == 1.0
    assert r.date == datetime(2026, 10, 3, 10, 37, tzinfo=UTC)
    assert r.currency == "UAH"
    assert r.fiscal.fiscal_number == "3001021466"


def test_fiscal_qr_works_without_any_text():
    r = parse(None, REF, qr_codes=samples.UA_MCDONALDS_QR)

    assert r.amount == Decimal("83.00")
    assert r.category == "food"           # from the feedback.mcdonalds.com QR
    assert r.retake_recommended is False


# ── Real McDonald's receipt ───────────────────────────────────────────────────

def test_mcdonalds_ocr_text_without_qr():
    r = parse(samples.UA_MCDONALDS_OCR, REF)

    assert r.amount == Decimal("83.00")   # "Сума 83.00", VAT line 13.83 ignored
    assert r.amount_source == "ocr"
    assert r.date == datetime(2026, 10, 3, 10, 37, 35, tzinfo=UTC)
    assert r.currency == "UAH"
    assert r.merchant == "McDonald's"                 # by its tax id, despite "КакДдональдз"
    assert r.category == "food"
    assert r.amount_confirmed                         # card payment + item + VAT all say 83.00


def test_old_pipeline_garbage_yields_no_merchant():
    r = parse(samples.UA_MCDONALDS_OLD_PIPELINE, REF)
    assert r.merchant is None
    assert r.amount is None
    assert r.retake_recommended is True


def test_low_ocr_quality_text_is_ignored():
    r = parse(samples.UA_ATB, REF, ocr_quality=0.3)

    assert r.text_unreadable is True
    assert r.amount is None and r.merchant is None
    assert r.confidence_label == "none"


def test_total_value_on_line_above_label():
    text = "Кава 40,00\n83.00\nСума\nПДВ 20% 13.83"
    assert parse(text, REF).amount == Decimal("83.00")


# ── Multi-pass voting & cross-checks (parser v4) ──────────────────────────────

def test_photo2_passes_vote_to_the_right_fields():
    r = receipt_parser.parse_multi(samples.UA_MCDONALDS_PHOTO2_PASSES, REF)

    assert r.amount == Decimal("83.00")
    assert r.amount_confirmed                        # card payment + item row
    assert r.currency == "UAH"                       # "83.00 гри" / "83.00 FPH"
    assert r.date == datetime(2026, 10, 3, 10, 37, tzinfo=UTC)   # "3.19.2026" repaired
    assert r.field_confidence["date"] < 0.85                      # … and flagged as a guess
    assert r.merchant == "McDonald's"                # tax id 237444526652, name unreadable
    assert r.category == "food"
    assert r.confidence_label == "high"


def test_each_photo2_pass_alone_is_weaker():
    singles = [parse(t, REF, ocr_quality=q) for t, q in samples.UA_MCDONALDS_PHOTO2_PASSES]
    assert not any(r.amount_confirmed and r.currency == "UAH" for r in singles)


def test_misread_total_is_repaired_by_vat():
    r = parse(samples.EN_PASS_MISREAD_TOTAL, REF)
    assert r.amount == Decimal("83.00")              # 63.00 × 20/120 ≠ 13.83, 83.00 fits


def test_total_without_any_check_is_kept():
    r = parse("Кава 40,00\nСума 63.00", REF)
    assert r.amount == Decimal("63.00")              # nothing contradicts it → not "repaired"
    assert not r.amount_confirmed


def test_vat_rate_is_not_an_amount():
    assert parse_amounts("ПДВ А 20.00% 13.83") == [Decimal("13.83")]


def test_card_payment_and_items_confirm_the_total():
    text = "Хліб 24,50 А\nМолоко 38,90 А\nСУМА 63,40\nКАРТКА 63,40"
    r = parse(text, REF)
    assert r.amount == Decimal("63.40")
    assert r.amount_confirmed


def test_payment_line_beats_lone_fallback():
    # The "Сума" line was lost by OCR; the card payment still gives the total.
    r = parse("Кава 40,00 А\nСік 43,00 А\nБЕЗГОТІВКОВА 83.00 грн", REF)
    assert r.amount == Decimal("83.00")
    assert r.amount_confirmed                        # matches the item sum


def test_impossible_month_is_repaired_not_swapped():
    r = parse("Сума 10.00\n3.19.2026 10:37", REF)
    assert r.date == datetime(2026, 10, 3, 10, 37, tzinfo=UTC)


def test_fiscal_markers_imply_uah():
    assert parse("ПН 123456789012\nСума 10.00", REF).currency == "UAH"
    assert parse("Сума 10.00\nФІСКАЛЬНИЙ ЧЕК", REF).currency == "UAH"
    assert parse("TOTAL 10.00", REF).currency is None


def test_garbage_header_is_not_a_merchant():
    assert receipt_parser.guess_merchant(["ШІ МЗКЦЦ", "Гаряча ””Пя Зргонп% К?Є\"93 6Об"]) == (None, 0.0)


def test_low_confidence_total_recommends_retake():
    r = parse("Item A 12.00\nItem B 30.00", REF)    # only the "largest number" fallback
    assert r.amount == Decimal("30.00")
    assert r.retake_recommended is True


# ── Degraded OCR (no OpenCV) ──────────────────────────────────────────────────

def test_address_and_item_rows_are_not_the_merchant():
    r = parse(samples.UA_MCDONALDS_PILLOW_FALLBACK, REF, ocr_quality=0.71)
    assert r.merchant is None                 # not "о Пьвів, прос. …", not "КАПУЧИНО ВЕЛИКЕ"
    assert r.amount == Decimal("83.00")       # card payment line
    assert r.currency == "UAH"                # "83.00 ГРя"


@pytest.mark.parametrize("text", ["Кава 83.00 ГРя", "Кава 83.00 FPH", "Кава 83.00 гри", "Кава 83,00 rpн"])
def test_misread_hryvnia_after_amount(text):
    assert receipt_parser.detect_currency(text) == "UAH"


def test_grams_are_not_hryvnia():
    assert receipt_parser.detect_currency("Сир 200 гр") is None


def test_ukrainian_text_implies_uah():
    text = "Кав'ярня Світанок\nКапучино 65,00\nПиріг з вишнею 55,00\nРазом 120,00\nДякуємо за візит"
    assert parse(text, REF).currency == "UAH"


def test_shop_name_with_number_is_kept():
    assert receipt_parser.guess_merchant(["Аптека Здоров'я 24", "вул. Шевченка 5"])[0] == "Аптека Здоров'я 24"
