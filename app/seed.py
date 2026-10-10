from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Category, Component, CustomField, Location, Manufacturer, Package, Workshop


def seed_if_needed(db: Session):
    has_existing_data = any(
        db.scalar(select(model.id).limit(1))
        for model in (Category, Component, CustomField, Location, Manufacturer, Package)
    )
    if not has_existing_data:
        return

    workshop = db.scalar(select(Workshop).order_by(Workshop.id.asc()).limit(1))
    if workshop is None:
        workshop = Workshop(name='Electronique', slug='electronics', description='Atelier par defaut.', is_active=True)
        db.add(workshop)
        db.flush()

    for item in db.scalars(select(Category).where(Category.workshop_id.is_(None))).all():
        item.workshop_id = workshop.id
    for item in db.scalars(select(Location).where(Location.workshop_id.is_(None))).all():
        item.workshop_id = workshop.id
    for item in db.scalars(select(CustomField).where(CustomField.workshop_id.is_(None))).all():
        item.workshop_id = workshop.id
    for item in db.scalars(select(Manufacturer).where(Manufacturer.workshop_id.is_(None))).all():
        item.workshop_id = workshop.id
    for item in db.scalars(select(Package).where(Package.workshop_id.is_(None))).all():
        item.workshop_id = workshop.id
    for item in db.scalars(select(Component).where(Component.workshop_id.is_(None))).all():
        item.workshop_id = workshop.id

    db.commit()
