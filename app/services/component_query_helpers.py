from __future__ import annotations

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models import Category, Component
from app.services.categories import get_descendant_ids
from app.services.location_form_helpers import resolve_location_search_redirect
from app.services.workshop_scope import scoped_query
from app.utils import parse_optional_int


def build_component_query(
    db: Session,
    search: str = '',
    workshop_id: int | None = None,
    category_id: int | None = None,
    manufacturer_id: int | None = None,
    package_id: int | None = None,
    location_id: int | None = None,
    stock_status: str = '',
    qty_min: int | None = None,
    qty_max: int | None = None,
):
    query = select(Component).options(
        joinedload(Component.category).joinedload(Category.parent),
        joinedload(Component.manufacturer),
        joinedload(Component.package),
        joinedload(Component.location),
    )
    query = scoped_query(query, Component, workshop_id)

    if search.strip():
        term = f'%{search.strip()}%'
        query = query.where(
            or_(
                Component.part_number.ilike(term),
                Component.name.ilike(term),
                Component.keywords.ilike(term),
                Component.description.ilike(term),
                Component.notes.ilike(term),
            )
        )

    if category_id:
        category = db.get(Category, category_id)
        if category:
            query = query.where(Component.category_id.in_(get_descendant_ids(category)))

    if manufacturer_id:
        query = query.where(Component.manufacturer_id == manufacturer_id)
    if package_id:
        query = query.where(Component.package_id == package_id)
    if location_id:
        query = query.where(Component.location_id == location_id)

    if stock_status == 'available':
        query = query.where(Component.quantity > Component.minimum_quantity)
    elif stock_status == 'low':
        query = query.where(Component.quantity <= Component.minimum_quantity)
    elif stock_status == 'empty':
        query = query.where(Component.quantity <= 0)

    if qty_min is not None:
        query = query.where(Component.quantity >= qty_min)
    if qty_max is not None:
        query = query.where(Component.quantity <= qty_max)
    return query


def resolve_component_search_redirect(db: Session, raw_search: str, workshop_id: int | None = None) -> str | None:
    search_value = (raw_search or '').strip()
    if not search_value:
        return None

    location_redirect = resolve_location_search_redirect(db, search_value, workshop_id)
    if location_redirect:
        return location_redirect

    normalized = search_value.upper()
    component_id = None
    if normalized.startswith('C:'):
        component_id = parse_optional_int(search_value[2:].strip())
    elif normalized.startswith('COMPONENT_ID:'):
        component_id = parse_optional_int(search_value.split(':', 1)[1].strip())

    if component_id:
        component = db.get(Component, component_id)
        if component and (workshop_id is None or component.workshop_id == workshop_id):
            return f'/components/{component.id}'

    exact_component = db.scalar(
        scoped_query(select(Component), Component, workshop_id).where(
            func.lower(Component.part_number) == search_value.lower()
        )
    )
    if exact_component:
        return f'/components/{exact_component.id}'
    return None
