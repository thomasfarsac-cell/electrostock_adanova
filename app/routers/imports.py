from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Component, Location, Manufacturer, Package
from app.security.permissions import require_stock_write_access
from app.services.component_form_helpers import populate_component_from_form
from app.services.export_helpers import export_template_csv
from app.services.import_reference_helpers import find_or_create_category_by_path, find_or_create_named_item
from app.services.imports import (
    IMPORT_FIELD_DEFINITIONS,
    delete_import_session,
    load_import_session,
    parse_import_file,
    save_import_session,
    suggest_mapping,
)
from app.services.reference_helpers import validate_component_reference_scope
from app.services.stock import add_stock_movement, adjust_stock_to_quantity
from app.utils import parse_int
from app.view_context import get_selected_workshop_id, render

router = APIRouter()


@router.get('/imports/components')
def import_components_page(request: Request, token: str = '', db: Session = Depends(get_db)):
    require_stock_write_access(request)
    active_workshop_id = get_selected_workshop_id(request, db)
    preview = None
    if token:
        try:
            preview = load_import_session(token)
        except FileNotFoundError:
            preview = None
    return render(request, 'imports/components.html', {
        'preview': preview,
        'token': token,
        'import_fields': IMPORT_FIELD_DEFINITIONS,
        'error_message': 'Choisis un atelier specifique avant dimporter des articles.' if active_workshop_id is None else '',
    })


@router.post('/imports/components/preview')
async def preview_component_import(request: Request, source_file: UploadFile = File(...), db: Session = Depends(get_db)):
    require_stock_write_access(request)
    if get_selected_workshop_id(request, db) is None:
        return render(request, 'imports/components.html', {
            'preview': None,
            'token': '',
            'import_fields': IMPORT_FIELD_DEFINITIONS,
            'error_message': 'Choisis un atelier specifique avant dimporter des articles.',
        }, status_code=400)
    if not source_file.filename:
        return render(request, 'imports/components.html', {
            'preview': None,
            'token': '',
            'import_fields': IMPORT_FIELD_DEFINITIONS,
            'error_message': 'Choisis un fichier avant de lancer lâ€™analyse.',
        }, status_code=400)

    content = await source_file.read()
    try:
        payload = parse_import_file(source_file.filename, content)
    except ValueError as exc:
        return render(request, 'imports/components.html', {
            'preview': None,
            'token': '',
            'import_fields': IMPORT_FIELD_DEFINITIONS,
            'error_message': str(exc),
        }, status_code=400)

    payload['suggested_mapping'] = suggest_mapping(payload['headers'])
    token = save_import_session(payload)
    return RedirectResponse(url=f'/imports/components?token={token}', status_code=303)


@router.get('/imports/components/template.csv')
def download_component_import_template():
    return export_template_csv()


@router.post('/imports/components/run')
async def run_component_import(
    request: Request,
    token: str = Form(...),
    import_mode: str = Form('upsert'),
    create_missing_references: bool = Form(False),
    create_missing_categories: bool = Form(False),
    db: Session = Depends(get_db),
):
    require_stock_write_access(request)
    active_workshop_id = get_selected_workshop_id(request, db)
    if active_workshop_id is None:
        return render(request, 'imports/components.html', {
            'preview': None,
            'token': '',
            'import_fields': IMPORT_FIELD_DEFINITIONS,
            'error_message': 'Choisis un atelier specifique avant dimporter des articles.',
        }, status_code=400)
    try:
        payload = load_import_session(token)
    except FileNotFoundError:
        return render(request, 'imports/components.html', {
            'preview': None,
            'token': '',
            'import_fields': IMPORT_FIELD_DEFINITIONS,
            'error_message': 'Session dâ€™import expirÃ©e. Recharge le fichier.',
        }, status_code=400)

    form = await request.form()
    mapping = {}
    for field in IMPORT_FIELD_DEFINITIONS:
        mapping[field['key']] = str(form.get(f'map_{field["key"]}', '')).strip()

    if not mapping.get('part_number') or not mapping.get('name'):
        return render(request, 'imports/components.html', {
            'preview': payload,
            'token': token,
            'import_fields': IMPORT_FIELD_DEFINITIONS,
            'error_message': 'RÃ©fÃ©rence et dÃ©signation doivent Ãªtre mappÃ©es.',
        }, status_code=400)

    results = {
        'created': 0,
        'updated': 0,
        'skipped': 0,
        'errors': [],
        'total': payload['row_count'],
    }

    for index, row in enumerate(payload['rows'], start=2):
        try:
            row_data = {field_key: row.get(column_name, '').strip() if column_name else '' for field_key, column_name in mapping.items()}
            part_number_value = row_data.get('part_number', '').strip()
            name_value = row_data.get('name', '').strip()
            if not part_number_value and not name_value:
                results['skipped'] += 1
                continue
            if not part_number_value or not name_value:
                raise ValueError('RÃ©fÃ©rence ou dÃ©signation manquante.')

            component = db.scalar(select(Component).where(Component.part_number == part_number_value))
            if component and component.workshop_id != active_workshop_id:
                raise ValueError('Reference deja existante dans un autre atelier.')
            if component and import_mode == 'create_only':
                results['skipped'] += 1
                continue
            if not component and import_mode == 'update_only':
                results['skipped'] += 1
                continue

            category = find_or_create_category_by_path(db, row_data.get('category_path'), create_missing_categories, active_workshop_id)
            manufacturer = find_or_create_named_item(db, Manufacturer, row_data.get('manufacturer_name'), create_missing_references, active_workshop_id)
            package = find_or_create_named_item(db, Package, row_data.get('package_name'), create_missing_references, active_workshop_id)
            location = find_or_create_named_item(db, Location, row_data.get('location_name'), create_missing_references, active_workshop_id)

            payload_data = {
                'part_number': part_number_value,
                'name': name_value,
                'workshop_id': active_workshop_id,
                'category_id': category.id if category else None,
                'manufacturer_id': manufacturer.id if manufacturer else None,
                'package_id': package.id if package else None,
                'location_id': location.id if location else None,
                'minimum_quantity': parse_int(row_data.get('minimum_quantity'), 0),
                'datasheet_url': row_data.get('datasheet_url') or None,
                'description': row_data.get('description') or None,
                'notes': row_data.get('notes') or None,
                'keywords': row_data.get('keywords') or None,
            }
            validate_component_reference_scope(db, payload_data)
            imported_quantity = parse_int(row_data.get('quantity'), 0)

            if component is None:
                component = Component(quantity=0)
                populate_component_from_form(component, payload_data)
                db.add(component)
                db.flush()
                if imported_quantity != 0:
                    add_stock_movement(
                        db=db,
                        component=component,
                        movement_type='import',
                        quantity_delta=imported_quantity,
                        reason='Import dâ€™articles',
                        source='import',
                        reference=payload['filename'],
                    )
                results['created'] += 1
            else:
                populate_component_from_form(component, payload_data)
                adjust_stock_to_quantity(
                    db=db,
                    component=component,
                    target_quantity=imported_quantity,
                    reason='Ajustement via import',
                    source='import',
                    reference=payload['filename'],
                )
                results['updated'] += 1
        except Exception as exc:  # noqa: BLE001 - summary wanted for end user
            db.rollback()
            results['errors'].append(f'Ligne {index}: {exc}')
            if len(results['errors']) >= 30:
                results['errors'].append('Trop dâ€™erreurs, journal tronquÃ©.')
                break
            continue

    db.commit()
    delete_import_session(token)
    return render(request, 'imports/components.html', {
        'preview': None,
        'token': '',
        'import_fields': IMPORT_FIELD_DEFINITIONS,
        'import_result': results,
    })
