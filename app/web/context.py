"""Everything the public pages show, read from the database for one studio."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.content.sections import SECTION_MODELS, default_content
from app.core.phone import format_ru_phone
from app.models import (
    GiftOption,
    MediaAsset,
    PortfolioCase,
    Review,
    Service,
    ServiceCategory,
    ServiceGroup,
    SiteSection,
    Studio,
    StudioHours,
)
from app.models.enums import ServiceKind

WEEKDAYS_SHORT = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"]


@dataclass
class GroupView:
    group: ServiceGroup
    services: list[Service]
    number: int

    @property
    def online_services(self) -> list[Service]:
        return [s for s in self.services if s.online_booking]


@dataclass
class PriceCategory:
    category: ServiceCategory
    services: list[Service]

    @property
    def min_price(self) -> int | None:
        prices = [s.price_from for s in self.services if s.price_from is not None]
        return min(prices) if prices else None


@dataclass
class SiteContext:
    studio: Studio
    sections: dict[str, dict[str, Any]]
    visible: set[str]
    order: list[str]
    groups: list[GroupView]
    price_categories: list[PriceCategory]
    packages: list[Service]
    cases: list[PortfolioCase]
    reviews: list[Review]
    gifts: list[GiftOption]
    media: dict[int, MediaAsset]
    hours: list[tuple[str, str]]
    year: int = field(default_factory=lambda: datetime.now(UTC).year)

    def section(self, key: str) -> dict[str, Any]:
        return self.sections[key]

    def shown(self, key: str) -> bool:
        return key in self.visible

    @property
    def bot_username(self) -> str | None:
        return self.studio.telegram_bot_username

    def bot_url(self, start: str | None = None) -> str | None:
        if not self.bot_username:
            return None
        return f"https://t.me/{self.bot_username}" + (f"?start={start}" if start else "")

    @property
    def phone_display(self) -> str | None:
        return format_ru_phone(self.studio.phone) if self.studio.phone else None

    @property
    def phone_href(self) -> str | None:
        return f"tel:{self.studio.phone}" if self.studio.phone else None

    @property
    def address_line(self) -> str | None:
        parts = [p for p in (self.studio.city, self.studio.address) if p]
        return ", ".join(parts) if parts else None

    @property
    def schedule_short(self) -> str:
        return self.studio.schedule_text or " · ".join(f"{label} {span}" for label, span in self.hours)

    @property
    def legal_line(self) -> str | None:
        parts = [self.studio.legal_name, f"ИНН {self.studio.inn}" if self.studio.inn else None]
        parts = [p for p in parts if p]
        return ", ".join(parts) if parts else None


def _hours_rows(rows: list[StudioHours]) -> list[tuple[str, str]]:
    """Weekly hours collapsed into ranges: [("Пн–Сб", "09:00–21:00"), ("Вс", "10:00–18:00")]."""
    by_day = {r.weekday: (f"{r.opens_at:%H:%M}–{r.closes_at:%H:%M}" if r.is_open else None) for r in rows}
    result: list[tuple[str, str]] = []
    start = 0
    while start < 7:
        span = by_day.get(start)
        end = start
        while end + 1 < 7 and by_day.get(end + 1) == span:
            end += 1
        if span:
            label = WEEKDAYS_SHORT[start] if start == end else f"{WEEKDAYS_SHORT[start]}–{WEEKDAYS_SHORT[end]}"
            result.append((label, span))
        start = end + 1
    return result


async def load_site(session: AsyncSession, studio: Studio) -> SiteContext:
    sid = studio.id
    stored = {s.key: s for s in await session.scalars(select(SiteSection).where(SiteSection.studio_id == sid))}
    sections: dict[str, dict[str, Any]] = {}
    visible: set[str] = set()
    order_keys = []
    for index, key in enumerate(SECTION_MODELS):
        row = stored.get(key)
        content = default_content(key)
        if row is not None:
            content.update(row.content or {})
        sections[key] = content
        if row is None or row.is_visible:
            visible.add(key)
        order_keys.append((row.sort_order if row else index, index, key))
    order = [key for _, _, key in sorted(order_keys)]

    services = list(
        await session.scalars(
            select(Service).where(Service.studio_id == sid, Service.is_active.is_(True)).order_by(Service.sort_order)
        )
    )
    groups = [
        GroupView(group=g, services=[s for s in services if s.group_id == g.id], number=i + 1)
        for i, g in enumerate(
            await session.scalars(
                select(ServiceGroup)
                .where(ServiceGroup.studio_id == sid, ServiceGroup.is_visible.is_(True))
                .order_by(ServiceGroup.sort_order, ServiceGroup.id)
            )
        )
    ]
    categories = list(
        await session.scalars(
            select(ServiceCategory).where(ServiceCategory.studio_id == sid).order_by(ServiceCategory.sort_order)
        )
    )
    price_categories = []
    for category in categories:
        listed = [
            s
            for s in services
            if s.category_id == category.id and s.show_in_price_list and s.kind == ServiceKind.SERVICE
        ]
        if listed:
            price_categories.append(PriceCategory(category=category, services=listed))
    packages = [s for s in services if s.kind == ServiceKind.PACKAGE and s.show_in_price_list]

    cases = list(
        await session.scalars(
            select(PortfolioCase)
            .where(PortfolioCase.studio_id == sid, PortfolioCase.is_published.is_(True))
            .order_by(PortfolioCase.sort_order, PortfolioCase.id)
        )
    )
    cases = [c for c in cases if c.before_image_id and c.after_image_id]
    reviews = list(
        await session.scalars(
            select(Review)
            .where(Review.studio_id == sid, Review.is_published.is_(True))
            .order_by(Review.sort_order, Review.id)
        )
    )
    gifts = list(
        await session.scalars(
            select(GiftOption)
            .where(GiftOption.studio_id == sid, GiftOption.is_visible.is_(True))
            .order_by(GiftOption.sort_order, GiftOption.id)
        )
    )
    media = {m.id: m for m in await session.scalars(select(MediaAsset).where(MediaAsset.studio_id == sid))}
    hours = _hours_rows(list(await session.scalars(select(StudioHours).where(StudioHours.studio_id == sid))))

    # Blocks without content to show are hidden instead of rendering empty frames.
    if not cases:
        visible.discard("works")
    if not reviews:
        visible.discard("reviews")
    if not gifts:
        visible.discard("gift")
    if not studio.telegram_bot_username:
        visible.discard("telegram")
    if not groups:
        visible.discard("services")

    return SiteContext(
        studio=studio,
        sections=sections,
        visible=visible,
        order=order,
        groups=groups,
        price_categories=price_categories,
        packages=packages,
        cases=cases,
        reviews=reviews,
        gifts=gifts,
        media=media,
        hours=hours,
    )
