from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.auth import hash_password
from app.db import get_db
from app.models import User
from app.security.permissions import require_admin_access
from app.services.notice_helpers import users_notice
from app.services.user_admin_helpers import VALID_ROLES, active_admin_count, would_remove_last_active_admin
from app.view_context import render, theme_label

router = APIRouter()


@router.get('/admin/users')
def users_page(request: Request, db: Session = Depends(get_db), notice: str = '', tone: str = 'success'):
    require_admin_access(request)
    users = db.scalars(select(User).order_by(User.username.asc())).all()
    context = {
        'users': users,
        'roles': [
            ('admin', 'Admin'),
            ('stock_manager', 'Gestionnaire stock'),
            ('viewer', 'Lecture seule'),
        ],
        'theme_label': theme_label,
        'users_notice': users_notice(tone, notice) if notice else None,
    }
    return render(request, 'admin/users.html', context)


@router.post('/admin/users/new')
def create_user(
    request: Request,
    username: str = Form(...),
    first_name: str = Form(''),
    last_name: str = Form(''),
    display_name: str = Form(''),
    email: str = Form(''),
    password: str = Form(...),
    role: str = Form('viewer'),
    is_active: bool = Form(False),
    db: Session = Depends(get_db),
):
    require_admin_access(request)
    username_value = username.strip()
    role_value = role if role in VALID_ROLES else 'viewer'
    if not username_value or not password:
        return RedirectResponse(url='/admin/users?notice=Utilisateur%20et%20mot%20de%20passe%20obligatoires&tone=danger', status_code=303)
    exists = db.scalar(select(User).where(func.lower(User.username) == username_value.lower()))
    if exists:
        return RedirectResponse(url='/admin/users?notice=Nom%20utilisateur%20deja%20utilise&tone=danger', status_code=303)
    db.add(User(
        username=username_value,
        first_name=first_name.strip() or None,
        last_name=last_name.strip() or None,
        display_name=display_name.strip() or None,
        email=email.strip() or None,
        password_hash=hash_password(password),
        role=role_value,
        is_active=bool(is_active),
    ))
    db.commit()
    return RedirectResponse(url='/admin/users?notice=Utilisateur%20cree', status_code=303)


@router.post('/admin/users/{user_id}/edit')
def update_user(
    request: Request,
    user_id: int,
    username: str = Form(...),
    first_name: str = Form(''),
    last_name: str = Form(''),
    display_name: str = Form(''),
    email: str = Form(''),
    role: str = Form('viewer'),
    is_active: bool = Form(False),
    db: Session = Depends(get_db),
):
    require_admin_access(request)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404)
    username_value = username.strip()
    role_value = role if role in VALID_ROLES else user.role
    active_value = bool(is_active)
    if would_remove_last_active_admin(db, user, new_role=role_value, new_is_active=active_value):
        return RedirectResponse(url='/admin/users?notice=Impossible%20de%20retirer%20le%20dernier%20admin%20actif&tone=danger', status_code=303)
    conflict = db.scalar(select(User).where(func.lower(User.username) == username_value.lower(), User.id != user.id))
    if conflict:
        return RedirectResponse(url='/admin/users?notice=Nom%20utilisateur%20deja%20utilise&tone=danger', status_code=303)
    user.username = username_value
    user.first_name = first_name.strip() or None
    user.last_name = last_name.strip() or None
    user.display_name = display_name.strip() or None
    user.email = email.strip() or None
    user.role = role_value
    user.is_active = active_value
    db.commit()
    return RedirectResponse(url='/admin/users?notice=Utilisateur%20mis%20a%20jour', status_code=303)


@router.post('/admin/users/{user_id}/reset-password')
def reset_user_password(
    request: Request,
    user_id: int,
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    require_admin_access(request)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404)
    if not password:
        return RedirectResponse(url='/admin/users?notice=Mot%20de%20passe%20obligatoire&tone=danger', status_code=303)
    user.password_hash = hash_password(password)
    db.commit()
    return RedirectResponse(url='/admin/users?notice=Mot%20de%20passe%20reinitialise', status_code=303)


@router.post('/admin/users/{user_id}/toggle-active')
def toggle_user_active(request: Request, user_id: int, db: Session = Depends(get_db)):
    require_admin_access(request)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404)
    next_active = not user.is_active
    if would_remove_last_active_admin(db, user, new_is_active=next_active):
        return RedirectResponse(url='/admin/users?notice=Impossible%20de%20desactiver%20le%20dernier%20admin%20actif&tone=danger', status_code=303)
    user.is_active = next_active
    db.commit()
    message = 'Utilisateur%20active' if next_active else 'Utilisateur%20desactive'
    return RedirectResponse(url=f'/admin/users?notice={message}', status_code=303)


@router.post('/admin/users/{user_id}/delete')
def delete_user(request: Request, user_id: int, db: Session = Depends(get_db)):
    require_admin_access(request)
    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404)
    if user.role == 'admin' and user.is_active and active_admin_count(db, exclude_user_id=user.id) == 0:
        return RedirectResponse(url='/admin/users?notice=Impossible%20de%20supprimer%20le%20dernier%20admin%20actif&tone=danger', status_code=303)
    db.delete(user)
    db.commit()
    return RedirectResponse(url='/admin/users?notice=Utilisateur%20supprime', status_code=303)
