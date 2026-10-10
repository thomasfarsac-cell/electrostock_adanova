from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models import Category, CustomField, Location, Manufacturer, Package
from app.services.category_helpers import get_category_children_map
from app.services.workshop_scope import scoped_query


def get_categories_for_select(db: Session, workshop_id: int | None = None):
    query = scoped_query(select(Category), Category, workshop_id)
    return db.scalars(
        query
        .options(joinedload(Category.parent), selectinload(Category.children))
        .order_by(Category.sort_order, Category.name)
    ).unique().all()


def get_reference_data(db: Session, workshop_id: int | None = None):
    categories = get_categories_for_select(db, workshop_id)
    manufacturers_query = scoped_query(select(Manufacturer), Manufacturer, workshop_id)
    packages_query = scoped_query(select(Package), Package, workshop_id)
    locations_query = scoped_query(select(Location), Location, workshop_id)
    custom_fields_query = scoped_query(
        select(CustomField).where(CustomField.is_active.is_(True)),
        CustomField,
        workshop_id,
    )
    return {
        'categories': categories,
        'category_children_map': get_category_children_map(categories),
        'manufacturers': db.scalars(manufacturers_query.order_by(Manufacturer.name)).all(),
        'packages': db.scalars(packages_query.order_by(Package.name)).all(),
        'locations': db.scalars(locations_query.order_by(Location.name)).all(),
        'custom_fields': db.scalars(
            custom_fields_query
            .order_by(CustomField.sort_order, CustomField.name)
        ).all(),
    }
