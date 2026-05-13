"""Tests for the slugify helper."""

import pytest

from docshelf_mcp.core.slugify import slugify


@pytest.mark.parametrize(
    "input_text, expected",
    [
        ("Chapter 4: Power Supplies", "chapter-4-power-supplies"),
        ("  Trailing dots.....", "trailing-dots"),
        ("Multiple   spaces  here", "multiple-spaces-here"),
        ("UPPER_case_TEXT", "upper_case_text"),
        ("punctuation!@#$%^&*()", "punctuation"),
        ("kebab-already-good", "kebab-already-good"),
    ],
)
def test_basic_slugify(input_text, expected):
    assert slugify(input_text) == expected


def test_empty_input_returns_default():
    assert slugify("") == "section"
    assert slugify("   ") == "section"
    assert slugify("!!!") == "section"


def test_max_length_is_respected():
    long = "a" * 100
    assert len(slugify(long, max_len=20)) == 20


def test_max_length_does_not_leave_trailing_hyphen():
    # A truncation that would land on a hyphen should strip it.
    text = "abcdef-ghijkl-mnopqr-stu"
    out = slugify(text, max_len=14)
    assert not out.endswith("-")


def test_unicode_input_does_not_crash():
    # Cyrillic — NFKD doesn't transliterate, but `\w` under re.UNICODE keeps
    # the letters. We just care that it doesn't crash and returns *something*.
    out = slugify("Маршрутизатор: настройка")
    assert out  # non-empty
    assert " " not in out
