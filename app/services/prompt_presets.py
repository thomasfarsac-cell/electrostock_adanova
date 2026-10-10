from __future__ import annotations

import json
from uuid import uuid4

from app.config import DATA_DIR

PRESETS_FILE = DATA_DIR / 'component_lookup_prompt_presets.json'
DEFAULT_PRESET_ID = 'default'


def _read_presets() -> list[dict]:
    if not PRESETS_FILE.exists():
        return []
    try:
        data = json.loads(PRESETS_FILE.read_text(encoding='utf-8'))
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _write_presets(items: list[dict]):
    PRESETS_FILE.parent.mkdir(parents=True, exist_ok=True)
    PRESETS_FILE.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding='utf-8')


def list_prompt_presets(default_prompt: str) -> list[dict]:
    stored = _read_presets()
    default_item = {
        'id': DEFAULT_PRESET_ID,
        'name': 'Preset par defaut',
        'prompt': default_prompt,
        'is_default': True,
    }
    custom_items = []
    for item in stored:
        if not isinstance(item, dict):
            continue
        preset_id = str(item.get('id', '')).strip()
        name = str(item.get('name', '')).strip()
        prompt = str(item.get('prompt', '')).strip()
        if not preset_id or not name or not prompt:
            continue
        custom_items.append({
            'id': preset_id,
            'name': name,
            'prompt': prompt,
            'is_default': False,
        })
    return [default_item, *custom_items]


def create_prompt_preset(name: str, prompt: str):
    items = _read_presets()
    items.append({
        'id': uuid4().hex,
        'name': name.strip(),
        'prompt': prompt.strip(),
    })
    _write_presets(items)


def update_prompt_preset(preset_id: str, name: str, prompt: str):
    if preset_id == DEFAULT_PRESET_ID:
        return
    items = _read_presets()
    for item in items:
        if str(item.get('id')) == preset_id:
            item['name'] = name.strip()
            item['prompt'] = prompt.strip()
            break
    _write_presets(items)


def delete_prompt_preset(preset_id: str):
    if preset_id == DEFAULT_PRESET_ID:
        return
    items = [item for item in _read_presets() if str(item.get('id')) != preset_id]
    _write_presets(items)


def get_prompt_preset(preset_id: str, default_prompt: str) -> dict | None:
    for item in list_prompt_presets(default_prompt):
        if item['id'] == preset_id:
            return item
    return None
