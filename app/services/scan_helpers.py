from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Component, Location
from app.utils import normalize_lookup


def resolve_scan(db: Session, raw_value: str):
    value = (raw_value or '').strip()
    if not value:
        return None

    upper = value.upper()
    if upper.startswith('C:'):
        payload = value.split(':', 1)[1].strip()
        if payload.isdigit():
            return db.get(Component, int(payload))
    if upper.startswith('COMPONENT_ID:'):
        payload = value.split(':', 1)[1].strip()
        if payload.isdigit():
            return db.get(Component, int(payload))
    if upper.startswith('L:'):
        payload = value.split(':', 1)[1].strip()
        if payload.isdigit():
            return db.get(Location, int(payload))
    if upper.startswith('LOCATION_ID:'):
        payload = value.split(':', 1)[1].strip()
        if payload.isdigit():
            return db.get(Location, int(payload))

    normalized = normalize_lookup(value)
    component = db.scalar(
        select(Component).where(func.lower(Component.part_number) == normalized.lower())
    )
    if component:
        return component
    location = db.scalar(
        select(Location).where(func.lower(Location.name) == normalized.lower())
    )
    if location:
        return location
    return None
