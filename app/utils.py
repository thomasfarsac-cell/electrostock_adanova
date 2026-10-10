import re
from collections import defaultdict


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r'[^a-z0-9]+', '-', value)
    value = re.sub(r'-+', '-', value).strip('-')
    return value or 'field'


def parse_int(value, default=0):
    try:
        text = str(value).strip()
        if text == '':
            return default
        return int(float(text.replace(',', '.')))
    except (TypeError, ValueError):
        return default


def parse_optional_int(value):
    text = str(value).strip() if value is not None else ''
    if text == '':
        return None
    try:
        return int(text)
    except ValueError:
        return None


def group_categories(categories):
    grouped = defaultdict(list)
    for category in categories:
        grouped[category.parent_id].append(category)
    return grouped


def normalize_lookup(value: str | None) -> str:
    return re.sub(r'\s+', ' ', (value or '').strip().lower())
