from __future__ import annotations

import os

from app.config import BASE_DIR

ENV_FILE = BASE_DIR / '.env'


def _read_env_lines() -> list[str]:
    if not ENV_FILE.exists():
        return []
    return ENV_FILE.read_text(encoding='utf-8').splitlines()


def _parse_line(raw_line: str):
    line = raw_line.strip()
    if not line or line.startswith('#') or '=' not in line:
        return None, None
    key, value = line.split('=', 1)
    return key.strip(), value.strip()


def get_env_value(key: str, default: str = '') -> str:
    for raw_line in _read_env_lines():
        current_key, value = _parse_line(raw_line)
        if current_key == key:
            return value.strip().strip('"').strip("'")
    runtime_value = os.getenv(key)
    if runtime_value not in (None, ''):
        return runtime_value
    return default


def set_env_value(key: str, value: str):
    lines = _read_env_lines()
    updated = False
    new_lines = []
    for raw_line in lines:
        current_key, _ = _parse_line(raw_line)
        if current_key == key:
            new_lines.append(f'{key}={value}')
            updated = True
        else:
            new_lines.append(raw_line)
    if not updated:
        new_lines.append(f'{key}={value}')
    ENV_FILE.write_text('\n'.join(new_lines).rstrip() + '\n', encoding='utf-8')
    os.environ[key] = value


def delete_env_value(key: str):
    lines = _read_env_lines()
    kept_lines = []
    for raw_line in lines:
        current_key, _ = _parse_line(raw_line)
        if current_key != key:
            kept_lines.append(raw_line)
    content = '\n'.join(kept_lines).strip()
    ENV_FILE.write_text((content + '\n') if content else '', encoding='utf-8')
    os.environ.pop(key, None)


def mask_secret(value: str, visible_prefix: int = 13) -> str:
    if not value:
        return ''
    if len(value) <= visible_prefix:
        return value
    return value[:visible_prefix] + '....'
