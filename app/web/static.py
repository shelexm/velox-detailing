"""Static files with caching: versioned URLs (?v=hash) are immutable, the rest are revalidated.

JavaScript modules imported by other modules ("./panel.js") are requested without a version, so they are
revalidated on every load (a cheap 304) and never get out of step with the page that imports them.
"""

from __future__ import annotations

from starlette.staticfiles import StaticFiles
from starlette.types import Scope


class CachedStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope: Scope):  # type: ignore[no-untyped-def]
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            versioned = b"v=" in scope.get("query_string", b"")
            if versioned:
                response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            elif path.endswith(".js"):
                response.headers["Cache-Control"] = "no-cache"
            else:
                response.headers["Cache-Control"] = "public, max-age=3600"
        return response
