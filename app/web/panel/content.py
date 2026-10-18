"""Site content screen: landing blocks (order, visibility, forms built from the block models) and gifts."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response
from sqlalchemy import select

from app.api.deps import DbSession
from app.content.sections import FIXED_SECTIONS, SECTION_MODELS, SECTION_TITLES, default_content
from app.models import GiftOption, MediaAsset, SiteSection
from app.web.panel.common import ManagerPanel, render
from app.web.panel.content_forms import form_spec

router = APIRouter()

Tab = Literal["blocks", "gifts"]
HINTS = {
    "hero": "Первое, что видит посетитель: заголовок, текст, кнопки и главное фото.",
    "works": "Тексты блока. Сами пары фото меняются в разделе «До и после».",
    "prices": "Тексты блока. Цены и пакеты берутся из раздела «Услуги».",
    "telegram": "Показывается на сайте, только когда в настройках указан бот.",
    "reviews": "Тексты блока. Сами отзывы в разделе «Отзывы».",
    "gift": "Тексты блока. Номиналы на вкладке «Сертификаты».",
    "contacts": "Тексты формы записи. Адрес, телефон и график задаются в «Настройках».",
    "seo": "Заголовок вкладки браузера и описание в поисковой выдаче.",
}


@router.get("/admin/{studio_id}/content")
async def content_page(
    request: Request,
    panel: ManagerPanel,
    session: DbSession,
    tab: Annotated[Tab, Query()] = "blocks",
    block: Annotated[str | None, Query(max_length=40)] = None,
) -> Response:
    sid = panel.studio.id
    rows = {r.key: r for r in await session.scalars(select(SiteSection).where(SiteSection.studio_id == sid))}
    order = sorted(SECTION_MODELS, key=lambda k: (k == "seo", k == "footer", rows[k].sort_order if k in rows else 99))
    order = ["hero"] + [k for k in order if k != "hero"]
    key = block if block in SECTION_MODELS else "hero"
    row = rows.get(key)
    content = {**default_content(key), **(row.content if row else {})}
    media = {m.id: m for m in await session.scalars(select(MediaAsset).where(MediaAsset.studio_id == sid))}
    gifts = list(
        await session.scalars(select(GiftOption).where(GiftOption.studio_id == sid).order_by(GiftOption.sort_order))
    )
    return render(
        request,
        "panel/content.html",
        panel,
        active="content",
        tab=tab,
        order=order,
        rows=rows,
        titles=SECTION_TITLES,
        fixed=FIXED_SECTIONS,
        key=key,
        spec=form_spec(SECTION_MODELS[key]),
        content=content,
        hint=HINTS.get(key, ""),
        media=media,
        gifts=gifts,
    )
