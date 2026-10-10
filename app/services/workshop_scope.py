from __future__ import annotations

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Workshop
from app.utils import parse_optional_int
from app.view_context import get_selected_workshop_id

DEFAULT_WORKSHOP_SLUG = 'electronics'


def get_default_workshop(db: Session) -> Workshop:
    workshop = db.scalar(select(Workshop).where(Workshop.slug == DEFAULT_WORKSHOP_SLUG))
    if workshop:
        return workshop
    workshop = Workshop(
        name='Electronique',
        slug=DEFAULT_WORKSHOP_SLUG,
        description='Atelier par defaut pour les donnees existantes.',
        is_active=True,
        sort_order=0,
    )
    db.add(workshop)
    db.flush()
    return workshop


def scoped_query(query, model_class, workshop_id: int | None):
    if workshop_id is None:
        return query
    return query.where(model_class.workshop_id == workshop_id)


def scoped_entity_or_404(request: Request, db: Session, entity):
    workshop_id = get_selected_workshop_id(request, db)
    if entity is None:
        raise HTTPException(status_code=404)
    if workshop_id is not None and getattr(entity, 'workshop_id', None) != workshop_id:
        raise HTTPException(status_code=404)
    return entity


def parse_workshop_choice(request: Request, db: Session, raw_value: str = '') -> int:
    active_id = get_selected_workshop_id(request, db)
    if active_id is not None:
        return active_id
    chosen_id = parse_optional_int(raw_value)
    if not chosen_id:
        raise HTTPException(status_code=400, detail='Choisis un atelier pour creer cet element.')
    workshop = db.get(Workshop, chosen_id)
    if not workshop or not workshop.is_active:
        raise HTTPException(status_code=400, detail='Atelier invalide.')
    return workshop.id
