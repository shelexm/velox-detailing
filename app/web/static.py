"""Static files with caching: versioned URLs (?v=hash) are immutable, the rest are revalidated hourly."""

from __future__ import annotations

from starlette.staticfiles import StaticFiles
from starlette.types import Scope


class CachedStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope: Scope):  # type: ignore[no-untyped-def]
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            versioned = b"v=" in scope.get("query_string", b"")
            response.headers["Cache-Control"] = (
                "public, max-age=31536000, immutable" if versioned else "public, max-age=3600"
            )
        return response
