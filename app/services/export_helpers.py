from __future__ import annotations

import csv
import io

from fastapi.responses import StreamingResponse

from app.models import Component, StockMovement
from app.services.categories import build_category_path
from app.services.imports import TEMPLATE_HEADERS, TEMPLATE_SAMPLE_ROW


def export_components_csv(filename: str, components: list[Component]):
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow([
        'ID', 'Reference', 'Designation', 'Categorie', 'Fabricant', 'Boitier', 'Quantite',
        'Stock mini', 'Emplacement', 'Datasheet', 'Mots-cles', 'Description', 'Notes',
        'Cree le', 'Modifie le',
    ])
    for component in components:
        writer.writerow([
            component.id,
            component.part_number,
            component.name,
            build_category_path(component.category),
            component.manufacturer.name if component.manufacturer else '',
            component.package.name if component.package else '',
            component.quantity,
            component.minimum_quantity,
            component.location.name if component.location else '',
            component.datasheet_url or '',
            component.keywords or '',
            component.description or '',
            component.notes or '',
            component.created_at.strftime('%Y-%m-%d %H:%M:%S') if component.created_at else '',
            component.updated_at.strftime('%Y-%m-%d %H:%M:%S') if component.updated_at else '',
        ])
    content = output.getvalue()
    output.close()
    headers = {'Content-Disposition': f'attachment; filename="{filename}"'}
    return StreamingResponse(iter([content.encode('utf-8-sig')]), media_type='text/csv; charset=utf-8', headers=headers)


def export_movements_csv(filename: str, movements: list[StockMovement]):
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow(['Date', 'Reference', 'DÃ©signation', 'Type', 'Delta', 'Stock aprÃ¨s', 'Raison', 'Notes', 'Source', 'Reference import'])
    for movement in movements:
        component = movement.component
        writer.writerow([
            movement.created_at.strftime('%Y-%m-%d %H:%M:%S') if movement.created_at else '',
            component.part_number if component else '',
            component.name if component else '',
            movement.movement_type,
            movement.quantity_delta,
            movement.resulting_quantity,
            movement.reason or '',
            movement.notes or '',
            movement.source or '',
            movement.reference or '',
        ])
    content = output.getvalue()
    output.close()
    headers = {'Content-Disposition': f'attachment; filename="{filename}"'}
    return StreamingResponse(iter([content.encode('utf-8-sig')]), media_type='text/csv; charset=utf-8', headers=headers)


def export_template_csv():
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow(TEMPLATE_HEADERS)
    writer.writerow(TEMPLATE_SAMPLE_ROW)
    content = output.getvalue()
    output.close()
    headers = {'Content-Disposition': 'attachment; filename="template_import_composants.csv"'}
    return StreamingResponse(iter([content.encode('utf-8-sig')]), media_type='text/csv; charset=utf-8', headers=headers)
