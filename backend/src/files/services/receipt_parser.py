"""
ReceiptParser
─────────────
Turns raw OCR text into structured receipt fields:

  amount    — the receipt total, cross-checked against the receipt's own numbers
              (payment line, cash − change, sum of items, VAT) — see `find_total`
  currency  — ISO code detected from symbols / words (₴, грн, $, EUR …);
              Ukrainian fiscal markers (ПН / ФН / ПДВ …) imply UAH
  date      — purchase date (+ time when printed next to it)
  merchant  — known chain from `merchants` (tax id / QR / fuzzy name), else the header line
  category  — the known chain's category, else guessed from brands and keywords

Ukrainian fiscal receipts carry a QR code (cabinet.tax.gov.ua/cashregs/check?
date=YYYYMMDD&time=HHMM&id=…&sm=<total>&fn=…). When it was decoded, its total
and date are exact and override the OCR guesses.

The OCR service runs several Tesseract passes; `parse_multi` takes all of them
and lets the passes vote, since a value lost in one pass is often read in another.
OCR slips are tolerated with fuzzy keyword anchors (`receipt_text`).

Every field carries a 0–1 confidence; `overall` is a weighted mix of them.
Pure functions only (no I/O) so the heuristics are cheap to unit test.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from itertools import product
from typing import Iterable, Optional
from urllib.parse import parse_qs, urlparse

from src.files.services import merchants
from src.files.services.receipt_text import has_anchor, normalise_line
from src.models import Currencies

PARSER_VERSION = 4

FALLBACK_CATEGORY = "shopping"

# Mean Tesseract word confidence (0–1) below which OCR text is treated as noise.
MIN_OCR_QUALITY = 0.5

# Below this amount confidence the user is asked for a clearer photo.
MIN_AMOUNT_CONFIDENCE = 0.5

_FISCAL_QR_HOST = "tax.gov.ua"

# ── Amounts ───────────────────────────────────────────────────────────────────
# Matches 25.50 / 1234,50 / 1,234.50 / 1.234,50 / 2 402,13 — always with 2 decimals.
# Thousand separator (group 2) must differ from the decimal separator, and the
# lookarounds stop dates such as 12.03.2026 from being read as "12.03" and
# rates such as "20.00%" from being read as money.
_AMOUNT_RE = re.compile(
    r"(?<![\d.,])"
    r"(\d{1,3}(?:([.,  ])\d{3})(?:\2\d{3})*|\d+)"
    r"(?!\2)[.,](\d{2})"
    r"(?![.,]?\d)(?!\s?%)"
)

# Structural keywords, matched fuzzily (OCR slips) — see receipt_text.has_anchor.
_STRONG_TOTAL = ("ДО СПЛАТИ", "ДО ОПЛАТИ", "К ОПЛАТЕ", "AMOUNT DUE", "TOTAL DUE", "BALANCE DUE", "GRAND TOTAL")
_TOTAL = ("СУМА", "СУММА", "РАЗОМ", "ВСЬОГО", "ИТОГО", "TOTAL", "AMOUNT")
_SUBTOTAL = ("SUBTOTAL", "SUB TOTAL", "ПРОМІЖНИЙ ПІДСУМОК")
_VAT = ("ПДВ", "НДС", "VAT")
_SALES_TAX = ("TAX",)
_DISCOUNT = ("ЗНИЖКА", "ЗНИЖКИ", "СКИДКА", "DISCOUNT", "АКЦИЗ", "БОНУС", "BONUS")
_CARD = ("БЕЗГОТІВКОВА", "БЕЗГОТІВКОВИЙ", "КАРТКА", "КАРТА", "CARD", "VISA", "MASTERCARD")
_CASH = ("ГОТІВКА", "НАЛИЧНЫЕ", "CASH", "TENDERED")
_CHANGE = ("РЕШТА", "СДАЧА", "CHANGE")

# Value-added tax rates (UA 20/7/14 %, also common EU ones) for the VAT cross-check.
_VAT_RATES = (Decimal(20), Decimal(7), Decimal(14), Decimal(23), Decimal(19), Decimal(21))
_VAT_TOLERANCE = Decimal("0.02")
# "20.00% 13.83" — a VAT line even when "ПДВ" itself is unreadable ("NABLA A = 20.00% 13.83").
# Two decimals on the rate keep product names like "Сметана 20%" out.
_VAT_RATE_RE = re.compile(r"(?<!\d)\d{1,2}[.,]\d{2}\s?%")

# Digits Tesseract confuses on thermal receipts.
_CONFUSABLE_DIGITS = {
    "0": "689", "1": "74", "3": "89", "4": "1", "5": "6", "6": "580", "7": "1", "8": "0369", "9": "0836",
}

# Evidence weights for choosing the total; "families" are independent ways to confirm it.
_EVIDENCE_WEIGHT = {
    "label_strong": 3.0, "label": 2.0, "payment": 2.0, "cash_change": 2.0,
    "items": 1.5, "vat": 1.5, "fallback": 0.5,
}
_EVIDENCE_FAMILY = {
    "label_strong": "label", "label": "label", "payment": "payment", "cash_change": "payment",
    "items": "items", "vat": "vat",
}

# ── Currency ──────────────────────────────────────────────────────────────────
_CURRENCY_PATTERNS: dict[str, re.Pattern] = {
    # "грн" right after an amount is often misread: "83.00 гри", "83.00 ГРя", "83.00 FPH".
    # Г→г/r/F, Р→р/p, Н→any letter; the 2-decimal amount keeps "200 гр" (grams) out.
    "UAH": re.compile(
        r"₴|\bгрн\b|\bгрив\w*|\buah\b|\d[.,]\d{2}\s*[гrf][рp][а-яіїєa-z](?!\w)",
        re.IGNORECASE,
    ),
    "USD": re.compile(r"\$|\busd\b", re.IGNORECASE),
    "EUR": re.compile(r"€|\beur\b|\beuro?\b", re.IGNORECASE),
    "GBP": re.compile(r"£|\bgbp\b", re.IGNORECASE),
    "PLN": re.compile(r"\bzł\b|\bzl\b|\bpln\b", re.IGNORECASE),
    "CHF": re.compile(r"\bchf\b", re.IGNORECASE),
    "JPY": re.compile(r"¥|\bjpy\b", re.IGNORECASE),
}
_SUPPORTED_CURRENCIES = {c.value for c in Currencies}

# Ukrainian fiscal receipt markers: tax id / fiscal / serial number of the register.
_UA_FISCAL_ID_RE = re.compile(r"(?<!\w)(?:ПН|ФН|ЗН|ІД)\s*[:№N]?\s*[A-ZА-ЯІ]{0,2}\s*\d{8,}", re.IGNORECASE)
_UA_FISCAL_ANCHORS = ("ФІСКАЛЬНИЙ ЧЕК", "ПДВ")
# Ukrainian-only letters, in words of ≥ 3 letters (OCR noise often yields a stray "і").
_UA_LETTERS_RE = re.compile(
    r"(?<![а-яґєіїa-z'’])(?=[а-яґєії'’]{3,})[а-яґєії'’]*[ґєії][а-яґєії'’]*", re.IGNORECASE
)
_MIN_UA_LINES = 3

# ── Dates ─────────────────────────────────────────────────────────────────────
_ISO_DATE_RE = re.compile(r"(?<!\d)(\d{4})[-./](\d{1,2})[-./](\d{1,2})(?!\d)")
_DMY_DATE_RE = re.compile(r"(?<!\d)(\d{1,2})[./-](\d{1,2})[./-](\d{4}|\d{2})(?!\d)")
_TIME_RE = re.compile(r"(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?::([0-5]\d))?(?!\d)")
_MAX_RECEIPT_AGE = timedelta(days=730)

# ── Merchant ──────────────────────────────────────────────────────────────────
_MERCHANT_SKIP_RE = re.compile(
    r"\b(?:пн|ід|ідентифікац\w*|єдрпоу|едрпоу|іпн|инн|код|tel|тел\w*|phone|www|http\w*|"
    r"вул|ул|просп|бульв|street|st|ave|road|адрес\w*|address|"
    r"касир\w*|кассир\w*|cashier|каса|касса|чек\w*|receipt|invoice|фіскальн\w*|фискальн\w*|"
    r"зн|фн|рро|прро|ласкаво|добро\s+пожаловать|welcome|дякуємо|thank\w*)\b|(?<!\w)[мг]\.\s|@|\.com\b|\.ua\b",
    re.IGNORECASE,
)
# Address / phone lines ("м. Львів, прос. Червоної калини 60Б", "Гаряча лінія: 0-800-…").
_ADDRESS_RE = re.compile(
    r"\b(?:вул|ул|просп?|пр-т|пров|пл|бульв?|б-р|шосе|наб|майдан|площа|буд|обл|р-н|"
    r"street|str|st|ave|road|rd)\b\.?|"
    r"\b(?:гаряча\s+лінія|лінія|тел\w*|tel|phone|hotline)\b|\d-\d{3}-\d{2}-\d{2}-\d{2}|\+?380\d{9}",
    re.IGNORECASE,
)
_LEGAL_FORM_RE = re.compile(
    r"^\s*(?:тов|фоп|пп|піі|пат|прат|ат|дп|ооо|ип|llc|ltd|inc|gmbh|sp\.?\s*z\s*o\.?\s*o\.?)\b\.?\s*",
    re.IGNORECASE,
)
# Legal names are usually quoted: ТОВ «АТБ-МАРКЕТ», ПІІ "МакДональдз Юкрейн Лтд".
_QUOTED_NAME_RE = re.compile(r"[\"«“„]([^\"«»“”„]{2,})[\"»”“]")
_WORD_STRIP = ".,:;!?()[]{}\"'«»“”„-–—|/\\*#_=+<>~"
_VOWEL_RE = re.compile(r"[аеиіїоуюяєaeiouy]", re.IGNORECASE)
_MERCHANT_HEADER_LINES = 8
_MIN_WORDLIKE_SHARE = 0.7

# ── Category ──────────────────────────────────────────────────────────────────
# Known brands are strong signals (weight 3); generic words are weak (weight 1).
# Cyrillic keywords are stems ("аптек") so prefix matching covers inflections.
# All categories must be in ALLOWED_EXPENSE_CATEGORIES.
_BRAND_CATEGORIES: dict[str, list[str]] = merchants.brand_terms()
_KEYWORD_CATEGORIES: dict[str, list[str]] = {
    "food": [
        "супермаркет", "supermarket", "grocery", "продукт", "хліб", "хлеб",
        "молок", "bread", "milk", "ресторан", "restaurant", "кафе", "cafe", "café",
        "кав'ярн", "coffee", "кава", "кофе", "піц", "pizza", "burger", "бургер", "sushi",
        "суші", "bakery", "пекарн", "bistro", "food", "закусочн", "їдальн", "капучино",
        "cappuccino", "латте", "latte", "еспресо", "espresso", "американо",
    ],
    "car": ["пальн", "бензин", "дизел", "газ пропан", "fuel", "petrol", "diesel", "азс", "а-95", "а-92"],
    "transportation": ["таксі", "taxi", "метро", "metro ticket", "автобус", "bus", "train", "квит", "ticket", "parking", "паркінг"],
    "health": ["аптек", "pharmacy", "drug", "ліки", "лекарств", "clinic", "клінік", "hospital", "dentist", "стоматолог"],
    "electronics": ["laptop", "ноутбук", "смартфон", "smartphone", "електронік", "electronics", "навушник", "headphones"],
    "home": ["господарч", "household", "furniture", "мебл"],
    "clothing": ["одяг", "одежд", "clothing", "взутт", "обув", "shoes", "apparel"],
    "beauty": ["косметик", "cosmetics", "парфум", "perfume", "салон краси", "beauty"],
    "utilities": ["комунальн", "electricity", "електроенергі", "водопостачанн", "water supply", "utility", "інтернет", "internet"],
    "entertainment": ["кіно", "cinema", "movie", "театр", "theater", "theatre", "концерт", "concert"],
    "travel": ["готел", "hotel", "hostel", "хостел", "авіа", "airline", "flight"],
    "education": ["курс", "course", "tuition", "університет", "university", "книгарн", "bookstore"],
    "pets": ["зоомагазин", "pet shop", "корм для", "pet food"],
    "alcohol": ["вино", "wine", "пиво", "beer", "горілк", "vodka", "whisky", "віскі"],
    "cigarettes": ["сигарет", "cigarettes", "тютюн", "tobacco", "iqos"],
}
_BRAND_WEIGHT = 3
_KEYWORD_WEIGHT = 1
_MERCHANT_MULTIPLIER = 2

# Field weights for the overall confidence score.
_FIELD_WEIGHTS = {"amount": 0.5, "date": 0.15, "merchant": 0.15, "category": 0.2}


def _term_re(term: str, allow_inflection: bool = True) -> re.Pattern:
    # Term must start at a word boundary. Cyrillic keywords may continue (inflections:
    # "аптека" → "аптеки"); Latin terms and brand names must end at a boundary too
    # (so "bar" doesn't match "barcode").
    inflected = allow_inflection and re.search(r"[а-яіїєґ]", term, re.IGNORECASE)
    tail = r"" if inflected else r"(?!\w)"
    return re.compile(r"(?<!\w)" + re.escape(term) + tail, re.IGNORECASE)


_BRAND_RES = {cat: [_term_re(t, allow_inflection=False) for t in terms] for cat, terms in _BRAND_CATEGORIES.items()}
_KEYWORD_RES = {cat: [_term_re(t) for t in terms] for cat, terms in _KEYWORD_CATEGORIES.items()}


# ── Result ────────────────────────────────────────────────────────────────────

@dataclass
class FiscalInfo:
    """Data from a Ukrainian fiscal receipt QR code."""
    amount:         Decimal
    date:           Optional[datetime] = None
    fiscal_number:  Optional[str] = None     # ФН — fiscal number of the cash register
    receipt_number: Optional[str] = None


@dataclass
class ParsedReceipt:
    amount:   Optional[Decimal] = None
    currency: Optional[str] = None
    date:     Optional[datetime] = None
    merchant: Optional[str] = None
    category: Optional[str] = None
    amounts:  list[Decimal] = field(default_factory=list)
    field_confidence: dict[str, float] = field(default_factory=dict)
    amount_source:    Optional[str] = None      # "fiscal_qr" | "ocr"
    amount_confirmed: bool = False               # total backed by ≥ 2 independent checks
    fiscal:           Optional[FiscalInfo] = None
    text_unreadable:  bool = False               # OCR ran but produced mostly noise

    @property
    def retake_recommended(self) -> bool:
        """No (trustworthy) total could be found — a clearer photo is the user's best option."""
        return self.amount is None or self.field_confidence.get("amount", 0.0) < MIN_AMOUNT_CONFIDENCE

    @property
    def confidence_score(self) -> float:
        score = sum(self.field_confidence.get(f, 0.0) * w for f, w in _FIELD_WEIGHTS.items())
        return round(score, 2)

    @property
    def confidence_label(self) -> str:
        score = self.confidence_score
        if score >= 0.75:
            return "high"
        if score >= 0.45:
            return "medium"
        if score > 0:
            return "low"
        return "none"


# ── Public API ────────────────────────────────────────────────────────────────

def parse(
        raw_text: Optional[str],
        reference: Optional[datetime] = None,
        qr_codes: Iterable[str] = (),
        ocr_quality: Optional[float] = None,
) -> ParsedReceipt:
    """
    Parse one OCR text (+ decoded QR payloads).

    *reference*   — "now" for date sanity checks; pass the receipt's upload
                    time when re-parsing old receipts.
    *ocr_quality* — mean Tesseract word confidence (0–1); below MIN_OCR_QUALITY
                    the text is noise and no fields are guessed from it.
    """
    return parse_multi([(raw_text, ocr_quality)], reference, qr_codes)


def parse_multi(
        passes: Iterable[tuple[Optional[str], Optional[float]]],
        reference: Optional[datetime] = None,
        qr_codes: Iterable[str] = (),
) -> ParsedReceipt:
    """
    Parse several OCR readings of the same receipt — (text, ocr_quality) per
    pass, best pass first — and let them vote field by field.
    """
    result = ParsedReceipt(field_confidence={f: 0.0 for f in _FIELD_WEIGHTS})
    qr_codes = [q for q in qr_codes if q]
    present = [(t, q) for t, q in passes if t and t.strip()]
    readable = [t for t, q in present if q is None or q >= MIN_OCR_QUALITY]
    result.text_unreadable = bool(present) and not readable

    texts = [_lines(t) for t in readable]
    all_text = "\n".join(line for lines in texts for line in lines)

    if texts:
        reference = reference or datetime.now(timezone.utc)
        if reference.tzinfo is None:
            reference = reference.replace(tzinfo=timezone.utc)

        result.amounts = parse_amounts(all_text)
        result.amount, result.field_confidence["amount"], result.amount_confirmed = find_total(texts)
        if result.amount is not None:
            result.amount_source = "ocr"

        result.currency = detect_currency(all_text) or ("UAH" if is_ua_fiscal(texts) else None)
        result.date, result.field_confidence["date"] = vote_date(
            texts, reference, month_first=result.currency == "USD"
        )

    known, known_confidence = merchants.match_merchant(texts, qr_codes)
    if known:
        result.merchant, result.field_confidence["merchant"] = known.name, known_confidence
    else:
        for lines in texts:
            result.merchant, result.field_confidence["merchant"] = guess_merchant(lines)
            if result.merchant:
                break

    # Fiscal QR beats OCR: its total and timestamp come straight from the cash register.
    result.fiscal = parse_fiscal_qr(qr_codes)
    if result.fiscal:
        result.amount, result.field_confidence["amount"] = result.fiscal.amount, 1.0
        result.amount_source = "fiscal_qr"
        result.amount_confirmed = True
        result.currency = "UAH"
        if result.fiscal.date:
            result.date, result.field_confidence["date"] = result.fiscal.date, 1.0

    if known:
        result.category, result.field_confidence["category"] = known.category, known_confidence
    else:
        # Other QR codes (feedback / loyalty links) often name the brand in their domain.
        category_text = " ".join(([all_text] if all_text else []) + _qr_hostnames(qr_codes))
        if category_text:
            result.category, result.field_confidence["category"] = guess_category(category_text, result.merchant)
    return result


def _lines(text: str) -> list[str]:
    return [normalise_line(ln) for ln in text.splitlines() if ln.strip()]


# ── Fiscal QR ─────────────────────────────────────────────────────────────────

def _fiscal_datetime(date: Optional[str], time: Optional[str]) -> Optional[datetime]:
    if not date or not re.fullmatch(r"\d{8}", date):
        return None
    try:
        d = datetime(int(date[:4]), int(date[4:6]), int(date[6:]), 12, tzinfo=timezone.utc)
    except ValueError:
        return None
    if time and re.fullmatch(r"\d{4}|\d{6}", time):
        try:
            d = d.replace(hour=int(time[:2]), minute=int(time[2:4]), second=int(time[4:6] or 0))
        except ValueError:
            pass
    return d


def parse_fiscal_qr(qr_codes: Iterable[str]) -> Optional[FiscalInfo]:
    """Extract total/date from a Ukrainian fiscal receipt QR (cabinet.tax.gov.ua …&sm=83.00)."""
    for payload in qr_codes:
        try:
            url = urlparse(payload.strip())
        except ValueError:
            continue
        if not (url.hostname or "").lower().endswith(_FISCAL_QR_HOST):
            continue
        params = {k.lower(): v[0] for k, v in parse_qs(url.query).items() if v}
        try:
            amount = Decimal(params["sm"].replace(",", "."))
        except (KeyError, InvalidOperation):
            continue
        if amount <= 0:
            continue
        return FiscalInfo(
            amount=amount.quantize(Decimal("0.01")),
            date=_fiscal_datetime(params.get("date"), params.get("time")),
            fiscal_number=params.get("fn"),
            receipt_number=params.get("id"),
        )
    return None


def _qr_hostnames(qr_codes: Iterable[str]) -> list[str]:
    hosts = []
    for payload in qr_codes:
        try:
            host = urlparse(payload.strip()).hostname
        except ValueError:
            continue
        if host and not host.lower().endswith(_FISCAL_QR_HOST):
            hosts.append(host.lower())
    return hosts


# ── Amounts ───────────────────────────────────────────────────────────────────

def _to_decimal(match: re.Match) -> Optional[Decimal]:
    integer = match.group(1)
    if match.group(2):
        integer = integer.replace(match.group(2), "")
    try:
        return Decimal(f"{integer}.{match.group(3)}")
    except InvalidOperation:
        return None


def _line_amounts(line: str) -> list[Decimal]:
    return [d for d in (_to_decimal(m) for m in _AMOUNT_RE.finditer(line)) if d is not None and d > 0]


def parse_amounts(text: str) -> list[Decimal]:
    """Unique positive amounts in the text, largest first (top 10)."""
    seen = sorted(set(_line_amounts(text)), reverse=True)
    return seen[:10]


def _is_special(line: str) -> bool:
    """VAT / discount / payment / subtotal lines — never the total label itself."""
    return has_anchor(line, *_VAT, *_SALES_TAX, *_DISCOUNT, *_CARD, *_CASH, *_CHANGE, *_SUBTOTAL)


def _neighbour_amounts(lines: list[str], i: int) -> list[Decimal]:
    """
    OCR often puts a big "Сума" / "TOTAL" and its value on separate lines —
    the value may land just below or just above. Skip VAT / discount / cash lines.
    """
    for j in (i + 1, i - 1):
        if 0 <= j < len(lines) and not _is_special(lines[j]):
            amounts = _line_amounts(lines[j])
            if amounts:
                return amounts
    return []


def _item_price(line: str) -> Optional[Decimal]:
    """
    Price of an item row — "name … 83.00 А": ≥ 3 letters of name, the amount at
    the end, optionally followed by a tax letter / unit (≤ 3 characters).
    """
    matches = list(_AMOUNT_RE.finditer(line))
    if not matches:
        return None
    last = matches[-1]
    if len(line[last.end():].strip()) > 3:
        return None
    if sum(ch.isalpha() for ch in line[:matches[0].start()]) < 3:
        return None
    return _to_decimal(last)


@dataclass
class _PassEvidence:
    candidates: list[tuple[Decimal, str]] = field(default_factory=list)   # (amount, kind)
    vats: list[Decimal] = field(default_factory=list)
    item_total: Optional[Decimal] = None
    sales_tax: Optional[Decimal] = None
    fallback: list[Decimal] = field(default_factory=list)


def _pass_evidence(lines: list[str]) -> _PassEvidence:
    """
    Walk one OCR text top to bottom collecting everything that says what the total is:
    total labels, card payment, cash − change, item rows (before the totals block), VAT.
    """
    ev = _PassEvidence()
    items: list[Decimal] = []
    cash = change = None
    totals_started = False

    for i, line in enumerate(lines):
        amounts = _line_amounts(line)
        last = amounts[-1] if amounts else None

        if has_anchor(line, *_VAT) or (last and _VAT_RATE_RE.search(line)):
            if last:
                ev.vats.append(last)
            totals_started = True
        elif has_anchor(line, *_DISCOUNT, *_SUBTOTAL):
            totals_started = True
        elif has_anchor(line, *_SALES_TAX):
            ev.sales_tax = last or ev.sales_tax
            totals_started = True
        elif has_anchor(line, *_CHANGE):
            change = last or change
            totals_started = True
        elif has_anchor(line, *_CASH):
            cash = last or cash
            totals_started = True
        elif has_anchor(line, *_CARD):
            if last:
                ev.candidates.append((last, "payment"))
            totals_started = True
        elif has_anchor(line, *_STRONG_TOTAL) or has_anchor(line, *_TOTAL):
            strong = has_anchor(line, *_STRONG_TOTAL)
            values = amounts or _neighbour_amounts(lines, i)
            if values:
                ev.candidates.append((values[-1], "label_strong" if strong else "label"))
            totals_started = True
        else:
            if not totals_started:
                price = _item_price(line)
                if price:
                    items.append(price)
            ev.fallback.extend(amounts)

    if cash is not None and change is not None and cash > change:
        ev.candidates.append((cash - change, "cash_change"))
    if items:
        ev.item_total = sum(items, Decimal(0))
    return ev


def _vat_error(total: Decimal, vat: Decimal) -> Decimal:
    """How far *vat* is from the VAT included in *total* at the closest known rate."""
    return min(abs(total * r / (100 + r) - vat) for r in _VAT_RATES)


def _vat_matches(total: Decimal, vat: Decimal) -> bool:
    return _vat_error(total, vat) <= _VAT_TOLERANCE


def _digit_variants(amount: Decimal) -> set[Decimal]:
    """Amounts one or two confusable-digit substitutions away (83.00 ↔ 63.00 ↔ 88.00 …)."""
    digits = f"{amount:.2f}"
    positions = [i for i, ch in enumerate(digits) if ch in _CONFUSABLE_DIGITS]
    variants: set[Decimal] = set()
    for i in positions:
        for sub in _CONFUSABLE_DIGITS[digits[i]]:
            variants.add(Decimal(digits[:i] + sub + digits[i + 1:]))
    for i, j in ((a, b) for a in positions for b in positions if a < b):
        for s1, s2 in product(_CONFUSABLE_DIGITS[digits[i]], _CONFUSABLE_DIGITS[digits[j]]):
            variants.add(Decimal(digits[:i] + s1 + digits[i + 1:j] + s2 + digits[j + 1:]))
    variants.discard(amount)
    return {v for v in variants if v > 0}


def find_total(texts: list[list[str]]) -> tuple[Optional[Decimal], float, bool]:
    """
    Pick the receipt total from all OCR passes. Returns (amount, confidence, confirmed).

    Each candidate collects evidence kinds; the one with the most weighted
    evidence wins. A total is *confirmed* when two independent families agree
    (e.g. "Сума 83.00" + card payment 83.00, or + VAT 13.83 = 83.00 × 20/120).
    A label value that nothing confirms is retried with confusable digits
    (63.00 → 83.00) and replaced when exactly one variant is confirmed.
    """
    evidences = [_pass_evidence(lines) for lines in texts]
    kinds: dict[Decimal, set[str]] = {}
    label_votes: Counter = Counter()
    for ev in evidences:
        for amount, kind in ev.candidates:
            kinds.setdefault(amount, set()).add(kind)
            if kind.startswith("label"):
                label_votes[amount] += 1

    vats = {v for ev in evidences for v in ev.vats}
    item_totals = {ev.item_total for ev in evidences if ev.item_total}
    item_totals |= {ev.item_total + ev.sales_tax for ev in evidences if ev.item_total and ev.sales_tax}

    def confirmations(amount: Decimal) -> set[str]:
        found = set()
        if any(_vat_matches(amount, v) for v in vats):
            found.add("vat")
        if amount in item_totals:
            found.add("items")
        return found

    for amount in list(kinds):
        kinds[amount] |= confirmations(amount)

    # Repair: an unconfirmed label value → the unique confusable variant backed by the
    # VAT line or the payment line (item sums are too weak: discounts break them).
    def backing(v: Decimal) -> Optional[tuple[int, Decimal]]:
        """(number of checks backing v, VAT error) — None when neither VAT nor payment backs it."""
        payment = bool(kinds.get(v, set()) & {"payment", "cash_change"})
        vat_error = min((_vat_error(v, vat) for vat in vats), default=None)
        if not payment and (vat_error is None or vat_error > _VAT_TOLERANCE):
            return None
        checks = payment + (vat_error is not None and vat_error <= _VAT_TOLERANCE) + (v in item_totals)
        return checks, vat_error if vat_error is not None else Decimal(0)

    for amount, k in list(kinds.items()):
        if not k <= {"label", "label_strong"}:
            continue
        backed = {v: b for v in _digit_variants(amount) if (b := backing(v))}
        if not backed:
            continue
        # Most checks first, then the closest VAT fit; give up when still ambiguous.
        ranked = sorted(backed, key=lambda v: (-backed[v][0], backed[v][1]))
        if len(ranked) == 1 or backed[ranked[0]] != backed[ranked[1]]:
            fixed = ranked[0]
            kinds.setdefault(fixed, set()).update(k | confirmations(fixed))
            label_votes[fixed] += label_votes.pop(amount, 0)
            del kinds[amount]

    if not kinds:
        fallback = [a for ev in evidences for a in ev.fallback]
        if not fallback:
            return None, 0.0, False
        return max(fallback), 0.4, False

    def score(amount: Decimal) -> tuple[float, bool, Decimal]:
        weight = sum(_EVIDENCE_WEIGHT[k] for k in kinds[amount])
        weight += 0.5 * max(0, label_votes[amount] - 1)
        return weight, "label_strong" in kinds[amount], amount

    best = max(kinds, key=score)
    k = kinds[best]
    families = {_EVIDENCE_FAMILY[x] for x in k}
    if len(families) >= 2:
        return best, 0.97, True
    if "label_strong" in k:
        return best, 0.95, False
    if "label" in k:
        return best, 0.85, False
    if families & {"payment"}:
        return best, 0.8, False
    return best, 0.6, False


# ── Currency ──────────────────────────────────────────────────────────────────

def detect_currency(text: str) -> Optional[str]:
    counts = {
        code: len(pattern.findall(text))
        for code, pattern in _CURRENCY_PATTERNS.items()
        if code in _SUPPORTED_CURRENCIES
    }
    best = max(counts, key=counts.get, default=None)
    return best if best and counts[best] > 0 else None


def is_ua_fiscal(texts: list[list[str]]) -> bool:
    """
    A Ukrainian receipt: fiscal markers (ПН / ФН / ЗН ids, ПДВ, "ФІСКАЛЬНИЙ ЧЕК"), or
    Ukrainian-only letters (і ї є ґ) in several lines — receipts printed in Ukrainian are in UAH.
    """
    if any(_UA_FISCAL_ID_RE.search(line) or has_anchor(line, *_UA_FISCAL_ANCHORS)
           for lines in texts for line in lines):
        return True
    return any(sum(bool(_UA_LETTERS_RE.search(line)) for line in lines) >= _MIN_UA_LINES for lines in texts)


# ── Dates ─────────────────────────────────────────────────────────────────────

def _build_date(year: int, month: int, day: int) -> Optional[datetime]:
    if year < 100:
        year += 2000
    try:
        return datetime(year, month, day, tzinfo=timezone.utc)
    except ValueError:
        return None


def _repair_number(value: str, valid) -> list[int]:
    """Values one confusable-digit substitution away from *value* that satisfy *valid*."""
    found = []
    for i, ch in enumerate(value):
        for sub in _CONFUSABLE_DIGITS.get(ch, ""):
            n = int(value[:i] + sub + value[i + 1:])
            if valid(n):
                found.append(n)
    return found


def _dates_in_line(line: str, month_first: bool = False) -> list[tuple[datetime, bool]]:
    """Dates in the line as (date, repaired)."""
    found: list[tuple[datetime, bool]] = []
    for m in _ISO_DATE_RE.finditer(line):
        d = _build_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if d:
            found.append((d, False))
    for m in _DMY_DATE_RE.finditer(line):
        a, b, year = m.group(1), m.group(2), int(m.group(3))
        if month_first:
            # US receipts: month first, unless the first number can't be a month.
            month, day = (int(a), int(b)) if int(a) <= 12 else (int(b), int(a))
            d = _build_date(year, month, day)
            if d:
                found.append((d, False))
            continue
        d = _build_date(year, int(b), int(a))
        if d:
            found.append((d, False))
            continue
        # Day-first, but the month is impossible ("3.19.2026"): an OCR slip is far more
        # likely than a month-first date on a UA/EU receipt → fix the digit if unambiguous.
        months = _repair_number(b, lambda n: 1 <= n <= 12) if int(b) > 12 else [int(b)]
        days = _repair_number(a, lambda n: 1 <= n <= 31) if int(a) > 31 else [int(a)]
        if len(months) == 1 and len(days) == 1:
            d = _build_date(year, months[0], days[0])
            if d:
                found.append((d, True))
                continue
        d = _build_date(year, int(a), int(b))                # last resort: month-first
        if d:
            found.append((d, True))
    return found


def _date_candidates(
        lines: list[str], reference: datetime, month_first: bool
) -> list[tuple[datetime, float]]:
    earliest = reference - _MAX_RECEIPT_AGE
    latest = reference + timedelta(days=1)       # tolerate timezone skew
    found = []
    for line in lines:
        for d, repaired in _dates_in_line(line, month_first):
            if not (earliest <= d <= latest):
                continue
            t = _TIME_RE.search(line)
            if t:
                d = d.replace(hour=int(t.group(1)), minute=int(t.group(2)), second=int(t.group(3) or 0))
                conf = 0.95
            else:
                # No time printed: noon UTC keeps the calendar day stable across timezones.
                d, conf = d.replace(hour=12), 0.85
            found.append((d, round(conf - 0.3, 2) if repaired else conf))
    return found


def find_date(
        lines: list[str], reference: datetime, month_first: bool = False
) -> tuple[Optional[datetime], float]:
    """First plausible date in one text (dates outside the last two years are ignored)."""
    candidates = _date_candidates(lines, reference, month_first)
    return candidates[0] if candidates else (None, 0.0)


def vote_date(
        texts: list[list[str]], reference: datetime, month_first: bool = False
) -> tuple[Optional[datetime], float]:
    """
    The first date of each OCR pass votes; the calendar day read by most passes
    wins, then the most confident reading of that day (with time if any).
    """
    firsts = [find_date(lines, reference, month_first) for lines in texts]
    firsts = [(d, c) for d, c in firsts if d]
    if not firsts:
        return None, 0.0
    votes = Counter(d.date() for d, _ in firsts)
    day = max(votes, key=lambda k: (votes[k], max(c for d, c in firsts if d.date() == k)))
    return max(((d, c) for d, c in firsts if d.date() == day), key=lambda dc: dc[1])


# ── Merchant ──────────────────────────────────────────────────────────────────

def _clean_merchant(line: str) -> str:
    name = _LEGAL_FORM_RE.sub("", line)
    name = re.sub(r"[«»\"“”„]", "", name)     # keep ' — it is part of Ukrainian words
    name = re.sub(r"\s{2,}", " ", name).strip(" .,-:;")
    return name[:64]


def _is_wordlike(token: str) -> bool:
    """A real word: ≥ 3 letters, one script, at least one vowel (OCR noise breaks all three)."""
    t = token.strip(_WORD_STRIP)
    if len(t) < 3 or not _VOWEL_RE.search(t):
        return False
    return bool(
        re.fullmatch(r"[а-яіїєґё'’\-&]+", t, re.IGNORECASE)
        or re.fullmatch(r"[a-z'’\-&.]+", t, re.IGNORECASE)
    )


def _looks_like_text(line: str) -> bool:
    """Most of the non-numeric tokens are real words."""
    tokens = [t for t in line.split() if not re.search(r"\d", t)]
    if not tokens:
        return False
    return sum(_is_wordlike(t) for t in tokens) / len(tokens) >= _MIN_WORDLIKE_SHARE


def guess_merchant(lines: list[str]) -> tuple[Optional[str], float]:
    """
    Unknown shop: the first header line that reads like a name (not an address / id / cashier).
    The name block ends at the address or phone line — below it are cashier and item rows
    ("КАПУЧИНО ВЕЛИКЕ"), so only a legal-form line ("ФОП Іваненко") may still follow.
    """
    name_block_over = False
    for idx, line in enumerate(lines[:_MERCHANT_HEADER_LINES]):
        if _ADDRESS_RE.search(line):
            name_block_over = True
            continue
        letters = sum(ch.isalpha() for ch in line)
        if letters < 3 or letters / len(line) < 0.5 or not _looks_like_text(line):
            continue
        if _MERCHANT_SKIP_RE.search(line) and not _LEGAL_FORM_RE.match(line):
            continue
        if name_block_over and not _LEGAL_FORM_RE.match(line):
            continue
        quoted = _QUOTED_NAME_RE.search(line)
        name = _clean_merchant(quoted.group(1) if quoted else line)
        if len(name) < 2:
            continue
        return name, (0.7 if idx < 3 else 0.45)
    return None, 0.0


# ── Category ──────────────────────────────────────────────────────────────────

def _score(text: str, patterns: dict[str, list[re.Pattern]], weight: int, scores: dict[str, int]) -> None:
    for category, regexes in patterns.items():
        hits = sum(1 for r in regexes if r.search(text))
        if hits:
            scores[category] = scores.get(category, 0) + hits * weight


def guess_category(text: str, merchant: Optional[str]) -> tuple[Optional[str], float]:
    scores: dict[str, int] = {}
    _score(text, _BRAND_RES, _BRAND_WEIGHT, scores)
    _score(text, _KEYWORD_RES, _KEYWORD_WEIGHT, scores)
    if merchant:
        merchant_scores: dict[str, int] = {}
        _score(merchant, _BRAND_RES, _BRAND_WEIGHT, merchant_scores)
        _score(merchant, _KEYWORD_RES, _KEYWORD_WEIGHT, merchant_scores)
        for cat, s in merchant_scores.items():
            scores[cat] = scores.get(cat, 0) + s * (_MERCHANT_MULTIPLIER - 1)

    if not scores:
        return None, 0.0

    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    best_cat, best = ranked[0]
    runner_up = ranked[1][1] if len(ranked) > 1 else 0

    confidence = 0.9 if best >= 3 else 0.7 if best == 2 else 0.5
    if runner_up and runner_up >= best * 0.75:
        confidence -= 0.2                     # close call between categories
    return best_cat, round(confidence, 2)
