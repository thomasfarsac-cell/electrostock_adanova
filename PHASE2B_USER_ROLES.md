# Phase 2B User Roles

Phase 2B makes users and roles usable while keeping legacy authentication compatibility.

## Roles

| Area | admin | stock_manager | viewer |
| --- | --- | --- | --- |
| Dashboard | read | read | read |
| Component list/detail/export | read | read | read |
| Component create/edit/delete | yes | yes | no |
| Stock movements | yes | yes | no |
| Locations list/detail/QR/PDF | read | read | read |
| Location create/edit/delete | yes | yes | no |
| Categories/references read | yes | yes | yes |
| Categories/references mutate | yes | yes | no |
| Component import | yes | yes | no |
| Component label PDF | yes | yes | yes |
| Component label preset write/delete | yes | yes | no |
| Settings | yes | no | no |
| Backup/export/restore | yes | no | no |
| User management | yes | no | no |

## Default Admin Bootstrap

If no users exist and `data/auth_password.hash` exists, startup creates:

```text
username: admin
role: admin
password_hash: contents of data/auth_password.hash
```

The legacy hash file is not deleted. Legacy cookie compatibility remains enabled for this transition phase.

## Manual Tests

Create three users from `/admin/users`:

- `admin_test` with role `admin`
- `stock_test` with role `stock_manager`
- `viewer_test` with role `viewer`

Admin checks:

- Can open `/admin/users`
- Can open `/settings`
- Can download `/settings/backups/export.zip`
- Can create/edit/delete a disposable component
- Cannot disable/delete the last active admin

Stock manager checks:

- Cannot open `/admin/users`
- Cannot open `/settings`
- Can create/edit/delete a disposable component
- Can add a stock movement
- Can create/edit/delete a disposable location
- Can mutate categories/references
- Can access imports

Viewer checks:

- Can open dashboard, component list/detail, locations, categories, references
- Cannot open `/components/new`
- Cannot post stock movements
- Cannot open `/locations/new`
- Cannot open `/imports/components`
- Cannot open `/settings`
- Cannot open `/admin/users`
- Mutation attempts return a 403 page

## Known Limitations

- Role enforcement is progressive, not a full route-by-route policy framework yet.
- Some complex modals may still show read-oriented controls, but server-side guards are authoritative.
- Backup merge restore does not yet deliberately merge users.
- There is no self-service password change page yet.
