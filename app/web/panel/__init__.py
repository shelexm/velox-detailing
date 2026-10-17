"""Studio panel (/admin): server-rendered pages; changes go through the admin JSON API."""

from __future__ import annotations

from fastapi import APIRouter

from app.web.panel import account, bookings, dashboard

router = APIRouter(include_in_schema=False)
router.include_router(account.router)
router.include_router(dashboard.router)
router.include_router(bookings.router)
