from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.db import get_db
from app.models import Category, Component, StockMovement, Workshop
from app.services.categories import build_category_path
from app.services.dashboard_helpers import build_workshop_summaries
from app.services.workshop_scope import scoped_query
from app.view_context import get_selected_workshop_id, render

router = APIRouter()


@router.get('/')
def dashboard(request: Request, db: Session = Depends(get_db)):
    active_workshop_id = get_selected_workshop_id(request, db)
    active_workshop = db.get(Workshop, active_workshop_id) if active_workshop_id else None
    component_count_query = scoped_query(select(func.count(Component.id)), Component, active_workshop_id)
    total_components = db.scalar(component_count_query) or 0
    total_stock = db.scalar(scoped_query(select(func.coalesce(func.sum(Component.quantity), 0)), Component, active_workshop_id)) or 0
    low_stock = db.scalar(
        scoped_query(select(func.count(Component.id)).where(Component.quantity <= Component.minimum_quantity), Component, active_workshop_id)
    ) or 0
    categories_count = db.scalar(scoped_query(select(func.count(Category.id)), Category, active_workshop_id)) or 0
    movements_7d = db.scalar(
        scoped_query(
            select(func.count(StockMovement.id))
            .join(Component, StockMovement.component_id == Component.id)
            .where(StockMovement.created_at >= func.datetime('now', '-7 day')),
            Component,
            active_workshop_id,
        )
    ) or 0
    latest_components = db.scalars(
        scoped_query(select(Component), Component, active_workshop_id)
        .options(joinedload(Component.category), joinedload(Component.manufacturer))
        .order_by(Component.updated_at.desc())
        .limit(8)
    ).unique().all()
    stock_by_category = db.execute(
        select(Category.id, Category.name, func.count(Component.id))
        .join(Component, Component.category_id == Category.id, isouter=True)
        .where(Category.workshop_id == active_workshop_id if active_workshop_id is not None else True)
        .group_by(Category.id, Category.name)
        .order_by(func.count(Component.id).desc(), Category.name)
        .limit(10)
    ).all()
    recent_movements = db.scalars(
        scoped_query(select(StockMovement).join(Component, StockMovement.component_id == Component.id), Component, active_workshop_id)
        .options(joinedload(StockMovement.component))
        .order_by(StockMovement.created_at.desc())
        .limit(8)
    ).all()
    return render(request, 'dashboard.html', {
        'dashboard_scope_title': active_workshop.name if active_workshop else 'Tous les ateliers',
        'dashboard_scope_is_all': active_workshop is None,
        'workshop_summaries': build_workshop_summaries(db),
        'total_components': total_components,
        'total_stock': total_stock,
        'low_stock': low_stock,
        'categories_count': categories_count,
        'movements_7d': movements_7d,
        'latest_components': latest_components,
        'stock_by_category': stock_by_category,
        'recent_movements': recent_movements,
        'build_category_path': build_category_path,
    })
