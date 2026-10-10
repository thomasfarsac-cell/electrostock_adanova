# Phase 2A Auth Foundation

Phase 2A introduces a real `users` table and signed per-user sessions without enforcing role permissions across the application yet.

## Users Table

Created by migration `0002_create_users`:

```sql
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username VARCHAR(80) NOT NULL UNIQUE,
    password_hash VARCHAR(300) NOT NULL,
    role VARCHAR(30) NOT NULL CHECK (role IN ('admin', 'stock_manager', 'viewer')),
    is_active BOOLEAN NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login_at DATETIME
);
```

## Initial Admin Bootstrap

On startup, if no users exist and `data/auth_password.hash` exists, ElectroStock creates:

```text
username: admin
role: admin
password_hash: contents of data/auth_password.hash
```

The legacy `auth_password.hash` file is preserved.

If no users exist and no legacy hash file exists, authentication remains disabled, matching the previous behavior.

## Session Cookie

Successful user login now stores a signed session cookie in `electrostock_auth`:

```text
v1:<user_id>:<issued_at>:<hmac_signature>
```

The signature uses `APP_SECRET_KEY`. The current max age is 90 days.

For this transition phase, the old static shared-password cookie is still accepted when the legacy password hash exists.

## Role Helpers

`app/auth.py` now provides:

- `get_current_user`
- `require_user`
- `require_role`
- `is_admin`
- `is_stock_manager`
- `is_viewer`

These helpers are available for Phase 2B permission enforcement. They are not applied globally in Phase 2A.

## Backup/Restore Note

Backups export the `users` table because it is part of SQLAlchemy metadata.

Restore behavior should be completed in Phase 2B:

- replace-mode raw table restore can include `users`
- merge-mode does not yet merge users intentionally
- user/password restore rules need a deliberate product decision before permissions are enforced
