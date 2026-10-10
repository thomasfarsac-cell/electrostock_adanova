from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.config import DATA_DIR
from app.db import get_db
from app.models import Category, Component, Location
from app.security.permissions import require_stock_write_access
from app.services.categories import build_category_path
from app.services.images import delete_relative_file, save_location_image
from app.services.location_form_helpers import (
    build_location_payload,
    populate_location_from_form,
    render_location_form_page,
    resolve_location_search_redirect,
)
from app.services.reference_helpers import location_name_exists
from app.services.workshop_scope import parse_workshop_choice, scoped_entity_or_404, scoped_query
from app.utils import parse_optional_int
from app.view_context import get_selected_workshop_id, render

router = APIRouter()


@router.get('/locations')
def list_locations(request: Request, search: str = '', db: Session = Depends(get_db)):
    search_value = search.strip()
    active_workshop_id = get_selected_workshop_id(request, db)
    if search_value:
        direct_url = resolve_location_search_redirect(db, search_value, active_workshop_id)
        if direct_url:
            return RedirectResponse(url=direct_url, status_code=302)

    query = scoped_query(select(Location), Location, active_workshop_id).options(selectinload(Location.components)).order_by(Location.name.asc())
    if search_value:
        term = f'%{search_value}%'
        query = query.where(or_(Location.name.ilike(term), Location.description.ilike(term)))

    locations = db.scalars(query).unique().all()
    return render(request, 'locations/list.html', {
        'locations': locations,
        'search': search_value,
        'total': len(locations),
    })


@router.get('/locations/new')
def new_location(request: Request, db: Session = Depends(get_db)):
    require_stock_write_access(request)
    return render_location_form_page(request, db, '/locations/new')


@router.post('/locations/new')
async def create_location_page(
    request: Request,
    name: str = Form(''),
    description: str = Form(''),
    workshop_id: str = Form(''),
    image: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    require_stock_write_access(request)
    payload = build_location_payload(name, description)
    location_state = {
        'name': payload['name'],
        'description': payload['description'],
        'workshop_id': parse_optional_int(workshop_id),
        'image_path': None,
        'thumbnail_path': None,
    }

    if not payload['name']:
        return render_location_form_page(
            request,
            db,
            '/locations/new',
            location_state,
            form_notice={'tone': 'danger', 'message': "Le nom de l'emplacement est obligatoire."},
            status_code=400,
        )

    selected_workshop_id = parse_workshop_choice(request, db, workshop_id)
    if location_name_exists(db, selected_workshop_id, payload['name']):
        return render_location_form_page(
            request,
            db,
            '/locations/new',
            location_state,
            form_notice={'tone': 'danger', 'message': 'Cet emplacement existe deja.'},
            status_code=400,
        )

    location = Location()
    populate_location_from_form(location, payload)
    location.workshop_id = selected_workshop_id
    if image and image.filename:
        image_path, thumbnail_path = save_location_image(image)
        location.image_path = image_path
        location.thumbnail_path = thumbnail_path
        location_state['image_path'] = image_path
        location_state['thumbnail_path'] = thumbnail_path

    db.add(location)
    db.commit()
    return RedirectResponse(url=f'/locations/{location.id}', status_code=303)


@router.get('/locations/{location_id}')
def location_detail(request: Request, location_id: int, db: Session = Depends(get_db)):
    location = db.scalar(
        select(Location)
        .where(Location.id == location_id)
        .options(
            selectinload(Location.components).joinedload(Component.category).joinedload(Category.parent),
            selectinload(Location.components).joinedload(Component.manufacturer),
            selectinload(Location.components).joinedload(Component.package),
        )
    )
    location = scoped_entity_or_404(request, db, location)

    components = sorted(
        location.components,
        key=lambda item: ((item.part_number or '').lower(), (item.name or '').lower()),
    )
    return render(request, 'locations/detail.html', {
        'location': location,
        'components': components,
        'build_category_path': build_category_path,
    })


@router.get('/locations/{location_id}/edit')
def edit_location(request: Request, location_id: int, db: Session = Depends(get_db)):
    require_stock_write_access(request)
    location = db.get(Location, location_id)
    location = scoped_entity_or_404(request, db, location)
    return render_location_form_page(
        request,
        db,
        f'/locations/{location.id}/edit',
        {
            'id': location.id,
            'name': location.name,
            'description': location.description,
            'workshop_id': location.workshop_id,
            'image_path': location.image_path,
            'thumbnail_path': location.thumbnail_path,
        },
    )


@router.post('/locations/{location_id}/edit')
async def update_location(
    request: Request,
    location_id: int,
    name: str = Form(''),
    description: str = Form(''),
    workshop_id: str = Form(''),
    replace_image: bool = Form(False),
    image: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    require_stock_write_access(request)
    location = db.get(Location, location_id)
    location = scoped_entity_or_404(request, db, location)

    payload = build_location_payload(name, description)
    location_state = {
        'id': location.id,
        'name': payload['name'],
        'description': payload['description'],
        'workshop_id': parse_optional_int(workshop_id) or location.workshop_id,
        'image_path': location.image_path,
        'thumbnail_path': location.thumbnail_path,
    }

    if not payload['name']:
        return render_location_form_page(
            request,
            db,
            f'/locations/{location.id}/edit',
            location_state,
            form_notice={'tone': 'danger', 'message': "Le nom de l'emplacement est obligatoire."},
            status_code=400,
        )

    selected_workshop_id = parse_workshop_choice(request, db, workshop_id or str(location.workshop_id or ''))
    if location_name_exists(db, selected_workshop_id, payload['name'], exclude_id=location.id):
        return render_location_form_page(
            request,
            db,
            f'/locations/{location.id}/edit',
            location_state,
            form_notice={'tone': 'danger', 'message': 'Un autre emplacement porte deja ce nom.'},
            status_code=400,
        )

    populate_location_from_form(location, payload)
    location.workshop_id = selected_workshop_id

    if replace_image and location.image_path:
        delete_relative_file(DATA_DIR, location.image_path)
        delete_relative_file(DATA_DIR, location.thumbnail_path)
        location.image_path = None
        location.thumbnail_path = None

    if image and image.filename:
        delete_relative_file(DATA_DIR, location.image_path)
        delete_relative_file(DATA_DIR, location.thumbnail_path)
        image_path, thumbnail_path = save_location_image(image)
        location.image_path = image_path
        location.thumbnail_path = thumbnail_path

    db.commit()
    return RedirectResponse(url=f'/locations/{location.id}', status_code=303)


@router.post('/locations/{location_id}/delete')
def delete_location_page(request: Request, location_id: int, db: Session = Depends(get_db)):
    require_stock_write_access(request)
    location = db.get(Location, location_id)
    location = scoped_entity_or_404(request, db, location)
    delete_relative_file(DATA_DIR, location.image_path)
    delete_relative_file(DATA_DIR, location.thumbnail_path)
    db.delete(location)
    db.commit()
    return RedirectResponse(url='/locations', status_code=303)
