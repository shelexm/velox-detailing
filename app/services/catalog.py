"""Catalog changes from the panel. Every id from the browser is checked against the studio first."""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, ValidationFailedError, russian_message
from app.core.text import slugify, unique_slug
from app.models import MediaAsset, Service, ServiceCategory, ServiceGroup, ServiceStaff, Staff
from app.models.enums import StaffSelection
from app.schemas.catalog import GroupDetailIn, GroupFields, ServiceFields

REQUIRED_SERVICE_FIELDS = frozenset(
    {"name", "kind", "online_booking", "requires_resource", "requires_staff", "show_in_price_list"}
)


def _invalid(field: str, message: str) -> ValidationFailedError:
    return ValidationFailedError(details=[{"field": field, "message": message}])


async def _owned(session: AsyncSession, model, studio_id: int, object_id: int | None, field: str, label: str):
    if object_id is None:
        return None
    row = await session.scalar(select(model).where(model.studio_id == studio_id, model.id == object_id))
    if row is None:
        raise _invalid(field, f"{label} не найдено")
    return row


async def get_service(session: AsyncSession, studio_id: int, service_id: int) -> Service:
    service = await session.scalar(
        select(Service).where(Service.studio_id == studio_id, Service.id == service_id, Service.is_active.is_(True))
    )
    if service is None:
        raise NotFoundError("Услуга не найдена")
    return service


async def service_staff_ids(session: AsyncSession, studio_id: int, service_id: int) -> list[int]:
    rows = await session.scalars(
        select(ServiceStaff.staff_id).where(ServiceStaff.studio_id == studio_id, ServiceStaff.service_id == service_id)
    )
    return list(rows)


def _duration(amount: int, unit: str) -> tuple[int | None, int | None]:
    """(minutes, days): a service lasts either some minutes or whole working days."""
    if unit == "days":
        return None, amount
    minutes = amount * 60 if unit == "hours" else amount
    if not 5 <= minutes <= 1440:
        raise _invalid("duration_value", "От 5 минут до 24 часов")
    return minutes, None


async def _apply_service(session: AsyncSession, studio_id: int, service: Service, data: ServiceFields) -> None:
    values = data.model_dump(exclude_unset=True)
    await _owned(session, ServiceCategory, studio_id, values.get("category_id"), "category_id", "Раздел")
    await _owned(session, ServiceGroup, studio_id, values.get("group_id"), "group_id", "Направление")
    await _owned(session, MediaAsset, studio_id, values.get("image_id"), "image_id", "Изображение")

    if "duration_value" in values and values["duration_value"] is not None:
        service.duration_minutes, service.duration_days = _duration(values["duration_value"], values["duration_unit"])
    if "client_selects_staff" in values and values["client_selects_staff"] is not None:
        service.staff_selection = StaffSelection.CLIENT if values["client_selects_staff"] else StaffSelection.STUDIO

    simple = (
        "name", "category_id", "group_id", "kind", "description", "items", "price_from", "duration_label",
        "badge", "note", "online_booking", "requires_resource", "requires_staff", "show_in_price_list", "image_id",
    )  # fmt: skip
    for field in simple:
        if field in values:
            value = values[field]
            if value is None and field in REQUIRED_SERVICE_FIELDS:
                continue
            if field == "items" and value is None:
                value = []
            setattr(service, field, value)
    if "short_description" in values:
        service.short_description = " ".join((values["short_description"] or "").split())

    if "staff_ids" in values and values["staff_ids"] is not None:
        wanted = list(dict.fromkeys(values["staff_ids"]))
        found = set(await session.scalars(select(Staff.id).where(Staff.studio_id == studio_id, Staff.id.in_(wanted))))
        if len(found) != len(wanted):
            raise _invalid("staff_ids", "Мастер не найден")
        await session.flush()
        await session.execute(
            delete(ServiceStaff).where(ServiceStaff.studio_id == studio_id, ServiceStaff.service_id == service.id)
        )
        session.add_all(ServiceStaff(studio_id=studio_id, service_id=service.id, staff_id=s) for s in wanted)
    picks_master = service.requires_staff and service.staff_selection == StaffSelection.CLIENT
    if picks_master and "staff_ids" in values and not values["staff_ids"]:
        raise _invalid("staff_ids", "Выберите мастеров или включите «Мастера назначает студия»")


async def create_service(session: AsyncSession, studio_id: int, data: ServiceFields) -> Service:
    taken = set(await session.scalars(select(Service.slug).where(Service.studio_id == studio_id)))
    last = await session.scalar(select(func.max(Service.sort_order)).where(Service.studio_id == studio_id))
    service = Service(
        studio_id=studio_id,
        slug=unique_slug(slugify(data.name or "", fallback="service"), taken),
        name=data.name,
        short_description="",
        items=[],
        is_active=True,
        sort_order=(last or 0) + 1,
    )
    service.duration_minutes, service.duration_days = _duration(data.duration_value, data.duration_unit)
    session.add(service)
    await session.flush()
    await _apply_service(session, studio_id, service, data)
    await session.commit()
    return service


async def update_service(session: AsyncSession, studio_id: int, service_id: int, data: ServiceFields) -> Service:
    service = await get_service(session, studio_id, service_id)
    await _apply_service(session, studio_id, service, data)
    await session.commit()
    return service


async def retire_service(session: AsyncSession, studio_id: int, service_id: int) -> None:
    """Bookings keep a copy of the name and price, so the service only disappears from the site and forms."""
    service = await get_service(session, studio_id, service_id)
    service.is_active = False
    service.online_booking = False
    await session.commit()


async def reorder(session: AsyncSession, model, studio_id: int, ids: list[int]) -> None:
    query = select(model).where(model.studio_id == studio_id, model.id.in_(ids))
    rows = {r.id: r for r in await session.scalars(query)}
    for position, object_id in enumerate(ids):
        if object_id in rows:
            rows[object_id].sort_order = position + 1
    await session.commit()


# ----- categories (price list sections) -----


async def create_category(session: AsyncSession, studio_id: int, name: str) -> ServiceCategory:
    taken = set(await session.scalars(select(ServiceCategory.slug).where(ServiceCategory.studio_id == studio_id)))
    last = await session.scalar(
        select(func.max(ServiceCategory.sort_order)).where(ServiceCategory.studio_id == studio_id)
    )
    category = ServiceCategory(
        studio_id=studio_id,
        slug=unique_slug(slugify(name, fallback="section"), taken),
        name=name,
        sort_order=(last or 0) + 1,
    )
    session.add(category)
    await session.commit()
    return category


async def rename_category(session: AsyncSession, studio_id: int, category_id: int, name: str) -> ServiceCategory:
    category = await session.scalar(
        select(ServiceCategory).where(ServiceCategory.studio_id == studio_id, ServiceCategory.id == category_id)
    )
    if category is None:
        raise NotFoundError("Раздел не найден")
    category.name = name
    await session.commit()
    return category


async def delete_category(session: AsyncSession, studio_id: int, category_id: int) -> None:
    category = await session.scalar(
        select(ServiceCategory).where(ServiceCategory.studio_id == studio_id, ServiceCategory.id == category_id)
    )
    if category is None:
        raise NotFoundError("Раздел не найден")
    used = await session.scalar(
        select(func.count()).where(Service.studio_id == studio_id, Service.category_id == category_id)
    )
    if used:
        raise ConflictError("В разделе есть услуги. Перенесите их в другой раздел", code="category_in_use")
    await session.delete(category)
    await session.commit()


# ----- landing directions (service groups) -----


async def get_group(session: AsyncSession, studio_id: int, group_id: int) -> ServiceGroup:
    group = await session.scalar(
        select(ServiceGroup).where(ServiceGroup.studio_id == studio_id, ServiceGroup.id == group_id)
    )
    if group is None:
        raise NotFoundError("Направление не найдено")
    return group


async def _apply_group(session: AsyncSession, studio_id: int, group: ServiceGroup, data: GroupFields) -> None:
    values = data.model_dump(exclude_unset=True)
    await _owned(session, MediaAsset, studio_id, values.get("image_id"), "image_id", "Изображение")
    if "detail" in values and values["detail"] is not None:
        try:
            detail = GroupDetailIn.model_validate(values.pop("detail"))
        except ValidationError as exc:
            raise ValidationFailedError(
                details=[
                    {"field": "detail." + ".".join(str(p) for p in err["loc"]), "message": russian_message(err)}
                    for err in exc.errors()
                ]
            ) from exc
        gallery = []
        for item in detail.gallery:
            image_id = item.get("image_id")
            if not isinstance(image_id, int):
                continue
            await _owned(session, MediaAsset, studio_id, image_id, "detail.gallery", "Изображение")
            gallery.append({"image_id": image_id, "label": str(item.get("label") or "")[:20]})
        cleaned: dict[str, Any] = {
            k: (" ".join(v.split()) or None) if isinstance(v, str) else v
            for k, v in detail.model_dump(exclude={"gallery"}).items()
        }
        cleaned["includes"] = [x for x in detail.includes if x and x.strip()]
        cleaned["gallery"] = gallery
        group.detail = cleaned
    else:
        values.pop("detail", None)
    for field, value in values.items():
        if field in ("title", "is_wide", "is_visible") and value is None:
            continue
        if field == "features" and value is None:
            value = []
        setattr(group, field, value)


async def create_group(session: AsyncSession, studio_id: int, data: GroupFields) -> ServiceGroup:
    taken = set(await session.scalars(select(ServiceGroup.slug).where(ServiceGroup.studio_id == studio_id)))
    last = await session.scalar(select(func.max(ServiceGroup.sort_order)).where(ServiceGroup.studio_id == studio_id))
    group = ServiceGroup(
        studio_id=studio_id,
        slug=unique_slug(slugify(data.title or "", fallback="service"), taken),
        title=data.title,
        features=[],
        detail={},
        is_visible=True,
        sort_order=(last or 0) + 1,
    )
    session.add(group)
    await session.flush()
    await _apply_group(session, studio_id, group, data)
    await session.commit()
    return group


async def update_group(session: AsyncSession, studio_id: int, group_id: int, data: GroupFields) -> ServiceGroup:
    group = await get_group(session, studio_id, group_id)
    await _apply_group(session, studio_id, group, data)
    await session.commit()
    return group


async def delete_group(session: AsyncSession, studio_id: int, group_id: int) -> None:
    group = await get_group(session, studio_id, group_id)
    used = await session.scalar(
        select(func.count()).where(
            Service.studio_id == studio_id, Service.group_id == group_id, Service.is_active.is_(True)
        )
    )
    if used:
        raise ConflictError("К направлению привязаны услуги. Сначала уберите их", code="group_in_use")
    # Retired services may still point at it; detach them so the row can go.
    for service in await session.scalars(
        select(Service).where(Service.studio_id == studio_id, Service.group_id == group_id)
    ):
        service.group_id = None
    await session.flush()
    await session.delete(group)
    await session.commit()
