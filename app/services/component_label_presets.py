from __future__ import annotations

import json
from uuid import uuid4

from app.config import DATA_DIR
from app.services.component_labels import get_default_label_config, get_page_format_options, normalize_label_config

PRESETS_FILE = DATA_DIR / 'component_label_presets.json'

PRESET_KINDS = {
    'page_formats': 'page_formats',
    'layout_presets': 'layout_presets',
    'global_presets': 'global_presets',
}

DEFAULT_LAYOUT_PRESET = {
    'id': 'atelier-standard',
    'name': 'Atelier standard 48x25',
    'built_in': True,
    'payload': {
        'margin_top_mm': 12.0,
        'margin_bottom_mm': 12.0,
        'margin_left_mm': 8.0,
        'margin_right_mm': 8.0,
        'gap_horizontal_mm': 2.0,
        'gap_vertical_mm': 2.0,
        'label_width_mm': 48.0,
        'label_height_mm': 25.0,
    },
}

DEFAULT_GLOBAL_PRESET = {
    'id': 'default-global',
    'name': 'Preset global atelier',
    'built_in': True,
    'payload': get_default_label_config(),
}


def _read_presets() -> dict:
    if not PRESETS_FILE.exists():
        return {}
    try:
        data = json.loads(PRESETS_FILE.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _write_presets(payload: dict):
    PRESETS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PRESETS_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')


def _sanitize_custom_items(items) -> list[dict]:
    sanitized = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        preset_id = str(item.get('id', '')).strip()
        name = str(item.get('name', '')).strip()
        payload = item.get('payload')
        if not preset_id or not name or not isinstance(payload, dict):
            continue
        sanitized.append({
            'id': preset_id,
            'name': name,
            'payload': payload,
            'built_in': False,
        })
    return sanitized


def list_component_label_presets() -> dict:
    stored = _read_presets()
    page_formats = [*get_page_format_options(), *_sanitize_custom_items(stored.get('page_formats'))]
    layout_presets = [dict(DEFAULT_LAYOUT_PRESET), *_sanitize_custom_items(stored.get('layout_presets'))]
    global_presets = [dict(DEFAULT_GLOBAL_PRESET), *_sanitize_custom_items(stored.get('global_presets'))]
    return {
        'page_formats': page_formats,
        'layout_presets': layout_presets,
        'global_presets': global_presets,
    }


def save_component_label_preset(kind: str, name: str, payload: dict, preset_id: str | None = None) -> dict:
    normalized_kind = PRESET_KINDS.get(kind)
    if not normalized_kind:
        raise ValueError('Type de preset invalide.')

    clean_name = str(name or '').strip()
    if not clean_name:
        raise ValueError('Le nom du preset est obligatoire.')

    stored = _read_presets()
    items = _sanitize_custom_items(stored.get(normalized_kind))
    target_id = str(preset_id or '').strip()

    normalized_payload = dict(payload)
    if normalized_kind == 'global_presets':
        normalized_payload = normalize_label_config(payload)

    if normalized_kind == 'page_formats':
        normalized_payload = {
            'width_mm': round(max(20.0, float(payload.get('width_mm', 0))), 3),
            'height_mm': round(max(20.0, float(payload.get('height_mm', 0))), 3),
        }

    if normalized_kind == 'layout_presets':
        normalized_payload = {
            'margin_top_mm': round(max(0.0, float(payload.get('margin_top_mm', 0))), 3),
            'margin_bottom_mm': round(max(0.0, float(payload.get('margin_bottom_mm', 0))), 3),
            'margin_left_mm': round(max(0.0, float(payload.get('margin_left_mm', 0))), 3),
            'margin_right_mm': round(max(0.0, float(payload.get('margin_right_mm', 0))), 3),
            'gap_horizontal_mm': round(max(0.0, float(payload.get('gap_horizontal_mm', 0))), 3),
            'gap_vertical_mm': round(max(0.0, float(payload.get('gap_vertical_mm', 0))), 3),
            'label_width_mm': round(max(5.0, float(payload.get('label_width_mm', 0))), 3),
            'label_height_mm': round(max(5.0, float(payload.get('label_height_mm', 0))), 3),
        }

    if target_id:
        found = False
        for item in items:
            if item['id'] == target_id:
                item['name'] = clean_name
                item['payload'] = normalized_payload
                found = True
                break
        if not found:
            items.append({
                'id': target_id,
                'name': clean_name,
                'payload': normalized_payload,
                'built_in': False,
            })
    else:
        target_id = uuid4().hex
        items.append({
            'id': target_id,
            'name': clean_name,
            'payload': normalized_payload,
            'built_in': False,
        })

    stored[normalized_kind] = [{key: value for key, value in item.items() if key != 'built_in'} for item in items]
    _write_presets(stored)
    return {
        'id': target_id,
        'name': clean_name,
        'payload': normalized_payload,
        'built_in': False,
    }


def delete_component_label_preset(kind: str, preset_id: str):
    normalized_kind = PRESET_KINDS.get(kind)
    if not normalized_kind:
        raise ValueError('Type de preset invalide.')
    if preset_id in {'atelier-standard', 'default-global', 'a4', 'a5'}:
        raise ValueError('Ce preset integre ne peut pas etre supprime.')

    stored = _read_presets()
    items = _sanitize_custom_items(stored.get(normalized_kind))
    stored[normalized_kind] = [
        {key: value for key, value in item.items() if key != 'built_in'}
        for item in items
        if item['id'] != preset_id
    ]
    _write_presets(stored)
