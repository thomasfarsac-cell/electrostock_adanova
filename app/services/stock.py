from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Component, StockMovement


def add_stock_movement(
    db: Session,
    component: Component,
    movement_type: str,
    quantity_delta: int,
    reason: str | None = None,
    notes: str | None = None,
    source: str | None = None,
    reference: str | None = None,
):
    component.quantity = (component.quantity or 0) + quantity_delta
    movement = StockMovement(
        component=component,
        movement_type=movement_type,
        quantity_delta=quantity_delta,
        resulting_quantity=component.quantity,
        reason=reason or None,
        notes=notes or None,
        source=source or None,
        reference=reference or None,
    )
    db.add(movement)
    return movement


def adjust_stock_to_quantity(
    db: Session,
    component: Component,
    target_quantity: int,
    reason: str | None = None,
    notes: str | None = None,
    source: str | None = None,
    reference: str | None = None,
):
    delta = target_quantity - (component.quantity or 0)
    if delta == 0:
        return None
    return add_stock_movement(
        db=db,
        component=component,
        movement_type='adjustment',
        quantity_delta=delta,
        reason=reason or 'Ajustement manuel',
        notes=notes,
        source=source,
        reference=reference,
    )
