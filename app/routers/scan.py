from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Component, Location
from app.services.scan_helpers import resolve_scan

router = APIRouter()


@router.get('/scan')
def scan_router(raw: str, db: Session = Depends(get_db)):
    item = resolve_scan(db, raw)
    if isinstance(item, Component):
        return RedirectResponse(url=f'/components/{item.id}', status_code=303)
    if isinstance(item, Location):
        return RedirectResponse(url=f'/locations/{item.id}', status_code=303)
    if str(raw or '').strip().upper().startswith(('L:', 'LOCATION_ID:')):
        return RedirectResponse(url=f'/locations?search={quote(raw)}', status_code=303)
    return RedirectResponse(url=f'/components?search={quote(raw)}', status_code=303)
