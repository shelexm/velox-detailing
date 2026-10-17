"""Import every model so Base.metadata is complete for Alembic and tests."""

from app.models.studio import Studio

__all__ = ["Studio"]
