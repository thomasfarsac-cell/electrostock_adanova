from __future__ import annotations

from urllib.parse import urlencode


def build_query_string(filters: dict):
    cleaned = {}
    for key, value in filters.items():
        if value is None:
            continue
        text = str(value).strip()
        if text == '':
            continue
        cleaned[key] = text
    return urlencode(cleaned)


def parse_id_list(raw_value) -> list[int]:
    if isinstance(raw_value, list):
        values = raw_value
    else:
        values = str(raw_value or '').split(',')
    parsed = []
    for item in values:
        text = str(item or '').strip()
        if text.isdigit():
            parsed.append(int(text))
    return parsed
