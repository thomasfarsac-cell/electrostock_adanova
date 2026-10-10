from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Package, Workshop
from app.services.ai_component_lookup_v2 import lookup_component_details
from app.services.categories import build_category_path
from app.services.component_form_context import get_reference_data
from app.services.reference_helpers import find_category_by_path, find_named_reference


def build_ai_lookup_response(db: Session, part_number: str, workshop_id: int | None = None):
    refs = get_reference_data(db, workshop_id)
    workshop = db.get(Workshop, workshop_id) if workshop_id else None
    ai_result = lookup_component_details(
        part_number=part_number.strip(),
        categories=[build_category_path(item) for item in refs['categories']],
        manufacturers=[item.name for item in refs['manufacturers']],
        packages=[item.name for item in refs['packages']],
        custom_fields=[
            {
                'name': field.name,
                'unit': field.unit or '',
            }
            for field in refs['custom_fields']
        ],
        system_prompt_override=workshop.ai_prompt if workshop and workshop.ai_prompt else None,
    )

    matched_category = find_category_by_path(refs['categories'], ai_result.get('category_path'))
    matched_manufacturer = find_named_reference(refs['manufacturers'], ai_result.get('manufacturer_name'))
    matched_package = find_named_reference(refs['packages'], ai_result.get('package_name'))
    created_packages = []
    package_name = (ai_result.get('package_name') or '').strip()
    if package_name and matched_package is None and workshop_id is not None:
        matched_package = Package(name=package_name, workshop_id=workshop_id)
        db.add(matched_package)
        db.flush()
        created_packages.append(package_name)
    if created_packages:
        db.commit()

    custom_field_map = {field.name.strip().lower(): field for field in refs['custom_fields']}
    matched_custom_fields = []
    unmatched_custom_fields = []
    for item in ai_result.get('custom_fields', []):
        name = str(item.get('name', '')).strip()
        value = str(item.get('value', '')).strip()
        if not name or not value:
            continue
        field = custom_field_map.get(name.lower())
        if field:
            matched_custom_fields.append({
                'id': field.id,
                'name': field.name,
                'value': value,
            })
        else:
            unmatched_custom_fields.append(name)

    unmatched = {}
    if ai_result.get('category_path') and not matched_category:
        unmatched['category'] = ai_result['category_path']
    if ai_result.get('manufacturer_name') and not matched_manufacturer:
        unmatched['manufacturer'] = ai_result['manufacturer_name']
    if ai_result.get('package_name') and not matched_package:
        unmatched['package'] = ai_result['package_name']
    if unmatched_custom_fields:
        unmatched['custom_fields'] = unmatched_custom_fields

    return {
        'component': {
            'part_number': part_number.strip(),
            'name': ai_result.get('name') or '',
            'category_id': matched_category.id if matched_category else '',
            'manufacturer_id': matched_manufacturer.id if matched_manufacturer else '',
            'package_id': matched_package.id if matched_package else '',
            'location_id': '',
            'minimum_quantity': ai_result.get('minimum_quantity') if ai_result.get('minimum_quantity') is not None else '',
            'datasheet_url': ai_result.get('datasheet_url') or '',
            'keywords': ', '.join(dict.fromkeys(item.strip() for item in ai_result.get('keywords', []) if item.strip())),
            'description': ai_result.get('description') or '',
            'notes': ai_result.get('notes') or '',
            'custom_fields': matched_custom_fields,
        },
        'meta': {
            'confidence': ai_result.get('confidence') or 'medium',
            'warnings': ai_result.get('warnings') or [],
            'sources': ai_result.get('sources') or [],
            'unmatched': unmatched,
            'created_packages': created_packages,
        },
    }


def merge_ai_component_state(base_state: dict, ai_payload: dict):
    merged = dict(base_state)
    ai_component = ai_payload.get('component', {})
    for key in (
        'part_number',
        'name',
        'category_id',
        'manufacturer_id',
        'package_id',
        'location_id',
        'minimum_quantity',
        'datasheet_url',
        'keywords',
        'description',
        'notes',
    ):
        value = ai_component.get(key)
        if value not in (None, ''):
            merged[key] = value
    return merged


def build_ai_lookup_notice(ai_payload: dict):
    meta = ai_payload.get('meta', {})
    messages = [
        f"Pre-remplissage IA termine. Confiance estimee: {meta.get('confidence') or 'medium'}.",
    ]
    created_packages = [str(item).strip() for item in meta.get('created_packages', []) if str(item).strip()]
    if created_packages:
        messages.append('Format / conditionnement ajoute automatiquement: ' + ', '.join(created_packages))
    warnings = [str(item).strip() for item in meta.get('warnings', []) if str(item).strip()]
    if warnings:
        messages.append('Points a verifier: ' + ' | '.join(warnings))
    unmatched = meta.get('unmatched', {})
    unmatched_messages = []
    if unmatched.get('category'):
        unmatched_messages.append(f"Categorie non mappee localement: {unmatched['category']}")
    if unmatched.get('manufacturer'):
        unmatched_messages.append(f"Marque / fabricant non mappe localement: {unmatched['manufacturer']}")
    if unmatched.get('package'):
        unmatched_messages.append(f"Format / conditionnement non mappe localement: {unmatched['package']}")
    if unmatched.get('custom_fields'):
        unmatched_messages.append('Champs personnalises non mappes: ' + ', '.join(unmatched['custom_fields']))
    if unmatched_messages:
        messages.append(' | '.join(unmatched_messages))
    return {
        'tone': 'warning' if unmatched_messages else 'success',
        'message': ' '.join(messages),
    }
