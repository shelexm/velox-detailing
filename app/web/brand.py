"""The studio brand: what the logo shows on the site, in the panel and in the Telegram calendar.

Set in the panel ("Настройки", "Бренд"): the brand word with a line under it, or an uploaded logo image
that replaces the word. Without a brand word the studio name is shown.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from markupsafe import escape
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MediaAsset, Studio
from app.services.media import fallback_src


@dataclass(frozen=True)
class Brand:
    name: str
    tagline: str | None = None
    image_url: str | None = None

    @property
    def initial(self) -> str:
        return next((ch.upper() for ch in self.name if ch.isalnum()), "•")

    @property
    def version(self) -> str:
        """Changes with the brand, so browsers fetch the new tab icon."""
        return hashlib.sha256(f"{self.name}|{self.image_url}".encode()).hexdigest()[:8]


def brand_of(studio: Studio, logo: MediaAsset | None) -> Brand:
    usable = logo is not None and logo.studio_id == studio.id and logo.variants
    return Brand(
        name=studio.brand_name or studio.name,
        tagline=studio.brand_tagline,
        image_url=fallback_src(logo, 480) if usable else None,
    )


async def load_brand(session: AsyncSession, studio: Studio) -> Brand:
    logo = await session.get(MediaAsset, studio.logo_image_id) if studio.logo_image_id else None
    return brand_of(studio, logo)


def favicon_svg(brand: Brand) -> str:
    """Tab icon: the first letter of the brand on the dark tile with the gold accent stroke."""
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
        '<rect width="64" height="64" rx="12" fill="#070708"/>'
        '<text x="32" y="45" text-anchor="middle" font-family="Helvetica, Arial, sans-serif" font-size="34" '
        f'font-weight="300" fill="#F3F1EC">{escape(brand.initial)}</text>'
        '<path d="M38 12l9-4" stroke="#C8A86B" stroke-width="3" stroke-linecap="round"/>'
        "</svg>"
    )
