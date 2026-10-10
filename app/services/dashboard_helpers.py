from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Category, Component, Location, Workshop


def build_workshop_summaries(db: Session, include_inactive: bool = False) -> list[dict]:
    query = select(Workshop).order_by(Workshop.sort_order.asc(), Workshop.name.asc())
    if not include_inactive:
        query = query.where(Workshop.is_active.is_(True))
    workshops = db.scalars(query).all()
    summaries = []
    for workshop in workshops:
        summaries.append({
            'workshop': workshop,
            'component_count': db.scalar(select(func.count(Component.id)).where(Component.workshop_id == workshop.id)) or 0,
            'category_count': db.scalar(select(func.count(Category.id)).where(Category.workshop_id == workshop.id)) or 0,
            'location_count': db.scalar(select(func.count(Location.id)).where(Location.workshop_id == workshop.id)) or 0,
            'total_quantity': db.scalar(select(func.coalesce(func.sum(Component.quantity), 0)).where(Component.workshop_id == workshop.id)) or 0,
            'low_stock_count': db.scalar(
                select(func.count(Component.id)).where(
                    Component.workshop_id == workshop.id,
                    Component.quantity <= Component.minimum_quantity,
                )
            ) or 0,
        })
    return summaries
