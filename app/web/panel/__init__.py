"""Studio panel (/admin): server-rendered pages; changes go through the admin JSON API."""

from __future__ import annotations

from fastapi import APIRouter

from app.web.panel import (
    account,
    bookings,
    clients,
    content,
    dashboard,
    media,
    owner,
    schedule,
    services,
    site_lists,
    slots,
    staff,
)

router = APIRouter(include_in_schema=False)
router.include_router(account.router)
router.include_router(dashboard.router)
router.include_router(bookings.router)
router.include_router(clients.router)
router.include_router(services.router)
router.include_router(staff.router)
router.include_router(schedule.router)
router.include_router(slots.router)
router.include_router(media.router)
router.include_router(content.router)
router.include_router(site_lists.router)
router.include_router(owner.router)
