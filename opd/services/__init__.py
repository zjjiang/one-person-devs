"""Services layer for business logic.

This package contains service classes that implement business logic
and orchestrate operations between models, external APIs, and other services.

Services should:
- Contain business logic and validation
- Orchestrate operations across multiple models
- Handle external API calls
- Be independent of the web framework (FastAPI)
- Be easily testable

Example:
    ```python
    from opd.services.user_service import UserService

    async def create_user_endpoint(
        user_data: UserCreate,
        db: AsyncSession = Depends(get_db)
    ):
        service = UserService(db)
        user = await service.create_user(user_data)
        return user
    ```
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class BaseService:
    """Base service class with common functionality.

    All service classes should inherit from this base class.
    """

    def __init__(self, db: AsyncSession) -> None:
        """Initialize service with database session.

        Args:
            db: SQLAlchemy async session
        """
        self.db = db

    async def commit(self) -> None:
        """Commit the current transaction."""
        await self.db.commit()

    async def rollback(self) -> None:
        """Rollback the current transaction."""
        await self.db.rollback()

    async def refresh(self, instance: object) -> None:
        """Refresh an instance from the database.

        Args:
            instance: Model instance to refresh
        """
        await self.db.refresh(instance)
