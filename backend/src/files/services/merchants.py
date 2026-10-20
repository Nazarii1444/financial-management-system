"""
Merchants
─────────
Directory of known shops/chains: canonical display name, expense category and
the identifiers that recognise them on a receipt even through OCR slips.

  match_merchant(lines, qr_codes) → (Merchant | None, confidence)

Lookup order (most reliable first):
  1. tax id printed on the receipt (ПН 12 digits / ЄДРПОУ 8 digits) — digits survive OCR well
  2. host of a non-fiscal QR code (feedback / loyalty links)
  3. fuzzy match of an alias in the receipt header

Only add tax ids copied from a real receipt — a wrong id mislabels every receipt of that shop.
All categories must be in ALLOWED_EXPENSE_CATEGORIES.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Optional
from urllib.parse import urlparse

from src.files.services.receipt_text import levenshtein, skeleton, words

_HEADER_LINES = 8
_TAX_ID_RE = re.compile(r"(?<!\d)(\d{12}|\d{10}|\d{8})(?!\d)")

# Suffixes of legal names that differ between receipts ("МакДональдз Юкрейн Лтд").
_NOISE_WORDS = {
    skeleton(w) for w in (
        "тов", "фоп", "пп", "піі", "пат", "прат", "ат", "дп", "ооо", "llc", "ltd", "inc",
        "юкрейн", "україна", "украина", "ukraine", "лтд", "маркет", "market", "ритейл", "рітейл",
        "retail", "магазин", "закусочна",
    )
}


@dataclass(frozen=True)
class Merchant:
    name: str
    category: str
    aliases: tuple[str, ...] = ()
    tax_ids: tuple[str, ...] = ()
    qr_hosts: tuple[str, ...] = ()
    keys: tuple[str, ...] = field(init=False, default=())

    def __post_init__(self):
        keys = {_alias_key(a) for a in (self.name, *self.aliases)}
        object.__setattr__(self, "keys", tuple(k for k in keys if k))


def _alias_key(text: str) -> str:
    tokens = [skeleton(w) for w in words(text)]
    return "".join(t for t in tokens if t not in _NOISE_WORDS) or "".join(tokens)


def _m(name: str, category: str, *aliases: str, tax_ids=(), qr_hosts=()) -> Merchant:
    return Merchant(name, category, aliases, tuple(tax_ids), tuple(qr_hosts))


MERCHANTS: list[Merchant] = [
    # ── food: groceries ──
    _m("АТБ", "food", "атб", "atb", "атб-маркет", qr_hosts=("atbmarket.com",)),
    _m("Сільпо", "food", "сільпо", "silpo", qr_hosts=("silpo.ua",)),
    _m("Novus", "food", "новус", qr_hosts=("novus.ua",)),
    _m("Фора", "food", "fora"),
    _m("Ашан", "food", "auchan"),
    _m("Metro", "food", "метро кеш", "metro cash"),
    _m("Varus", "food", "варус"),
    _m("ЕКО маркет", "food", "eko market", "еко маркет"),
    _m("Велмарт", "food", "velmart"),
    _m("Наш край", "food"),
    _m("Spar", "food", "спар"),
    _m("Lidl", "food"),
    _m("Biedronka", "food"),
    _m("Tesco", "food"),
    _m("Aldi", "food"),
    _m("Carrefour", "food"),
    # ── food: cafés / fast food ──
    _m("McDonald's", "food", "mcdonalds", "mcdonald", "макдональдс", "макдональдз",
       tax_ids=("237444526652",), qr_hosts=("mcdonalds.com",)),
    _m("KFC", "food"),
    _m("Starbucks", "food"),
    _m("Пузата хата", "food"),
    _m("Domino's", "food", "dominos"),
    _m("Glovo", "food"),
    _m("Bolt Food", "food"),
    _m("Lviv Croissants", "food"),
    _m("Aroma Kava", "food"),
    # ── car (fuel) ──
    _m("WOG", "car", "вог", qr_hosts=("wog.ua",)),
    _m("OKKO", "car", "окко", qr_hosts=("okko.ua",)),
    _m("SOCAR", "car", "сокар"),
    _m("UPG", "car"),
    _m("Shell", "car"),
    _m("KLO", "car", "кло"),
    _m("BRSM", "car", "брсм"),
    _m("Amic", "car", "амік"),
    _m("Авіас", "car", "avias"),
    _m("Укрнафта", "car", "ukrnafta"),
    # ── transportation ──
    _m("Uber", "transportation"),
    _m("Bolt", "transportation"),
    _m("Uklon", "transportation", "уклон"),
    _m("Укрзалізниця", "transportation", "ukrzaliznytsia"),
    # ── health ──
    _m("Аптека Доброго Дня", "health"),
    _m("АНЦ", "health"),
    _m("Подорожник", "health"),
    _m("Бажаємо здоров'я", "health"),
    _m("D.S.", "health"),
    _m("Аптека 911", "health"),
    # ── electronics ──
    _m("Rozetka", "electronics", "розетка", qr_hosts=("rozetka.com.ua",)),
    _m("Comfy", "electronics", "комфі", qr_hosts=("comfy.ua",)),
    _m("Foxtrot", "electronics", "фокстрот"),
    _m("Eldorado", "electronics", "ельдорадо"),
    _m("Allo", "electronics", "алло"),
    _m("Citrus", "electronics", "цитрус"),
    _m("Moyo", "electronics", "мойо"),
    _m("Apple", "electronics"),
    _m("Samsung", "electronics"),
    _m("Media Markt", "electronics"),
    # ── home ──
    _m("Епіцентр", "home", "epicentr", "епіцентр к"),
    _m("Нова лінія", "home"),
    _m("Leroy Merlin", "home"),
    _m("IKEA", "home"),
    _m("JYSK", "home"),
    _m("Praktiker", "home"),
    # ── clothing ──
    _m("Zara", "clothing"),
    _m("H&M", "clothing"),
    _m("Reserved", "clothing"),
    _m("LC Waikiki", "clothing"),
    _m("Bershka", "clothing"),
    _m("Pull&Bear", "clothing"),
    _m("Sinsay", "clothing"),
    _m("Colin's", "clothing"),
    # ── beauty ──
    _m("EVA", "beauty", "єва", qr_hosts=("eva.ua",)),
    _m("Watsons", "beauty"),
    _m("Prostor", "beauty", "простор"),
    _m("Makeup", "beauty"),
    _m("Rossmann", "beauty"),
    # ── phone ──
    _m("Kyivstar", "phone", "київстар"),
    _m("Vodafone", "phone"),
    _m("lifecell", "phone", "лайфсел"),
    # ── entertainment ──
    _m("Multiplex", "entertainment", "мультиплекс"),
    _m("Planeta Kino", "entertainment", "планета кіно"),
    _m("Netflix", "entertainment"),
    _m("Spotify", "entertainment"),
    _m("Steam", "entertainment"),
    # ── pets ──
    _m("MasterZoo", "pets", "мастерзоо"),
    _m("Zoomagazin", "pets"),
    _m("Pethouse", "pets"),
    # ── travel ──
    _m("Booking.com", "travel"),
    _m("Airbnb", "travel"),
    _m("МАУ", "travel"),
    _m("Ryanair", "travel"),
    _m("Wizz Air", "travel"),
]

_BY_TAX_ID = {tid: m for m in MERCHANTS for tid in m.tax_ids}


def brand_terms() -> dict[str, list[str]]:
    """category → lower-case brand names/aliases (for the keyword-based category guess)."""
    terms: dict[str, list[str]] = {}
    for m in MERCHANTS:
        terms.setdefault(m.category, []).extend(t.lower() for t in (m.name, *m.aliases))
    return terms


def _host_matches(host: str, suffix: str) -> bool:
    return host == suffix or host.endswith("." + suffix)


def _by_qr(qr_codes: Iterable[str]) -> Optional[Merchant]:
    for payload in qr_codes:
        try:
            host = (urlparse(payload.strip()).hostname or "").lower()
        except ValueError:
            continue
        for m in MERCHANTS:
            if any(_host_matches(host, h) for h in m.qr_hosts):
                return m
    return None


def _line_keys(line: str) -> list[str]:
    """Skeletons of single words and of 2–3 word runs, without legal-form / suffix noise."""
    tokens = [skeleton(w) for w in words(line)]
    tokens = [t for t in tokens if t not in _NOISE_WORDS]
    keys = []
    for size in (1, 2, 3):
        keys += ["".join(tokens[i:i + size]) for i in range(len(tokens) - size + 1)]
    return keys


def _alias_matches(key: str, alias: str) -> bool:
    if len(alias) <= 4:                      # short brands ("АТБ", "WOG") must match exactly
        return key == alias
    limit = 1 if len(alias) <= 7 else 2
    return levenshtein(key, alias, limit) <= limit


def _by_alias(lines: list[str]) -> Optional[Merchant]:
    for line in lines[:_HEADER_LINES]:
        keys = _line_keys(line)
        for m in MERCHANTS:
            if any(_alias_matches(k, a) for k in keys for a in m.keys):
                return m
    return None


def match_merchant(texts: Iterable[list[str]], qr_codes: Iterable[str] = ()) -> tuple[Optional[Merchant], float]:
    """
    *texts* — the receipt lines of each OCR pass. Returns the known merchant and
    how sure the match is (0 when nothing matched).
    """
    texts = list(texts)
    for lines in texts:
        for line in lines:
            for tid in _TAX_ID_RE.findall(line):
                if tid in _BY_TAX_ID:
                    return _BY_TAX_ID[tid], 0.95
    m = _by_qr(qr_codes)
    if m:
        return m, 0.9
    for lines in texts:
        m = _by_alias(lines)
        if m:
            return m, 0.85
    return None, 0.0
