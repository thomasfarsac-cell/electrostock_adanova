# Phase 2D Admin Recovery

## Normal Password Reset

Administrators reset user passwords from:

```text
/admin/users
```

The reset form does not require the old password. It is admin-only.

## Emergency Recovery

On startup, ElectroStock checks whether at least one active admin exists.

If no active admin exists, the app automatically creates or reactivates:

```text
username: admin
password: 1234
role: admin
is_active: true
```

If a user named `admin` already exists but is inactive or has another role, that account is reactivated and promoted to admin.

The password is set to `1234` only in this emergency no-active-admin case. If at least one active admin already exists, no admin password is overwritten.

After emergency recovery, log in as `admin` / `1234` and change the password immediately from `/admin/users`.

## Legacy Compatibility

Legacy `data/auth_password.hash` compatibility remains in place for now, but the old reset instruction to delete that file is no longer shown in the UI.

## Manual Tests

- Normal case: keep one active admin, restart, confirm the admin password is not changed.
- Lockout case: deactivate or demote every admin, restart, confirm `admin` / `1234` works.
- Reset another user's password as admin and confirm login with the new password.
- Confirm stock_manager and viewer receive 403 when posting to password reset routes.
- Confirm the login page no longer says to delete `data/auth_password.hash`.
