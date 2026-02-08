"""Utility functions and helpers."""

from __future__ import annotations

import hashlib
import secrets
import string
from datetime import datetime, timedelta
from typing import Any

from pydantic import BaseModel


def generate_random_string(length: int = 32) -> str:
    """Generate a random string of specified length.

    Args:
        length: Length of the random string

    Returns:
        Random string containing letters and digits
    """
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def generate_token(length: int = 64) -> str:
    """Generate a secure random token.

    Args:
        length: Length of the token in bytes (will be hex encoded)

    Returns:
        Hex-encoded random token
    """
    return secrets.token_hex(length)


def hash_string(value: str, salt: str = "") -> str:
    """Hash a string using SHA-256.

    Args:
        value: String to hash
        salt: Optional salt to add before hashing

    Returns:
        Hex-encoded hash
    """
    combined = f"{salt}{value}"
    return hashlib.sha256(combined.encode()).hexdigest()


def utcnow() -> datetime:
    """Get current UTC datetime.

    Returns:
        Current UTC datetime
    """
    return datetime.utcnow()


def format_datetime(dt: datetime, fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """Format datetime to string.

    Args:
        dt: Datetime to format
        fmt: Format string

    Returns:
        Formatted datetime string
    """
    return dt.strftime(fmt)


def parse_datetime(dt_str: str, fmt: str = "%Y-%m-%d %H:%M:%S") -> datetime:
    """Parse datetime from string.

    Args:
        dt_str: Datetime string to parse
        fmt: Format string

    Returns:
        Parsed datetime

    Raises:
        ValueError: If string doesn't match format
    """
    return datetime.strptime(dt_str, fmt)


def add_days(dt: datetime, days: int) -> datetime:
    """Add days to a datetime.

    Args:
        dt: Base datetime
        days: Number of days to add (can be negative)

    Returns:
        New datetime with days added
    """
    return dt + timedelta(days=days)


def dict_to_model(data: dict[str, Any], model_class: type[BaseModel]) -> BaseModel:
    """Convert dictionary to Pydantic model.

    Args:
        data: Dictionary data
        model_class: Pydantic model class

    Returns:
        Model instance

    Raises:
        ValidationError: If data doesn't match model schema
    """
    return model_class.model_validate(data)


def model_to_dict(model: BaseModel, exclude_none: bool = True) -> dict[str, Any]:
    """Convert Pydantic model to dictionary.

    Args:
        model: Pydantic model instance
        exclude_none: Whether to exclude None values

    Returns:
        Dictionary representation
    """
    return model.model_dump(exclude_none=exclude_none)


def sanitize_filename(filename: str) -> str:
    """Sanitize filename by removing unsafe characters.

    Args:
        filename: Original filename

    Returns:
        Sanitized filename safe for filesystem
    """
    # Remove path separators and other unsafe characters
    unsafe_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']
    sanitized = filename
    for char in unsafe_chars:
        sanitized = sanitized.replace(char, '_')
    return sanitized


def truncate_string(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """Truncate string to maximum length.

    Args:
        text: Text to truncate
        max_length: Maximum length including suffix
        suffix: Suffix to add if truncated

    Returns:
        Truncated string
    """
    if len(text) <= max_length:
        return text
    return text[:max_length - len(suffix)] + suffix
