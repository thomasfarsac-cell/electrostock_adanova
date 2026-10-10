from __future__ import annotations

from fastapi import HTTPException, Request

from app.auth import (
    get_current_user,
    is_admin as auth_is_admin,
    is_auth_enabled,
    is_legacy_cookie_authenticated,
    is_stock_manager as auth_is_stock_manager,
)

ROLE_LABELS = {
    'admin': 'admin',
    'stock_manager': 'stock manager',
    'viewer': 'viewer',
}


def has_admin_access(request: Request) -> bool:
    if not is_auth_enabled():
        return True
    if is_legacy_cookie_authenticated(request):
        return True
    return auth_is_admin(get_current_user(request))


def has_stock_write_access(request: Request) -> bool:
    if not is_auth_enabled():
        return True
    if is_legacy_cookie_authenticated(request):
        return True
    user = get_current_user(request)
    return auth_is_admin(user) or auth_is_stock_manager(user)


def require_admin_access(request: Request):
    if not has_admin_access(request):
        raise HTTPException(status_code=403, detail='Acces reserve aux administrateurs.')


def require_stock_write_access(request: Request):
    if not has_stock_write_access(request):
        raise HTTPException(status_code=403, detail='Action reservee aux administrateurs et gestionnaires de stock.')
