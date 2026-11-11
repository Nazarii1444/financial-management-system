"""
Typo- and case-tolerant text matching for transaction search.

Pure functions, no DB. A query matches a transaction when *every* query word
matches some word of the searchable text:

- exact / prefix / substring match            → 1.0
- Damerau–Levenshtein distance 1 (words ≥ 4)  → 0.8   ("ремнот" ~ "ремонт")
- distance 2 (words ≥ 8)                      → 0.6
- the same after fixing the keyboard layout   → ×0.9  ("htvjyn" → "ремонт")

Words are compared to whole words and to word prefixes of similar length, so
"ремнт" also finds "ремонту". Case, apostrophes (ʼ ’ ') and punctuation are
ignored; ё/є-style variants are not folded (different letters in Ukrainian).
"""
import re
from functools import lru_cache
from typing import Iterable, List, Optional, Sequence, Tuple

_APOSTROPHES = re.compile(r"[ʼ’'`´]")
_NON_WORD = re.compile(r"[^\w]+", re.UNICODE)

# Physical key positions: QWERTY (en) → ЙЦУКЕН (uk)
_EN = "qwertyuiop[]asdfghjkl;'zxcvbnm,."
_UK = "йцукенгшщзхїфівапролджєячсмитьбю"
_EN_TO_UK = str.maketrans(_EN, _UK)
_UK_TO_EN = str.maketrans(_UK, _EN)


def normalize(text: Optional[str]) -> str:
    text = _APOSTROPHES.sub("", (text or "").casefold())
    return " ".join(_NON_WORD.sub(" ", text).split())


def words(text: Optional[str]) -> List[str]:
    return list(_words(text or ""))


@lru_cache(maxsize=8192)
def _words(text: str) -> Tuple[str, ...]:
    # Names / notes / categories repeat a lot across transactions — normalise each text once
    return tuple(normalize(text).split())


def _layout_variants(raw_query: str) -> List[str]:
    """The query as typed plus the same keys read in the other layout."""
    q = (raw_query or "").casefold()
    variants = [q]
    for table in (_EN_TO_UK, _UK_TO_EN):
        swapped = q.translate(table)
        if swapped != q and swapped not in variants:
            variants.append(swapped)
    return variants


def damerau_levenshtein(a: str, b: str, limit: int = 3) -> int:
    """Optimal string alignment distance, early exit once it exceeds *limit*."""
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    prev2: List[int] = []
    prev = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        cur = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                cur[j] = min(cur[j], prev2[j - 2] + 1)
        if min(cur) > limit:
            return limit + 1
        prev2, prev = prev, cur
    return prev[-1]


def _allowed_typos(token: str) -> int:
    if len(token) >= 8:
        return 2
    if len(token) >= 4:
        return 1
    return 0


def token_score(token: str, candidates: Sequence[str]) -> float:
    best = 0.0
    for word in candidates:
        score = _word_score(token, word)
        if score == 1.0:
            return 1.0
        if score > best:
            best = score
    return best


@lru_cache(maxsize=65536)
def _word_score(token: str, word: str) -> float:
    """Score of one query token against one word; cached — the vocabulary is small and repetitive."""
    if word.startswith(token) or (len(token) >= 3 and token in word):
        return 1.0
    typos = _allowed_typos(token)
    if not typos:
        return 0.0
    best = 0.0
    # whole word, and prefixes around the token's length ("ремнт" ~ "ремонту")
    for cut in {len(word), len(token) - 1, len(token), len(token) + 1}:
        if cut < 3 or cut > len(word):
            continue
        d = damerau_levenshtein(token, word[:cut], typos)
        if d <= typos:
            best = max(best, 1.0 - 0.2 * d)
    return best


def compile_query(query: str) -> List[Tuple[str, ...]]:
    """Query tokens per keyboard-layout variant; build once, score many transactions."""
    return [_words(variant) for variant in _layout_variants(query)]


def match_score(query: str, fields: Iterable[Tuple[Optional[str], float]]) -> float:
    """
    Score in (0, 1] when every query word matches one of *fields* (text, weight),
    else 0. An empty query matches everything with 1.0.
    """
    return match_compiled(compile_query(query), fields)


def match_compiled(variants: Sequence[Tuple[str, ...]], fields: Iterable[Tuple[Optional[str], float]]) -> float:
    """`match_score` for a query already passed through `compile_query`."""
    field_words = [(_words(text or ""), weight) for text, weight in fields]
    best = 0.0
    for variant_index, tokens in enumerate(variants):
        if not tokens:
            return 1.0
        total = 0.0
        for token in tokens:
            score = max((token_score(token, ws) * weight for ws, weight in field_words), default=0.0)
            if score == 0:
                total = 0.0
                break
            total += score
        score = total / len(tokens)
        if variant_index:
            score *= 0.9
        best = max(best, score)
    return best
