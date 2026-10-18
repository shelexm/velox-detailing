"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.routes import (
    admin,
    admin_catalog,
    admin_media,
    admin_schedule,
    admin_slots,
    admin_staff,
    auth,
    health,
    public,
)
from app.core.config import BASE_DIR, Settings, get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestIdMiddleware
from app.core.ratelimit import Limiters
from app.core.security import SecurityHeadersMiddleware
from app.db.migrations import migration_heads
from app.db.session import create_engine, create_sessionmaker
from app.web import panel, site
from app.web.panel.common import LoginRequired, login_redirect
from app.web.static import CachedStaticFiles

# Container health checks always call the app on the loopback interface.
_LOCAL_HOSTS = ["127.0.0.1", "localhost"]


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        engine = create_engine(settings)
        app.state.engine = engine
        app.state.sessionmaker = create_sessionmaker(engine)
        try:
            yield
        finally:
            await engine.dispose()

    app = FastAPI(
        title=settings.app_name,
        lifespan=lifespan,
        docs_url="/api/docs" if settings.app_env != "production" else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if settings.app_env != "production" else None,
    )
    app.state.settings = settings
    app.state.migration_heads = migration_heads()
    app.state.limiters = Limiters()

    register_error_handlers(app)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=[*settings.allowed_hosts, *_LOCAL_HOSTS])
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestIdMiddleware)

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(public.router)
    app.include_router(admin.router)
    app.include_router(admin_media.router)
    app.include_router(admin_catalog.router)
    app.include_router(admin_staff.router)
    app.include_router(admin_schedule.router)
    app.include_router(admin_slots.router)
    app.include_router(panel.router)
    app.include_router(site.router)
    app.mount("/static", CachedStaticFiles(directory=BASE_DIR / "static"), name="static")
    app.state.html_error_renderer = site.render_error
    app.add_exception_handler(LoginRequired, login_redirect)
    return app
