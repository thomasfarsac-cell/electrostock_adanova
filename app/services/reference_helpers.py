from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Category, CustomField, Location, Manufacturer, Package
from app.services.categories import build_category_path


def location_name_exists(db: Session, workshop_id: int, name: str, exclude_id: int | None = None) -> bool:
    query = select(func.count(Location.id)).where(
        Location.workshop_id == workshop_id,
        func.lower(Location.name) == name.strip().lower(),
    )
    if exclude_id is not None:
        query = query.where(Location.id != exclude_id)
    return (db.scalar(query) or 0) > 0


def category_name_exists(db: Session, workshop_id: int, parent_id: int | None, name: str, exclude_id: int | None = None) -> bool:
    query = select(func.count(Category.id)).where(
        Category.workshop_id == workshop_id,
        Category.parent_id == parent_id,
        func.lower(Category.name) == name.strip().lower(),
    )
    if exclude_id is not None:
        query = query.where(Category.id != exclude_id)
    return (db.scalar(query) or 0) > 0


def custom_field_name_or_slug_exists(db: Session, workshop_id: int, name: str, slug: str, exclude_id: int | None = None) -> bool:
    query = select(func.count(CustomField.id)).where(
        CustomField.workshop_id == workshop_id,
        or_(
            func.lower(CustomField.name) == name.strip().lower(),
            func.lower(CustomField.slug) == slug.strip().lower(),
        ),
    )
    if exclude_id is not None:
        query = query.where(CustomField.id != exclude_id)
    return (db.scalar(query) or 0) > 0


def named_reference_exists(db: Session, model_class, workshop_id: int, name: str, exclude_id: int | None = None) -> bool:
    query = select(func.count(model_class.id)).where(
        model_class.workshop_id == workshop_id,
        func.lower(model_class.name) == name.strip().lower(),
    )
    if exclude_id is not None:
        query = query.where(model_class.id != exclude_id)
    return (db.scalar(query) or 0) > 0


def validate_component_reference_scope(db: Session, payload: dict):
    workshop_id = payload.get('workshop_id')
    if not workshop_id:
        raise HTTPException(status_code=400, detail='Choisis un atelier pour cet article.')
    for key, model_class, message in (
        ('category_id', Category, 'Categorie hors atelier.'),
        ('manufacturer_id', Manufacturer, 'Marque / fabricant hors atelier.'),
        ('package_id', Package, 'Format / conditionnement hors atelier.'),
        ('location_id', Location, 'Emplacement hors atelier.'),
    ):
        reference_id = payload.get(key)
        if not reference_id:
            continue
        item = db.get(model_class, reference_id)
        if not item or item.workshop_id != workshop_id:
            raise HTTPException(status_code=400, detail=message)


def find_named_reference(items, wanted_name: str | None):
    normalized = (wanted_name or '').strip().lower()
    if not normalized:
        return None
    for item in items:
        if item.name.strip().lower() == normalized:
            return item
    return None


def find_category_by_path(categories: list[Category], wanted_path: str | None):
    normalized = (wanted_path or '').strip().lower()
    if not normalized:
        return None
    for category in categories:
        if build_category_path(category).strip().lower() == normalized:
            return category
    return None
