from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
from pathlib import Path
from datetime import datetime

from fastapi import HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import DATA_DIR, SECRET_KEY
from app.models import User

PASSWORD_FILE = DATA_DIR / 'auth_password.hash'
COOKIE_NAME = 'electrostock_auth'
PBKDF2_ROUNDS = 260_000
SESSION_VERSION = 'v1'
SESSION_MAX_AGE_SECONDS = 90 * 24 * 3600
ROLES = ('admin', 'stock_manager', 'viewer')

logger = logging.getLogger('uvicorn.error')


def is_auth_enabled() -> bool:
    if PASSWORD_FILE.exists() and PASSWORD_FILE.is_file():
        return True
    try:
        from app.db import SessionLocal

        db = SessionLocal()
        try:
            return (db.scalar(select(func.count(User.id))) or 0) > 0
        finally:
            db.close()
    except Exception:
        return False


def read_password_hash() -> str | None:
    if not PASSWORD_FILE.exists() or not PASSWORD_FILE.is_file():
        return None
    return PASSWORD_FILE.read_text(encoding='utf-8').strip() or None


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    derived = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, PBKDF2_ROUNDS)
    return 'pbkdf2_sha256${}${}${}'.format(
        PBKDF2_ROUNDS,
        base64.urlsafe_b64encode(salt).decode('ascii'),
        base64.urlsafe_b64encode(derived).decode('ascii'),
    )


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        algo, rounds_str, salt_b64, digest_b64 = stored.split('$', 3)
        if algo != 'pbkdf2_sha256':
            return False
        rounds = int(rounds_str)
        salt = base64.urlsafe_b64decode(salt_b64.encode('ascii'))
        expected = base64.urlsafe_b64decode(digest_b64.encode('ascii'))
    except Exception:
        return False
    candidate = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, rounds)
    return hmac.compare_digest(candidate, expected)


def build_auth_cookie_value() -> str:
    signature = hmac.new(SECRET_KEY.encode('utf-8'), b'electrostock-auth', hashlib.sha256).hexdigest()
    return signature


def build_session_cookie_value(user_id: int) -> str:
    issued_at = str(int(datetime.utcnow().timestamp()))
    payload = f'{SESSION_VERSION}:{user_id}:{issued_at}'
    signature = hmac.new(SECRET_KEY.encode('utf-8'), payload.encode('utf-8'), hashlib.sha256).hexdigest()
    return f'{payload}:{signature}'


def parse_session_cookie_value(cookie_value: str) -> int | None:
    try:
        version, user_id_raw, issued_at_raw, signature = cookie_value.split(':', 3)
        if version != SESSION_VERSION:
            return None
        payload = f'{version}:{user_id_raw}:{issued_at_raw}'
        expected = hmac.new(SECRET_KEY.encode('utf-8'), payload.encode('utf-8'), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        issued_at = int(issued_at_raw)
        if int(datetime.utcnow().timestamp()) - issued_at > SESSION_MAX_AGE_SECONDS:
            return None
        user_id = int(user_id_raw)
    except Exception:
        return None
    return user_id


def has_users(db: Session) -> bool:
    return (db.scalar(select(func.count(User.id))) or 0) > 0


def get_user_by_username(db: Session, username: str) -> User | None:
    normalized = (username or '').strip().lower()
    if not normalized:
        return None
    return db.scalar(select(User).where(func.lower(User.username) == normalized))


def authenticate_user(db: Session, username: str, password: str) -> User | None:
    user = get_user_by_username(db, username or 'admin')
    if not user or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    user.last_login_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    return user


def ensure_initial_admin_user(db: Session) -> User | None:
    if has_users(db):
        return None
    stored = read_password_hash()
    if not stored:
        logger.info('No users or legacy auth_password.hash found; authentication remains disabled.')
        return None
    user = User(username='admin', password_hash=stored, role='admin', is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    logger.info('Created initial admin user from legacy auth_password.hash.')
    return user


def ensure_active_admin_recovery(db: Session) -> User | None:
    active_admin_count = db.scalar(
        select(func.count(User.id)).where(User.role == 'admin', User.is_active.is_(True))
    ) or 0
    if active_admin_count > 0:
        return None

    admin = get_user_by_username(db, 'admin')
    if admin is None:
        admin = User(username='admin')
        db.add(admin)

    admin.password_hash = hash_password('1234')
    admin.role = 'admin'
    admin.is_active = True
    db.commit()
    db.refresh(admin)
    logger.warning(
        'Emergency admin recovery activated: no active admin existed. '
        'User "admin" is active with temporary password "1234". Change it immediately.'
    )
    return admin


def get_current_user(request: Request, db: Session | None = None) -> User | None:
    cookie_value = request.cookies.get(COOKIE_NAME, '')
    user_id = parse_session_cookie_value(cookie_value)
    if not user_id:
        return None

    if db is not None:
        user = db.get(User, user_id)
        return user if user and user.is_active else None

    try:
        from app.db import SessionLocal

        local_db = SessionLocal()
        try:
            user = local_db.get(User, user_id)
            if not user or not user.is_active:
                return None
            local_db.expunge(user)
            return user
        finally:
            local_db.close()
    except Exception:
        return None


def is_legacy_cookie_authenticated(request: Request) -> bool:
    if not read_password_hash():
        return False
    cookie_value = request.cookies.get(COOKIE_NAME, '')
    return hmac.compare_digest(cookie_value, build_auth_cookie_value())


def is_request_authenticated(request: Request) -> bool:
    if not is_auth_enabled():
        return True
    return get_current_user(request) is not None or is_legacy_cookie_authenticated(request)


def require_user(request: Request, db: Session) -> User:
    user = get_current_user(request, db)
    if user:
        return user
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Authentication required')


def user_has_role(user: User | None, *roles: str) -> bool:
    return bool(user and user.is_active and user.role in roles)


def require_role(user: User, *roles: str) -> User:
    if user_has_role(user, *roles):
        return user
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail='Insufficient permissions')


def is_admin(user: User | None) -> bool:
    return user_has_role(user, 'admin')


def is_stock_manager(user: User | None) -> bool:
    return user_has_role(user, 'stock_manager')


def is_viewer(user: User | None) -> bool:
    return user_has_role(user, 'viewer')
