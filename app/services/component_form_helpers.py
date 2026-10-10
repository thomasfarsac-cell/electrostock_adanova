from __future__ import annotations

from types import SimpleNamespace

from fastapi import Request
from sqlalchemy.orm import Session

from app.models import Component, ComponentCustomFieldValue, CustomField, Workshop
from app.services.ai_component_lookup_v2 import is_ai_component_lookup_enabled
from app.services.category_helpers import get_category_chain_labels
from app.services.component_form_context import get_reference_data
from app.services.item_profiles import item_field_label, item_field_visible, merge_item_profile
from app.utils import parse_int, parse_optional_int
from app.view_context import (
    get_selected_workshop,
    get_selected_workshop_id,
    list_active_workshops,
    render,
)


def populate_component_from_form(component: Component, payload: dict):
    component.part_number = payload['part_number'].strip()
    component.name = payload['name'].strip()
    component.workshop_id = payload.get('workshop_id')
    component.category_id = payload.get('category_id')
    component.manufacturer_id = payload.get('manufacturer_id')
    component.package_id = payload.get('package_id')
    component.location_id = payload.get('location_id')
    component.minimum_quantity = payload.get('minimum_quantity', 0)
    component.datasheet_url = payload.get('datasheet_url') or None
    component.description = payload.get('description') or None
    component.notes = payload.get('notes') or None
    component.keywords = payload.get('keywords') or None


def build_component_payload(
    part_number: str,
    name: str,
    category_id_raw: str,
    manufacturer_id_raw: str,
    package_id_raw: str,
    location_id_raw: str,
    workshop_id_raw: str,
    minimum_quantity_raw: str,
    datasheet_url: str,
    description: str,
    notes: str,
    keywords: str,
):
    return {
        'part_number': part_number.strip(),
        'name': name.strip(),
        'workshop_id': parse_optional_int(workshop_id_raw),
        'category_id': parse_optional_int(category_id_raw),
        'manufacturer_id': parse_optional_int(manufacturer_id_raw),
        'package_id': parse_optional_int(package_id_raw),
        'location_id': parse_optional_int(location_id_raw),
        'minimum_quantity': parse_int(minimum_quantity_raw, 0),
        'datasheet_url': datasheet_url.strip() or None,
        'description': description.strip() or None,
        'notes': notes.strip() or None,
        'keywords': keywords.strip() or None,
    }


def build_form_component_state(
    part_number: str,
    name: str,
    category_id: str,
    manufacturer_id: str,
    package_id: str,
    location_id: str,
    workshop_id: str,
    quantity: str,
    minimum_quantity: str,
    datasheet_url: str,
    description: str,
    notes: str,
    keywords: str,
    image_path: str | None = None,
    thumbnail_path: str | None = None,
):
    payload = build_component_payload(
        part_number=part_number,
        name=name,
        category_id_raw=category_id,
        manufacturer_id_raw=manufacturer_id,
        package_id_raw=package_id,
        location_id_raw=location_id,
        workshop_id_raw=workshop_id,
        minimum_quantity_raw=minimum_quantity,
        datasheet_url=datasheet_url,
        description=description,
        notes=notes,
        keywords=keywords,
    )
    payload['quantity'] = parse_int(quantity, 0)
    payload['image_path'] = image_path
    payload['thumbnail_path'] = thumbnail_path
    return payload


def render_component_form_page(
    request: Request,
    db: Session,
    action_url: str,
    component_state: dict | None,
    custom_values: dict,
    ai_lookup_notice: dict | None = None,
    status_code: int = 200,
):
    active_workshop_id = get_selected_workshop_id(request, db)
    component_view = SimpleNamespace(**component_state) if component_state else None
    category_id_value = component_state.get('category_id') if component_state else None
    profile_workshop_id = component_state.get('workshop_id') if component_state else active_workshop_id
    profile_workshop = db.get(Workshop, profile_workshop_id) if profile_workshop_id else get_selected_workshop(request, db)
    reference_workshop_id = profile_workshop_id if profile_workshop_id else active_workshop_id
    refs = get_reference_data(db, reference_workshop_id if reference_workshop_id else -1)
    item_profile = merge_item_profile(profile_workshop)
    return render(request, 'components/form.html', {
        'component': component_view,
        'custom_values': custom_values,
        'action_url': action_url,
        'workshops': list_active_workshops(db),
        'selected_category_chain': [],
        'category_level_labels': get_category_chain_labels(refs['categories'], category_id_value),
        'ai_component_lookup_enabled': is_ai_component_lookup_enabled(),
        'ai_lookup_notice': ai_lookup_notice,
        'item_profile': item_profile,
        'item_field_label': item_field_label,
        'item_field_visible': item_field_visible,
        **refs,
    }, status_code=status_code)


def apply_custom_fields_from_form(db: Session, component: Component, form_data, active_fields: list[CustomField]):
    field_values = {item.custom_field_id: item for item in component.custom_values}
    for field in active_fields:
        raw_value = str(form_data.get(f'custom_{field.id}', '')).strip()
        existing_value = field_values.get(field.id)
        if raw_value:
            if existing_value:
                existing_value.value = raw_value
            else:
                db.add(ComponentCustomFieldValue(component_id=component.id, custom_field_id=field.id, value=raw_value))
        elif existing_value:
            db.delete(existing_value)
