from __future__ import annotations

import io
from dataclasses import dataclass
from math import floor

import qrcode
from qrcode.constants import ERROR_CORRECT_H, ERROR_CORRECT_L, ERROR_CORRECT_M, ERROR_CORRECT_Q
from reportlab.lib.utils import ImageReader
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen import canvas

from app.models import Component
from app.services.categories import build_category_path

PAGE_FORMAT_OPTIONS = [
    {
        'id': 'a4',
        'name': 'A4 standard',
        'width_mm': 210.0,
        'height_mm': 297.0,
        'built_in': True,
    },
    {
        'id': 'a5',
        'name': 'A5 standard',
        'width_mm': 148.0,
        'height_mm': 210.0,
        'built_in': True,
    },
]

LABEL_FIELD_OPTIONS = [
    {'key': 'part_number', 'label': 'Reference', 'short_label': 'Ref', 'default_text': True, 'default_qr': True},
    {'key': 'name', 'label': 'Designation', 'short_label': 'Nom', 'default_text': False, 'default_qr': False},
    {'key': 'category', 'label': 'Famille', 'short_label': 'Fam', 'default_text': False, 'default_qr': False},
    {'key': 'manufacturer', 'label': 'Marque / fabricant', 'short_label': 'Marque', 'default_text': False, 'default_qr': False},
    {'key': 'package', 'label': 'Format / conditionnement', 'short_label': 'Format', 'default_text': False, 'default_qr': False},
    {'key': 'location', 'label': 'Emplacement', 'short_label': 'Empl', 'default_text': False, 'default_qr': False},
    {'key': 'description', 'label': 'Description', 'short_label': 'Desc', 'default_text': False, 'default_qr': False},
]

QR_ERROR_LEVELS = ('L', 'M', 'Q', 'H')

DEFAULT_LABEL_CONFIG = {
    'source': 'selected',
    'page_format_id': 'a4',
    'page_width_mm': 210.0,
    'page_height_mm': 297.0,
    'label_width_mm': 48.0,
    'label_height_mm': 25.0,
    'margin_top_mm': 12.0,
    'margin_bottom_mm': 12.0,
    'margin_left_mm': 8.0,
    'margin_right_mm': 8.0,
    'gap_horizontal_mm': 2.0,
    'gap_vertical_mm': 2.0,
    'text_fields': ['part_number'],
    'qr_enabled': True,
    'qr_fields': ['part_number'],
    'qr_error_correction': 'L',
}


@dataclass
class LabelLayout:
    page_width_mm: float
    page_height_mm: float
    label_width_mm: float
    label_height_mm: float
    margin_top_mm: float
    margin_bottom_mm: float
    margin_left_mm: float
    margin_right_mm: float
    gap_horizontal_mm: float
    gap_vertical_mm: float
    columns: int
    rows: int
    labels_per_page: int


def get_default_label_config() -> dict:
    return {
        key: list(value) if isinstance(value, list) else value
        for key, value in DEFAULT_LABEL_CONFIG.items()
    }


def get_field_options() -> list[dict]:
    return [dict(item) for item in LABEL_FIELD_OPTIONS]


def get_page_format_options() -> list[dict]:
    return [dict(item) for item in PAGE_FORMAT_OPTIONS]


def get_page_format_by_id(format_id: str | None) -> dict | None:
    wanted = str(format_id or '').strip().lower()
    for item in PAGE_FORMAT_OPTIONS:
        if item['id'] == wanted:
            return dict(item)
    return None


def _parse_number(raw_value, fallback: float, *, minimum: float = 0.0) -> float:
    try:
        value = float(raw_value)
    except (TypeError, ValueError):
        value = fallback
    return round(max(minimum, value), 3)


def _normalize_field_keys(raw_values, *, default_key: str) -> list[str]:
    allowed = {item['key'] for item in LABEL_FIELD_OPTIONS}
    values = raw_values if isinstance(raw_values, list) else []
    normalized = []
    for item in values:
        key = str(item or '').strip()
        if key and key in allowed and key not in normalized:
            normalized.append(key)
    if not normalized:
        normalized.append(default_key)
    return normalized


def normalize_label_config(raw_config: dict | None) -> dict:
    source = str((raw_config or {}).get('source') or DEFAULT_LABEL_CONFIG['source']).strip()
    if source not in {'selected', 'filtered', 'current_page'}:
        source = DEFAULT_LABEL_CONFIG['source']

    page_format_id = str((raw_config or {}).get('page_format_id') or DEFAULT_LABEL_CONFIG['page_format_id']).strip().lower()
    format_item = get_page_format_by_id(page_format_id)
    page_width_mm = _parse_number(
        (raw_config or {}).get('page_width_mm'),
        format_item['width_mm'] if format_item else DEFAULT_LABEL_CONFIG['page_width_mm'],
        minimum=20.0,
    )
    page_height_mm = _parse_number(
        (raw_config or {}).get('page_height_mm'),
        format_item['height_mm'] if format_item else DEFAULT_LABEL_CONFIG['page_height_mm'],
        minimum=20.0,
    )

    config = {
        'source': source,
        'page_format_id': page_format_id or DEFAULT_LABEL_CONFIG['page_format_id'],
        'page_width_mm': page_width_mm,
        'page_height_mm': page_height_mm,
        'label_width_mm': _parse_number((raw_config or {}).get('label_width_mm'), DEFAULT_LABEL_CONFIG['label_width_mm'], minimum=5.0),
        'label_height_mm': _parse_number((raw_config or {}).get('label_height_mm'), DEFAULT_LABEL_CONFIG['label_height_mm'], minimum=5.0),
        'margin_top_mm': _parse_number((raw_config or {}).get('margin_top_mm'), DEFAULT_LABEL_CONFIG['margin_top_mm']),
        'margin_bottom_mm': _parse_number((raw_config or {}).get('margin_bottom_mm'), DEFAULT_LABEL_CONFIG['margin_bottom_mm']),
        'margin_left_mm': _parse_number((raw_config or {}).get('margin_left_mm'), DEFAULT_LABEL_CONFIG['margin_left_mm']),
        'margin_right_mm': _parse_number((raw_config or {}).get('margin_right_mm'), DEFAULT_LABEL_CONFIG['margin_right_mm']),
        'gap_horizontal_mm': _parse_number((raw_config or {}).get('gap_horizontal_mm'), DEFAULT_LABEL_CONFIG['gap_horizontal_mm']),
        'gap_vertical_mm': _parse_number((raw_config or {}).get('gap_vertical_mm'), DEFAULT_LABEL_CONFIG['gap_vertical_mm']),
        'text_fields': _normalize_field_keys((raw_config or {}).get('text_fields'), default_key='part_number'),
        'qr_enabled': bool((raw_config or {}).get('qr_enabled', DEFAULT_LABEL_CONFIG['qr_enabled'])),
        'qr_fields': _normalize_field_keys((raw_config or {}).get('qr_fields'), default_key='part_number'),
        'qr_error_correction': str((raw_config or {}).get('qr_error_correction') or DEFAULT_LABEL_CONFIG['qr_error_correction']).strip().upper(),
    }

    if config['qr_error_correction'] not in QR_ERROR_LEVELS:
        config['qr_error_correction'] = DEFAULT_LABEL_CONFIG['qr_error_correction']

    return config


def calculate_label_layout(config: dict) -> LabelLayout:
    page_inner_width = config['page_width_mm'] - config['margin_left_mm'] - config['margin_right_mm']
    page_inner_height = config['page_height_mm'] - config['margin_top_mm'] - config['margin_bottom_mm']
    if page_inner_width <= 0 or page_inner_height <= 0:
        raise ValueError('Les marges de page depassent le format choisi.')

    columns = floor((page_inner_width + config['gap_horizontal_mm']) / (config['label_width_mm'] + config['gap_horizontal_mm']))
    rows = floor((page_inner_height + config['gap_vertical_mm']) / (config['label_height_mm'] + config['gap_vertical_mm']))

    if columns <= 0 or rows <= 0:
        raise ValueError("Aucune etiquette ne tient sur la page avec cette configuration.")

    return LabelLayout(
        page_width_mm=config['page_width_mm'],
        page_height_mm=config['page_height_mm'],
        label_width_mm=config['label_width_mm'],
        label_height_mm=config['label_height_mm'],
        margin_top_mm=config['margin_top_mm'],
        margin_bottom_mm=config['margin_bottom_mm'],
        margin_left_mm=config['margin_left_mm'],
        margin_right_mm=config['margin_right_mm'],
        gap_horizontal_mm=config['gap_horizontal_mm'],
        gap_vertical_mm=config['gap_vertical_mm'],
        columns=columns,
        rows=rows,
        labels_per_page=columns * rows,
    )


def serialize_layout(layout: LabelLayout) -> dict:
    return {
        'page_width_mm': layout.page_width_mm,
        'page_height_mm': layout.page_height_mm,
        'label_width_mm': layout.label_width_mm,
        'label_height_mm': layout.label_height_mm,
        'margin_top_mm': layout.margin_top_mm,
        'margin_bottom_mm': layout.margin_bottom_mm,
        'margin_left_mm': layout.margin_left_mm,
        'margin_right_mm': layout.margin_right_mm,
        'gap_horizontal_mm': layout.gap_horizontal_mm,
        'gap_vertical_mm': layout.gap_vertical_mm,
        'columns': layout.columns,
        'rows': layout.rows,
        'labels_per_page': layout.labels_per_page,
    }


def build_layout_summary(config: dict, component_count: int) -> dict:
    layout = calculate_label_layout(config)
    total_pages = max(1, (component_count + layout.labels_per_page - 1) // layout.labels_per_page) if component_count else 0
    return {
        **serialize_layout(layout),
        'component_count': component_count,
        'total_pages': total_pages,
    }


def get_component_field_value(component: Component, field_key: str) -> str:
    if field_key == 'part_number':
        return (component.part_number or '').strip()
    if field_key == 'name':
        return (component.name or '').strip()
    if field_key == 'category':
        return (build_category_path(component.category) or '').strip()
    if field_key == 'manufacturer':
        return (component.manufacturer.name if component.manufacturer else '').strip()
    if field_key == 'package':
        return (component.package.name if component.package else '').strip()
    if field_key == 'location':
        return (component.location.name if component.location else '').strip()
    if field_key == 'description':
        return (component.description or '').strip()
    return ''


def build_label_text_rows(component: Component, selected_fields: list[str]) -> list[dict]:
    field_map = {item['key']: item for item in LABEL_FIELD_OPTIONS}
    rows = []
    for index, key in enumerate(selected_fields):
        value = get_component_field_value(component, key)
        if not value:
            continue
        if key == 'part_number':
            text = value
        elif key == 'name':
            text = value
        else:
            text = f"{field_map[key]['short_label']}: {value}"
        rows.append({
            'text': text,
            'is_primary': index == 0,
        })
    return rows


def build_qr_payload_for_component(component: Component, selected_fields: list[str]) -> str:
    values = []
    for key in selected_fields:
        value = get_component_field_value(component, key)
        if value:
            values.append(value)
    return '\n'.join(values)


def _qr_correction_value(level: str):
    mapping = {
        'L': ERROR_CORRECT_L,
        'M': ERROR_CORRECT_M,
        'Q': ERROR_CORRECT_Q,
        'H': ERROR_CORRECT_H,
    }
    return mapping.get(level, ERROR_CORRECT_L)


def make_qr_png(payload: str, error_level: str = 'L') -> bytes:
    qr = qrcode.QRCode(
        version=None,
        error_correction=_qr_correction_value(error_level),
        box_size=8,
        border=2,
    )
    qr.add_data(payload)
    qr.make(fit=True)
    image = qr.make_image(fill_color='black', back_color='white')
    buffer = io.BytesIO()
    image.save(buffer, format='PNG')
    return buffer.getvalue()


def _wrap_text(text: str, font_name: str, font_size: float, max_width: float) -> list[str]:
    words = text.split()
    if not words:
        return ['']

    lines = []
    current = words[0]
    for word in words[1:]:
        candidate = f'{current} {word}'
        if stringWidth(candidate, font_name, font_size) <= max_width:
            current = candidate
            continue
        lines.append(current)
        current = word
    lines.append(current)

    final_lines = []
    for line in lines:
        if stringWidth(line, font_name, font_size) <= max_width:
            final_lines.append(line)
            continue
        chunk = ''
        for char in line:
            candidate = f'{chunk}{char}'
            if chunk and stringWidth(candidate, font_name, font_size) > max_width:
                final_lines.append(chunk)
                chunk = char
            else:
                chunk = candidate
        if chunk:
            final_lines.append(chunk)
    return final_lines


def _fit_text_rows(rows: list[dict], max_width: float, max_height: float) -> tuple[list[dict], float]:
    if not rows:
        return [], 0.0

    start_size = 10.0
    min_size = 5.0
    font_step = 0.5
    while start_size >= min_size:
        line_height = start_size * 1.18
        rendered = []
        used_height = 0.0
        fits = True

        for row in rows:
            font_name = 'Helvetica-Bold' if row['is_primary'] else 'Helvetica'
            wrapped = _wrap_text(row['text'], font_name, start_size, max_width)
            row_height = len(wrapped) * line_height
            if used_height + row_height > max_height + 0.01:
                fits = False
                break
            rendered.append({
                'font_name': font_name,
                'lines': wrapped,
            })
            used_height += row_height

        if fits:
            return rendered, start_size
        start_size -= font_step

    fallback_size = min_size
    fallback_line_height = fallback_size * 1.18
    rendered = []
    used_height = 0.0
    for row in rows:
        font_name = 'Helvetica-Bold' if row['is_primary'] else 'Helvetica'
        wrapped = _wrap_text(row['text'], font_name, fallback_size, max_width)
        kept_lines = []
        for line in wrapped:
            if used_height + fallback_line_height > max_height + 0.01:
                break
            kept_lines.append(line)
            used_height += fallback_line_height
        if not kept_lines:
            break
        rendered.append({
            'font_name': font_name,
            'lines': kept_lines,
        })
    if rendered and used_height > max_height + 0.01:
        rendered = rendered[:-1]
    return rendered, fallback_size


def generate_component_labels_pdf(components: list[Component], config: dict) -> tuple[bytes, dict]:
    normalized = normalize_label_config(config)
    layout = calculate_label_layout(normalized)

    packet = io.BytesIO()
    page_size = (normalized['page_width_mm'] * mm, normalized['page_height_mm'] * mm)
    pdf = canvas.Canvas(packet, pagesize=page_size)

    labels_per_page = layout.labels_per_page
    for index, component in enumerate(components):
        slot = index % labels_per_page
        if index and slot == 0:
            pdf.showPage()

        col = slot % layout.columns
        row = slot // layout.columns

        label_x_mm = layout.margin_left_mm + col * (layout.label_width_mm + layout.gap_horizontal_mm)
        label_y_mm = layout.page_height_mm - layout.margin_top_mm - (row + 1) * layout.label_height_mm - row * layout.gap_vertical_mm

        x = label_x_mm * mm
        y = label_y_mm * mm
        width = layout.label_width_mm * mm
        height = layout.label_height_mm * mm

        pdf.setLineWidth(0.4)
        pdf.setStrokeColorRGB(0.65, 0.65, 0.65)
        pdf.rect(x, y, width, height)

        inner_padding = 2.0 * mm
        content_x = x + inner_padding
        content_y = y + inner_padding
        content_w = width - 2 * inner_padding
        content_h = height - 2 * inner_padding

        qr_payload = build_qr_payload_for_component(component, normalized['qr_fields']) if normalized['qr_enabled'] else ''
        qr_size = 0.0
        if normalized['qr_enabled'] and qr_payload:
            qr_size = min(content_h, content_w * 0.34, 18.0 * mm)
            qr_png = make_qr_png(qr_payload, normalized['qr_error_correction'])
            qr_buffer = ImageReader(io.BytesIO(qr_png))
            pdf.drawImage(
                qr_buffer,
                content_x,
                content_y + max(0.0, (content_h - qr_size) / 2),
                qr_size,
                qr_size,
                preserveAspectRatio=True,
                mask='auto',
            )

        text_rows = build_label_text_rows(component, normalized['text_fields'])
        text_x = content_x + (qr_size + 2.0 * mm if qr_size else 0.0)
        text_w = content_w - (qr_size + 2.0 * mm if qr_size else 0.0)
        if text_w <= 5.0 * mm:
            text_x = content_x
            text_w = content_w

        rendered_rows, font_size = _fit_text_rows(text_rows, text_w, content_h)
        line_height = font_size * 1.18 if font_size else 0.0
        total_line_count = sum(len(item['lines']) for item in rendered_rows)
        total_height = total_line_count * line_height
        cursor_y = y + height - inner_padding - max(0.0, (content_h - total_height) / 2)

        for item in rendered_rows:
            pdf.setFont(item['font_name'], font_size)
            for line in item['lines']:
                pdf.drawString(text_x, cursor_y - font_size, line)
                cursor_y -= line_height

    pdf.save()
    packet.seek(0)
    metadata = build_layout_summary(normalized, len(components))
    metadata['config'] = normalized
    return packet.getvalue(), metadata
