"""
OcrService
──────────
Extracts text (and QR codes) from images and PDFs, then hands them to
`receipt_parser` for amount / date / currency / merchant / category detection.

Image pipeline (with OpenCV, see `image_preprocess`):
  1. find the receipt in the photo and straighten it (perspective warp)
  2. decode QR codes — a Ukrainian fiscal QR gives the exact total and date
  3. upscale + binarise with shadows flattened
  4. OCR in several passes (languages / layout modes); all passes are kept and
     the parser lets them vote, so a field lost in one pass can come from another

Without OpenCV it falls back to a single Pillow-preprocessed Tesseract pass.

Dependencies
------------
  pdfplumber             — text extraction from PDFs (no system deps)
  pytesseract            — OCR for images (requires Tesseract binary; graceful fallback)
  pillow                 — image decoding / fallback pre-processing
  opencv-python-headless — receipt detection, binarisation, QR decoding (optional)
  zxing-cpp              — more robust QR decoding than OpenCV's (optional)

Optional env vars
-----------------
  TESSERACT_CMD — path to the tesseract executable when it is not on PATH
                  (e.g. C:\\Program Files\\Tesseract-OCR\\tesseract.exe)
  OCR_LANG      — comma-separated Tesseract languages tried in order, e.g.
                  "ukr,eng" (default when the Ukrainian pack is installed;
                  otherwise "eng"). "+" combines languages within one pass.

If Tesseract is not installed, image OCR returns raw_text=None — the file is
still stored, and a fiscal QR can still provide the total and date.
"""
from __future__ import annotations

import io
import logging
import os
from datetime import datetime
from functools import lru_cache
from typing import Iterable, Optional

from src.files.services import image_preprocess, receipt_parser

logger = logging.getLogger(__name__)

# ── Optional imports (graceful fallback) ─────────────────────────────────────
try:
    import pytesseract
    from PIL import Image as PilImage, ImageFilter, ImageOps
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

_MIN_OCR_WIDTH = 1000        # px — Pillow fallback: small thumbnails are upscaled
_GOOD_ENOUGH_SCORE = 0.75    # stop trying further OCR passes once a parse is this confident
_MIN_LINE_CONFIDENCE = 55    # Tesseract 0–100; lines below this are treated as noise


# ── Public API ────────────────────────────────────────────────────────────────

def analyse(data: bytes, content_type: str) -> dict:
    """
    Run OCR/text-extraction on *data* and return the JSON stored in
    `Receipt.ocr_result` (see `result_from_passes` for the shape).
    """
    passes: list[tuple[str, Optional[float]]] = []
    qr_codes: list[str] = []
    pipeline = None

    if content_type == "application/pdf":
        text = _extract_pdf_text(data)
        passes = [(text, None)] if text else []
        pipeline = "pdf_text"
    elif content_type.startswith("image/"):
        passes, qr_codes = _extract_image(data)
        pipeline = _image_pipeline()

    return {**result_from_passes(passes, qr_codes=qr_codes), "pipeline": pipeline}


def capabilities() -> dict:
    """What the OCR pipeline can use on this host — logged at startup."""
    langs: list[str] = []
    if _TESSERACT_AVAILABLE:
        _configure_tesseract_cmd()
        try:
            langs = sorted(pytesseract.get_languages(config=""))
        except Exception:
            langs = []
    return {
        "opencv": image_preprocess.CV2_AVAILABLE,
        "zxing": image_preprocess.ZXING_AVAILABLE,
        "tesseract": bool(langs),
        "langs": langs,
        "pdf": _PDFPLUMBER_AVAILABLE,
    }


def capability_warnings(caps: dict) -> list[str]:
    """Human-readable problems with *caps* — each one makes receipt photos read noticeably worse."""
    warnings = []
    if not caps["opencv"]:
        warnings.append("opencv-python-headless is not installed: no receipt cropping, binarisation "
                        "or QR decoding — photos are OCR'd as-is (much lower accuracy)")
    if not caps["zxing"]:
        warnings.append("zxing-cpp is not installed: fiscal QR codes on crumpled receipts are often missed")
    if not caps["tesseract"]:
        warnings.append("Tesseract is not found (install it or set TESSERACT_CMD): no text from images")
    elif "ukr" not in caps["langs"]:
        warnings.append("Tesseract has no 'ukr' language data: Ukrainian receipts read poorly")
    return warnings


def _image_pipeline() -> str:
    """Which image path `analyse` takes — stored with every result so a degraded run is visible."""
    if image_preprocess.CV2_AVAILABLE:
        return "opencv" if _TESSERACT_AVAILABLE else "qr_only"
    return "pillow_fallback" if _TESSERACT_AVAILABLE else "none"


def result_from_text(
        raw_text: Optional[str],
        reference: Optional[datetime] = None,
        qr_codes: Iterable[str] = (),
        ocr_quality: Optional[float] = None,
) -> dict:
    """Single-text variant of `result_from_passes`."""
    return result_from_passes([(raw_text, ocr_quality)] if raw_text else [], reference, qr_codes)


def stored_passes(ocr_result: dict) -> list[tuple[str, Optional[float]]]:
    """(text, quality) per OCR pass from a stored `ocr_result` (older results only have raw_text)."""
    passes = [(p.get("text"), p.get("quality")) for p in ocr_result.get("ocr_passes") or [] if p.get("text")]
    if not passes and ocr_result.get("raw_text"):
        passes = [(ocr_result["raw_text"], ocr_result.get("ocr_quality"))]
    return passes


def result_from_passes(
        passes: list[tuple[str, Optional[float]]],
        reference: Optional[datetime] = None,
        qr_codes: Iterable[str] = (),
) -> dict:
    """
    *passes* — (text, ocr_quality) per OCR pass, best first.

    {
        "raw_text":           str | None,        # text of the best pass
        "ocr_passes":         [{"text", "quality"}, ...],   # every pass; build_draft re-parses them
        "qr_codes":           [str, ...],        # decoded QR payloads
        "ocr_quality":        float | None,      # mean Tesseract word confidence of the best pass, 0..1
        "amounts":            [float, ...],
        "suggested_amount":   float | None,
        "amount_source":      "fiscal_qr" | "ocr" | None,
        "amount_confirmed":   bool,              # total backed by ≥ 2 independent checks
        "suggested_currency": str   | None,
        "suggested_date":     str   | None,      # ISO-8601
        "suggested_category": str   | None,
        "merchant":           str   | None,
        "fiscal":             {"fiscal_number", "receipt_number"} | None,
        "confidence":         "high" | "medium" | "low" | "none",
        "confidence_score":   float,             # 0..1
        "field_confidence":   {"amount": float, "date": float, "merchant": float, "category": float},
        "text_unreadable":    bool,              # OCR produced mostly noise
        "retake_recommended": bool,              # no trustworthy total → ask for a clearer photo
        "parser_version":     int,
    }
    """
    qr_codes = list(qr_codes)
    passes = [(t, q) for t, q in passes if t]
    parsed = receipt_parser.parse_multi(passes, reference, qr_codes=qr_codes)
    raw_text, quality = passes[0] if passes else (None, None)
    return {
        "raw_text":           raw_text,
        "ocr_passes":         [{"text": t, "quality": round(q, 2) if q is not None else None} for t, q in passes],
        "qr_codes":           qr_codes,
        "ocr_quality":        round(quality, 2) if quality is not None else None,
        "amounts":            [float(a) for a in parsed.amounts],
        "suggested_amount":   float(parsed.amount) if parsed.amount is not None else None,
        "amount_source":      parsed.amount_source,
        "amount_confirmed":   parsed.amount_confirmed,
        "suggested_currency": parsed.currency,
        "suggested_date":     parsed.date.isoformat() if parsed.date else None,
        "suggested_category": parsed.category,
        "merchant":           parsed.merchant,
        "fiscal": {
            "fiscal_number":  parsed.fiscal.fiscal_number,
            "receipt_number": parsed.fiscal.receipt_number,
        } if parsed.fiscal else None,
        "confidence":         parsed.confidence_label,
        "confidence_score":   parsed.confidence_score,
        "field_confidence":   parsed.field_confidence,
        "text_unreadable":    parsed.text_unreadable,
        "retake_recommended": parsed.retake_recommended,
        "parser_version":     receipt_parser.PARSER_VERSION,
    }


# ── PDF ───────────────────────────────────────────────────────────────────────

def _extract_pdf_text(data: bytes) -> Optional[str]:
    if not _PDFPLUMBER_AVAILABLE:
        return None
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            pages = [page.extract_text() or "" for page in pdf.pages]
        return "\n".join(pages).strip() or None
    except Exception:
        return None


# ── Images ────────────────────────────────────────────────────────────────────

def _extract_image(data: bytes) -> tuple[list[tuple[str, float]], list[str]]:
    """Return (OCR passes best first, qr_codes) for an image upload."""
    if not image_preprocess.CV2_AVAILABLE:
        if not _TESSERACT_AVAILABLE:
            return [], []
        try:
            image = _preprocess_pil(PilImage.open(io.BytesIO(data)))
        except Exception:
            return [], []
        return _ocr_passes_ranked(image), []

    try:
        bgr, gray = image_preprocess.load(data)
    except Exception:
        logger.warning("OCR: could not decode image", exc_info=True)
        return [], []

    try:
        receipt = image_preprocess.crop_receipt(bgr, gray)
    except Exception:
        logger.warning("OCR: receipt detection failed", exc_info=True)
        receipt = None

    try:
        qr_codes = image_preprocess.decode_qr(gray, receipt)
    except Exception:
        logger.warning("OCR: QR decoding failed", exc_info=True)
        qr_codes = []

    if not _TESSERACT_AVAILABLE:
        return [], qr_codes

    try:
        image = image_preprocess.prepare_for_ocr(receipt if receipt is not None else gray)
    except Exception:
        logger.warning("OCR: preprocessing failed, using raw greyscale", exc_info=True)
        image = gray

    return _ocr_passes_ranked(image), qr_codes


def _preprocess_pil(img: "PilImage.Image") -> "PilImage.Image":
    img = ImageOps.exif_transpose(img)           # phone photos are often rotated via EXIF
    img = img.convert("L")                       # greyscale
    if img.width < _MIN_OCR_WIDTH:
        scale = _MIN_OCR_WIDTH / img.width
        img = img.resize((_MIN_OCR_WIDTH, int(img.height * scale)), PilImage.LANCZOS)
    img = ImageOps.autocontrast(img)
    return img.filter(ImageFilter.SHARPEN)


def _configure_tesseract_cmd() -> None:
    cmd = os.getenv("TESSERACT_CMD")
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd


@lru_cache(maxsize=1)
def _ocr_passes() -> tuple[tuple[str, int], ...]:
    """
    (language, page-segmentation mode) pairs, tried in order:
    each language with --psm 6 (uniform text block), then the first language
    with --psm 4 (single column of variable-size text).
    """
    _configure_tesseract_cmd()

    configured = os.getenv("OCR_LANG")
    if configured:
        langs = [lang.strip() for lang in configured.split(",") if lang.strip()]
    else:
        try:
            installed = set(pytesseract.get_languages(config=""))
        except Exception:
            installed = set()
        # Separate passes beat "ukr+eng": combined, Tesseract flips Cyrillic to look-alike Latin.
        langs = ["ukr", "eng"] if "ukr" in installed else ["eng"]

    return tuple((lang, 6) for lang in langs) + ((langs[0], 4),)


def _ocr(image, lang: str, psm: int) -> tuple[str, float]:
    """
    Run Tesseract once; return (text, quality 0..1).

    Lines whose mean word confidence is below _MIN_LINE_CONFIDENCE are dropped:
    on receipts they are ASCII-art order numbers, QR codes, logos or a table
    texture — noise that would otherwise pollute amount/merchant detection.
    Quality is the mean confidence of the words that survive (0 if none).
    """
    data = pytesseract.image_to_data(
        image, lang=lang, config=f"--psm {psm}", output_type=pytesseract.Output.DICT,
    )
    lines: dict[tuple, list[tuple[str, float]]] = {}
    for i, word in enumerate(data["text"]):
        word = word.strip()
        conf = float(data["conf"][i])
        if not word or conf < 0:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        lines.setdefault(key, []).append((word, conf))

    kept_lines: list[str] = []
    kept_confidences: list[float] = []
    for words in lines.values():
        confs = [c for _, c in words]
        if sum(confs) / len(confs) >= _MIN_LINE_CONFIDENCE:
            kept_lines.append(" ".join(w for w, _ in words))
            kept_confidences.extend(confs)

    quality = sum(kept_confidences) / len(kept_confidences) / 100 if kept_confidences else 0.0
    return "\n".join(kept_lines), quality


def _ocr_passes_ranked(image) -> list[tuple[str, float]]:
    """
    Run the OCR passes and return every non-empty (text, quality), best first —
    ranked by how well the text alone parses plus a bit of Tesseract's own
    confidence. Stops early once the passes so far confirm the total (≥ 2
    independent checks) and agree on a date; otherwise all passes run, since
    the parser lets them vote field by field.
    """
    ranked: list[tuple[float, str, float]] = []
    for lang, psm in _ocr_passes():
        try:
            text, quality = _ocr(image, lang, psm)
        except Exception:
            logger.warning("OCR pass failed: lang=%s psm=%s", lang, psm, exc_info=True)
            continue
        if not text:
            continue
        score = receipt_parser.parse(text, ocr_quality=quality).confidence_score
        logger.info("OCR pass lang=%s psm=%s score=%.2f quality=%.2f", lang, psm, score, quality)
        ranked.append((score + 0.25 * quality, text, quality))

        combined = receipt_parser.parse_multi([(t, q) for _, t, q in ranked])
        if combined.amount_confirmed and combined.date and combined.confidence_score >= _GOOD_ENOUGH_SCORE:
            break

    ranked.sort(key=lambda r: r[0], reverse=True)
    return [(text, quality) for _, text, quality in ranked]
