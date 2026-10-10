from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth import (
    COOKIE_NAME,
    SESSION_MAX_AGE_SECONDS,
    authenticate_user,
    build_auth_cookie_value,
    build_session_cookie_value,
    get_current_user,
    has_users,
    hash_password,
    is_auth_enabled,
    read_password_hash,
    verify_password,
)
from app.db import get_db
from app.services.notice_helpers import users_notice
from app.view_context import (
    DEFAULT_THEME_ID,
    THEMES,
    normalize_theme_id,
    render,
    theme_label,
)

router = APIRouter()


@router.get('/login')
def login_page(request: Request, next: str = '/', error: str = ''):
    if not is_auth_enabled():
        return RedirectResponse(url='/', status_code=303)
    return render(request, 'login.html', {'next': next, 'error': error})


@router.post('/login')
def login_submit(
    request: Request,
    username: str = Form('admin'),
    password: str = Form(...),
    next: str = Form('/'),
    db: Session = Depends(get_db),
):
    if has_users(db):
        user = authenticate_user(db, username or 'admin', password)
        if not user:
            return render(request, 'login.html', {'next': next, 'username': username, 'error': 'Identifiants invalides.'}, status_code=401)
        response = RedirectResponse(url=next or '/', status_code=303)
        response.set_cookie(
            COOKIE_NAME,
            build_session_cookie_value(user.id),
            max_age=SESSION_MAX_AGE_SECONDS,
            httponly=True,
            samesite='lax',
        )
        return response

    stored = read_password_hash()
    if not verify_password(password, stored):
        return render(request, 'login.html', {'next': next, 'error': 'Mot de passe invalide.'}, status_code=401)
    response = RedirectResponse(url=next or '/', status_code=303)
    response.set_cookie(COOKIE_NAME, build_auth_cookie_value(), max_age=90 * 24 * 3600, httponly=True, samesite='lax')
    return response


@router.post('/logout')
def logout():
    response = RedirectResponse(url='/login', status_code=303)
    response.delete_cookie(COOKIE_NAME)
    return response


@router.get('/profile')
def profile_page(request: Request, db: Session = Depends(get_db), notice: str = '', tone: str = 'success'):
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail='Authentication required')
    return render(request, 'profile.html', {
        'profile_user': user,
        'themes': THEMES,
        'theme_label': theme_label,
        'profile_notice': users_notice(tone, notice) if notice else None,
    })


@router.post('/profile/update')
def update_profile(
    request: Request,
    first_name: str = Form(''),
    last_name: str = Form(''),
    display_name: str = Form(''),
    email: str = Form(''),
    theme_id: str = Form(DEFAULT_THEME_ID),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail='Authentication required')
    user.first_name = first_name.strip() or None
    user.last_name = last_name.strip() or None
    user.display_name = display_name.strip() or None
    user.email = email.strip() or None
    user.theme_id = normalize_theme_id(theme_id)
    db.commit()
    return RedirectResponse(url='/profile?notice=Profil%20mis%20a%20jour', status_code=303)


@router.post('/profile/change-password')
def change_profile_password(
    request: Request,
    current_password: str = Form(''),
    new_password: str = Form(''),
    confirm_password: str = Form(''),
    db: Session = Depends(get_db),
):
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail='Authentication required')
    if not verify_password(current_password, user.password_hash):
        return RedirectResponse(url='/profile?notice=Mot%20de%20passe%20actuel%20incorrect&tone=danger', status_code=303)
    if not new_password or new_password != confirm_password:
        return RedirectResponse(url='/profile?notice=Confirmation%20du%20nouveau%20mot%20de%20passe%20invalide&tone=danger', status_code=303)
    user.password_hash = hash_password(new_password)
    db.commit()
    return RedirectResponse(url='/profile?notice=Mot%20de%20passe%20mis%20a%20jour', status_code=303)
