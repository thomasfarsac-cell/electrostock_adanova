from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.auth import PASSWORD_FILE, is_auth_enabled
from app.config import APP_NAME, DATA_DIR, DB_URL
from app.db import Base
from app.services.env_settings import ENV_FILE, get_env_value
from app.services.prompt_presets import PRESETS_FILE


BACKUP_ENV_KEYS = [
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


def _csv_bytes(headers: list[str], rows: list[list[object]]) -> bytes:
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow(headers)
    for row in rows:
        writer.writerow(['' if value is None else value for value in row])
    return output.getvalue().encode('utf-8-sig')


def _serialize_value(value):
    if value is None:
        return ''
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, bool):
        return '1' if value else '0'
    return str(value)


def _build_table_csvs(session: Session) -> tuple[dict[str, bytes], dict[str, int]]:
    csv_files: dict[str, bytes] = {}
    row_counts: dict[str, int] = {}

    for table in Base.metadata.sorted_tables:
        columns = [column.name for column in table.columns]
        rows = session.execute(select(*table.c).order_by(*table.primary_key.columns)).mappings().all()
        serialized_rows = []
        for row in rows:
            serialized_rows.append([_serialize_value(row[column]) for column in columns])
        csv_files[f'db/{table.name}.csv'] = _csv_bytes(columns, serialized_rows)
        row_counts[table.name] = len(serialized_rows)

    return csv_files, row_counts


def _build_env_exports() -> tuple[bytes, bytes]:
    raw_lines = ENV_FILE.read_text(encoding='utf-8') if ENV_FILE.exists() else ''
    env_rows = []
    for key in BACKUP_ENV_KEYS:
        env_rows.append([key, get_env_value(key, '')])
    return raw_lines.encode('utf-8'), _csv_bytes(['key', 'value'], env_rows)


def _add_file_if_exists(zip_file: ZipFile, source_path: Path, target_path: str):
    if source_path.exists() and source_path.is_file():
        zip_file.write(source_path, target_path)


def _add_tree(zip_file: ZipFile, root: Path, target_root: str) -> int:
    if not root.exists():
        return 0
    count = 0
    for file_path in sorted(path for path in root.rglob('*') if path.is_file()):
        relative = file_path.relative_to(root).as_posix()
        zip_file.write(file_path, f'{target_root}/{relative}')
        count += 1
    return count


def build_backup_archive(session: Session) -> tuple[bytes, str]:
    buffer = io.BytesIO()
    created_at = datetime.now(timezone.utc)
    inspector = inspect(session.bind)
    env_raw, env_csv = _build_env_exports()
    table_csvs, row_counts = _build_table_csvs(session)
    filename = f"electrostock-backup-{created_at.strftime('%Y%m%d-%H%M%S')}.zip"

    with ZipFile(buffer, mode='w', compression=ZIP_DEFLATED) as zip_file:
        for archive_path, content in table_csvs.items():
            zip_file.writestr(archive_path, content)

        zip_file.writestr(
            'README.txt',
            (
                "Sauvegarde ElectroStock\n"
                "\n"
                "Contenu:\n"
                "- db/: un CSV par table SQL\n"
                "- settings/: configuration utile a la restauration\n"
                "- media/: images et miniatures\n"
                "- manifest.json: resume technique de l'archive\n"
            ).encode('utf-8'),
        )
        zip_file.writestr('settings/.env', env_raw)
        zip_file.writestr('settings/app_env.csv', env_csv)
        _add_file_if_exists(zip_file, PRESETS_FILE, 'settings/component_lookup_prompt_presets.json')
        _add_file_if_exists(zip_file, PASSWORD_FILE, 'settings/auth_password.hash')
        media_file_count = _add_tree(zip_file, DATA_DIR / 'images', 'media/images')

        manifest = {
            'app_name': APP_NAME,
            'created_at_utc': created_at.isoformat(),
            'db_url': DB_URL,
            'tables': row_counts,
            'table_names': inspector.get_table_names(),
            'env_keys': BACKUP_ENV_KEYS,
            'has_auth_password': is_auth_enabled(),
            'has_prompt_presets': PRESETS_FILE.exists(),
            'media_file_count': media_file_count,
            'format_version': 1,
        }
        zip_file.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf-8'))

    return buffer.getvalue(), filename
