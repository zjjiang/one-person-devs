"""Tests for utility functions."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from pydantic import BaseModel

from opd.utils import (
    add_days,
    format_datetime,
    generate_random_string,
    generate_token,
    hash_string,
    model_to_dict,
    sanitize_filename,
    truncate_string,
)


def test_generate_random_string() -> None:
    """Test random string generation."""
    result = generate_random_string(32)
    assert len(result) == 32
    assert result.isalnum()

    # Test different lengths
    result_short = generate_random_string(10)
    assert len(result_short) == 10


def test_generate_token() -> None:
    """Test secure token generation."""
    token = generate_token(32)
    assert len(token) == 64  # 32 bytes = 64 hex chars
    assert all(c in "0123456789abcdef" for c in token)


def test_hash_string() -> None:
    """Test string hashing."""
    text = "test_password"
    hash1 = hash_string(text)
    hash2 = hash_string(text)

    # Same input produces same hash
    assert hash1 == hash2
    assert len(hash1) == 64  # SHA-256 produces 64 hex chars

    # Different salt produces different hash
    hash_with_salt = hash_string(text, salt="mysalt")
    assert hash_with_salt != hash1


def test_format_datetime() -> None:
    """Test datetime formatting."""
    dt = datetime(2024, 1, 15, 10, 30, 45)
    formatted = format_datetime(dt)
    assert formatted == "2024-01-15 10:30:45"

    # Test custom format
    custom = format_datetime(dt, fmt="%Y-%m-%d")
    assert custom == "2024-01-15"


def test_add_days() -> None:
    """Test adding days to datetime."""
    dt = datetime(2024, 1, 15)
    future = add_days(dt, 5)
    assert future == datetime(2024, 1, 20)

    # Test negative days
    past = add_days(dt, -5)
    assert past == datetime(2024, 1, 10)


def test_sanitize_filename() -> None:
    """Test filename sanitization."""
    unsafe = "file/with\\unsafe:chars*.txt"
    safe = sanitize_filename(unsafe)
    assert "/" not in safe
    assert "\\" not in safe
    assert ":" not in safe
    assert "*" not in safe
    assert safe == "file_with_unsafe_chars_.txt"


def test_truncate_string() -> None:
    """Test string truncation."""
    text = "This is a very long string that needs to be truncated"
    truncated = truncate_string(text, max_length=20)
    assert len(truncated) == 20
    assert truncated.endswith("...")

    # Test string shorter than max_length
    short = "Short"
    assert truncate_string(short, max_length=20) == short


def test_model_to_dict() -> None:
    """Test Pydantic model to dict conversion."""

    class TestModel(BaseModel):
        name: str
        value: int
        optional: str | None = None

    model = TestModel(name="test", value=42)
    result = model_to_dict(model)

    assert result == {"name": "test", "value": 42}
    assert "optional" not in result  # None values excluded by default

    # Test with exclude_none=False
    result_with_none = model_to_dict(model, exclude_none=False)
    assert result_with_none["optional"] is None
