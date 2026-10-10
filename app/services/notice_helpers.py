from __future__ import annotations


def users_notice(tone: str, message: str):
    return {'tone': tone, 'message': message}


def build_restore_notice(summary: dict):
    db_counts = summary.get('db_counts', {})
    changed_tables = []
    for table_name, count in db_counts.items():
        if count:
            changed_tables.append(f'{table_name}: {count}')

    message_parts = [
        f"Restauration terminee en mode {summary.get('mode')}.",
    ]
    if changed_tables:
        message_parts.append('Donnees traitees: ' + ' | '.join(changed_tables[:8]))
    message_parts.append(f"Fichiers media: {summary.get('media_count', 0)}.")
    message_parts.append(f"Elements de configuration: {summary.get('settings_count', 0)}.")
    manifest = summary.get('manifest') or {}
    if manifest.get('created_at_utc'):
        message_parts.append(f"Archive creee le {manifest['created_at_utc']}.")
    return {
        'tone': 'success',
        'message': ' '.join(message_parts),
    }
