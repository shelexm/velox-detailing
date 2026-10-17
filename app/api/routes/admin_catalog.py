"""Catalog API for the panel: services, price list sections, landing directions."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response

from app.api.deps import DbSession, Manager
from app.models import Service, ServiceCategory, ServiceGroup
from app.models.enums import StaffSelection
from app.schemas.catalog import (
    CategoryIn,
    CategoryOut,
    GroupCreateIn,
    GroupFields,
    GroupOut,
    ServiceAdminOut,
    ServiceCreateIn,
    ServiceUpdateIn,
)
from app.schemas.media import OrderIn
from app.services import catalog

router = APIRouter(prefix="/api/v1/admin/studios/{studio_id}", tags=["admin-catalog"])


async def _service_out(session, studio_id: int, service: Service) -> ServiceAdminOut:
    return ServiceAdminOut(
        id=service.id,
        slug=service.slug,
        name=service.name,
        category_id=service.category_id,
        group_id=service.group_id,
        kind=service.kind,
        short_description=service.short_description or "",
        description=service.description,
        items=list(service.items or []),
        price_from=service.price_from,
        duration_minutes=service.duration_minutes,
        duration_days=service.duration_days,
        duration_label=service.duration_label,
        badge=service.badge,
        note=service.note,
        online_booking=service.online_booking,
        client_selects_staff=service.staff_selection == StaffSelection.CLIENT,
        requires_resource=service.requires_resource,
        requires_staff=service.requires_staff,
        show_in_price_list=service.show_in_price_list,
        image_id=service.image_id,
        staff_ids=await catalog.service_staff_ids(session, studio_id, service.id),
        sort_order=service.sort_order,
    )


@router.post("/services", status_code=201)
async def create_service(payload: ServiceCreateIn, access: Manager, session: DbSession) -> ServiceAdminOut:
    service = await catalog.create_service(session, access.studio.id, payload)
    return await _service_out(session, access.studio.id, service)


@router.get("/services/{service_id}")
async def get_service(service_id: int, access: Manager, session: DbSession) -> ServiceAdminOut:
    service = await catalog.get_service(session, access.studio.id, service_id)
    return await _service_out(session, access.studio.id, service)


@router.patch("/services/{service_id}")
async def update_service(
    service_id: int, payload: ServiceUpdateIn, access: Manager, session: DbSession
) -> ServiceAdminOut:
    service = await catalog.update_service(session, access.studio.id, service_id, payload)
    return await _service_out(session, access.studio.id, service)


@router.delete("/services/{service_id}", status_code=204)
async def retire_service(service_id: int, access: Manager, session: DbSession) -> Response:
    await catalog.retire_service(session, access.studio.id, service_id)
    return Response(status_code=204)


@router.post("/services/order", status_code=204)
async def order_services(payload: OrderIn, access: Manager, session: DbSession) -> Response:
    await catalog.reorder(session, Service, access.studio.id, payload.ids)
    return Response(status_code=204)


@router.post("/categories", status_code=201)
async def create_category(payload: CategoryIn, access: Manager, session: DbSession) -> CategoryOut:
    return CategoryOut.model_validate(await catalog.create_category(session, access.studio.id, payload.name))


@router.patch("/categories/{category_id}")
async def rename_category(category_id: int, payload: CategoryIn, access: Manager, session: DbSession) -> CategoryOut:
    category = await catalog.rename_category(session, access.studio.id, category_id, payload.name)
    return CategoryOut.model_validate(category)


@router.delete("/categories/{category_id}", status_code=204)
async def delete_category(category_id: int, access: Manager, session: DbSession) -> Response:
    await catalog.delete_category(session, access.studio.id, category_id)
    return Response(status_code=204)


@router.post("/categories/order", status_code=204)
async def order_categories(payload: OrderIn, access: Manager, session: DbSession) -> Response:
    await catalog.reorder(session, ServiceCategory, access.studio.id, payload.ids)
    return Response(status_code=204)


@router.post("/groups", status_code=201)
async def create_group(payload: GroupCreateIn, access: Manager, session: DbSession) -> GroupOut:
    return GroupOut.model_validate(await catalog.create_group(session, access.studio.id, payload))


@router.patch("/groups/{group_id}")
async def update_group(group_id: int, payload: GroupFields, access: Manager, session: DbSession) -> GroupOut:
    return GroupOut.model_validate(await catalog.update_group(session, access.studio.id, group_id, payload))


@router.delete("/groups/{group_id}", status_code=204)
async def delete_group(group_id: int, access: Manager, session: DbSession) -> Response:
    await catalog.delete_group(session, access.studio.id, group_id)
    return Response(status_code=204)


@router.post("/groups/order", status_code=204)
async def order_groups(payload: OrderIn, access: Manager, session: DbSession) -> Response:
    await catalog.reorder(session, ServiceGroup, access.studio.id, payload.ids)
    return Response(status_code=204)
