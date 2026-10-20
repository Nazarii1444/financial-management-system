"""
ImagePreprocess
───────────────
Turns a phone photo of a receipt into images Tesseract can read, and decodes
QR codes (Ukrainian fiscal receipts carry the total and date in one).

  load           — bytes → upright colour + greyscale arrays (EXIF rotation applied)
  decode_qr      — all QR payloads found in the photo (zxing-cpp, then OpenCV)
  crop_receipt   — find the receipt (most rectangular paper-like region) and
                   straighten it with a perspective warp
  prepare_for_ocr — upscale + shadow-tolerant binarisation

Requires opencv-python-headless; `CV2_AVAILABLE` is False without it and
callers fall back to the plain Pillow pipeline.
"""
from __future__ import annotations

import io
from typing import Optional

from PIL import Image as PilImage, ImageOps

try:
    import cv2
    import numpy as np
    CV2_AVAILABLE = True
except ImportError:
    cv2 = None               # type: ignore[assignment]
    np = None                # type: ignore[assignment]
    CV2_AVAILABLE = False

try:
    import zxingcpp           # deterministic barcode decoder; more robust than OpenCV's on photos
    ZXING_AVAILABLE = True
except ImportError:
    zxingcpp = None          # type: ignore[assignment]
    ZXING_AVAILABLE = False

_DETECT_MAX_SIDE = 900       # px — receipt detection runs on a downscaled copy
_MIN_RECEIPT_AREA = 0.08     # receipt must cover ≥ 8 % of the photo …
_MAX_RECEIPT_AREA = 0.9      # … and not (almost) all of it — then it's already cropped
_MIN_QUAD_FILL = 0.93        # region area / area of its 4-corner fit
_OCR_TARGET_WIDTH = 1400     # px — ≈ 35 px per character on a 40-column receipt


def load(data: bytes) -> tuple["np.ndarray", "np.ndarray"]:
    """Decode *data* into (BGR colour, greyscale) arrays with EXIF orientation applied."""
    img = ImageOps.exif_transpose(PilImage.open(io.BytesIO(data))).convert("RGB")
    rgb = np.asarray(img)
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    return bgr, cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)


# ── QR codes ──────────────────────────────────────────────────────────────────

def _is_fiscal_qr(text: str) -> bool:
    return "tax.gov.ua" in text.lower()


def _qr_variants(gray: "np.ndarray", receipt: Optional["np.ndarray"]):
    """Images to try, cheapest / most likely first: full photo, straightened receipt, rescaled, binarised."""
    yield gray
    if receipt is not None:
        yield receipt
    for scale in (0.75, 0.5, 0.35):
        yield cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
    for img in ([gray] + ([receipt] if receipt is not None else [])):
        yield cv2.adaptiveThreshold(img, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 51, 10)


def _decode_zxing(img: "np.ndarray") -> list[str]:
    return [r.text for r in zxingcpp.read_barcodes(img, formats=zxingcpp.BarcodeFormat.QRCode) if r.text]


def _decode_cv2(img: "np.ndarray") -> list[str]:
    try:
        ok, texts, _, _ = cv2.QRCodeDetectorAruco().detectAndDecodeMulti(img)
    except cv2.error:
        return []
    return [t for t in texts if t] if ok else []


def decode_qr(gray: "np.ndarray", receipt: Optional["np.ndarray"] = None) -> list[str]:
    """
    Decode every QR code in the photo. Tries several image variants (and zxing-cpp
    before OpenCV's detector when installed); stops as soon as the fiscal QR is found.
    """
    decoders = ([_decode_zxing] if ZXING_AVAILABLE else []) + [_decode_cv2]
    found: list[str] = []
    for img in _qr_variants(gray, receipt):
        for decode in decoders:
            found.extend(t for t in decode(img) if t not in found)
        if any(_is_fiscal_qr(t) for t in found):
            break
    return found


# ── Receipt detection ─────────────────────────────────────────────────────────

def _order_corners(pts: "np.ndarray") -> "np.ndarray":
    """Order 4 points as top-left, top-right, bottom-right, bottom-left."""
    s = pts.sum(axis=1)
    d = np.diff(pts, axis=1).ravel()
    return np.array([pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]], dtype="float32")


def _paper_masks(small: "np.ndarray") -> list["np.ndarray"]:
    """
    Candidate "this pixel is paper" masks. Which cue works depends on the
    background: colourful tables → low saturation / low chroma; dark tables →
    brightness. Shadows break each cue differently, so all are tried.
    """
    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
    lab = cv2.cvtColor(small, cv2.COLOR_BGR2LAB).astype("float32")
    chroma = np.sqrt((lab[:, :, 1] - 128) ** 2 + (lab[:, :, 2] - 128) ** 2)
    chroma = cv2.normalize(chroma, None, 0, 255, cv2.NORM_MINMAX).astype("uint8")

    # Colour distance from the background, estimated from the photo's border strip.
    # Only a/b (not lightness) are compared, so shadows on the table don't matter.
    bw = max(2, int(min(small.shape[:2]) * 0.04))
    border = np.concatenate([
        lab[:bw].reshape(-1, 3), lab[-bw:].reshape(-1, 3),
        lab[:, :bw].reshape(-1, 3), lab[:, -bw:].reshape(-1, 3),
    ])
    bg_a, bg_b = np.median(border[:, 1]), np.median(border[:, 2])
    distance = np.sqrt((lab[:, :, 1] - bg_a) ** 2 + (lab[:, :, 2] - bg_b) ** 2)
    distance = cv2.normalize(distance, None, 0, 255, cv2.NORM_MINMAX).astype("uint8")

    masks = []
    for channel, invert in (
            (distance, False), (hsv[:, :, 1], True), (chroma, True), (hsv[:, :, 2], False),
    ):
        blurred = cv2.GaussianBlur(channel, (7, 7), 0)
        mode = cv2.THRESH_BINARY_INV if invert else cv2.THRESH_BINARY
        _, mask = cv2.threshold(blurred, 0, 255, mode + cv2.THRESH_OTSU)
        masks.append(mask)
    return masks


def _fit_quad(contour: "np.ndarray") -> Optional["np.ndarray"]:
    """Approximate the region by 4 corners (a receipt photographed at an angle is a trapezoid)."""
    hull = cv2.convexHull(contour)
    perimeter = cv2.arcLength(hull, True)
    for eps in (0.02, 0.03, 0.05):
        approx = cv2.approxPolyDP(hull, eps * perimeter, True)
        if len(approx) == 4:
            return approx.reshape(4, 2).astype("float32")
    return None


def _find_receipt_quad(masks: list["np.ndarray"]) -> Optional["np.ndarray"]:
    """
    First mask (in priority order) whose largest region is well described by a
    quadrilateral — i.e. the region fills ≥ _MIN_QUAD_FILL of its 4-corner fit.
    """
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
    for mask in masks:
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)    # fill printed text / QR holes
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)     # cut thin bridges to the background
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            continue
        contour = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(contour)
        if not (_MIN_RECEIPT_AREA <= area / float(mask.size) <= _MAX_RECEIPT_AREA):
            continue
        quad = _fit_quad(contour)
        if quad is not None and area / max(cv2.contourArea(quad), 1.0) >= _MIN_QUAD_FILL:
            return quad
    return None


def crop_receipt(bgr: "np.ndarray", gray: "np.ndarray") -> Optional["np.ndarray"]:
    """
    Return the straightened greyscale receipt, or None when no receipt-like
    region is found (the photo is then OCR'd as-is).
    """
    h, w = gray.shape
    scale = min(1.0, _DETECT_MAX_SIDE / max(h, w))
    small = cv2.resize(bgr, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA) if scale < 1 else bgr

    quad = _find_receipt_quad(_paper_masks(small))
    if quad is None:
        return None

    tl, tr, br, bl = _order_corners(quad / scale)
    out_w = int(max(np.linalg.norm(tr - tl), np.linalg.norm(br - bl)))
    out_h = int(max(np.linalg.norm(bl - tl), np.linalg.norm(br - tr)))
    if out_w < 50 or out_h < 50:
        return None

    dst = np.array([[0, 0], [out_w - 1, 0], [out_w - 1, out_h - 1], [0, out_h - 1]], dtype="float32")
    matrix = cv2.getPerspectiveTransform(np.array([tl, tr, br, bl], dtype="float32"), dst)
    return cv2.warpPerspective(gray, matrix, (out_w, out_h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


# ── OCR preparation ───────────────────────────────────────────────────────────

def _normalise_illumination(gray: "np.ndarray") -> "np.ndarray":
    """Divide by the estimated paper background so shadows and gradients flatten out."""
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (41, 41))
    background = cv2.morphologyEx(gray, cv2.MORPH_CLOSE, kernel)    # removes dark text, keeps paper
    background = cv2.GaussianBlur(background, (31, 31), 0)
    return cv2.divide(gray, background, scale=255)


def prepare_for_ocr(gray: "np.ndarray") -> "np.ndarray":
    """Upscale a (cropped) receipt to OCR size and binarise it with shadows flattened."""
    if gray.shape[1] < _OCR_TARGET_WIDTH:
        factor = _OCR_TARGET_WIDTH / gray.shape[1]
        gray = cv2.resize(gray, None, fx=factor, fy=factor, interpolation=cv2.INTER_CUBIC)

    norm = _normalise_illumination(gray)
    _, binary = cv2.threshold(norm, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return binary
