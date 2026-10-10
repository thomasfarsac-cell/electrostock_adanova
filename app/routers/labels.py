from __future__ import annotations

import io

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.db import get_db
from app.models import Category, Component, Location
from app.services.component_labels import generate_component_labels_pdf, get_default_label_config
from app.services.label_route_helpers import label_layout_config
from app.services.qr_helpers import build_location_qr_payload, build_qr_payload, make_qr_png
from app.services.query_helpers import parse_id_list
from app.services.workshop_scope import scoped_entity_or_404, scoped_query
from app.view_context import get_selected_workshop_id

component_labels_router = APIRouter()
location_labels_router = APIRouter()


@component_labels_router.get('/components/{component_id}/qr.png')
def component_qr(component_id: int, db: Session = Depends(get_db)):
    component = db.get(Component, component_id)
    if not component:
        raise HTTPException(status_code=404, detail='Composant introuvable')
    payload = build_qr_payload(component)
    png = make_qr_png(payload)
    headers = {'Content-Disposition': f'inline; filename="component-{component.id}-qr.png"'}
    return StreamingResponse(iter([png]), media_type='image/png', headers=headers)


@component_labels_router.get('/labels/components.pdf')
def components_labels_pdf(
    request: Request,
    ids: str,
    layout: str = '48x25',
    copies: int = 1,
    db: Session = Depends(get_db),
):
    parsed_ids = parse_id_list(ids)
    if not parsed_ids:
        raise HTTPException(status_code=400, detail='Aucun article selectionne')
    components = db.scalars(
        select(Component)
        .where(Component.id.in_(parsed_ids))
        .options(
            joinedload(Component.category).joinedload(Category.parent),
            joinedload(Component.manufacturer),
            joinedload(Component.package),
            joinedload(Component.location),
        )
        .order_by(Component.part_number)
    ).unique().all()
    if not components:
        raise HTTPException(status_code=404, detail='Articles introuvables')

    layout_cfg = label_layout_config(layout)
    config = get_default_label_config()
    config.update({
        'label_width_mm': round(layout_cfg['w'] / mm, 3),
        'label_height_mm': round(layout_cfg['h'] / mm, 3),
        'margin_top_mm': round(layout_cfg['margin_y'] / mm, 3),
        'margin_bottom_mm': round(layout_cfg['margin_y'] / mm, 3),
        'margin_left_mm': round(layout_cfg['margin_x'] / mm, 3),
        'margin_right_mm': round(layout_cfg['margin_x'] / mm, 3),
        'gap_horizontal_mm': 0.0,
        'gap_vertical_mm': 0.0,
    })

    labels = []
    for component in components:
        for _ in range(max(copies, 1)):
            labels.append(component)

    pdf_bytes, _ = generate_component_labels_pdf(labels, config)
    headers = {'Content-Disposition': 'attachment; filename="etiquettes-composants.pdf"'}
    return StreamingResponse(io.BytesIO(pdf_bytes), media_type='application/pdf', headers=headers)


@location_labels_router.get('/locations/{location_id}/qr.png')
def location_qr(request: Request, location_id: int, db: Session = Depends(get_db)):
    location = db.get(Location, location_id)
    location = scoped_entity_or_404(request, db, location)
    png = make_qr_png(build_location_qr_payload(location))
    headers = {'Content-Disposition': f'inline; filename="location-{location.id}-qr.png"'}
    return StreamingResponse(iter([png]), media_type='image/png', headers=headers)


@location_labels_router.get('/labels/locations.pdf')
def locations_labels_pdf(
    request: Request,
    ids: str,
    layout: str = '48x25',
    copies: int = 1,
    db: Session = Depends(get_db),
):
    parsed_ids = [int(item) for item in ids.split(',') if item.strip().isdigit()]
    if not parsed_ids:
        raise HTTPException(status_code=400, detail='Aucun emplacement selectionne')
    active_workshop_id = get_selected_workshop_id(request, db)
    locations = db.scalars(
        scoped_query(select(Location), Location, active_workshop_id)
        .where(Location.id.in_(parsed_ids))
        .options(selectinload(Location.components))
        .order_by(Location.name.asc())
    ).all()
    if not locations:
        raise HTTPException(status_code=404, detail='Emplacements introuvables')

    layout_cfg = label_layout_config(layout)
    packet = io.BytesIO()
    pdf = canvas.Canvas(packet, pagesize=A4)
    page_w, page_h = A4
    labels = []
    for location in locations:
        for _ in range(max(copies, 1)):
            labels.append(location)

    for index, location in enumerate(labels):
        slot = index % (layout_cfg['cols'] * layout_cfg['rows'])
        if index and slot == 0:
            pdf.showPage()
        col = slot % layout_cfg['cols']
        row = slot // layout_cfg['cols']
        x = layout_cfg['margin_x'] + col * layout_cfg['w']
        y = page_h - layout_cfg['margin_y'] - (row + 1) * layout_cfg['h']
        pdf.rect(x, y, layout_cfg['w'], layout_cfg['h'])
        qr_size = min(layout_cfg['h'] - 6 * mm, 18 * mm)
        qr_png = make_qr_png(build_location_qr_payload(location))
        qr_buffer = ImageReader(io.BytesIO(qr_png))
        pdf.drawImage(qr_buffer, x + 2 * mm, y + 2 * mm, qr_size, qr_size)
        text_x = x + qr_size + 4 * mm
        text_y = y + layout_cfg['h'] - 5 * mm
        pdf.setFont('Helvetica-Bold', 8)
        pdf.drawString(text_x, text_y, (location.name or '')[:24])
        pdf.setFont('Helvetica', 7)
        pdf.drawString(text_x, text_y - 4 * mm, f'ID: {location.id}')
        pdf.drawString(text_x, text_y - 8 * mm, f'QR: L:{location.id}')
        pdf.drawString(text_x, text_y - 12 * mm, f'Contenu: {len(location.components)} comp.')

    pdf.save()
    packet.seek(0)
    headers = {'Content-Disposition': 'attachment; filename="etiquettes-emplacements.pdf"'}
    return StreamingResponse(packet, media_type='application/pdf', headers=headers)
