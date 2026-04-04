"""
OcrService
──────────
Extracts text from images and PDFs, then parses:
  - monetary amounts
  - merchant name (heuristic)
  - suggested expense category (keyword matching)

Dependencies
------------
  pdfplumber  — text extraction from PDFs (no system deps)
  pytesseract — OCR for images (requires Tesseract binary; graceful fallback)
  pillow      — image pre-processing before Tesseract

If Tesseract is not installed, image OCR returns raw_text=None and
amounts/category are left empty — the file is still stored.
"""
from __future__ import annotations

import io
import re
from decimal import Decimal, InvalidOperation
from typing import Optional

# ── Optional imports (graceful fallback) ─────────────────────────────────────
try:
    import pytesseract
    from PIL import Image as PilImage
    _TESSERACT_AVAILABLE = True
except ImportError:
    pytesseract = None       # type: ignore[assignment]
    PilImage = None          # type: ignore[assignment]
    _TESSERACT_AVAILABLE = False

try:
    import pdfplumber
    _PDFPLUMBER_AVAILABLE = True
except ImportError:
    pdfplumber = None        # type: ignore[assignment]
    _PDFPLUMBER_AVAILABLE = False

# ── Category keyword map ──────────────────────────────────────────────────────
_CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "food": [
        "restaurant", "cafe", "pizza", "burger", "sushi", "mcdonald",
        "kfc", "subway", "starbucks", "coffee", "bakery", "grocery",
        "supermarket", "bistro", "tavern", "bar", "pub", "fast food",
        "їжа", "кафе", "ресторан", "піца", "бургер",
    ],
    "shopping": [
        "mall", "shop", "store", "amazon", "ebay", "walmart", "ikea",
        "zara", "h&m", "asos", "aliexpress", "market", "boutique",
        "магазин", "торговий", "супермаркет",
    ],
    "health": [
        "pharmacy", "drug", "hospital", "clinic", "doctor", "medical",
        "dentist", "optician", "lab", "аптека", "лікарня", "клініка",
    ],
    "transportation": [
        "uber", "lyft", "taxi", "fuel", "gas", "petrol", "parking",
        "metro", "bus", "train", "airline", "flight", "авіа", "таксі",
        "пальне", "бензин", "автобус", "метро",
    ],
    "electronics": [
        "apple", "samsung", "sony", "microsoft", "dell", "hp",
        "computer", "laptop", "phone", "gadget", "electronics",
    ],
    "entertainment": [
        "cinema", "movie", "theater", "concert", "spotify", "netflix",
        "game", "steam", "кіно", "театр", "концерт",
    ],
    "utilities": [
        "electric", "water", "gas", "internet", "phone bill", "rent",
        "utility", "комунальні", "електро", "інтернет",
    ],
    "travel": [
        "hotel", "airbnb", "booking", "hostel", "resort", "tour",
        "готель", "туристичний",
    ],
    "education": [
        "university", "school", "course", "tuition", "book", "library",
        "навчання", "університет", "курси",
    ],
}

# Regex: find monetary values like 25.50 / 1,234.00 / 100 UAH / $99.99 / 10 грн
_AMOUNT_RE = re.compile(
    r"(?:total|sum|amount|subtotal|due|підсумок|сума|до\sсплати)?\s*"
    r"[$€£₴]?\s*(\d{1,6}(?:[.,]\d{3})*(?:[.,]\d{1,2}))",
    re.IGNORECASE,
)
_STANDALONE_AMOUNT_RE = re.compile(r"\b(\d{1,6}[.,]\d{2})\b")


# ── Public API ────────────────────────────────────────────────────────────────

def analyse(data: bytes, content_type: str) -> dict:
    """
    Run OCR/text-extraction on *data* and return a result dict:
    {
        "raw_text":           str | None,
        "amounts":            [float, ...],
        "suggested_amount":   float | None,
        "suggested_category": str  | None,
        "merchant":           str  | None,
        "confidence":         "high" | "medium" | "low" | "none",
    }
    """
    raw_text: Optional[str] = None

    if content_type == "application/pdf":
        raw_text = _extract_pdf_text(data)
    elif content_type.startswith("image/"):
        raw_text = _extract_image_text(data)

    if not raw_text:
        return _empty_result("none")

    amounts       = _parse_amounts(raw_text)
    suggested_amt = _pick_best_amount(raw_text, amounts)
    category      = _suggest_category(raw_text)
    merchant      = _guess_merchant(raw_text)
    confidence    = _confidence(raw_text, amounts)

    return {
        "raw_text":           raw_text,
        "amounts":            amounts,
        "suggested_amount":   float(suggested_amt) if suggested_amt else None,
        "suggested_category": category,
        "merchant":           merchant,
        "confidence":         confidence,
    }


# ── Text extraction ───────────────────────────────────────────────────────────

def _extract_pdf_text(data: bytes) -> Optional[str]:
    if not _PDFPLUMBER_AVAILABLE:
        return None
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
        return "\n".join(pages).strip() or None
    except Exception:
        return None


def _extract_image_text(data: bytes) -> Optional[str]:
    if not _TESSERACT_AVAILABLE:
        return None
    try:
        img = PilImage.open(io.BytesIO(data)).convert("L")   # greyscale
        text = pytesseract.image_to_string(img, config="--psm 6")
        return text.strip() or None
    except Exception:
        return None


# ── Amount parsing ────────────────────────────────────────────────────────────

def _parse_amounts(text: str) -> list[float]:
    raw_matches = _STANDALONE_AMOUNT_RE.findall(text)
    seen: list[float] = []
    for m in raw_matches:
        normalised = m.replace(",", ".")
        try:
            val = float(Decimal(normalised))
            if val > 0 and val not in seen:
                seen.append(val)
        except InvalidOperation:
            pass
    return sorted(seen, reverse=True)[:10]   # top-10 unique amounts


def _pick_best_amount(text: str, amounts: list[float]) -> Optional[Decimal]:
    """Try to find the 'Total' line amount; fall back to largest amount."""
    total_re = re.compile(
        r"(?:total|sum|due|subtotal|підсумок|сума|до\sсплати)[^\d]*(\d+[.,]\d{2})",
        re.IGNORECASE,
    )
    m = total_re.search(text)
    if m:
        try:
            return Decimal(m.group(1).replace(",", "."))
        except InvalidOperation:
            pass
    return Decimal(str(amounts[0])) if amounts else None


# ── Category / merchant heuristics ───────────────────────────────────────────

def _suggest_category(text: str) -> Optional[str]:
    lower = text.lower()
    best_cat: Optional[str] = None
    best_count = 0
    for category, keywords in _CATEGORY_KEYWORDS.items():
        count = sum(1 for kw in keywords if kw in lower)
        if count > best_count:
            best_count = count
            best_cat = category
    return best_cat if best_count > 0 else None


def _guess_merchant(text: str) -> Optional[str]:
    """Return the first non-empty line of the receipt as a heuristic merchant name."""
    for line in text.splitlines():
        clean = line.strip()
        if len(clean) >= 3 and not re.match(r"^\d", clean):
            return clean[:128]
    return None


def _confidence(text: str, amounts: list[float]) -> str:
    if not text:
        return "none"
    if len(text) > 100 and amounts:
        return "high"
    if amounts:
        return "medium"
    return "low"


def _empty_result(confidence: str) -> dict:
    return {
        "raw_text":           None,
        "amounts":            [],
        "suggested_amount":   None,
        "suggested_category": None,
        "merchant":           None,
        "confidence":         confidence,
    }

