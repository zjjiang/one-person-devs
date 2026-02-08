"""Tests for common schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from opd.schemas.common import (
    ErrorResponse,
    MessageResponse,
    PaginatedResponse,
    PaginationParams,
)


def test_message_response() -> None:
    """Test MessageResponse schema."""
    response = MessageResponse(message="Operation successful")
    assert response.message == "Operation successful"
    assert response.success is True

    response_fail = MessageResponse(message="Failed", success=False)
    assert response_fail.success is False


def test_error_response() -> None:
    """Test ErrorResponse schema."""
    error = ErrorResponse(
        error="Not Found",
        detail="Resource does not exist",
        code="404",
    )
    assert error.error == "Not Found"
    assert error.detail == "Resource does not exist"
    assert error.code == "404"
    assert error.timestamp is not None


def test_pagination_params() -> None:
    """Test PaginationParams schema."""
    params = PaginationParams(page=2, page_size=50)
    assert params.page == 2
    assert params.page_size == 50
    assert params.offset == 50  # (2-1) * 50
    assert params.limit == 50


def test_pagination_params_defaults() -> None:
    """Test PaginationParams default values."""
    params = PaginationParams()
    assert params.page == 1
    assert params.page_size == 20
    assert params.offset == 0
    assert params.limit == 20


def test_pagination_params_validation() -> None:
    """Test PaginationParams validation."""
    # Page must be >= 1
    with pytest.raises(ValidationError):
        PaginationParams(page=0)

    # Page size must be >= 1
    with pytest.raises(ValidationError):
        PaginationParams(page_size=0)

    # Page size must be <= 100
    with pytest.raises(ValidationError):
        PaginationParams(page_size=101)


def test_paginated_response() -> None:
    """Test PaginatedResponse creation."""
    items = [1, 2, 3, 4, 5]
    response = PaginatedResponse.create(
        items=items,
        total=25,
        page=1,
        page_size=5,
    )

    assert response.items == items
    assert response.total == 25
    assert response.page == 1
    assert response.page_size == 5
    assert response.total_pages == 5  # 25 / 5


def test_paginated_response_partial_page() -> None:
    """Test PaginatedResponse with partial last page."""
    items = [1, 2, 3]
    response = PaginatedResponse.create(
        items=items,
        total=23,
        page=3,
        page_size=10,
    )

    assert len(response.items) == 3
    assert response.total == 23
    assert response.total_pages == 3  # ceil(23 / 10)
