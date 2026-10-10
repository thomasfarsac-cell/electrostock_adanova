from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import User
from app.services.env_settings import get_env_value, set_env_value

SETUP_COMPLETED_KEY = 'ELECTROSTOCK_SETUP_COMPLETED'


def has_admin_user(db: Session) -> bool:
    return (db.scalar(select(func.count(User.id)).where(User.role == 'admin')) or 0) > 0


def is_setup_completed(db: Session) -> bool:
    return get_env_value(SETUP_COMPLETED_KEY, '').strip().lower() == 'true' or has_admin_user(db)


def mark_setup_completed():
    set_env_value(SETUP_COMPLETED_KEY, 'true')
