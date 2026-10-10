from __future__ import annotations

from reportlab.lib.units import mm
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import Category, Component
from app.services.component_query_helpers import build_component_query
from app.services.workshop_scope import scoped_query
from app.utils import parse_optional_int


def get_component_label_query(
    db: Session,
    source: str,
    filters: dict,
    selected_ids: list[int],
    current_page_ids: list[int],
    workshop_id: int | None = None,
):
    if source == 'selected':
        if not selected_ids:
            raise ValueError('Aucun article selectionne.')
        query = (
            select(Component)
            .where(Component.id.in_(selected_ids))
            .options(
                joinedload(Component.category).joinedload(Category.parent),
                joinedload(Component.manufacturer),
                joinedload(Component.package),
                joinedload(Component.location),
            )
            .order_by(Component.part_number.asc())
        )
        return scoped_query(query, Component, workshop_id)

    if source == 'current_page':
        if not current_page_ids:
            raise ValueError('Aucun article present sur la page courante.')
        query = (
            select(Component)
            .where(Component.id.in_(current_page_ids))
            .options(
                joinedload(Component.category).joinedload(Category.parent),
                joinedload(Component.manufacturer),
                joinedload(Component.package),
                joinedload(Component.location),
            )
            .order_by(Component.part_number.asc())
        )
        return scoped_query(query, Component, workshop_id)

    return build_component_query(
        db=db,
        search=str(filters.get('search') or ''),
        workshop_id=workshop_id,
        category_id=parse_optional_int(filters.get('category_id')),
        manufacturer_id=parse_optional_int(filters.get('manufacturer_id')),
        package_id=parse_optional_int(filters.get('package_id')),
        location_id=parse_optional_int(filters.get('location_id')),
        stock_status=str(filters.get('stock_status') or ''),
        qty_min=parse_optional_int(filters.get('qty_min')),
        qty_max=parse_optional_int(filters.get('qty_max')),
    ).order_by(Component.part_number.asc())


def label_layout_config(layout_key: str):
    layouts = {
        '38x21': {'cols': 5, 'rows': 13, 'w': 38 * mm, 'h': 21 * mm, 'margin_x': 10 * mm, 'margin_y': 12 * mm},
        '48x25': {'cols': 4, 'rows': 10, 'w': 48 * mm, 'h': 25 * mm, 'margin_x': 8 * mm, 'margin_y': 12 * mm},
        '63x38': {'cols': 3, 'rows': 7, 'w': 63 * mm, 'h': 38 * mm, 'margin_x': 10 * mm, 'margin_y': 10 * mm},
    }
    return layouts.get(layout_key, layouts['48x25'])
