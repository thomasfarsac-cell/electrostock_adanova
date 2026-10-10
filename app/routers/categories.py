from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.db import get_db
from app.models import Category, Component
from app.security.permissions import require_stock_write_access
from app.services.categories import build_category_path, validate_parent_depth
from app.services.category_helpers import (
    get_category_chain_ids,
    get_category_chain_labels,
    get_category_children_map,
    get_descendants_for_cycle_check,
)
from app.services.reference_helpers import category_name_exists
from app.services.workshop_scope import parse_workshop_choice, scoped_entity_or_404, scoped_query
from app.utils import group_categories, parse_int, parse_optional_int
from app.view_context import get_selected_workshop_id, list_active_workshops, render

router = APIRouter()


@router.get('/categories')
def categories_page(request: Request, db: Session = Depends(get_db)):
    active_workshop_id = get_selected_workshop_id(request, db)
    categories = db.scalars(
        scoped_query(select(Category), Category, active_workshop_id)
        .options(joinedload(Category.parent), selectinload(Category.children))
        .order_by(Category.sort_order, Category.name)
    ).unique().all()
    grouped = group_categories(categories)
    return render(request, 'admin/categories.html', {
        'categories': categories,
        'grouped_categories': grouped,
        'build_category_path': build_category_path,
        'category_children_map': get_category_children_map(categories),
        'category_level_labels': get_category_chain_labels(categories),
        'edit_chain_map_json': json.dumps({str(category.id): get_category_chain_ids(category)[:-1] for category in categories}),
        'workshops': list_active_workshops(db),
    })


@router.post('/categories/new')
def create_category(
    request: Request,
    name: str = Form(...),
    parent_id: str = Form(''),
    workshop_id: str = Form(''),
    sort_order: str = Form('0'),
    db: Session = Depends(get_db),
):
    require_stock_write_access(request)
    parent_id_value = parse_optional_int(parent_id)
    parent = db.get(Category, parent_id_value) if parent_id_value else None
    validate_parent_depth(parent)
    selected_workshop_id = parse_workshop_choice(request, db, workshop_id)
    if parent and parent.workshop_id != selected_workshop_id:
        raise HTTPException(status_code=400, detail='Parent hors atelier.')
    if category_name_exists(db, selected_workshop_id, parent_id_value, name):
        raise HTTPException(status_code=400, detail='Cette categorie existe deja dans ce niveau de cet atelier.')
    db.add(Category(name=name.strip(), workshop_id=selected_workshop_id, parent_id=parent_id_value, sort_order=parse_int(sort_order, 0)))
    db.commit()
    return RedirectResponse(url='/categories', status_code=303)


@router.post('/categories/{category_id}/edit')
def update_category(
    request: Request,
    category_id: int,
    name: str = Form(...),
    parent_id: str = Form(''),
    sort_order: str = Form('0'),
    is_active: bool = Form(False),
    db: Session = Depends(get_db),
):
    require_stock_write_access(request)
    category = db.get(Category, category_id)
    category = scoped_entity_or_404(request, db, category)
    parent_id_value = parse_optional_int(parent_id)
    parent = db.get(Category, parent_id_value) if parent_id_value else None
    if parent and parent.id == category.id:
        raise HTTPException(status_code=400, detail='Une catÃ©gorie ne peut pas Ãªtre son propre parent.')
    if parent and parent.id in get_descendants_for_cycle_check(category):
        raise HTTPException(status_code=400, detail='Parent invalide : boucle dÃ©tectÃ©e.')
    validate_parent_depth(parent)
    if parent and parent.workshop_id != category.workshop_id:
        raise HTTPException(status_code=400, detail='Parent hors atelier.')
    if category_name_exists(db, category.workshop_id, parent_id_value, name, exclude_id=category.id):
        raise HTTPException(status_code=400, detail='Cette categorie existe deja dans ce niveau de cet atelier.')
    category.name = name.strip()
    category.parent_id = parent_id_value
    category.sort_order = parse_int(sort_order, 0)
    category.is_active = bool(is_active)
    db.commit()
    return RedirectResponse(url='/categories', status_code=303)


@router.post('/categories/{category_id}/delete')
def delete_category(request: Request, category_id: int, db: Session = Depends(get_db)):
    require_stock_write_access(request)
    category = db.get(Category, category_id)
    category = scoped_entity_or_404(request, db, category)
    has_children = db.scalar(select(func.count(Category.id)).where(Category.parent_id == category_id)) or 0
    has_components = db.scalar(select(func.count(Component.id)).where(Component.category_id == category_id)) or 0
    if has_children or has_components:
        raise HTTPException(status_code=400, detail='Suppression impossible : catÃ©gorie utilisÃ©e ou avec enfants.')
    db.delete(category)
    db.commit()
    return RedirectResponse(url='/categories', status_code=303)
