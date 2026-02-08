"""Common schemas for request/response validation."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field, field_validator

T = TypeVar("T")


class MessageResponse(BaseModel):
    """Standard message response schema."""

    message: str = Field(..., description="Response message")
    success: bool = Field(default=True, description="Operation success status")


class ErrorResponse(BaseModel):
    """Standard error response schema."""

    error: str = Field(..., description="Error message")
    detail: str | None = Field(None, description="Detailed error information")
    code: str | None = Field(None, description="Error code")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Error timestamp",
    )


class HealthResponse(BaseModel):
    """Health check response schema."""

    status: str = Field(..., description="Service health status")
    timestamp: str = Field(..., description="Check timestamp")
    service: str = Field(..., description="Service name")


class PaginationParams(BaseModel):
    """Pagination parameters for list endpoints."""

    page: int = Field(default=1, ge=1, description="Page number (1-indexed)")
    page_size: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Number of items per page",
    )

    @field_validator("page")
    @classmethod
    def validate_page(cls, v: int) -> int:
        """Validate page number is positive."""
        if v < 1:
            raise ValueError("Page number must be >= 1")
        return v

    @property
    def offset(self) -> int:
        """Calculate offset for database queries."""
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        """Get limit for database queries."""
        return self.page_size


class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated response wrapper."""

    items: list[T] = Field(..., description="List of items")
    total: int = Field(..., description="Total number of items")
    page: int = Field(..., description="Current page number")
    page_size: int = Field(..., description="Items per page")
    total_pages: int = Field(..., description="Total number of pages")

    @classmethod
    def create(
        cls,
        items: list[T],
        total: int,
        page: int,
        page_size: int,
    ) -> PaginatedResponse[T]:
        """Create a paginated response.

        Args:
            items: List of items for current page
            total: Total number of items
            page: Current page number
            page_size: Number of items per page

        Returns:
            PaginatedResponse instance
        """
        total_pages = (total + page_size - 1) // page_size
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )


class BaseSchema(BaseModel):
    """Base schema with common configuration."""

    model_config = {
        "from_attributes": True,
        "populate_by_name": True,
        "use_enum_values": True,
    }
