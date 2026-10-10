# ElectroStock Phase 0 Smoke Tests

Run these checks after deploying the Phase 0 stabilization changes.

## Security checks

- Open `/data/app.db` in the browser. Expected: not downloadable, 404 or another non-file response.
- Open `/data/auth_password.hash` in the browser. Expected: not downloadable, 404 or another non-file response.
- Open `/data/.env`, `/data/imports/`, `/data/backups/`, and any known non-image data path. Expected: not downloadable.
- Open a known image URL such as `/data/images/components/<file>.webp` or `/data/images/thumbnails/<file>.webp`. Expected: image displays.
- Open a known location image URL such as `/data/images/locations/<file>.webp` or `/data/images/thumbnails/locations/<file>.webp` when location images exist. Expected: image displays.

## Authentication

- Visit `/login`. Expected: login page loads.
- Log in with the configured password. Expected: redirect to the requested page or dashboard.
- Click logout. Expected: session is cleared and protected pages redirect to login.

## Dashboard

- Open `/`. Expected: dashboard loads with stock counters, recent components, category distribution, and recent movements.

## Components

- Open `/components`. Expected: list loads, filters render, existing component images display.
- Open a component detail page. Expected: metadata, image, QR, and movement history display.
- Create a test component if appropriate. Expected: creation succeeds and appears in the list.
- Edit the test component. Expected: changes persist.
- Add a stock movement. Expected: quantity updates and movement appears in history.
- Delete the test component if delete is supported and the data is safe to remove. Expected: component disappears and related image files do not break the page.

## Locations

- Open `/locations`. Expected: list loads and location thumbnails display when present.
- Open a location detail page. Expected: image, QR, and contained components display.
- Create/edit/delete a test location only if safe for the current data.

## Categories And References

- Open `/categories`. Expected: category tree loads and expand/collapse works.
- Open `/references`. Expected: manufacturers, packages, locations, and custom fields load.
- Add/edit/delete only disposable reference data.

## Import And Export

- Download `/components/export.csv`. Expected: CSV downloads.
- Open `/imports/components`. Expected: import page loads.
- Download the import template. Expected: CSV template downloads.
- Preview a small test import file if safe. Expected: mapping preview appears.

## Backup And Restore

- Open `/settings`.
- Download `/settings/backups/export.zip`. Expected: backup archive downloads.
- Restore only in a safe test environment or with a fresh backup already saved.

## Labels And PDFs

- Generate a component label PDF from the component list. Expected: PDF downloads/opens.
- Generate a location label PDF from a location detail page. Expected: PDF downloads/opens.

## Header Notice

- Load any normal page with no configured `persistent_notice`. Expected: no empty green banner under the navigation.
- Temporarily provide a `persistent_notice` in the render context in a development environment. Expected: the green notice banner appears with the notice text.
