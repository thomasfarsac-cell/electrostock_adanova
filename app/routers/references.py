from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import DATA_DIR
from app.db import get_db
from app.models import CustomField, Location, Manufacturer, Package
from app.security.permissions import require_stock_write_access
from app.services.images import delete_relative_file
from app.services.reference_helpers import (
    custom_field_name_or_slug_exists,
    location_name_exists,
    named_reference_exists,
)
from app.services.workshop_scope import parse_workshop_choice, scoped_entity_or_404, scoped_query
from app.utils import parse_int, slugify
from app.view_context import get_selected_workshop_id, list_active_workshops, render

router = APIRouter()


@router.get('/references')
def references_page(request: Request, db: Session = Depends(get_db)):
    active_workshop_id = get_selected_workshop_id(request, db)
    manufacturers = db.scalars(
        scoped_query(select(Manufacturer), Manufacturer, active_workshop_id)
        .order_by(Manufacturer.name)
    ).all()
    packages = db.scalars(
        scoped_query(select(Package), Package, active_workshop_id)
        .order_by(Package.name)
    ).all()
    custom_fields = db.scalars(
        scoped_query(select(CustomField), CustomField, active_workshop_id)
        .order_by(CustomField.sort_order, CustomField.name)
    ).all()
    return render(request, 'admin/references.html', {
        'manufacturers': manufacturers,
        'packages': packages,
        'custom_fields': custom_fields,
        'workshops': list_active_workshops(db),
    })


@router.post('/references/manufacturers/new')
def create_manufacturer(
    request: Request,
    name: str = Form(...),
    website_url: str = Form(''),
    notes: str = Form(''),
    workshop_id: str = Form(''),
    db: Session = Depends(get_db),
):
    require_stock_write_access(request)
    selected_workshop_id = parse_workshop_choice(request, db, workshop_id)
    if named_reference_exists(db, Manufacturer, selected_workshop_id, name):
        raise HTTPException(status_code=400, detail='Cette marque / fabricant existe deja dans cet atelier.')
    item = Manufacturer(name=name.strip(), workshop_id=selected_workshop_id, website_url=website_url.strip() or None, notes=notes.strip() or None)
    try:
        db.add(item)
        db.commit()
    except IntegrityError:
        db.rollback()
    return RedirectResponse(url='/references', status_code=303)


@router.post('/references/manufacturers/{item_id}/delete')
def delete_manufacturer(request: Request, item_id: int, db: Session = Depends(get_db)):
    require_stock_write_access(request)
    item = db.get(Manufacturer, item_id)
    item = scoped_entity_or_404(request, db, item)
    if item:
        try:
            db.delete(item)
            db.commit()
        except IntegrityError:
            db.rollback()
    return RedirectResponse(url='/references', status_code=303)


@router.post('/references/packages/new')
def create_package(
    request: Request,
    name: str = Form(...),
    description: str = Form(''),
    workshop_id: str = Form(''),
    db: Session = Depends(get_db),
):
    require_stock_write_access(request)
    selected_workshop_id = parse_workshop_choice(request, db, workshop_id)
    if named_reference_exists(db, Package, selected_workshop_id, name):
        raise HTTPException(status_code=400, detail='Ce format / conditionnement existe deja dans cet atelier.')
    item = Package(name=name.strip(), workshop_id=selected_workshop_id, description=description.strip() or None)
    try:
        db.add(item)
        db.commit()
    except IntegrityError:
        db.rollback()
    return RedirectResponse(url='/references', status_code=303)


@router.post('/references/packages/{item_id}/delete')
def delete_package(request: Request, item_id: int, db: Session = Depends(get_db)):
    require_stock_write_access(request)
    item = db.get(Package, item_id)
    item = scoped_entity_or_404(request, db, item)
    if item:
        try:
            db.delete(item)
            db.commit()
        except IntegrityError:
            db.rollback()
    return RedirectResponse(url='/references', status_code=303)


@router.post('/references/locations/new')
def create_location(request: Request, name: str = Form(...), description: str = Form(''), workshop_id: str = Form(''), db: Session = Depends(get_db)):
    require_stock_write_access(request)
    selected_workshop_id = parse_workshop_choice(request, db, workshop_id)
    if location_name_exists(db, selected_workshop_id, name):
        return RedirectResponse(url='/locations?notice=Emplacement%20deja%20existant', status_code=303)
    item = Location(name=name.strip(), description=description.strip() or None, workshop_id=selected_workshop_id)
    try:
        db.add(item)
        db.commit()
        return RedirectResponse(url=f'/locations/{item.id}', status_code=303)
    except IntegrityError:
        db.rollback()
    return RedirectResponse(url='/locations', status_code=303)


@router.post('/references/locations/{item_id}/delete')
def delete_location(request: Request, item_id: int, db: Session = Depends(get_db)):
    require_stock_write_access(request)
    item = db.get(Location, item_id)
    item = scoped_entity_or_404(request, db, item)
    if item:
        try:
            delete_relative_file(DATA_DIR, item.image_path)
            delete_relative_file(DATA_DIR, item.thumbnail_path)
            db.delete(item)
            db.commit()
        except IntegrityError:
            db.rollback()
    return RedirectResponse(url='/locations', status_code=303)


@router.post('/references/custom-fields/new')
def create_custom_field(
    request: Request,
    name: str = Form(...),
    field_type: str = Form('text'),
    unit: str = Form(''),
    sort_order: str = Form('0'),
    workshop_id: str = Form(''),
    db: Session = Depends(get_db),
):
    require_stock_write_access(request)
    selected_workshop_id = parse_workshop_choice(request, db, workshop_id)
    slug_base = slugify(name)
    slug = slug_base
    index = 2
    while db.scalar(select(CustomField).where(CustomField.workshop_id == selected_workshop_id, func.lower(CustomField.slug) == slug.lower())):
        slug = f'{slug_base}-{index}'
        index += 1
    if custom_field_name_or_slug_exists(db, selected_workshop_id, name, slug):
        raise HTTPException(status_code=400, detail='Ce champ personnalise existe deja dans cet atelier.')
    db.add(CustomField(
        name=name.strip(),
        workshop_id=selected_workshop_id,
        slug=slug,
        field_type=field_type,
        unit=unit.strip() or None,
        sort_order=parse_int(sort_order, 0),
    ))
    db.commit()
    return RedirectResponse(url='/references', status_code=303)


@router.post('/references/custom-fields/{item_id}/toggle')
def toggle_custom_field(request: Request, item_id: int, db: Session = Depends(get_db)):
    require_stock_write_access(request)
    item = db.get(CustomField, item_id)
    item = scoped_entity_or_404(request, db, item)
    if item:
        item.is_active = not item.is_active
        db.commit()
    return RedirectResponse(url='/references', status_code=303)


@router.post('/references/custom-fields/{item_id}/delete')
def delete_custom_field(request: Request, item_id: int, db: Session = Depends(get_db)):
    require_stock_write_access(request)
    item = db.get(CustomField, item_id)
    item = scoped_entity_or_404(request, db, item)
    if item:
        db.delete(item)
        db.commit()
    return RedirectResponse(url='/references', status_code=303)
