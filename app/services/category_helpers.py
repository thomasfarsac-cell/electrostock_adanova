from __future__ import annotations

from app.models import Category
from app.services.categories import build_category_path, get_descendant_ids


def get_category_children_map(categories):
    children_map = {}
    for category in categories:
        children_map.setdefault(str(category.parent_id or 'root'), []).append({
            'id': category.id,
            'name': category.name,
            'path': build_category_path(category),
            'sort_order': category.sort_order,
        })
    for key in children_map:
        children_map[key].sort(key=lambda item: (item['sort_order'], item['name'].lower()))
    return children_map


def get_category_chain_ids(category: Category | None) -> list[int]:
    ids = []
    current = category
    while current is not None:
        ids.append(current.id)
        current = current.parent
    return list(reversed(ids))


def get_category_chain_labels(categories: list[Category], selected_category_id: int | None = None):
    by_id = {category.id: category for category in categories}
    selected = by_id.get(selected_category_id) if selected_category_id else None
    chain_ids = get_category_chain_ids(selected) if selected else []

    labels = []
    parent_id = None
    level = 1
    while True:
        children = [item for item in categories if item.parent_id == parent_id]
        if not children:
            break
        labels.append({'level': level, 'label': f'Niveau {level}'})
        next_selected = chain_ids[level - 1] if len(chain_ids) >= level else None
        if next_selected is None:
            break
        parent_id = next_selected
        level += 1
    if not labels:
        labels = [{'level': 1, 'label': 'Niveau 1'}]
    return labels


def get_descendants_for_cycle_check(category: Category) -> set[int]:
    return set(get_descendant_ids(category))
