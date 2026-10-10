from __future__ import annotations

from math import ceil

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.config import DATA_DIR
from app.db import get_db
from app.models import Category, Component, ComponentCustomFieldValue, CustomField, StockMovement, Workshop
from app.security.permissions import require_stock_write_access
from app.services.ai_component_lookup_v2 import is_ai_component_lookup_enabled
from app.services.categories import build_category_path
from app.services.category_helpers import get_category_chain_labels
from app.services.component_ai_helpers import (
    build_ai_lookup_notice,
    build_ai_lookup_response,
    merge_ai_component_state,
)
from app.services.component_form_context import get_reference_data
from app.services.component_form_helpers import (
    apply_custom_fields_from_form,
    build_component_payload,
    build_form_component_state,
    populate_component_from_form,
    render_component_form_page,
)
from app.services.component_label_presets import list_component_label_presets
from app.services.component_labels import get_default_label_config, get_field_options
from app.services.component_query_helpers import build_component_query, resolve_component_search_redirect
from app.services.export_helpers import export_components_csv, export_movements_csv
from app.services.images import delete_relative_file, save_component_image
from app.services.item_profiles import item_field_label, item_field_visible, merge_item_profile
from app.services.query_helpers import build_query_string
from app.services.reference_helpers import validate_component_reference_scope
from app.services.stock import add_stock_movement, adjust_stock_to_quantity
from app.services.workshop_scope import parse_workshop_choice, scoped_entity_or_404, scoped_query
from app.utils import parse_int, parse_optional_int
from app.view_context import get_selected_workshop, get_selected_workshop_id, render

router = APIRouter()

@router.get('/components')
def list_components(
    request: Request,
    page: int = 1,
    search: str = '',
    category_id: str = '',
    manufacturer_id: str = '',
    package_id: str = '',
    location_id: str = '',
    stock_status: str = '',
    qty_min: str = '',
    qty_max: str = '',
    db: Session = Depends(get_db),
):
    category_id_value = parse_optional_int(category_id)
    manufacturer_id_value = parse_optional_int(manufacturer_id)
    package_id_value = parse_optional_int(package_id)
    location_id_value = parse_optional_int(location_id)
    qty_min_value = parse_optional_int(qty_min)
    qty_max_value = parse_optional_int(qty_max)
    active_workshop_id = get_selected_workshop_id(request, db)

    has_secondary_filters = any([
        category_id_value,
        manufacturer_id_value,
        package_id_value,
        location_id_value,
        stock_status.strip(),
        qty_min_value is not None,
        qty_max_value is not None,
    ])

    if search.strip() and not has_secondary_filters:
        redirect_url = resolve_component_search_redirect(db, search, active_workshop_id)
        if redirect_url:
            return RedirectResponse(url=redirect_url, status_code=302)

    page_size = 20
    query = build_component_query(
        db=db,
        search=search,
        workshop_id=active_workshop_id,
        category_id=category_id_value,
        manufacturer_id=manufacturer_id_value,
        package_id=package_id_value,
        location_id=location_id_value,
        stock_status=stock_status,
        qty_min=qty_min_value,
        qty_max=qty_max_value,
    )

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    pages = max(1, ceil(total / page_size))
    page = max(1, min(page, pages))
    items = db.scalars(
        query.order_by(Component.updated_at.desc(), Component.name.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).unique().all()

    refs = get_reference_data(db, active_workshop_id)
    label_workshop = get_selected_workshop(request, db) if active_workshop_id is not None else None
    item_profile = merge_item_profile(label_workshop)
    filters = {
        'search': search,
        'category_id': category_id_value or '',
        'manufacturer_id': manufacturer_id_value or '',
        'package_id': package_id_value or '',
        'location_id': location_id_value or '',
        'stock_status': stock_status,
        'qty_min': qty_min_value if qty_min_value is not None else '',
        'qty_max': qty_max_value if qty_max_value is not None else '',
    }
    return render(request, 'components/list.html', {
        'components': items,
        'page': page,
        'pages': pages,
        'total': total,
        'filters': filters,
        'export_query_string': build_query_string(filters),
        'component_label_defaults': get_default_label_config(),
        'component_label_fields': get_field_options(),
        'component_label_presets': list_component_label_presets(),
        'component_label_current_page_ids': [item.id for item in items],
        'build_category_path': build_category_path,
        'category_level_labels': get_category_chain_labels(refs['categories'], category_id_value),
        'item_profile': item_profile,
        'item_field_label': item_field_label,
        **refs,
    })

@router.get('/components/export.csv')
def export_components(
    request: Request,
    search: str = '',
    category_id: str = '',
    manufacturer_id: str = '',
    package_id: str = '',
    location_id: str = '',
    stock_status: str = '',
    qty_min: str = '',
    qty_max: str = '',
    db: Session = Depends(get_db),
):
    active_workshop_id = get_selected_workshop_id(request, db)
    query = build_component_query(
        db=db,
        search=search,
        workshop_id=active_workshop_id,
        category_id=parse_optional_int(category_id),
        manufacturer_id=parse_optional_int(manufacturer_id),
        package_id=parse_optional_int(package_id),
        location_id=parse_optional_int(location_id),
        stock_status=stock_status,
        qty_min=parse_optional_int(qty_min),
        qty_max=parse_optional_int(qty_max),
    )
    items = db.scalars(query.order_by(Component.part_number.asc())).unique().all()
    return export_components_csv('composants.csv', items)


@router.get('/components/new')
def new_component(request: Request, db: Session = Depends(get_db)):
    require_stock_write_access(request)
    return render_component_form_page(request, db, '/components/new', None, {})


@router.post('/components/new')
async def create_component(
    request: Request,
    part_number: str = Form(''),
    name: str = Form(''),
    category_id: str = Form(''),
    manufacturer_id: str = Form(''),
    package_id: str = Form(''),
    location_id: str = Form(''),
    workshop_id: str = Form(''),
    quantity: str = Form('0'),
    minimum_quantity: str = Form('0'),
    datasheet_url: str = Form(''),
    description: str = Form(''),
    notes: str = Form(''),
    keywords: str = Form(''),
    form_action: str = Form('save'),
    image: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    require_stock_write_access(request)
    form = await request.form()
    component_state = build_form_component_state(
        part_number=part_number,
        name=name,
        category_id=category_id,
        manufacturer_id=manufacturer_id,
        package_id=package_id,
        location_id=location_id,
        workshop_id=workshop_id,
        quantity=quantity,
        minimum_quantity=minimum_quantity,
        datasheet_url=datasheet_url,
        description=description,
        notes=notes,
        keywords=keywords,
    )
    component_state['workshop_id'] = parse_workshop_choice(request, db, workshop_id) if form_action != 'ai_lookup' else parse_optional_int(workshop_id)
    form_workshop_id = component_state.get('workshop_id') or get_selected_workshop_id(request, db)
    active_fields = db.scalars(
        scoped_query(select(CustomField).where(CustomField.is_active.is_(True)), CustomField, form_workshop_id)
    ).all()
    custom_values = {field.id: str(form.get(f'custom_{field.id}', '')).strip() for field in active_fields}

    if form_action == 'ai_lookup':
        if not part_number.strip():
            return render_component_form_page(
                request,
                db,
                '/components/new',
                component_state,
                custom_values,
                ai_lookup_notice={'tone': 'warning', 'message': 'Saisis une reference avant de lancer la recherche IA.'},
                status_code=400,
            )
        try:
            ai_payload = build_ai_lookup_response(db, part_number.strip(), form_workshop_id)
        except RuntimeError as exc:
            return render_component_form_page(
                request,
                db,
                '/components/new',
                component_state,
                custom_values,
                ai_lookup_notice={'tone': 'danger', 'message': str(exc)},
                status_code=502,
            )

        merged_state = merge_ai_component_state(component_state, ai_payload)
        for item in ai_payload.get('component', {}).get('custom_fields', []):
            custom_values[item['id']] = item['value']
        return render_component_form_page(
            request,
            db,
            '/components/new',
            merged_state,
            custom_values,
            ai_lookup_notice=build_ai_lookup_notice(ai_payload),
        )

    payload = build_component_payload(
        part_number=part_number,
        name=name,
        category_id_raw=category_id,
        manufacturer_id_raw=manufacturer_id,
        package_id_raw=package_id,
        location_id_raw=location_id,
        workshop_id_raw=str(component_state.get('workshop_id') or ''),
        minimum_quantity_raw=minimum_quantity,
        datasheet_url=datasheet_url,
        description=description,
        notes=notes,
        keywords=keywords,
    )
    initial_quantity = parse_int(quantity, 0)

    if not payload['part_number'] or not payload['name']:
        raise HTTPException(status_code=400, detail='Référence et désignation obligatoires.')
    validate_component_reference_scope(db, payload)

    existing = db.scalar(select(Component).where(Component.part_number == payload['part_number']))
    if existing:
        raise HTTPException(status_code=400, detail='Cette référence existe déjà.')

    component = Component(quantity=0)
    populate_component_from_form(component, payload)
    if image and image.filename:
        image_path, thumbnail_path = save_component_image(image)
        component.image_path = image_path
        component.thumbnail_path = thumbnail_path

    db.add(component)
    db.flush()

    apply_custom_fields_from_form(db, component, form, active_fields)

    if initial_quantity != 0:
        add_stock_movement(
            db=db,
            component=component,
            movement_type='initial',
            quantity_delta=initial_quantity,
            reason='Création de l’article',
            source='manual',
        )

    db.commit()
    return RedirectResponse(url=f'/components/{component.id}', status_code=303)


@router.get('/components/{component_id}')
def component_detail(request: Request, component_id: int, db: Session = Depends(get_db)):
    component = db.scalar(
        select(Component)
        .where(Component.id == component_id)
        .options(
            joinedload(Component.category).joinedload(Category.parent),
            joinedload(Component.manufacturer),
            joinedload(Component.package),
            joinedload(Component.location),
            selectinload(Component.custom_values).joinedload(ComponentCustomFieldValue.custom_field),
            selectinload(Component.stock_movements),
        )
    )
    component = scoped_entity_or_404(request, db, component)
    movements = db.scalars(
        select(StockMovement)
        .where(StockMovement.component_id == component.id)
        .order_by(StockMovement.created_at.desc(), StockMovement.id.desc())
        .limit(30)
    ).all()
    return render(request, 'components/detail.html', {
        'component': component,
        'movements': movements,
        'build_category_path': build_category_path,
        'item_profile': merge_item_profile(component.workshop),
        'item_field_label': item_field_label,
        'item_field_visible': item_field_visible,
    })


@router.get('/components/{component_id}/movements/export.csv')
def export_component_movements(request: Request, component_id: int, db: Session = Depends(get_db)):
    component = db.get(Component, component_id)
    component = scoped_entity_or_404(request, db, component)
    movements = db.scalars(
        select(StockMovement)
        .where(StockMovement.component_id == component_id)
        .options(joinedload(StockMovement.component))
        .order_by(StockMovement.created_at.desc(), StockMovement.id.desc())
    ).all()
    filename = f'mouvements_{component.part_number}.csv'
    return export_movements_csv(filename, movements)


@router.post('/components/{component_id}/movements/new')
def create_stock_movement_route(
    request: Request,
    component_id: int,
    movement_action: str = Form(...),
    quantity: str = Form('0'),
    reason: str = Form(''),
    notes: str = Form(''),
    db: Session = Depends(get_db),
):
    require_stock_write_access(request)
    component = db.get(Component, component_id)
    component = scoped_entity_or_404(request, db, component)

    amount = abs(parse_int(quantity, 0))
    if amount <= 0:
        raise HTTPException(status_code=400, detail='Quantité invalide.')

    if movement_action == 'in':
        add_stock_movement(db, component, 'in', amount, reason or 'Entrée de stock', notes, 'manual')
    elif movement_action == 'out':
        if component.quantity - amount < 0:
            raise HTTPException(status_code=400, detail='Stock insuffisant pour cette sortie.')
        add_stock_movement(db, component, 'out', -amount, reason or 'Sortie de stock', notes, 'manual')
    elif movement_action == 'set':
        adjust_stock_to_quantity(db, component, amount, reason or 'Inventaire / correction', notes, 'manual')
    else:
        raise HTTPException(status_code=400, detail='Type de mouvement invalide.')

    db.commit()
    return RedirectResponse(url=f'/components/{component_id}', status_code=303)


@router.get('/components/{component_id}/edit')
def edit_component(request: Request, component_id: int, db: Session = Depends(get_db)):
    require_stock_write_access(request)
    component = db.scalar(
        select(Component)
        .where(Component.id == component_id)
        .options(selectinload(Component.custom_values), joinedload(Component.category).joinedload(Category.parent))
    )
    component = scoped_entity_or_404(request, db, component)
    custom_values = {item.custom_field_id: item.value for item in component.custom_values}
    return render_component_form_page(
        request,
        db,
        f'/components/{component_id}/edit',
        {
            'id': component.id,
            'part_number': component.part_number,
            'name': component.name,
            'workshop_id': component.workshop_id,
            'category_id': component.category_id,
            'manufacturer_id': component.manufacturer_id,
            'package_id': component.package_id,
            'location_id': component.location_id,
            'quantity': component.quantity,
            'minimum_quantity': component.minimum_quantity,
            'datasheet_url': component.datasheet_url,
            'description': component.description,
            'notes': component.notes,
            'keywords': component.keywords,
            'image_path': component.image_path,
            'thumbnail_path': component.thumbnail_path,
        },
        custom_values,
    )


@router.post('/components/ai-lookup')
async def ai_lookup_component(
    request: Request,
    part_number: str = Form(...),
    db: Session = Depends(get_db),
):
    require_stock_write_access(request)
    normalized = part_number.strip()
    if not normalized:
        return JSONResponse({'detail': 'La reference est obligatoire.'}, status_code=400)
    if not is_ai_component_lookup_enabled():
        return JSONResponse(
            {'detail': "La recherche IA n'est pas configuree. Ajoutez OPENAI_API_KEY dans le .env."},
            status_code=400,
        )
    try:
        payload = build_ai_lookup_response(db, normalized, get_selected_workshop_id(request, db))
    except RuntimeError as exc:
        return JSONResponse({'detail': str(exc)}, status_code=502)
    return JSONResponse(payload)


@router.post('/components/{component_id}/edit')
async def update_component(
    request: Request,
    component_id: int,
    part_number: str = Form(''),
    name: str = Form(''),
    category_id: str = Form(''),
    manufacturer_id: str = Form(''),
    package_id: str = Form(''),
    location_id: str = Form(''),
    workshop_id: str = Form(''),
    quantity: str = Form('0'),
    minimum_quantity: str = Form('0'),
    datasheet_url: str = Form(''),
    description: str = Form(''),
    notes: str = Form(''),
    keywords: str = Form(''),
    form_action: str = Form('save'),
    replace_image: bool = Form(False),
    image: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    require_stock_write_access(request)
    component = db.get(Component, component_id)
    component = scoped_entity_or_404(request, db, component)

    form = await request.form()
    component_state = build_form_component_state(
        part_number=part_number,
        name=name,
        category_id=category_id,
        manufacturer_id=manufacturer_id,
        package_id=package_id,
        location_id=location_id,
        workshop_id=workshop_id or str(component.workshop_id or ''),
        quantity=quantity,
        minimum_quantity=minimum_quantity,
        datasheet_url=datasheet_url,
        description=description,
        notes=notes,
        keywords=keywords,
        image_path=component.image_path,
        thumbnail_path=component.thumbnail_path,
    )
    component_state['id'] = component.id
    component_state['workshop_id'] = parse_workshop_choice(request, db, workshop_id) if form_action != 'ai_lookup' else parse_optional_int(workshop_id) or component.workshop_id
    form_workshop_id = component_state.get('workshop_id') or get_selected_workshop_id(request, db)
    active_fields = db.scalars(
        scoped_query(select(CustomField).where(CustomField.is_active.is_(True)), CustomField, form_workshop_id)
    ).all()
    custom_values = {field.id: str(form.get(f'custom_{field.id}', '')).strip() for field in active_fields}
    profile_workshop = db.get(Workshop, component_state['workshop_id']) if component_state.get('workshop_id') else component.workshop
    item_profile = merge_item_profile(profile_workshop)
    if not item_field_visible(item_profile, 'part_number'):
        part_number = component.part_number
        component_state['part_number'] = component.part_number
    if not item_field_visible(item_profile, 'manufacturer'):
        manufacturer_id = str(component.manufacturer_id or '')
        component_state['manufacturer_id'] = component.manufacturer_id
    if not item_field_visible(item_profile, 'package'):
        package_id = str(component.package_id or '')
        component_state['package_id'] = component.package_id
    if not item_field_visible(item_profile, 'minimum_quantity'):
        minimum_quantity = str(component.minimum_quantity or 0)
        component_state['minimum_quantity'] = component.minimum_quantity
    if not item_field_visible(item_profile, 'datasheet_url'):
        datasheet_url = component.datasheet_url or ''
        component_state['datasheet_url'] = component.datasheet_url
    if not item_field_visible(item_profile, 'keywords'):
        keywords = component.keywords or ''
        component_state['keywords'] = component.keywords
    if not item_field_visible(item_profile, 'description'):
        description = component.description or ''
        component_state['description'] = component.description
    if not item_field_visible(item_profile, 'notes'):
        notes = component.notes or ''
        component_state['notes'] = component.notes

    if form_action == 'ai_lookup':
        if not part_number.strip():
            return render_component_form_page(
                request,
                db,
                f'/components/{component_id}/edit',
                component_state,
                custom_values,
                ai_lookup_notice={'tone': 'warning', 'message': 'Saisis une reference avant de lancer la recherche IA.'},
                status_code=400,
            )
        try:
            ai_payload = build_ai_lookup_response(db, part_number.strip(), form_workshop_id)
        except RuntimeError as exc:
            return render_component_form_page(
                request,
                db,
                f'/components/{component_id}/edit',
                component_state,
                custom_values,
                ai_lookup_notice={'tone': 'danger', 'message': str(exc)},
                status_code=502,
            )

        merged_state = merge_ai_component_state(component_state, ai_payload)
        merged_state['id'] = component.id
        for item in ai_payload.get('component', {}).get('custom_fields', []):
            custom_values[item['id']] = item['value']
        return render_component_form_page(
            request,
            db,
            f'/components/{component_id}/edit',
            merged_state,
            custom_values,
            ai_lookup_notice=build_ai_lookup_notice(ai_payload),
        )

    payload = build_component_payload(
        part_number=part_number,
        name=name,
        category_id_raw=category_id,
        manufacturer_id_raw=manufacturer_id,
        package_id_raw=package_id,
        location_id_raw=location_id,
        workshop_id_raw=str(component_state.get('workshop_id') or ''),
        minimum_quantity_raw=minimum_quantity,
        datasheet_url=datasheet_url,
        description=description,
        notes=notes,
        keywords=keywords,
    )
    target_quantity = parse_int(quantity, 0)
    validate_component_reference_scope(db, payload)

    conflict = db.scalar(select(Component).where(Component.part_number == payload['part_number'], Component.id != component_id))
    if conflict:
        raise HTTPException(status_code=400, detail='Cette référence existe déjà.')

    populate_component_from_form(component, payload)

    if replace_image and component.image_path:
        delete_relative_file(DATA_DIR, component.image_path)
        delete_relative_file(DATA_DIR, component.thumbnail_path)
        component.image_path = None
        component.thumbnail_path = None

    if image and image.filename:
        delete_relative_file(DATA_DIR, component.image_path)
        delete_relative_file(DATA_DIR, component.thumbnail_path)
        image_path, thumbnail_path = save_component_image(image)
        component.image_path = image_path
        component.thumbnail_path = thumbnail_path

    apply_custom_fields_from_form(db, component, form, active_fields)

    adjust_stock_to_quantity(
        db,
        component,
        target_quantity,
        reason='Ajustement depuis la fiche article',
        source='manual',
    )

    db.commit()
    return RedirectResponse(url=f'/components/{component.id}', status_code=303)


@router.post('/components/{component_id}/delete')
def delete_component(request: Request, component_id: int, db: Session = Depends(get_db)):
    require_stock_write_access(request)
    component = db.get(Component, component_id)
    component = scoped_entity_or_404(request, db, component)
    delete_relative_file(DATA_DIR, component.image_path)
    delete_relative_file(DATA_DIR, component.thumbnail_path)
    db.delete(component)
    db.commit()
    return RedirectResponse(url='/components', status_code=303)
