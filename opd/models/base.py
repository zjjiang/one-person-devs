"""Base database models and utilities."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all database models.

    Provides common functionality and columns for all models.
    """

    pass


class TimestampMixin:
    """Mixin to add created_at and updated_at timestamp columns."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        comment="Record creation timestamp",
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        comment="Record last update timestamp",
    )


class BaseModel(Base, TimestampMixin):
    """Base model with timestamps for all application models.

    Includes:
    - created_at: Timestamp when record was created
    - updated_at: Timestamp when record was last updated
    """

    __abstract__ = True

    def to_dict(self) -> dict[str, Any]:
        """Convert model instance to dictionary.

        Returns:
            Dictionary representation of the model
        """
        return {
            column.name: getattr(self, column.name)
            for column in self.__table__.columns
        }
