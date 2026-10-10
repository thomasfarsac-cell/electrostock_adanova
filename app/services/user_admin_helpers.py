from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import User

VALID_ROLES = {'admin', 'stock_manager', 'viewer'}


def active_admin_count(db: Session, exclude_user_id: int | None = None) -> int:
    query = select(func.count(User.id)).where(User.role == 'admin', User.is_active.is_(True))
    if exclude_user_id is not None:
        query = query.where(User.id != exclude_user_id)
    return db.scalar(query) or 0


def would_remove_last_active_admin(db: Session, user: User, new_role: str | None = None, new_is_active: bool | None = None) -> bool:
    future_role = new_role if new_role is not None else user.role
    future_active = new_is_active if new_is_active is not None else user.is_active
    if user.role != 'admin' or not user.is_active:
        return False
    if future_role == 'admin' and future_active:
        return False
    return active_admin_count(db, exclude_user_id=user.id) == 0
