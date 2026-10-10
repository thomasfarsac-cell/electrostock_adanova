from __future__ import annotations

import json
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import SESSION_MAX_AGE_SECONDS, get_current_user
from app.db import get_db
from app.models import Category, Component, CustomField, Location, User, Workshop
from app.security.permissions import require_admin_access
from app.services.item_profiles import (
    ITEM_PROFILE_TEMPLATES,
    ITEM_PROFILE_TEMPLATE_OPTIONS,
    build_item_profile_from_form,
    item_profile_settings_rows,
    merge_item_profile,
)
from app.services.notice_helpers import users_notice
from app.utils import parse_int, parse_optional_int, slugify
from app.view_context import WORKSHOP_COOKIE_NAME, get_selected_workshop, render

router = APIRouter()


@router.post('/workshops/select')
def select_workshop(request: Request, workshop_id: str = Form('all'), db: Session = Depends(get_db)):
    selected = (workshop_id or 'all').strip()
    if selected != 'all':
        selected_id = parse_optional_int(selected)
        workshop = db.get(Workshop, selected_id) if selected_id else None
        if not workshop or not workshop.is_active:
            raise HTTPException(status_code=400, detail='Atelier invalide.')
        selected = str(workshop.id)

    current_user = get_current_user(request)
    if current_user:
        user = db.get(User, current_user.id)
        if user:
            user.active_workshop_id = None if selected == 'all' else int(selected)
            db.commit()

    response = RedirectResponse(url=request.headers.get('referer') or '/', status_code=303)
    response.set_cookie(WORKSHOP_COOKIE_NAME, selected, max_age=SESSION_MAX_AGE_SECONDS, httponly=True, samesite='lax')
    return response


@router.get('/admin/workshops')
def workshops_page(request: Request, db: Session = Depends(get_db), notice: str = '', tone: str = 'success'):
    require_admin_access(request)
    workshops = db.scalars(select(Workshop).order_by(Workshop.sort_order.asc(), Workshop.name.asc())).all()
    return render(request, 'admin/workshops.html', {
        'workshops': workshops,
        'workshop_notice': users_notice(tone, notice) if notice else None,
    })


@router.post('/admin/workshops/new')
def create_workshop(
    request: Request,
    name: str = Form(...),
    slug: str = Form(''),
    description: str = Form(''),
    sort_order: str = Form('0'),
    ai_prompt: str = Form(''),
    is_active: bool = Form(False),
    db: Session = Depends(get_db),
):
    require_admin_access(request)
    slug_value = slugify(slug or name)
    if not slug_value:
        raise HTTPException(status_code=400, detail='Slug atelier invalide.')
    workshop = Workshop(
        name=name.strip(),
        slug=slug_value,
        description=description.strip() or None,
        sort_order=parse_int(sort_order, 0),
        is_active=bool(is_active),
        ai_prompt=ai_prompt.strip() or None,
    )
    try:
        db.add(workshop)
        db.commit()
    except IntegrityError:
        db.rollback()
        return RedirectResponse(url='/admin/workshops?notice=Slug%20atelier%20deja%20utilise&tone=danger', status_code=303)
    return RedirectResponse(url='/admin/workshops?notice=Atelier%20cree', status_code=303)


@router.post('/admin/workshops/{workshop_id}/edit')
def update_workshop(
    request: Request,
    workshop_id: int,
    name: str = Form(...),
    description: str = Form(''),
    sort_order: str = Form('0'),
    ai_prompt: str = Form(''),
    is_active: bool = Form(False),
    db: Session = Depends(get_db),
):
    require_admin_access(request)
    workshop = db.get(Workshop, workshop_id)
    if not workshop:
        raise HTTPException(status_code=404)
    workshop.name = name.strip()
    workshop.description = description.strip() or None
    workshop.sort_order = parse_int(sort_order, 0)
    workshop.is_active = bool(is_active)
    workshop.ai_prompt = ai_prompt.strip() or None
    db.commit()
    return RedirectResponse(url='/admin/workshops?notice=Atelier%20mis%20a%20jour', status_code=303)


@router.post('/admin/workshops/{workshop_id}/delete')
def delete_workshop(request: Request, workshop_id: int, db: Session = Depends(get_db)):
    require_admin_access(request)
    workshop = db.get(Workshop, workshop_id)
    if not workshop:
        raise HTTPException(status_code=404)
    blockers = {
        'composants': db.scalar(select(func.count(Component.id)).where(Component.workshop_id == workshop.id)) or 0,
        'categories': db.scalar(select(func.count(Category.id)).where(Category.workshop_id == workshop.id)) or 0,
        'emplacements': db.scalar(select(func.count(Location.id)).where(Location.workshop_id == workshop.id)) or 0,
        'champs personnalises': db.scalar(select(func.count(CustomField.id)).where(CustomField.workshop_id == workshop.id)) or 0,
    }
    used = [f'{name}: {count}' for name, count in blockers.items() if count]
    if used:
        message = quote('Suppression impossible, atelier utilise (' + ', '.join(used) + ').')
        return RedirectResponse(url=f'/admin/workshops?notice={message}&tone=danger', status_code=303)
    db.delete(workshop)
    db.commit()
    return RedirectResponse(url='/admin/workshops?notice=Atelier%20supprime', status_code=303)


@router.get('/workshops/settings')
def current_workshop_settings(request: Request, db: Session = Depends(get_db)):
    require_admin_access(request)
    workshop = get_selected_workshop(request, db)
    if not workshop:
        return RedirectResponse(url='/admin/workshops?notice=Choisis%20un%20atelier%20specifique%20pour%20ouvrir%20ses%20parametres&tone=danger', status_code=303)
    item_profile = merge_item_profile(workshop)
    return render(request, 'admin/workshop_settings.html', {
        'workshop': workshop,
        'item_profile_fields': item_profile_settings_rows(item_profile),
        'item_profile_template_options': ITEM_PROFILE_TEMPLATE_OPTIONS,
        'current_item_profile_template': item_profile.get('template') or 'custom',
        'item_profile_template_data': ITEM_PROFILE_TEMPLATES,
    })


@router.post('/workshops/settings')
async def update_current_workshop_settings(
    request: Request,
    name: str = Form(...),
    description: str = Form(''),
    sort_order: str = Form('0'),
    ai_prompt: str = Form(''),
    is_active: bool = Form(False),
    db: Session = Depends(get_db),
):
    require_admin_access(request)
    workshop = get_selected_workshop(request, db)
    if not workshop:
        raise HTTPException(status_code=400, detail='Choisis un atelier specifique.')
    form = await request.form()
    workshop.name = name.strip()
    workshop.description = description.strip() or None
    workshop.sort_order = parse_int(sort_order, 0)
    workshop.ai_prompt = ai_prompt.strip() or None
    workshop.is_active = bool(is_active)
    workshop.item_profile_json = json.dumps(build_item_profile_from_form(form), ensure_ascii=False, sort_keys=True)
    db.commit()
    return RedirectResponse(url='/workshops/settings', status_code=303)
