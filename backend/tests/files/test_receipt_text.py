"""Unit tests for receipt_text — OCR-tolerant keyword matching."""

import pytest

from src.files.services.receipt_text import has_anchor, levenshtein, normalise_line, skeleton


@pytest.mark.parametrize(
    "line, anchor",
    [
        ("Сума 83.00", "СУМА"),
        ("Cyma 63.00", "СУМА"),                       # English pass reads Cyrillic as Latin look-alikes
        ("- БЕЗГОТІВКОВЯ 83.00 грн", "БЕЗГОТІВКОВА"),  # one OCR slip
        ("БЕЗГОТ ІВКОВА 83.00", "БЕЗГОТІВКОВА"),       # word split by OCR
        ("ДО  СПЛАТИ: 120,00", "ДО СПЛАТИ"),
        ("ПДВ.Я Я - 20.005 13.83", "ПДВ"),
        ("TOTAL 59.00", "TOTAL"),
    ],
)
def test_anchor_found(line, anchor):
    assert has_anchor(line, anchor)


@pytest.mark.parametrize(
    "line, anchor",
    [
        ("SUBTOTAL 50.00", "TOTAL"),      # a different word, not a slip
        ("CASH 100.00", "CARD"),
        ("Хліб білий 24,50", "СУМА"),
        ("ПН 237444526652", "ПДВ"),       # short anchors must match exactly
    ],
)
def test_anchor_not_found(line, anchor):
    assert not has_anchor(line, anchor)


def test_latin_lookalikes_in_cyrillic_words_are_fixed():
    assert normalise_line("СУMA 83. 00") == "СУМА 83.00"     # 2 Cyrillic + 2 Latin letters
    assert normalise_line("VISA 83.00") == "VISA 83.00"    # Latin words stay Latin


def test_skeleton_maps_scripts_together():
    assert skeleton("Сума") == skeleton("Cyma")


def test_levenshtein():
    assert levenshtein("CYMA", "CYMA") == 0
    assert levenshtein("CYMA", "CYMN") == 1
    assert levenshtein("ABCDEFGH", "A", limit=2) == 3     # stops early past the limit
