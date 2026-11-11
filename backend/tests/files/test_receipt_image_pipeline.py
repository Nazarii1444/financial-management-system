"""
Integration tests for the image pipeline on a real phone photo
(fixtures/receipt_mcdonalds_ua.jpg: receipt on a wooden table, partly in shadow).

Skipped when OpenCV / Tesseract (+ Ukrainian data) are not installed.
"""

import os
import shutil
from decimal import Decimal
from pathlib import Path

import pytest

from src.files.services import image_preprocess, ocr_service

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE = FIXTURES / "receipt_mcdonalds_ua.jpg"
# Same receipt, crumpled: its fiscal QR is detected but cannot be decoded.
FIXTURE_2 = FIXTURES / "receipt_mcdonalds_ua_2.jpg"

needs_cv2 = pytest.mark.skipif(not image_preprocess.CV2_AVAILABLE, reason="opencv not installed")


def _tesseract_with_ukr() -> bool:
    if not ocr_service._TESSERACT_AVAILABLE:
        return False
    if os.getenv("TESSERACT_CMD"):
        ocr_service.pytesseract.pytesseract.tesseract_cmd = os.environ["TESSERACT_CMD"]
    elif not shutil.which("tesseract"):
        default = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
        if not default.exists():
            return False
        ocr_service.pytesseract.pytesseract.tesseract_cmd = str(default)
    try:
        return "ukr" in ocr_service.pytesseract.get_languages(config="")
    except Exception:
        return False


@pytest.fixture(scope="module")
def photo() -> bytes:
    return FIXTURE.read_bytes()


@needs_cv2
def test_fiscal_qr_is_decoded(photo):
    _, gray = image_preprocess.load(photo)
    codes = image_preprocess.decode_qr(gray)
    assert any("cabinet.tax.gov.ua" in c and "sm=83.00" in c for c in codes)


@needs_cv2
def test_receipt_is_found_and_straightened(photo):
    bgr, gray = image_preprocess.load(photo)
    receipt = image_preprocess.crop_receipt(bgr, gray)

    assert receipt is not None
    h, w = receipt.shape
    assert h / w > 2.5                          # tall, narrow paper strip
    assert w < gray.shape[1] * 0.5              # table cropped away


@needs_cv2
def test_no_receipt_found_in_blank_image():
    import numpy as np
    blank = np.full((400, 300, 3), 120, dtype=np.uint8)
    assert image_preprocess.crop_receipt(blank, blank[:, :, 0]) is None


@needs_cv2
@pytest.mark.skipif(not _tesseract_with_ukr(), reason="tesseract with Ukrainian data not installed")
def test_full_pipeline_on_photo(photo):
    ocr_service._ocr_passes.cache_clear()
    result = ocr_service.analyse(photo, "image/jpeg")

    assert result["suggested_amount"] == 83.0
    assert result["amount_source"] == "fiscal_qr"
    assert result["suggested_currency"] == "UAH"
    assert result["suggested_date"].startswith("2026-10-03T10:37")
    assert result["suggested_category"] == "food"
    assert result["merchant"] == "McDonald's"
    assert result["confidence"] == "high"
    assert Decimal(str(result["suggested_amount"])) in {Decimal(str(a)) for a in result["amounts"]}


@needs_cv2
def test_feedback_qr_is_decoded_on_crumpled_photo():
    if not image_preprocess.ZXING_AVAILABLE:
        pytest.skip("zxing-cpp not installed")
    bgr, gray = image_preprocess.load(FIXTURE_2.read_bytes())
    codes = image_preprocess.decode_qr(gray, image_preprocess.crop_receipt(bgr, gray))
    assert any("mcdonalds.com" in c for c in codes)


@needs_cv2
@pytest.mark.skipif(not _tesseract_with_ukr(), reason="tesseract with Ukrainian data not installed")
def test_full_pipeline_without_fiscal_qr():
    ocr_service._ocr_passes.cache_clear()
    result = ocr_service.analyse(FIXTURE_2.read_bytes(), "image/jpeg")

    assert result["amount_source"] == "ocr"                 # no fiscal QR — everything from OCR
    assert result["suggested_amount"] == 83.0
    assert result["amount_confirmed"] is True
    assert result["suggested_currency"] == "UAH"
    assert result["suggested_date"].startswith("2026-10-03T10:37")
    assert result["merchant"] == "McDonald's"
    assert result["suggested_category"] == "food"
    assert result["retake_recommended"] is False
    assert len(result["ocr_passes"]) >= 2
