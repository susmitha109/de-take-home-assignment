"""Unit tests for src.cleaners — one scenario test per cleaner."""

from decimal import Decimal

import pandas as pd

from src.raw_to_stage import (
    clean_amount,
    clean_country,
    clean_currency,
    clean_date,
    clean_email,
    clean_phone,
    clean_postal_code,
    clean_quantity,
    clean_text,
)


def s(values):
    return pd.Series(values, dtype="object")


def test_clean_text():
    out = clean_text(s(["  hi  ", "a   b", "N/A", ""]))
    assert out.tolist()[:2] == ["hi", "a b"]
    assert out.iloc[2:].isna().all()


def test_clean_email():
    out = clean_email(s(["John@Example.COM", "no-at", "two@@x.com", "bad@nodot"]))
    assert out.iloc[0] == "john@example.com"
    assert out.iloc[1:].isna().all()


def test_clean_phone():
    out = clean_phone(s(["(555) 123-4567", "555-123-4567 ext 99", "+1 555 123 4567", "junk"]))
    assert out.tolist()[:3] == ["5551234567", "5551234567", "15551234567"]
    assert pd.isna(out.iloc[3])


def test_clean_date():
    out = clean_date(s(["2025-07-19", "07/19/2025", "2025-02-30", ""]))
    assert out.iloc[0] == pd.Timestamp("2025-07-19")
    assert out.iloc[1] == pd.Timestamp("2025-07-19")
    assert out.iloc[2:].isna().all()


def test_clean_amount():
    out = clean_amount(s(["$1,299.99", "1.299,99", "29,99", "abc"]))
    assert out.iloc[0] == Decimal("1299.99")
    assert out.iloc[1] == Decimal("1299.99")
    assert out.iloc[2] == Decimal("29.99")
    assert out.iloc[3] is None


def test_clean_quantity():
    out = clean_quantity(s(["3", "abc", ""]))
    assert out.iloc[0] == 3
    assert out.iloc[1:].isna().all()
    assert str(out.dtype) == "Int64"


def test_clean_country():
    out = clean_country(s(["us", "USA", "GB"]))
    assert out.iloc[0] == "US"
    assert pd.isna(out.iloc[1])
    assert out.iloc[2] == "GB"


def test_clean_currency():
    out = clean_currency(s(["usd", "US$", "EUR"]))
    assert out.iloc[0] == "USD"
    assert pd.isna(out.iloc[1])
    assert out.iloc[2] == "EUR"


def test_clean_postal_code():
    out = clean_postal_code(s(["  sw1a 1aa ", "10001"]))
    assert out.tolist() == ["SW1A 1AA", "10001"]
