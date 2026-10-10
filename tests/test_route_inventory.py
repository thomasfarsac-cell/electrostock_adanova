from fastapi.routing import APIRoute

from app.main import app


IGNORED_PATHS = {"/docs", "/redoc", "/openapi.json"}

EXPECTED_ROUTES = [
    ("GET", "/setup", "setup_page"),
    ("POST", "/setup", "setup_submit"),
    ("GET", "/login", "login_page"),
    ("POST", "/login", "login_submit"),
    ("POST", "/logout", "logout"),
    ("GET", "/profile", "profile_page"),
    ("POST", "/profile/update", "update_profile"),
    ("POST", "/profile/change-password", "change_profile_password"),
    ("GET", "/admin/users", "users_page"),
    ("POST", "/admin/users/new", "create_user"),
    ("POST", "/admin/users/{user_id}/edit", "update_user"),
    ("POST", "/admin/users/{user_id}/reset-password", "reset_user_password"),
    ("POST", "/admin/users/{user_id}/toggle-active", "toggle_user_active"),
    ("POST", "/admin/users/{user_id}/delete", "delete_user"),
    ("POST", "/workshops/select", "select_workshop"),
    ("GET", "/admin/workshops", "workshops_page"),
    ("POST", "/admin/workshops/new", "create_workshop"),
    ("POST", "/admin/workshops/{workshop_id}/edit", "update_workshop"),
    ("POST", "/admin/workshops/{workshop_id}/delete", "delete_workshop"),
    ("GET", "/workshops/settings", "current_workshop_settings"),
    ("POST", "/workshops/settings", "update_current_workshop_settings"),
    ("GET", "/settings", "settings_page"),
    ("POST", "/settings/branding", "save_branding_settings"),
    ("POST", "/settings/openai-api-key", "save_openai_api_key"),
    ("POST", "/settings/openai-api-key/delete", "delete_openai_api_key"),
    ("POST", "/settings/openai-web-search", "save_openai_web_search_setting"),
    ("POST", "/settings/component-lookup-prompt", "save_component_lookup_prompt"),
    ("POST", "/settings/component-lookup-prompt/presets/new", "create_component_lookup_prompt_preset_route"),
    ("POST", "/settings/component-lookup-prompt/presets/{preset_id}/apply", "apply_component_lookup_prompt_preset_route"),
    ("POST", "/settings/component-lookup-prompt/presets/{preset_id}/update", "update_component_lookup_prompt_preset_route"),
    ("POST", "/settings/component-lookup-prompt/presets/{preset_id}/delete", "delete_component_lookup_prompt_preset_route"),
    ("GET", "/settings/backups/export.zip", "export_backup_archive"),
    ("POST", "/settings/backups/restore", "restore_backup_archive_route"),
    ("GET", "/scan", "scan_router"),
    ("GET", "/components/{component_id}/qr.png", "component_qr"),
    ("GET", "/labels/components.pdf", "components_labels_pdf"),
    ("GET", "/api/component-labels/presets", "component_label_presets_api"),
    ("POST", "/api/component-labels/presets/{kind}", "save_component_label_preset_api"),
    ("POST", "/api/component-labels/presets/{kind}/{preset_id}/delete", "delete_component_label_preset_api"),
    ("POST", "/api/component-labels/layout-summary", "component_label_layout_summary_api"),
    ("POST", "/api/component-labels/pdf", "component_labels_pdf_api"),
    ("GET", "/", "dashboard"),
    ("GET", "/components", "list_components"),
    ("GET", "/components/export.csv", "export_components"),
    ("GET", "/components/new", "new_component"),
    ("POST", "/components/new", "create_component"),
    ("GET", "/components/{component_id}", "component_detail"),
    ("GET", "/components/{component_id}/movements/export.csv", "export_component_movements"),
    ("POST", "/components/{component_id}/movements/new", "create_stock_movement_route"),
    ("GET", "/components/{component_id}/edit", "edit_component"),
    ("POST", "/components/ai-lookup", "ai_lookup_component"),
    ("POST", "/components/{component_id}/edit", "update_component"),
    ("POST", "/components/{component_id}/delete", "delete_component"),
    ("GET", "/locations", "list_locations"),
    ("GET", "/locations/new", "new_location"),
    ("POST", "/locations/new", "create_location_page"),
    ("GET", "/locations/{location_id}", "location_detail"),
    ("GET", "/locations/{location_id}/edit", "edit_location"),
    ("POST", "/locations/{location_id}/edit", "update_location"),
    ("POST", "/locations/{location_id}/delete", "delete_location_page"),
    ("GET", "/locations/{location_id}/qr.png", "location_qr"),
    ("GET", "/labels/locations.pdf", "locations_labels_pdf"),
    ("GET", "/categories", "categories_page"),
    ("POST", "/categories/new", "create_category"),
    ("POST", "/categories/{category_id}/edit", "update_category"),
    ("POST", "/categories/{category_id}/delete", "delete_category"),
    ("GET", "/references", "references_page"),
    ("POST", "/references/manufacturers/new", "create_manufacturer"),
    ("POST", "/references/manufacturers/{item_id}/delete", "delete_manufacturer"),
    ("POST", "/references/packages/new", "create_package"),
    ("POST", "/references/packages/{item_id}/delete", "delete_package"),
    ("POST", "/references/locations/new", "create_location"),
    ("POST", "/references/locations/{item_id}/delete", "delete_location"),
    ("POST", "/references/custom-fields/new", "create_custom_field"),
    ("POST", "/references/custom-fields/{item_id}/toggle", "toggle_custom_field"),
    ("POST", "/references/custom-fields/{item_id}/delete", "delete_custom_field"),
    ("GET", "/imports/components", "import_components_page"),
    ("POST", "/imports/components/preview", "preview_component_import"),
    ("GET", "/imports/components/template.csv", "download_component_import_template"),
    ("POST", "/imports/components/run", "run_component_import"),
]


def project_route_inventory():
    inventory = []
    for route in app.routes:
        if not isinstance(route, APIRoute) or route.path in IGNORED_PATHS:
            continue
        for method in sorted(route.methods):
            if method in {"HEAD", "OPTIONS"}:
                continue
            inventory.append((method, route.path, route.endpoint.__name__))
    return inventory


def test_project_route_inventory_is_unchanged():
    assert project_route_inventory() == EXPECTED_ROUTES
