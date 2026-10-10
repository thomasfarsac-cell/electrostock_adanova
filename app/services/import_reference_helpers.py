from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Category


def find_or_create_named_item(db: Session, model_class, name: str | None, create_missing: bool, workshop_id: int | None = None):
    text = (name or '').strip()
    if not text:
        return None
    query = select(model_class).where(func.lower(model_class.name) == text.lower())
    if workshop_id is not None and hasattr(model_class, 'workshop_id'):
        query = query.where(model_class.workshop_id == workshop_id)
    existing = db.scalar(query)
    if existing:
        return existing
    if not create_missing:
        return None
    item = model_class(name=text)
    if workshop_id is not None and hasattr(item, 'workshop_id'):
        item.workshop_id = workshop_id
    db.add(item)
    db.flush()
    return item


def find_or_create_category_by_path(db: Session, category_path: str | None, create_missing: bool, workshop_id: int | None = None):
    path = (category_path or '').strip()
    if not path:
        return None
    parts = [segment.strip() for segment in path.replace('>', '/').replace('\\', '/').split('/') if segment.strip()]
    if not parts:
        return None

    parent = None
    current = None
    for index, part in enumerate(parts):
        current = db.scalar(
            select(Category)
            .where(
                Category.parent_id == (parent.id if parent else None),
                Category.workshop_id == workshop_id,
                func.lower(Category.name) == part.lower(),
            )
        )
        if current is None:
            if not create_missing:
                return None
            if index >= 6:
                raise ValueError('Chemin de catÃ©gorie trop profond (max 6 niveaux).')
            current = Category(name=part, workshop_id=workshop_id, parent_id=parent.id if parent else None, sort_order=0)
            db.add(current)
            db.flush()
        parent = current
    return current
