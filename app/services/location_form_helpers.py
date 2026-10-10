from __future__ import annotations

from types import SimpleNamespace

from fastapi import Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Location
from app.services.workshop_scope import scoped_query
from app.utils import parse_optional_int
from app.view_context import list_active_workshops, render


def render_location_form_page(
    request: Request,
    db: Session,
    action_url: str,
    location_state: dict | None = None,
    form_notice: dict | None = None,
    status_code: int = 200,
):
    location_view = SimpleNamespace(**location_state) if location_state else None
    return render(request, 'locations/form.html', {
        'location': location_view,
        'action_url': action_url,
        'form_notice': form_notice,
        'workshops': list_active_workshops(db),
    }, status_code=status_code)


def build_location_payload(name: str, description: str):
    return {
        'name': name.strip(),
        'description': description.strip() or None,
    }


def populate_location_from_form(location: Location, payload: dict):
    location.name = payload['name']
    location.description = payload.get('description')


def resolve_location_search_redirect(db: Session, raw_search: str, workshop_id: int | None = None) -> str | None:
    search_value = (raw_search or '').strip()
    if not search_value:
        return None

    normalized = search_value.upper()
    location_id = None

    if normalized.startswith('L:'):
        location_id = parse_optional_int(search_value[2:].strip())
    elif normalized.startswith('LOCATION_ID:'):
        location_id = parse_optional_int(search_value.split(':', 1)[1].strip())

    if location_id:
        location = db.get(Location, location_id)
        if location and (workshop_id is None or location.workshop_id == workshop_id):
            return f'/locations/{location.id}'

    exact_location = db.scalar(scoped_query(select(Location), Location, workshop_id).where(func.lower(Location.name) == search_value.lower()))
    if exact_location:
        return f'/locations/{exact_location.id}'

    return None
