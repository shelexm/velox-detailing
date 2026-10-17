"""Jinja2 environment for the site and the panel: responsive images, prices, versioned static URLs."""

from __future__ import annotations

import hashlib
from functools import lru_cache
from typing import Any

from fastapi.templating import Jinja2Templates
from markupsafe import Markup, escape

from app.core.config import BASE_DIR
from app.models import MediaAsset
from app.services.media import fallback_src, srcsets

TEMPLATES_DIR = BASE_DIR / "app" / "templates"
STATIC_DIR = BASE_DIR / "static"


@lru_cache(maxsize=256)
def _static_version(path: str) -> str:
    file = STATIC_DIR / path
    try:
        return hashlib.sha256(file.read_bytes()).hexdigest()[:10]
    except OSError:
        return "0"


def static_url(path: str) -> str:
    return f"/static/{path}?v={_static_version(path)}"


def rub(value: int | None, prefix: str = "от ") -> str:
    if value is None:
        return ""
    return f"{prefix}{value:,}".replace(",", " ") + " ₽"


def picture(
    media: dict[int, MediaAsset],
    media_id: int | None,
    *,
    sizes: str = "100vw",
    cls: str = "",
    img_cls: str = "",
    alt: str | None = None,
    loading: str = "lazy",
    priority: bool = False,
    position: str | None = None,
    decorative: bool = False,
) -> Markup:
    asset = media.get(media_id) if media_id else None
    if asset is None or not asset.variants:
        return Markup("")
    sets = srcsets(asset)
    text = "" if decorative else (asset.alt if alt is None else alt)
    attrs = [
        f'src="{escape(fallback_src(asset))}"',
        f'srcset="{escape(sets.get("jpg", ""))}"',
        f'sizes="{escape(sizes)}"',
        f'alt="{escape(text)}"',
        f'width="{asset.width}"',
        f'height="{asset.height}"',
        'decoding="async"',
        'loading="eager"' if priority else f'loading="{escape(loading)}"',
    ]
    if priority:
        attrs.append('fetchpriority="high"')
    if img_cls:
        attrs.append(f'class="{escape(img_cls)}"')
    if position:
        attrs.append(f'style="object-position: {escape(position)}"')
    sources = "".join(
        f'<source type="image/{fmt}" srcset="{escape(sets[fmt])}" sizes="{escape(sizes)}">'
        for fmt in ("avif", "webp")
        if fmt in sets
    )
    cls_attr = f' class="{escape(cls)}"' if cls else ""
    # Every interpolated value above is escaped explicitly.
    return Markup(f"<picture{cls_attr}>{sources}<img {' '.join(attrs)}></picture>")  # noqa: S704


def art_picture(
    media: dict[int, MediaAsset],
    desktop_id: int | None,
    mobile_id: int | None,
    *,
    img_cls: str = "",
    breakpoint: int = 900,
) -> Markup:
    """Art direction: a separate (portrait) image on phones, the wide one above the breakpoint."""
    desktop = media.get(desktop_id) if desktop_id else None
    mobile = media.get(mobile_id) if mobile_id else None
    main = desktop or mobile
    if main is None:
        return Markup("")
    sources = []
    for asset, query in ((mobile, f"(max-width: {breakpoint}px)"), (desktop, None)):
        if asset is None:
            continue
        sets = srcsets(asset)
        media_attr = f' media="{query}"' if query else ""
        for fmt in ("avif", "webp", "jpg"):
            if fmt in sets and (fmt != "jpg" or query):
                mime = "" if fmt == "jpg" else f' type="image/{fmt}"'
                sources.append(f'<source{media_attr}{mime} srcset="{escape(sets[fmt])}" sizes="100vw">')
    main_sets = srcsets(main)
    img = (
        f'<img class="{escape(img_cls)}" src="{escape(fallback_src(main))}" '
        f'srcset="{escape(main_sets.get("jpg", ""))}" '
        f'sizes="100vw" alt="{escape(main.alt)}" width="{main.width}" height="{main.height}" '
        'fetchpriority="high" loading="eager" decoding="async">'
    )
    return Markup(f"<picture>{''.join(sources)}{img}</picture>")  # noqa: S704 (values escaped above)


def media_src(media: dict[int, MediaAsset], media_id: int | None, width: int = 480) -> str:
    asset = media.get(media_id) if media_id else None
    return fallback_src(asset, width) if asset else ""


def plural(number: int, one: str, few: str, many: str) -> str:
    n = abs(number) % 100
    if 11 <= n <= 14:
        return many
    n %= 10
    if n == 1:
        return one
    if 2 <= n <= 4:
        return few
    return many


def build_templates() -> Jinja2Templates:
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    env = templates.env
    env.globals.update(
        static_url=static_url, picture=picture, art_picture=art_picture, media_src=media_src, plural=plural
    )
    env.filters["rub"] = rub
    env.trim_blocks = True
    env.lstrip_blocks = True
    return templates


def render_attrs(values: dict[str, Any]) -> Markup:
    """data-* attributes for the scripts (no inline JavaScript is allowed by the CSP)."""
    pairs = (f'data-{escape(k)}="{escape(v)}"' for k, v in values.items() if v not in (None, ""))
    return Markup(" ".join(pairs))  # noqa: S704 (keys and values escaped)
