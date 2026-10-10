from __future__ import annotations

import io
import json

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.security.permissions import require_stock_write_access
from app.services.component_label_presets import (
    delete_component_label_preset,
    list_component_label_presets,
    save_component_label_preset,
)
from app.services.component_labels import (
    build_layout_summary,
    generate_component_labels_pdf,
    get_default_label_config,
    get_field_options,
    get_page_format_options,
    normalize_label_config,
)
from app.services.label_route_helpers import get_component_label_query
from app.services.query_helpers import parse_id_list
from app.utils import parse_int
from app.view_context import get_selected_workshop_id

router = APIRouter()


@router.get('/api/component-labels/presets')
def component_label_presets_api():
    return JSONResponse({
        'presets': list_component_label_presets(),
        'page_formats': get_page_format_options(),
        'fields': get_field_options(),
        'defaults': get_default_label_config(),
    })


@router.post('/api/component-labels/presets/{kind}')
async def save_component_label_preset_api(kind: str, request: Request):
    require_stock_write_access(request)
    payload = await request.json()
    try:
        preset = save_component_label_preset(
            kind=kind,
            name=payload.get('name'),
            payload=payload.get('payload') or {},
            preset_id=payload.get('id'),
        )
    except (TypeError, ValueError) as exc:
        return JSONResponse({'error': str(exc)}, status_code=400)

    return JSONResponse({
        'preset': preset,
        'presets': list_component_label_presets(),
    })


@router.post('/api/component-labels/presets/{kind}/{preset_id}/delete')
def delete_component_label_preset_api(request: Request, kind: str, preset_id: str):
    require_stock_write_access(request)
    try:
        delete_component_label_preset(kind, preset_id)
    except ValueError as exc:
        return JSONResponse({'error': str(exc)}, status_code=400)

    return JSONResponse({
        'ok': True,
        'presets': list_component_label_presets(),
    })


@router.post('/api/component-labels/layout-summary')
async def component_label_layout_summary_api(request: Request):
    payload = await request.json()
    component_count = parse_int(payload.get('component_count'), 0)
    try:
        normalized = normalize_label_config(payload.get('config') or {})
        summary = build_layout_summary(normalized, component_count)
    except ValueError as exc:
        return JSONResponse({'error': str(exc)}, status_code=400)
    return JSONResponse({'summary': summary, 'config': normalized})


@router.post('/api/component-labels/pdf')
async def component_labels_pdf_api(request: Request, db: Session = Depends(get_db)):
    payload = await request.json()
    selected_ids = parse_id_list(payload.get('selected_ids'))
    current_page_ids = parse_id_list(payload.get('current_page_ids'))
    sample_page = bool(payload.get('sample_page'))
    try:
        normalized = normalize_label_config(payload.get('config') or {})
        query = get_component_label_query(
            db=db,
            source=normalized['source'],
            filters=payload.get('filters') or {},
            selected_ids=selected_ids,
            current_page_ids=current_page_ids,
            workshop_id=get_selected_workshop_id(request, db),
        )
        components = db.scalars(query).unique().all()
        if not components:
            raise ValueError('Aucun article ne correspond a cette source.')
        layout_summary = build_layout_summary(normalized, len(components))
        if sample_page and layout_summary['labels_per_page'] > 0:
            components = components[:layout_summary['labels_per_page']]
        pdf_bytes, metadata = generate_component_labels_pdf(components, normalized)
    except ValueError as exc:
        return JSONResponse({'error': str(exc)}, status_code=400)

    headers = {
        'Content-Disposition': 'attachment; filename="etiquettes-composants.pdf"',
        'X-Label-Metadata': json.dumps(metadata),
    }
    return StreamingResponse(io.BytesIO(pdf_bytes), media_type='application/pdf', headers=headers)
