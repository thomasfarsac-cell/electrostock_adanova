from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Callable

from sqlalchemy.engine import Connection
from sqlalchemy import inspect, text

logger = logging.getLogger('uvicorn.error')

SCHEMA_MIGRATIONS_TABLE = 'schema_migrations'
MIGRATION_MANAGED_TABLES = {'users', 'workshops'}


@dataclass(frozen=True)
class Migration:
    id: str
    name: str
    apply: Callable[[Connection], None]


def ensure_optional_columns(engine):
    inspector = inspect(engine)
    existing_columns = {column['name'] for column in inspector.get_columns('locations')}
    statements = []

    if 'image_path' not in existing_columns:
        statements.append("ALTER TABLE locations ADD COLUMN image_path VARCHAR(300)")
    if 'thumbnail_path' not in existing_columns:
        statements.append("ALTER TABLE locations ADD COLUMN thumbnail_path VARCHAR(300)")

    if not statements:
        return

    with engine.begin() as connection:
        for statement in statements:
            logger.info('Applying schema safety fix: %s', statement)
            connection.execute(text(statement))


def baseline_existing_schema(connection: Connection):
    """No-op baseline: the existing schema is now tracked by migrations."""
    return None


def create_users_table(connection: Connection):
    connection.execute(text("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username VARCHAR(80) NOT NULL UNIQUE,
            password_hash VARCHAR(300) NOT NULL,
            role VARCHAR(30) NOT NULL CHECK (role IN ('admin', 'stock_manager', 'viewer')),
            is_active BOOLEAN NOT NULL DEFAULT 1,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_login_at DATETIME
        )
    """))


def add_user_profile_fields(connection: Connection):
    existing_columns = {column['name'] for column in inspect(connection).get_columns('users')}
    statements = []
    if 'first_name' not in existing_columns:
        statements.append("ALTER TABLE users ADD COLUMN first_name VARCHAR(120)")
    if 'last_name' not in existing_columns:
        statements.append("ALTER TABLE users ADD COLUMN last_name VARCHAR(120)")
    if 'display_name' not in existing_columns:
        statements.append("ALTER TABLE users ADD COLUMN display_name VARCHAR(120)")
    if 'email' not in existing_columns:
        statements.append("ALTER TABLE users ADD COLUMN email VARCHAR(200)")
    for statement in statements:
        logger.info('Applying user profile schema change: %s', statement)
        connection.execute(text(statement))


def _column_names(connection: Connection, table_name: str) -> set[str]:
    return {column['name'] for column in inspect(connection).get_columns(table_name)}


def _table_exists(connection: Connection, table_name: str) -> bool:
    return table_name in inspect(connection).get_table_names()


def _row_count(connection: Connection, table_name: str) -> int:
    if not _table_exists(connection, table_name):
        return 0
    return int(connection.execute(text(f'SELECT COUNT(*) FROM {table_name}')).scalar_one() or 0)


def _any_rows(connection: Connection, table_names: tuple[str, ...]) -> bool:
    return any(_row_count(connection, table_name) > 0 for table_name in table_names)


def _ensure_default_workshop(connection: Connection) -> int:
    row = connection.execute(text("SELECT id FROM workshops WHERE slug = 'electronics'")).first()
    if row:
        return int(row[0])
    connection.execute(text("""
        INSERT INTO workshops (name, slug, description, is_active, sort_order, ai_prompt, created_at, updated_at)
        VALUES ('Electronique', 'electronics', 'Atelier par defaut pour les donnees existantes.', 1, 0, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    """))
    return int(connection.execute(text("SELECT id FROM workshops WHERE slug = 'electronics'")).scalar_one())


def create_workshops_and_scope_stock(connection: Connection):
    connection.execute(text("""
        CREATE TABLE IF NOT EXISTS workshops (
            id INTEGER PRIMARY KEY,
            name VARCHAR(120) NOT NULL,
            slug VARCHAR(120) NOT NULL UNIQUE,
            description TEXT,
            is_active BOOLEAN NOT NULL DEFAULT 1,
            sort_order INTEGER NOT NULL DEFAULT 0,
            ai_prompt TEXT,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """))
    scoped_tables = ('components', 'categories', 'locations', 'custom_fields')
    default_workshop_id = _ensure_default_workshop(connection) if _any_rows(connection, scoped_tables) else None

    for table_name in scoped_tables:
        if not _table_exists(connection, table_name):
            continue
        if 'workshop_id' not in _column_names(connection, table_name):
            statement = f"ALTER TABLE {table_name} ADD COLUMN workshop_id INTEGER REFERENCES workshops(id) ON DELETE SET NULL"
            logger.info('Applying workshop schema change: %s', statement)
            connection.execute(text(statement))
        if default_workshop_id is not None:
            connection.execute(
                text(f"UPDATE {table_name} SET workshop_id = :workshop_id WHERE workshop_id IS NULL"),
                {'workshop_id': default_workshop_id},
            )

    if _table_exists(connection, 'users') and 'active_workshop_id' not in _column_names(connection, 'users'):
        statement = "ALTER TABLE users ADD COLUMN active_workshop_id INTEGER REFERENCES workshops(id) ON DELETE SET NULL"
        logger.info('Applying workshop preference schema change: %s', statement)
        connection.execute(text(statement))


def _rebuild_locations_for_workshop_uniqueness(connection: Connection):
    if not _table_exists(connection, 'locations') or 'locations_old_unique' in inspect(connection).get_table_names():
        return
    logger.info('Rebuilding locations table to remove global name uniqueness.')
    connection.execute(text('PRAGMA foreign_keys=OFF'))
    connection.execute(text('ALTER TABLE locations RENAME TO locations_old_unique'))
    connection.execute(text("""
        CREATE TABLE locations (
            id INTEGER PRIMARY KEY,
            name VARCHAR(120) NOT NULL,
            workshop_id INTEGER REFERENCES workshops(id) ON DELETE SET NULL,
            description TEXT,
            image_path VARCHAR(300),
            thumbnail_path VARCHAR(300),
            created_at DATETIME,
            updated_at DATETIME
        )
    """))
    connection.execute(text("""
        INSERT INTO locations (id, name, workshop_id, description, image_path, thumbnail_path, created_at, updated_at)
        SELECT id, name, workshop_id, description, image_path, thumbnail_path, created_at, updated_at
        FROM locations_old_unique
    """))
    connection.execute(text('DROP TABLE locations_old_unique'))
    connection.execute(text('PRAGMA foreign_keys=ON'))


def _rebuild_custom_fields_for_workshop_uniqueness(connection: Connection):
    if not _table_exists(connection, 'custom_fields') or 'custom_fields_old_unique' in inspect(connection).get_table_names():
        return
    logger.info('Rebuilding custom_fields table to remove global name/slug uniqueness.')
    connection.execute(text('PRAGMA foreign_keys=OFF'))
    connection.execute(text('ALTER TABLE custom_fields RENAME TO custom_fields_old_unique'))
    connection.execute(text("""
        CREATE TABLE custom_fields (
            id INTEGER PRIMARY KEY,
            name VARCHAR(120) NOT NULL,
            workshop_id INTEGER REFERENCES workshops(id) ON DELETE SET NULL,
            slug VARCHAR(120) NOT NULL,
            field_type VARCHAR(20),
            unit VARCHAR(30),
            is_active BOOLEAN,
            sort_order INTEGER,
            created_at DATETIME,
            updated_at DATETIME
        )
    """))
    connection.execute(text("""
        INSERT INTO custom_fields (id, name, workshop_id, slug, field_type, unit, is_active, sort_order, created_at, updated_at)
        SELECT id, name, workshop_id, slug, field_type, unit, is_active, sort_order, created_at, updated_at
        FROM custom_fields_old_unique
    """))
    connection.execute(text('DROP TABLE custom_fields_old_unique'))
    connection.execute(text('PRAGMA foreign_keys=ON'))


def add_workshop_scoped_uniqueness(connection: Connection):
    scoped_tables = ('locations', 'categories', 'custom_fields')
    default_workshop_id = _ensure_default_workshop(connection) if _any_rows(connection, scoped_tables) else None
    for table_name in ('locations', 'categories', 'custom_fields'):
        if _table_exists(connection, table_name) and 'workshop_id' in _column_names(connection, table_name):
            if default_workshop_id is not None:
                connection.execute(
                    text(f'UPDATE {table_name} SET workshop_id = :workshop_id WHERE workshop_id IS NULL'),
                    {'workshop_id': default_workshop_id},
                )

    _rebuild_locations_for_workshop_uniqueness(connection)
    _rebuild_custom_fields_for_workshop_uniqueness(connection)

    logger.info('Creating workshop-scoped uniqueness indexes.')
    connection.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_locations_workshop_name_ci
        ON locations (workshop_id, lower(name))
    """))
    connection.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_categories_workshop_parent_name_ci
        ON categories (workshop_id, COALESCE(parent_id, 0), lower(name))
    """))
    connection.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_custom_fields_workshop_name_ci
        ON custom_fields (workshop_id, lower(name))
    """))
    connection.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_custom_fields_workshop_slug_ci
        ON custom_fields (workshop_id, lower(slug))
    """))


def add_user_theme_field(connection: Connection):
    if not _table_exists(connection, 'users'):
        return
    if 'theme_id' not in _column_names(connection, 'users'):
        statement = "ALTER TABLE users ADD COLUMN theme_id VARCHAR(40) NOT NULL DEFAULT 'sober_dark'"
        logger.info('Applying user theme schema change: %s', statement)
        connection.execute(text(statement))
    connection.execute(text("UPDATE users SET theme_id = 'sober_dark' WHERE theme_id IS NULL OR trim(theme_id) = ''"))


def add_workshop_item_profiles(connection: Connection):
    if not _table_exists(connection, 'workshops'):
        return
    if 'item_profile_json' not in _column_names(connection, 'workshops'):
        statement = "ALTER TABLE workshops ADD COLUMN item_profile_json TEXT"
        logger.info('Applying workshop item profile schema change: %s', statement)
        connection.execute(text(statement))


def _foreign_key_targets(connection: Connection, table_name: str) -> dict[str, str]:
    if not _table_exists(connection, table_name):
        return {}
    return {
        row[3]: row[2]
        for row in connection.execute(text(f'PRAGMA foreign_key_list({table_name})')).all()
    }


def _rebuild_components_for_foreign_key_repair(connection: Connection):
    if not _table_exists(connection, 'components'):
        return
    targets = _foreign_key_targets(connection, 'components')
    expected_targets = {
        'workshop_id': 'workshops',
        'category_id': 'categories',
        'manufacturer_id': 'manufacturers',
        'package_id': 'packages',
        'location_id': 'locations',
    }
    if all(targets.get(column_name) == table_name for column_name, table_name in expected_targets.items()):
        return

    missing_targets = [
        table_name
        for table_name in expected_targets.values()
        if not _table_exists(connection, table_name)
    ]
    if missing_targets and _row_count(connection, 'components') == 0:
        logger.warning(
            'Skipping empty components foreign key repair because target tables are missing: %s.',
            ', '.join(sorted(missing_targets)),
        )
        return
    if missing_targets:
        raise RuntimeError(
            'Cannot repair components foreign keys because target tables are missing: '
            + ', '.join(sorted(missing_targets))
        )

    logger.warning(
        'Repairing components foreign keys: location_id currently references %s.',
        targets.get('location_id'),
    )
    connection.execute(text('DROP TABLE IF EXISTS components_fk_repair'))
    connection.execute(text("""
        CREATE TABLE components_fk_repair (
            id INTEGER PRIMARY KEY,
            part_number VARCHAR(150) NOT NULL UNIQUE,
            name VARCHAR(200) NOT NULL,
            workshop_id INTEGER REFERENCES workshops(id) ON DELETE SET NULL,
            category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
            manufacturer_id INTEGER REFERENCES manufacturers(id) ON DELETE SET NULL,
            package_id INTEGER REFERENCES packages(id) ON DELETE SET NULL,
            location_id INTEGER REFERENCES locations(id) ON DELETE SET NULL,
            quantity INTEGER NOT NULL DEFAULT 0,
            minimum_quantity INTEGER NOT NULL DEFAULT 0,
            datasheet_url VARCHAR(300),
            image_path VARCHAR(300),
            thumbnail_path VARCHAR(300),
            description TEXT,
            notes TEXT,
            keywords VARCHAR(300),
            created_at DATETIME,
            updated_at DATETIME
        )
    """))
    connection.execute(text("""
        INSERT INTO components_fk_repair (
            id, part_number, name, workshop_id, category_id, manufacturer_id,
            package_id, location_id, quantity, minimum_quantity, datasheet_url,
            image_path, thumbnail_path, description, notes, keywords, created_at, updated_at
        )
        SELECT
            id, part_number, name, workshop_id, category_id, manufacturer_id,
            package_id, location_id, quantity, minimum_quantity, datasheet_url,
            image_path, thumbnail_path, description, notes, keywords, created_at, updated_at
        FROM components
    """))
    connection.execute(text('DROP TABLE components'))
    connection.execute(text('ALTER TABLE components_fk_repair RENAME TO components'))


def _rebuild_component_custom_values_for_foreign_key_repair(connection: Connection):
    if not _table_exists(connection, 'component_custom_field_values'):
        return
    targets = _foreign_key_targets(connection, 'component_custom_field_values')
    if targets.get('custom_field_id') == 'custom_fields' and targets.get('component_id') == 'components':
        return

    expected_targets = {
        'component_id': 'components',
        'custom_field_id': 'custom_fields',
    }
    missing_targets = [
        table_name
        for table_name in expected_targets.values()
        if not _table_exists(connection, table_name)
    ]
    if missing_targets and _row_count(connection, 'component_custom_field_values') == 0:
        logger.warning(
            'Skipping empty component_custom_field_values foreign key repair because target tables are missing: %s.',
            ', '.join(sorted(missing_targets)),
        )
        return
    if missing_targets:
        raise RuntimeError(
            'Cannot repair component_custom_field_values foreign keys because target tables are missing: '
            + ', '.join(sorted(missing_targets))
        )

    logger.warning(
        'Repairing component_custom_field_values foreign keys: component_id=%s custom_field_id=%s.',
        targets.get('component_id'),
        targets.get('custom_field_id'),
    )
    connection.execute(text('DROP TABLE IF EXISTS component_custom_field_values_fk_repair'))
    connection.execute(text("""
        CREATE TABLE component_custom_field_values_fk_repair (
            id INTEGER PRIMARY KEY,
            component_id INTEGER NOT NULL REFERENCES components(id) ON DELETE CASCADE,
            custom_field_id INTEGER NOT NULL REFERENCES custom_fields(id) ON DELETE CASCADE,
            value TEXT,
            created_at DATETIME,
            updated_at DATETIME,
            UNIQUE (component_id, custom_field_id)
        )
    """))
    connection.execute(text("""
        INSERT INTO component_custom_field_values_fk_repair (
            id, component_id, custom_field_id, value, created_at, updated_at
        )
        SELECT id, component_id, custom_field_id, value, created_at, updated_at
        FROM component_custom_field_values
    """))
    connection.execute(text('DROP TABLE component_custom_field_values'))
    connection.execute(text('ALTER TABLE component_custom_field_values_fk_repair RENAME TO component_custom_field_values'))


def repair_component_location_foreign_key(connection: Connection):
    old_refs = []
    for table_name in ('components', 'component_custom_field_values', 'stock_movements'):
        for column_name, target_table in _foreign_key_targets(connection, table_name).items():
            if target_table.endswith('_old_unique'):
                old_refs.append(f'{table_name}.{column_name}->{target_table}')

    if not old_refs:
        logger.info('No stale SQLite foreign keys found for repaired stock tables.')
        return

    logger.warning('Repairing stale SQLite foreign keys: %s', ', '.join(old_refs))
    connection.execute(text('PRAGMA foreign_keys=OFF'))
    _rebuild_component_custom_values_for_foreign_key_repair(connection)
    _rebuild_components_for_foreign_key_repair(connection)
    connection.execute(text('PRAGMA foreign_keys=ON'))


def _rebuild_manufacturers_for_workshop_scope(connection: Connection, default_workshop_id: int | None):
    if not _table_exists(connection, 'manufacturers'):
        return

    columns = _column_names(connection, 'manufacturers')
    needs_rebuild = 'workshop_id' not in columns
    indexes = connection.execute(text("PRAGMA index_list(manufacturers)")).all()
    needs_rebuild = needs_rebuild or any(row[2] and str(row[1]).startswith('sqlite_autoindex_') for row in indexes)
    if not needs_rebuild:
        if default_workshop_id is not None:
            connection.execute(
                text('UPDATE manufacturers SET workshop_id = :workshop_id WHERE workshop_id IS NULL'),
                {'workshop_id': default_workshop_id},
            )
        return
    if default_workshop_id is None and _row_count(connection, 'manufacturers') > 0:
        raise RuntimeError('Cannot scope existing manufacturers without a default workshop.')

    logger.info('Rebuilding manufacturers table for workshop-scoped references.')
    connection.execute(text('DROP TABLE IF EXISTS manufacturers_workshop_scope'))
    connection.execute(text("""
        CREATE TABLE manufacturers_workshop_scope (
            id INTEGER PRIMARY KEY,
            name VARCHAR(120) NOT NULL,
            workshop_id INTEGER REFERENCES workshops(id) ON DELETE SET NULL,
            website_url VARCHAR(300),
            notes TEXT,
            created_at DATETIME,
            updated_at DATETIME
        )
    """))
    workshop_select = 'workshop_id' if 'workshop_id' in columns else ':workshop_id'
    connection.execute(
        text(f"""
            INSERT INTO manufacturers_workshop_scope (id, name, workshop_id, website_url, notes, created_at, updated_at)
            SELECT id, name, COALESCE({workshop_select}, :workshop_id), website_url, notes, created_at, updated_at
            FROM manufacturers
        """),
        {'workshop_id': default_workshop_id},
    )
    connection.execute(text('DROP TABLE manufacturers'))
    connection.execute(text('ALTER TABLE manufacturers_workshop_scope RENAME TO manufacturers'))


def _rebuild_packages_for_workshop_scope(connection: Connection, default_workshop_id: int | None):
    if not _table_exists(connection, 'packages'):
        return

    columns = _column_names(connection, 'packages')
    needs_rebuild = 'workshop_id' not in columns
    indexes = connection.execute(text("PRAGMA index_list(packages)")).all()
    needs_rebuild = needs_rebuild or any(row[2] and str(row[1]).startswith('sqlite_autoindex_') for row in indexes)
    if not needs_rebuild:
        if default_workshop_id is not None:
            connection.execute(
                text('UPDATE packages SET workshop_id = :workshop_id WHERE workshop_id IS NULL'),
                {'workshop_id': default_workshop_id},
            )
        return
    if default_workshop_id is None and _row_count(connection, 'packages') > 0:
        raise RuntimeError('Cannot scope existing packages without a default workshop.')

    logger.info('Rebuilding packages table for workshop-scoped references.')
    connection.execute(text('DROP TABLE IF EXISTS packages_workshop_scope'))
    connection.execute(text("""
        CREATE TABLE packages_workshop_scope (
            id INTEGER PRIMARY KEY,
            name VARCHAR(120) NOT NULL,
            workshop_id INTEGER REFERENCES workshops(id) ON DELETE SET NULL,
            description TEXT,
            created_at DATETIME,
            updated_at DATETIME
        )
    """))
    workshop_select = 'workshop_id' if 'workshop_id' in columns else ':workshop_id'
    connection.execute(
        text(f"""
            INSERT INTO packages_workshop_scope (id, name, workshop_id, description, created_at, updated_at)
            SELECT id, name, COALESCE({workshop_select}, :workshop_id), description, created_at, updated_at
            FROM packages
        """),
        {'workshop_id': default_workshop_id},
    )
    connection.execute(text('DROP TABLE packages'))
    connection.execute(text('ALTER TABLE packages_workshop_scope RENAME TO packages'))


def scope_manufacturers_packages_by_workshop(connection: Connection):
    scoped_tables = ('manufacturers', 'packages', 'components')
    default_workshop_id = _ensure_default_workshop(connection) if _any_rows(connection, scoped_tables) else None
    connection.execute(text('PRAGMA foreign_keys=OFF'))
    _rebuild_manufacturers_for_workshop_scope(connection, default_workshop_id)
    _rebuild_packages_for_workshop_scope(connection, default_workshop_id)
    _rebuild_components_for_foreign_key_repair(connection)
    connection.execute(text('PRAGMA foreign_keys=ON'))

    logger.info('Creating workshop-scoped uniqueness indexes for manufacturers and packages.')
    connection.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_manufacturers_workshop_name_ci
        ON manufacturers (workshop_id, lower(name))
    """))
    connection.execute(text("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_packages_workshop_name_ci
        ON packages (workshop_id, lower(name))
    """))

    targets = _foreign_key_targets(connection, 'components')
    for column_name, expected_target in (
        ('manufacturer_id', 'manufacturers'),
        ('package_id', 'packages'),
        ('location_id', 'locations'),
        ('category_id', 'categories'),
        ('workshop_id', 'workshops'),
    ):
        actual_target = targets.get(column_name)
        if actual_target != expected_target:
            logger.warning('Unexpected components foreign key target after reference scoping: %s -> %s', column_name, actual_target)


MIGRATIONS = (
    Migration(
        id='0001_baseline',
        name='Register existing schema under migration control',
        apply=baseline_existing_schema,
    ),
    Migration(
        id='0002_create_users',
        name='Create users table for session-backed authentication',
        apply=create_users_table,
    ),
    Migration(
        id='0003_add_user_profile_fields',
        name='Add profile fields to users',
        apply=add_user_profile_fields,
    ),
    Migration(
        id='0004_create_workshops_and_scope_stock',
        name='Create workshops and assign stock data to the default workshop',
        apply=create_workshops_and_scope_stock,
    ),
    Migration(
        id='0005_add_workshop_scoped_uniqueness',
        name='Scope location, category, and custom field uniqueness by workshop',
        apply=add_workshop_scoped_uniqueness,
    ),
    Migration(
        id='0006_add_user_theme_field',
        name='Add per-user visual theme preference',
        apply=add_user_theme_field,
    ),
    Migration(
        id='0007_add_workshop_item_profiles',
        name='Add configurable built-in article field profiles to workshops',
        apply=add_workshop_item_profiles,
    ),
    Migration(
        id='0008_repair_component_location_foreign_key',
        name='Repair stale SQLite foreign keys left by stock table rebuilds',
        apply=repair_component_location_foreign_key,
    ),
    Migration(
        id='0009_scope_manufacturers_packages_by_workshop',
        name='Scope manufacturer and package references by workshop',
        apply=scope_manufacturers_packages_by_workshop,
    ),
)


def ensure_migration_table(engine):
    with engine.begin() as connection:
        connection.execute(text(f"""
            CREATE TABLE IF NOT EXISTS {SCHEMA_MIGRATIONS_TABLE} (
                id VARCHAR(80) PRIMARY KEY,
                name VARCHAR(200) NOT NULL,
                applied_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))


def run_migrations(engine):
    logger.info('Checking schema migrations.')
    ensure_migration_table(engine)

    with engine.begin() as connection:
        applied = set(
            connection.execute(text(f'SELECT id FROM {SCHEMA_MIGRATIONS_TABLE}'))
            .scalars()
            .all()
        )

        pending_count = 0
        for migration in MIGRATIONS:
            if migration.id in applied:
                logger.info('Skipping already applied migration %s: %s', migration.id, migration.name)
                continue

            logger.info('Applying migration %s: %s', migration.id, migration.name)
            migration.apply(connection)
            connection.execute(
                text(f"""
                    INSERT INTO {SCHEMA_MIGRATIONS_TABLE} (id, name)
                    VALUES (:id, :name)
                """),
                {'id': migration.id, 'name': migration.name},
            )
            pending_count += 1
            logger.info('Applied migration %s: %s', migration.id, migration.name)

        if pending_count == 0:
            logger.info('No pending schema migrations.')
