# Financial Management System — Receipt OCR Accuracy Plan

> Goal: turn a phone photo (or PDF / e-receipt) of **any** receipt into an accurate
> transaction draft — total, date, currency, merchant, category **and line items** —
> using only local, deterministic technology.
>
> **Constraints**
> - No generative or cloud AI (no LLM / vision APIs, no LayoutLM/Donut-style document models).
> - Local OCR engines (Tesseract, PaddleOCR) are allowed: they only turn pixels into characters.
> - Everything runs offline on the server.
>
> **Realistic target** (on reasonably clear photos): total ~98 % when the Ukrainian fiscal QR
> is readable, ~85–90 % without it; date ~90–95 %; fully correct item lists ~70–90 %.
> No system reads 100 % of receipts (faded thermal paper, crumpled, handwritten) — the design
> degrades gracefully: empty field + low confidence + `retake_recommended`, never garbage, and
> the user always confirms the draft.

Complexity: **Low** (days) · **Medium** (1–2 weeks) · **High** (multi-week / research-flavored).

---

## Current state (parser v3)

Pipeline in `src/files/services/`:

| Step | Where | Notes |
|---|---|---|
| EXIF rotation | `image_preprocess.load` | |
| QR decoding | `image_preprocess.decode_qr` | `cv2.QRCodeDetectorAruco`; fiscal QR → exact total + date |
| Receipt detection + perspective warp | `image_preprocess.crop_receipt` | 4 "paper" masks, first with a good quadrilateral fit |
| Upscale + shadow removal + Otsu | `image_preprocess.prepare_for_ocr` | divide by estimated paper background |
| Multi-pass Tesseract | `ocr_service._best_ocr_pass` | `ukr` → `eng` → `ukr`/psm 4, early exit at score ≥ 0.75 |
| Noise-line filter | `ocr_service._ocr` | drop lines with mean word confidence < 55 |
| Field parsing | `receipt_parser.parse` | regex/keyword heuristics; no line items |
| Draft + confirm | `receipt_transaction_service`, `file_router` | user confirms with `{}` or edited fields |

Fallback without OpenCV: Pillow greyscale/upscale/autocontrast/sharpen only — no crop, no QR.

**Known weaknesses:** exact keyword matching breaks on OCR slips (`ГРя`, `ЗВМОВЛЕННЯ`,
`HOMEP`); Tesseract line grouping sometimes splits a name from its price; nothing
cross-checks numbers (a `93.00` misread of `83.00` goes through); no line items; merchant
names keep OCR typos; no orientation / blur handling.

### Prerequisite (ops)
The server must run with `backend/.venv` (which has `opencv-python-headless`). Receipt 32
was processed by an interpreter without OpenCV, i.e. the fallback path. Add a one-time
startup log line reporting `opencv=… tesseract=… langs=…` so this is visible.

---

## Phase 0 — Evaluation corpus & harness · **Low–Medium**

Everything after this is measured, not guessed.

- **Corpus:** `tests/files/fixtures/receipts/<name>.jpg|pdf` + `<name>.json` ground truth:
  ```json
  { "merchant": "McDonald's", "total": "303.00", "currency": "UAH",
    "date": "2026-10-03T10:37", "category": "food",
    "items": [{"name": "БІГ МАК МЕНЮ ВЕЛИКЕ", "qty": 1, "amount": "219.00"}] }
  ```
  30–50 receipts: supermarkets (АТБ, Сільпо, Novus), fuel (WOG, OKKO), pharmacies, cafés,
  fast food, small ФОП shops; hard cases (shadow, crumpled, faded, long, weighed goods,
  discounts, no QR, English). Card numbers / personal data blurred before committing.
- **Harness:** `scripts/eval_receipts.py` → per-field accuracy table:
  total, date, currency, merchant, category, item precision/recall (name fuzzy + amount
  exact), "items sum to total" rate, mean processing time. Option `--engine` to compare OCR
  engines; `--save-debug` writes intermediate images.
- **Baseline:** run on the current pipeline and keep the numbers in the doc / thesis.

---

## Phase 1 — Preprocessing improvements · **Low–Medium**

All in `image_preprocess.py`; each one is kept only if the harness shows a gain.

| Item | Technique | Fixes |
|---|---|---|
| **P1. Orientation** | Tesseract OSD (`--psm 0`) on the cropped receipt → rotate 90/180/270° | upside-down / sideways photos without EXIF |
| **P2. Blur / quality gate** | variance of Laplacian (+ min receipt size in px); below threshold → skip OCR, `retake_recommended=true`, reason `"blurry"` | wasted OCR, confusing drafts |
| **P3. Faint print** | try Sauvola local thresholding and a contrast stretch besides Otsu; pick the binarisation whose OCR parses best (reuse multi-pass ranking) | faded thermal receipts |
| **P4. Dot-matrix fonts** | light morphological dilation / closing of the binary image when characters are fragmented (many tiny components) | old cash-register fonts with gaps |
| **P5. Curved paper** *(later)* | detect text-line curvature, piecewise remap to flatten | crumpled / hand-held receipts — **High** |
| **P6. Long receipts** *(later)* | accept several photos per receipt; OCR in order and concatenate (overlap de-dup by matching lines) | supermarket receipts that don't fit one photo |

Also: return a `quality` block in `ocr_result` (`sharpness`, `receipt_found`, `rotation`) so
the frontend can explain *why* a retake is suggested.

---

## Phase 2 — Pluggable OCR engine · **Medium**

Decouple recognition from everything else so engines can be compared on the corpus.

- **Interface** (`src/files/services/ocr_engines/base.py`):
  ```python
  class OcrFragment:      # a word (Tesseract) or a text line (PaddleOCR)
      text: str
      confidence: float   # 0..1
      box: tuple[int, int, int, int]   # x, y, w, h in the prepared image

  class OcrEngine(Protocol):
      name: str
      def available(self) -> bool: ...
      def recognize(self, image, languages: list[str]) -> list[OcrFragment]: ...
  ```
  The layout step (Phase 3) works on fragments + boxes, so it doesn't care whether an engine
  returns words or whole lines.
- **`TesseractEngine`** — current behaviour (multi-pass, `image_to_data`), moved out of
  `ocr_service.py`.
- **`PaddleOcrEngine`** — optional dependency (`paddleocr` + `paddlepaddle`, CPU build,
  Cyrillic recognition model). Lazy import; absent → engine reports unavailable.
- **Selection:** env `OCR_ENGINE=tesseract|paddle|auto` (default `tesseract`); `auto` =
  first available in a configured order. Record `engine` in `ocr_result`.
- **Decision rule:** run the harness on both; switch the default only if PaddleOCR wins on
  total/item accuracy by a clear margin and its install/runtime cost is acceptable on the
  deployment host. EasyOCR is not considered (slower, heavier, no accuracy advantage).

---

## Phase 3 — Layout reconstruction & text normalisation · **Medium**

New `receipt_layout.py`, between OCR and parsing.

- **Rows from geometry:** cluster fragments by vertical centre (tolerance ~0.5 × median
  text height), order left→right. Each row → `{text, price_tokens, tax_letter, y, confidence}`;
  the price column is the right-aligned cluster of numeric fragments.
- **Homoglyph normalisation:** in mostly-Cyrillic upper-case tokens map Latin look-alikes
  `A B C E H I K M O P T X` → `А В С Е Н І К М О Р Т Х` (and the reverse for Latin tokens).
- **Fuzzy anchors:** Levenshtein ≤ 1–2 (length-dependent) for structural keywords —
  `СУМА`, `ДО СПЛАТИ`, `ПДВ`, `БЕЗГОТІВКОВА`, `КАРТКА`, `ГОТІВКА`, `РЕШТА`, `ЗНИЖКА`,
  `ЧЕК`, `ФІСКАЛЬНИЙ ЧЕК`, `грн`, `TOTAL`, `SUBTOTAL`, `CASH`, `CHANGE`.
- **Tesseract user-words:** a receipt vocabulary file (anchors + top brands) passed via
  `--user-words` to bias recognition.
- **Currency inference:** fiscal markers (`ПН`, `ФН`, `ЗН`, `ПДВ`, `ФІСКАЛЬНИЙ ЧЕК`) ⇒ UAH
  even when `грн` is unreadable.

---

## Phase 4 — Section segmentation & item grammar · **Medium**

New `receipt_items.py`. Ukrainian fiscal receipts follow a legally fixed order, parsed with a
small state machine over the rows:

| Section | Entered at | Contents |
|---|---|---|
| HEADER | top | legal name, address, ПН/ІД, cashier |
| ITEMS | first row with price (+ tax letter) | goods, qty rows, weight rows, modifiers, discounts |
| TOTALS | `СУМА` / `ДО СПЛАТИ` | total, ПДВ, rounding |
| PAYMENT | `КАРТКА` / `БЕЗГОТІВКОВА` / `ГОТІВКА` / bank name | method, terminal, change |
| FOOTER | `ЧЕК №` / date / `ФН` / `ЗН` | receipt number, timestamp, fiscal ids |

Separator rows (`-----`) and fuzzy anchors mark boundaries; rows that fit no section
(ASCII-art order numbers, survey prompts) are ignored.

**Item rules**
- Item row: name + price [+ tax letter `А/Б/В/…`].
- Wrapped name: price-less row(s) followed by a row ending in a price → joined.
- Quantity: `2.000 X 19.99`, `2 x 19.99 = 39.98` → `quantity`, `unit_price` of the adjacent item.
- Weight: `0.456 кг X 89.90` → `quantity=0.456`, `unit="кг"`.
- Modifiers: rows starting with `*` → appended to the previous item's `note`, never items.
- Discounts: `ЗНИЖКА -5.00` / `Знижка 10%` → applied to the preceding item.
- Ignored: barcodes, УКТЗЕД codes, excise rows (`АМ …`), digit-only rows.

The **total** comes from the TOTALS section; the "largest number" fallback becomes last resort.
A generic non-fiscal grammar (English/EU receipts: `TOTAL`, `SUBTOTAL`, item rows) uses the
same row model with different anchors.

---

## Phase 5 — Reconciliation & numeric re-OCR · **Medium**  ⭐ biggest accuracy gain

New `reconcile.py`: use the receipt's internal consistency to detect and fix OCR errors.

1. **Σ items = total** (total from fiscal QR when present — exact).
2. **Per item:** `quantity × unit_price = amount` (± 0.01).
3. **VAT:** `ПДВ = total × 20/120` (or 7/107) — validates the total without a QR.
4. **Payment:** card/cash amount = total; cash − change = total.
5. **Digit-confusion repair:** on mismatch, try confusable substitutions
   (`8↔3↔9`, `0↔6↔8`, `1↔7`, `5↔6`) on the lowest-confidence amounts; accept the unique
   minimal change that satisfies all checks; flag repaired values.
6. **Numeric re-OCR:** for amounts still failing, crop the price box and re-recognise with
   a digit whitelist (`0-9.,-`) as a single line (Tesseract `--psm 7`); feed back into 1–5.

Output on the draft: `items_status = matched | corrected | mismatch | none`, `difference`,
and per-item `confidence` / `corrected`. Field confidences derive from passed checks, not
only OCR confidence.

---

## Phase 6 — Merchant templates · **Medium**

Config-driven layouts for the chains that cover most purchases.

- `src/files/templates/*.yaml`, e.g.
  ```yaml
  name: McDonald's
  category: food
  match: { tax_ids: ["237444526652"], brands: ["макдональдз", "mcdonald"] }
  items:
    modifier_prefix: "*"
  ignore: ["НОМЕР ЗАМОВЛЕННЯ", "НОМЕР ТЕНТА", "Розкажи про візит"]
  ```
- Matching order: tax ID `ПН` (exact, from header) → fiscal number → fuzzy brand.
- A template only overrides what differs from the generic grammar (anchors, ignore rows,
  modifier syntax, quirks); unknown merchants use the generic rules.
- Start with ~10 chains from the corpus; templates are data, easy to extend and to describe.

---

## Phase 7 — Merchant & category accuracy, learning from users · **Medium**

1. **Canonical brands:** dictionary `brand → display name, category`, fuzzy-matched
   (`КакДдональдз Юкрейн Лтгд` → `McDonald's`); strip corporate suffixes
   (`Юкрейн`, `Україна`, `Лтд`, `LLC`).
2. **Per-register memory:** fiscal QR `fn` identifies the cash register. Table
   `merchant_aliases (user_id, fiscal_number | tax_id, name, category)`, written when the user
   confirms a draft; next receipt from the same register is pre-filled from it.
3. **User correction rules:** when the user changes a draft's category / item category, store
   `merchant → category` and `item keyword → category`; drafts apply user rules first, then
   templates, then the built-in dictionary.
4. **Per-item categories:** keyword map (`пиво` → alcohol, `сигарети` → cigarettes,
   `корм` → pets …); unmatched items inherit the transaction category.

---

## Phase 8 — Line items data model & API · **Low–Medium**

- **Table** `transaction_items`: `id_`, `transaction_id` (FK, `ON DELETE CASCADE`),
  `position`, `name`, `quantity` `Numeric(10,3)`, `unit`, `unit_price`, `amount`,
  `category_name` (null = inherit), `note`. Alembic revision.
- **Draft:** `items[]`, `items_total`, `items_status`, `difference`.
- **Confirm:** `POST /api/files/receipts/{id}/transaction` accepts `items` (full replacement);
  422 if Σ items ≠ amount.
- **Read:** `GET /api/transactions/{id}` includes items; later analytics option
  `?split_items=true` for per-item category breakdown.
- Can be built in parallel with Phases 4–5.

---

## Phase 9 — Exact-text sources · **Low**

- **E-receipts:** ПРРО e-receipts (PDF, email, bank apps) contain exact text — the existing
  `pdfplumber` path parses them with no OCR. Promote "upload e-receipt" in the UI.
- **Tax-cabinet lookup** *(deferred, needs a decision)*: the fiscal QR URL leads to the
  receipt page on cabinet.tax.gov.ua, which lists items. Not AI, but an external request +
  fragile HTML parsing; only as opt-in cross-check.

---

## Order, dependencies, expected effect

| # | Phase | Depends on | Complexity | Expected effect |
|---|---|---|---|---|
| — | Ops: run server from `.venv`, startup capability log | — | Low | unlocks the existing pipeline |
| 0 | Corpus + harness | — | Low–Med | makes everything measurable |
| 1 | Preprocessing P1–P4 | 0 | Low–Med | fewer unreadable photos; faint/rotated receipts |
| 2 | Pluggable OCR engine (+ PaddleOCR benchmark) | 0 | Med | data-driven engine choice |
| 3 | Layout + normalisation | 2 | Med | most keyword misses fixed |
| 4 | Sections + item grammar | 3 | Med | line items exist |
| 5 | Reconciliation + numeric re-OCR | 4 | Med | biggest gain on totals & items |
| 8 | Items data model / API | — (parallel to 4–5) | Low–Med | items stored and editable |
| 6 | Merchant templates | 4 | Med | top chains near-perfect |
| 7 | Brands, register memory, user rules | 8 | Med | merchant/category improve with use |
| 1b | Preprocessing P5–P6 | 1 | High | crumpled / long receipts |
| 9 | E-receipts (+ optional tax lookup) | — | Low | exact data where available |

**Testing per phase:** unit tests on text/row samples for each rule; regression tests on
the fixture photos; harness run on the whole corpus after every phase with results recorded
here (baseline → phase N).
