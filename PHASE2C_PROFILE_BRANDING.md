# Phase 2C Profile And Branding

## User Profile Fields

Migration `0003_add_user_profile_fields` adds nullable profile fields to `users`:

- `first_name`
- `last_name`
- `display_name`
- `email`

Login still uses `username` / pseudo. Email is stored for future use and is not accepted for login yet.

## Header Behavior

When authenticated, the header shows:

- custom logo when configured
- app display name
- organization / fablab name when configured
- current user display name, falling back to username
- current role label
- logout button

When no user is authenticated because auth is disabled, the user block is hidden.

## Branding Storage

Branding settings are admin-only and stored as environment settings:

- `APP_DISPLAY_NAME`
- `APP_ORGANIZATION_NAME`
- `APP_LOGO_PATH`

Uploaded logos are stored under:

```text
data/images/branding/<uuid>.webp
```

They are served through the existing safe public media path:

```text
/data/images/branding/<uuid>.webp
```

The sensitive data root is still not publicly mounted.

## Current Auth State

- Authentication is enabled when at least one user exists, or when legacy `data/auth_password.hash` exists.
- If there are zero users and no `auth_password.hash`, the app intentionally allows open access. This preserves the original development/first-run behavior.
- If no users exist but `auth_password.hash` exists, startup creates the initial `admin` user from that hash.

## Manual Tests

Admin:

- Open `/settings`
- Set app display name and organization name
- Upload a logo and confirm it appears in the header
- Remove the logo and confirm the header falls back cleanly
- Open `/admin/users`
- Create/edit first name, last name, display name, username, email, role, active status
- Reset a user password
- Confirm the last active admin cannot be disabled or deleted

Stock manager / viewer:

- Confirm `/settings` returns 403
- Confirm `/admin/users` returns 403
- Confirm header displays their display name and role after login

Login:

- Confirm login works with username/pseudo
- Confirm email does not log in yet
- Confirm logout clears the session cookie
