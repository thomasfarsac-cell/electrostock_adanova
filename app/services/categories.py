from __future__ import annotations

from app.config import MAX_CATEGORY_DEPTH


def get_depth(category) -> int:
    depth = 1
    current = category
    while current and current.parent is not None:
        depth += 1
        current = current.parent
    return depth


def build_category_path(category) -> str:
    if category is None:
        return ''
    names = []
    current = category
    while current is not None:
        names.append(current.name)
        current = current.parent
    return ' / '.join(reversed(names))


def get_descendant_ids(category) -> list[int]:
    ids = [category.id]
    for child in category.children:
        ids.extend(get_descendant_ids(child))
    return ids


def validate_parent_depth(parent):
    if parent is None:
        return True
    depth = get_depth(parent)
    if depth >= MAX_CATEGORY_DEPTH:
        raise ValueError(f'Profondeur maximale atteinte ({MAX_CATEGORY_DEPTH} niveaux).')
    return True
