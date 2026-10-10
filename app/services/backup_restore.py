from __future__ import annotations

import csv
import io
import json
import shutil
from datetime import datetime
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import PASSWORD_FILE
from app.config import DATA_DIR
from app.db import Base
from app.models import Category, Component, ComponentCustomFieldValue, CustomField, Location, Manufacturer, Package, StockMovement, Workshop
from app.services.env_settings import ENV_FILE, delete_env_value, set_env_value
from app.services.prompt_presets import PRESETS_FILE


RESTORE_ENV_KEYS = [
    'APP_NAME',
    'APP_DATA_DIR',
    'APP_DB_URL',
    'APP_SECRET_KEY',
    'APP_DISPLAY_NAME',
    'APP_ORGANIZATION_NAME',
    'APP_LOGO_PATH',
    'OPENAI_API_KEY',
    'OPENAI_COMPONENT_LOOKUP_MODEL',
    'OPENAI_COMPONENT_LOOKUP_USE_WEB_SEARCH',
    'OPENAI_COMPONENT_LOOKUP_TIMEOUT',
    'OPENAI_RESPONSES_API_URL',
    'OPENAI_COMPONENT_LOOKUP_SYSTEM_PROMPT',
]


def _read_csv_from_zip(zip_file: ZipFile, path: str) -> list[dict[str, str]]:
    try:
        raw = zip_file.read(path)
    except KeyError:
        return []
    text = raw.decode('utf-8-sig')
    reader = csv.DictReader(io.StringIO(text), delimiter=';')
    return [dict(row) for row in reader]


def _parse_datetime(value: str | None):
    text = (value or '').strip()
    if not text:
        return None
    return datetime.fromisoformat(text)


def _parse_int(value: str | None):
    text = (value or '').strip()
    if text == '':
        return None
    return int(text)


def _parse_bool(value: str | None):
    text = (value or '').strip().lower()
    if text == '':
        return None
    return text in {'1', 'true', 'yes', 'on'}


def _ensure_default_workshop(session: Session) -> Workshop:
    workshop = session.scalar(select(Workshop).where(Workshop.slug == 'electronics'))
    if workshop:
        return workshop
    workshop = Workshop(
        name='Electronique',
        slug='electronics',
        description='Atelier par defaut pour les donnees restaurees.',
        is_active=True,
        sort_order=0,
    )
    session.add(workshop)
    session.flush()
    return workshop


def _prepare_table_rows(zip_file: ZipFile) -> dict[str, list[dict[str, str]]]:
    return {
        table.name: _read_csv_from_zip(zip_file, f'db/{table.name}.csv')
        for table in Base.metadata.sorted_tables
    }


def _write_bytes(path: Path, content: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def _restore_media(zip_file: ZipFile, mode: str) -> int:
    image_root = DATA_DIR / 'images'
    if mode == 'replace' and image_root.exists():
        shutil.rmtree(image_root, ignore_errors=True)

    restored = 0
    for member in zip_file.namelist():
        if not member.startswith('media/images/') or member.endswith('/'):
            continue
        relative = member.removeprefix('media/images/')
        if not relative:
            continue
        target = (image_root / Path(relative)).resolve()
        if image_root.resolve() not in target.parents and target != image_root.resolve():
            continue
        _write_bytes(target, zip_file.read(member))
        restored += 1
    return restored


def _restore_settings(zip_file: ZipFile, mode: str) -> int:
    restored = 0
    env_rows = _read_csv_from_zip(zip_file, 'settings/app_env.csv')
    if env_rows:
        seen = set()
        for row in env_rows:
            key = str(row.get('key', '')).strip()
            if not key:
                continue
            set_env_value(key, str(row.get('value', '')))
            seen.add(key)
            restored += 1
        if mode == 'replace':
            for key in RESTORE_ENV_KEYS:
                if key not in seen:
                    delete_env_value(key)

    try:
        presets_raw = zip_file.read('settings/component_lookup_prompt_presets.json')
    except KeyError:
        presets_raw = None
    if presets_raw is not None:
        _write_bytes(PRESETS_FILE, presets_raw)
        restored += 1
    elif mode == 'replace' and PRESETS_FILE.exists():
        PRESETS_FILE.unlink(missing_ok=True)

    try:
        auth_raw = zip_file.read('settings/auth_password.hash')
    except KeyError:
        auth_raw = None
    if auth_raw is not None:
        _write_bytes(PASSWORD_FILE, auth_raw)
        restored += 1
    elif mode == 'replace' and PASSWORD_FILE.exists():
        PASSWORD_FILE.unlink(missing_ok=True)

    try:
        env_raw = zip_file.read('settings/.env')
    except KeyError:
        env_raw = None
    if env_raw is not None and mode == 'replace':
        _write_bytes(ENV_FILE, env_raw)
        restored += 1

    return restored


def _coerce_raw_table_row(table, row: dict[str, str]) -> dict:
    values = {}
    for column in table.columns:
        raw = row.get(column.name, '')
        if table.name == 'users' and column.name == 'theme_id' and not str(raw or '').strip():
            values[column.name] = 'sober_dark'
            continue
        if raw == '' and column.nullable:
            values[column.name] = None
            continue
        python_type = getattr(column.type, 'python_type', str)
        if python_type is int:
            values[column.name] = int(raw) if raw != '' else 0
        elif python_type is bool:
            values[column.name] = raw.strip().lower() in {'1', 'true', 'yes', 'on'}
        elif python_type.__name__ == 'datetime':
            values[column.name] = _parse_datetime(raw)
        else:
            values[column.name] = raw
    return values


def _replace_database(session: Session, rows_by_table: dict[str, list[dict[str, str]]]) -> dict[str, int]:
    counts = {}
    for table in reversed(Base.metadata.sorted_tables):
        session.execute(table.delete())
    session.flush()

    for table in Base.metadata.sorted_tables:
        prepared = [_coerce_raw_table_row(table, row) for row in rows_by_table.get(table.name, [])]
        if prepared:
            session.execute(table.insert(), prepared)
        counts[table.name] = len(prepared)
    session.flush()
    _backfill_default_workshop(session)
    return counts


def _backfill_default_workshop(session: Session):
    default_workshop = _ensure_default_workshop(session)
    for model_class in (Category, Manufacturer, Package, Location, CustomField, Component):
        for item in session.scalars(select(model_class).where(model_class.workshop_id.is_(None))).all():
            item.workshop_id = default_workshop.id
    session.flush()


def _merge_workshops(session: Session, rows: list[dict[str, str]]) -> tuple[dict[int, int], int, Workshop]:
    default_workshop = _ensure_default_workshop(session)
    existing_items = session.scalars(select(Workshop)).all()
    by_slug = {item.slug.strip().lower(): item for item in existing_items}
    mapped: dict[int, int] = {}
    created = 0
    for row in rows:
        source_id = _parse_int(row.get('id'))
        name = str(row.get('name', '')).strip()
        slug = str(row.get('slug', '')).strip().lower()
        if not source_id or not name or not slug:
            continue
        item = by_slug.get(slug)
        if item is None:
            item = Workshop(name=name, slug=slug)
            session.add(item)
            session.flush()
            by_slug[slug] = item
            created += 1
        item.name = name
        item.description = str(row.get('description', '')).strip() or None
        item.is_active = bool(_parse_bool(row.get('is_active')))
        item.sort_order = _parse_int(row.get('sort_order')) or 0
        item.ai_prompt = str(row.get('ai_prompt', '')).strip() or None
        item.item_profile_json = str(row.get('item_profile_json', '')).strip() or None
        mapped[source_id] = item.id
    return mapped, created, default_workshop


def _resolve_workshop_id(row: dict[str, str], workshop_map: dict[int, int], default_workshop: Workshop) -> int:
    return workshop_map.get(_parse_int(row.get('workshop_id'))) or default_workshop.id


def _merge_categories(session: Session, rows: list[dict[str, str]], workshop_map: dict[int, int], default_workshop: Workshop) -> tuple[dict[int, int], int]:
    source_rows = {int(row['id']): row for row in rows if str(row.get('id', '')).strip().isdigit()}
    existing_rows = session.scalars(select(Category).order_by(Category.sort_order, Category.name)).all()
    count = 0
    mapped: dict[int, int] = {}
    pending = set(source_rows)

    while pending:
        progressed = False
        for source_id in list(pending):
            row = source_rows[source_id]
            parent_source = _parse_int(row.get('parent_id'))
            if parent_source is not None and parent_source not in mapped:
                continue
            parent_id = mapped.get(parent_source) if parent_source is not None else None
            name = str(row.get('name', '')).strip()
            workshop_id = _resolve_workshop_id(row, workshop_map, default_workshop)
            existing = next(
                (
                    item for item in existing_rows
                    if item.name.strip().lower() == name.lower() and (item.parent_id or None) == parent_id and item.workshop_id == workshop_id
                ),
                None,
            )
            if existing is None:
                existing = Category(name=name, workshop_id=workshop_id, parent_id=parent_id)
                session.add(existing)
                session.flush()
                existing_rows.append(existing)
                count += 1
            existing.sort_order = _parse_int(row.get('sort_order')) or 0
            existing.is_active = bool(_parse_bool(row.get('is_active')))
            existing.workshop_id = workshop_id
            mapped[source_id] = existing.id
            pending.remove(source_id)
            progressed = True
        if not progressed:
            break
    return mapped, count


def _merge_named_model(session: Session, model_class, rows: list[dict[str, str]], extra_fields: list[str], workshop_map: dict[int, int] | None = None, default_workshop: Workshop | None = None) -> tuple[dict[int, int], int]:
    existing_items = session.scalars(select(model_class)).all()
    by_name = {item.name.strip().lower(): item for item in existing_items}
    mapped: dict[int, int] = {}
    created = 0
    for row in rows:
        source_id = _parse_int(row.get('id'))
        name = str(row.get('name', '')).strip()
        if not source_id or not name:
            continue
        workshop_id = _resolve_workshop_id(row, workshop_map, default_workshop) if workshop_map is not None and default_workshop is not None and hasattr(model_class, 'workshop_id') else None
        item = None
        for candidate in existing_items:
            if candidate.name.strip().lower() == name.lower() and (workshop_id is None or getattr(candidate, 'workshop_id', None) == workshop_id):
                item = candidate
                break
        if item is None:
            item = model_class(name=name)
            if workshop_id is not None:
                item.workshop_id = workshop_id
            session.add(item)
            session.flush()
            by_name[name.lower()] = item
            created += 1
        for field in extra_fields:
            raw = row.get(field, '')
            setattr(item, field, raw or None)
        if workshop_id is not None:
            item.workshop_id = workshop_id
        mapped[source_id] = item.id
    return mapped, created


def _merge_custom_fields(session: Session, rows: list[dict[str, str]], workshop_map: dict[int, int], default_workshop: Workshop) -> tuple[dict[int, int], int]:
    existing_items = session.scalars(select(CustomField)).all()
    by_slug = {item.slug.strip().lower(): item for item in existing_items}
    by_name = {item.name.strip().lower(): item for item in existing_items}
    mapped: dict[int, int] = {}
    created = 0
    for row in rows:
        source_id = _parse_int(row.get('id'))
        slug = str(row.get('slug', '')).strip()
        name = str(row.get('name', '')).strip()
        if not source_id or not slug or not name:
            continue
        workshop_id = _resolve_workshop_id(row, workshop_map, default_workshop)
        item = by_slug.get(slug.lower()) or by_name.get(name.lower())
        if item is None:
            item = CustomField(name=name, workshop_id=workshop_id, slug=slug)
            session.add(item)
            session.flush()
            by_slug[slug.lower()] = item
            by_name[name.lower()] = item
            created += 1
        item.name = name
        item.workshop_id = workshop_id
        item.slug = slug
        item.field_type = str(row.get('field_type', '')).strip() or 'text'
        item.unit = str(row.get('unit', '')).strip() or None
        item.is_active = bool(_parse_bool(row.get('is_active')))
        item.sort_order = _parse_int(row.get('sort_order')) or 0
        mapped[source_id] = item.id
    return mapped, created


def _merge_components(
    session: Session,
    rows: list[dict[str, str]],
    category_map: dict[int, int],
    manufacturer_map: dict[int, int],
    package_map: dict[int, int],
    location_map: dict[int, int],
    workshop_map: dict[int, int],
    default_workshop: Workshop,
) -> tuple[dict[int, int], set[int], int]:
    existing_items = session.scalars(select(Component)).all()
    by_part_number = {item.part_number.strip().lower(): item for item in existing_items}
    mapped: dict[int, int] = {}
    new_component_ids: set[int] = set()
    created = 0

    for row in rows:
        source_id = _parse_int(row.get('id'))
        part_number = str(row.get('part_number', '')).strip()
        if not source_id or not part_number:
            continue
        workshop_id = _resolve_workshop_id(row, workshop_map, default_workshop)
        item = by_part_number.get(part_number.lower())
        is_new = item is None
        if item is None:
            item = Component(part_number=part_number, name=str(row.get('name', '')).strip() or part_number, quantity=0)
            session.add(item)
            session.flush()
            by_part_number[part_number.lower()] = item
            new_component_ids.add(item.id)
            created += 1

        item.part_number = part_number
        item.name = str(row.get('name', '')).strip() or part_number
        item.workshop_id = workshop_id
        item.category_id = category_map.get(_parse_int(row.get('category_id')))
        item.manufacturer_id = manufacturer_map.get(_parse_int(row.get('manufacturer_id')))
        item.package_id = package_map.get(_parse_int(row.get('package_id')))
        item.location_id = location_map.get(_parse_int(row.get('location_id')))
        if is_new:
            item.quantity = _parse_int(row.get('quantity')) or 0
        item.minimum_quantity = _parse_int(row.get('minimum_quantity')) or 0
        item.datasheet_url = str(row.get('datasheet_url', '')).strip() or None
        item.image_path = str(row.get('image_path', '')).strip() or None
        item.thumbnail_path = str(row.get('thumbnail_path', '')).strip() or None
        item.description = str(row.get('description', '')).strip() or None
        item.notes = str(row.get('notes', '')).strip() or None
        item.keywords = str(row.get('keywords', '')).strip() or None
        mapped[source_id] = item.id
    return mapped, new_component_ids, created


def _merge_custom_values(
    session: Session,
    rows: list[dict[str, str]],
    component_map: dict[int, int],
    custom_field_map: dict[int, int],
) -> int:
    existing_items = session.scalars(select(ComponentCustomFieldValue)).all()
    existing_map = {(item.component_id, item.custom_field_id): item for item in existing_items}
    created = 0

    for row in rows:
        component_id = component_map.get(_parse_int(row.get('component_id')))
        custom_field_id = custom_field_map.get(_parse_int(row.get('custom_field_id')))
        if not component_id or not custom_field_id:
            continue
        value = str(row.get('value', '')).strip()
        item = existing_map.get((component_id, custom_field_id))
        if item is None:
            item = ComponentCustomFieldValue(component_id=component_id, custom_field_id=custom_field_id)
            session.add(item)
            existing_map[(component_id, custom_field_id)] = item
            created += 1
        item.value = value or None
    return created


def _movement_signature(item: StockMovement):
    return (
        item.component_id,
        item.movement_type or '',
        item.quantity_delta,
        item.resulting_quantity,
        item.reason or '',
        item.notes or '',
        item.source or '',
        item.reference or '',
        item.created_at.isoformat() if item.created_at else '',
    )


def _merge_stock_movements(session: Session, rows: list[dict[str, str]], component_map: dict[int, int]) -> int:
    existing_items = session.scalars(select(StockMovement)).all()
    existing_signatures = {_movement_signature(item) for item in existing_items}
    created = 0

    for row in rows:
        component_id = component_map.get(_parse_int(row.get('component_id')))
        if not component_id:
            continue
        item = StockMovement(
            component_id=component_id,
            movement_type=str(row.get('movement_type', '')).strip() or 'adjustment',
            quantity_delta=_parse_int(row.get('quantity_delta')) or 0,
            resulting_quantity=_parse_int(row.get('resulting_quantity')) or 0,
            reason=str(row.get('reason', '')).strip() or None,
            notes=str(row.get('notes', '')).strip() or None,
            source=str(row.get('source', '')).strip() or None,
            reference=str(row.get('reference', '')).strip() or None,
            created_at=_parse_datetime(row.get('created_at')) or datetime.utcnow(),
        )
        signature = _movement_signature(item)
        if signature in existing_signatures:
            continue
        session.add(item)
        existing_signatures.add(signature)
        created += 1
    return created


def _merge_database(session: Session, rows_by_table: dict[str, list[dict[str, str]]]) -> dict[str, int]:
    counts = {}
    workshop_map, counts['workshops'], default_workshop = _merge_workshops(session, rows_by_table.get('workshops', []))
    category_map, counts['categories'] = _merge_categories(session, rows_by_table.get('categories', []), workshop_map, default_workshop)
    manufacturer_map, counts['manufacturers'] = _merge_named_model(session, Manufacturer, rows_by_table.get('manufacturers', []), ['website_url', 'notes'], workshop_map, default_workshop)
    package_map, counts['packages'] = _merge_named_model(session, Package, rows_by_table.get('packages', []), ['description'], workshop_map, default_workshop)
    location_map, counts['locations'] = _merge_named_model(session, Location, rows_by_table.get('locations', []), ['description', 'image_path', 'thumbnail_path'], workshop_map, default_workshop)
    custom_field_map, counts['custom_fields'] = _merge_custom_fields(session, rows_by_table.get('custom_fields', []), workshop_map, default_workshop)
    component_map, _, counts['components'] = _merge_components(
        session,
        rows_by_table.get('components', []),
        category_map,
        manufacturer_map,
        package_map,
        location_map,
        workshop_map,
        default_workshop,
    )
    counts['component_custom_field_values'] = _merge_custom_values(
        session,
        rows_by_table.get('component_custom_field_values', []),
        component_map,
        custom_field_map,
    )
    counts['stock_movements'] = _merge_stock_movements(session, rows_by_table.get('stock_movements', []), component_map)
    session.flush()
    return counts


def restore_backup_archive(session: Session, archive_bytes: bytes, mode: str = 'merge') -> dict:
    try:
        zip_file = ZipFile(io.BytesIO(archive_bytes))
    except BadZipFile as exc:
        raise ValueError("L'archive fournie n'est pas un fichier ZIP valide.") from exc

    with zip_file:
        try:
            manifest = json.loads(zip_file.read('manifest.json').decode('utf-8'))
        except KeyError:
            manifest = {}
        except json.JSONDecodeError:
            manifest = {}

        rows_by_table = _prepare_table_rows(zip_file)

        try:
            if mode == 'replace':
                db_counts = _replace_database(session, rows_by_table)
            else:
                db_counts = _merge_database(session, rows_by_table)
            media_count = _restore_media(zip_file, mode)
            settings_count = _restore_settings(zip_file, mode)
            session.commit()
        except Exception:
            session.rollback()
            raise

    return {
        'mode': mode,
        'manifest': manifest,
        'db_counts': db_counts,
        'media_count': media_count,
        'settings_count': settings_count,
    }
