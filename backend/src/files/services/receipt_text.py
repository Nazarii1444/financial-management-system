"""
ReceiptText
───────────
Text helpers that make keyword matching tolerant of typical OCR slips on receipts:

  normalise_line — fix Latin look-alikes inside Cyrillic words ("CУMA" → "СУМА")
                   and spacing inside amounts ("83. 00" → "83.00")
  skeleton       — script-independent shape of a word: Cyrillic and Latin
                   look-alikes map to the same letters, so the English OCR pass
                   reading "Сума" as "Cyma" still matches
  has_anchor     — fuzzy (Levenshtein) search for a structural keyword in a line

Pure functions only.
"""
from __future__ import annotations

import re
from functools import lru_cache

# Latin letters that Tesseract emits for Cyrillic ones (and vice versa).
_LATIN_TO_CYRILLIC = str.maketrans({
    "A": "А", "B": "В", "C": "С", "E": "Е", "H": "Н", "I": "І", "K": "К", "M": "М",
    "O": "О", "P": "Р", "T": "Т", "X": "Х", "Y": "У",
    "a": "а", "c": "с", "e": "е", "i": "і", "o": "о", "p": "р", "x": "х", "y": "у",
})

# Upper-case Cyrillic → the Latin/digit shape Tesseract's English model reads it as.
_SKELETON = str.maketrans({
    "А": "A", "В": "B", "С": "C", "Е": "E", "Н": "H", "І": "I", "К": "K", "М": "M",
    "О": "O", "Р": "P", "Т": "T", "Х": "X", "У": "Y", "Г": "F", "П": "N", "И": "N",
    "Д": "A", "Ч": "U", "Ш": "W", "З": "3", "Ї": "I", "Й": "N", "Л": "N", "Я": "A",
    "Є": "E", "Ь": "B", "Б": "6", "Ц": "U", "Щ": "W", "Ж": "X", "Ф": "O", "Ю": "IO",
    "Ґ": "F", "Ё": "E", "Ы": "BI", "Э": "3",
})

_CYRILLIC_RE = re.compile(r"[а-яіїєґё]", re.IGNORECASE)
_LATIN_RE = re.compile(r"[a-z]", re.IGNORECASE)
_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)
_SPLIT_AMOUNT_RE = re.compile(r"(?<=\d)([.,])\s(?=\d{2}(?!\d))")


def _fix_token(token: str) -> str:
    cyr = len(_CYRILLIC_RE.findall(token))
    lat = len(_LATIN_RE.findall(token))
    if cyr and cyr >= lat:
        return token.translate(_LATIN_TO_CYRILLIC)
    return token


def normalise_line(line: str) -> str:
    """Latin look-alikes in mostly-Cyrillic tokens → Cyrillic; "83. 00" → "83.00"."""
    line = _SPLIT_AMOUNT_RE.sub(r"\1", line)
    return " ".join(_fix_token(t) for t in line.split())


def skeleton(word: str) -> str:
    return word.upper().translate(_SKELETON)


def levenshtein(a: str, b: str, limit: int = 3) -> int:
    """Edit distance, stopping early once it exceeds *limit*."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        if min(cur) > limit:
            return limit + 1
        prev = cur
    return prev[-1]


def _max_distance(length: int) -> int:
    if length <= 3:
        return 0
    if length <= 5:
        return 1
    return 2


@lru_cache(maxsize=256)
def _anchor_skeleton(anchor: str) -> tuple[str, int]:
    words = _WORD_RE.findall(anchor)
    return skeleton("".join(words)), len(words)


def words(line: str) -> list[str]:
    return _WORD_RE.findall(line)


def has_anchor(line: str, *anchors: str) -> bool:
    """
    True when the line contains one of *anchors* up to a few OCR slips.
    Multi-word anchors ("ДО СПЛАТИ") are compared against runs of adjacent words,
    and a word may be split or merged by OCR ("БЕЗГОТ ІВКОВА").
    """
    tokens = [skeleton(w) for w in words(line)]
    if not tokens:
        return False
    for anchor in anchors:
        target, n_words = _anchor_skeleton(anchor)
        limit = _max_distance(len(target))
        for size in {n_words, n_words + 1}:
            for i in range(len(tokens) - size + 1):
                candidate = "".join(tokens[i:i + size])
                if abs(len(candidate) - len(target)) > limit:
                    continue
                if levenshtein(candidate, target, limit) <= limit:
                    return True
    return False
