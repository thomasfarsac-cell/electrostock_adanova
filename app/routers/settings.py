from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.config import APP_NAME, DATA_DIR
from app.db import get_db
from app.security.permissions import require_admin_access
from app.services.ai_component_lookup_v2 import DEFAULT_COMPONENT_LOOKUP_SYSTEM_PROMPT
from app.services.backup_export import build_backup_archive
from app.services.backup_restore import restore_backup_archive
from app.services.env_settings import delete_env_value, get_env_value, set_env_value
from app.services.images import delete_relative_file, save_brand_logo
from app.services.notice_helpers import build_restore_notice
from app.services.prompt_presets import create_prompt_preset, delete_prompt_preset, get_prompt_preset, update_prompt_preset
from app.services.settings_context import build_settings_context
from app.view_context import render

router = APIRouter()


@router.get('/settings')
def settings_page(request: Request):
    require_admin_access(request)
    return render(request, 'settings.html', build_settings_context())


@router.post('/settings/branding')
async def save_branding_settings(
    request: Request,
    app_display_name: str = Form(''),
    organization_name: str = Form(''),
    remove_logo: bool = Form(False),
    logo: UploadFile | None = File(None),
):
    require_admin_access(request)
    display_name = app_display_name.strip() or APP_NAME
    organization = organization_name.strip()
    set_env_value('APP_DISPLAY_NAME', display_name)
    set_env_value('APP_ORGANIZATION_NAME', organization)

    current_logo = get_env_value('APP_LOGO_PATH', '').strip()
    if remove_logo and current_logo:
        delete_relative_file(DATA_DIR, current_logo)
        delete_env_value('APP_LOGO_PATH')
        current_logo = ''

    if logo and logo.filename:
        if current_logo:
            delete_relative_file(DATA_DIR, current_logo)
        logo_path = save_brand_logo(logo)
        set_env_value('APP_LOGO_PATH', logo_path)

    return render(
        request,
        'settings.html',
        {
            **build_settings_context(),
            'settings_notice': {'tone': 'success', 'message': 'Identite visuelle enregistree.'},
        },
    )
    query = scoped_query(query, Component, workshop_id)


@router.post('/settings/openai-api-key')
def save_openai_api_key(request: Request, openai_api_key: str = Form('')):
    require_admin_access(request)
    value = openai_api_key.strip()
    if not value:
        return render(
            request,
            'settings.html',
            {
                **build_settings_context(),
                'settings_notice': {'tone': 'danger', 'message': 'La cle API ne peut pas etre vide.'},
            },
            status_code=400,
        )
    set_env_value('OPENAI_API_KEY', value)
    return render(
        request,
        'settings.html',
        {
            **build_settings_context(),
            'settings_notice': {'tone': 'success', 'message': 'Cle API OpenAI enregistree.'},
        },
    )


@router.post('/settings/openai-api-key/delete')
def delete_openai_api_key(request: Request):
    require_admin_access(request)
    delete_env_value('OPENAI_API_KEY')
    return render(
        request,
        'settings.html',
        {
            **build_settings_context(),
            'settings_notice': {'tone': 'success', 'message': 'Cle API OpenAI supprimee.'},
        },
    )


@router.post('/settings/openai-web-search')
def save_openai_web_search_setting(request: Request, openai_web_search_enabled: str = Form('off')):
    require_admin_access(request)
    enabled = str(openai_web_search_enabled).strip().lower() in {'1', 'true', 'yes', 'on'}
    set_env_value('OPENAI_COMPONENT_LOOKUP_USE_WEB_SEARCH', 'true' if enabled else 'false')
    return render(
        request,
        'settings.html',
        {
            **build_settings_context(),
            'settings_notice': {
                'tone': 'success',
                'message': f"Recherche web pour l'IA {'activee' if enabled else 'desactivee'}.",
            },
        },
    )


@router.post('/settings/component-lookup-prompt')
def save_component_lookup_prompt(request: Request, component_lookup_system_prompt: str = Form('')):
    require_admin_access(request)
    value = component_lookup_system_prompt.strip()
    if not value:
        return render(
            request,
            'settings.html',
            {
                **build_settings_context(),
                'settings_notice': {'tone': 'danger', 'message': 'Le prompt systeme ne peut pas etre vide.'},
            },
            status_code=400,
        )
    set_env_value('OPENAI_COMPONENT_LOOKUP_SYSTEM_PROMPT', value)
    return render(
        request,
        'settings.html',
        {
            **build_settings_context(),
            'settings_notice': {'tone': 'success', 'message': 'Prompt systeme IA enregistre.'},
        },
    )


@router.post('/settings/component-lookup-prompt/presets/new')
def create_component_lookup_prompt_preset_route(
    request: Request,
    preset_name: str = Form(''),
    preset_prompt: str = Form(''),
    component_lookup_system_prompt: str = Form(''),
):
    require_admin_access(request)
    name = preset_name.strip()
    prompt = preset_prompt.strip() or component_lookup_system_prompt.strip()
    if not name or not prompt:
        return render(
            request,
            'settings.html',
            {
                **build_settings_context(),
                'settings_notice': {'tone': 'danger', 'message': 'Le nom et le prompt du preset sont obligatoires.'},
            },
            status_code=400,
        )
    create_prompt_preset(name, prompt)
    return render(
        request,
        'settings.html',
        {
            **build_settings_context(),
            'component_lookup_system_prompt_current': prompt,
            'settings_notice': {'tone': 'success', 'message': 'Preset enregistre.'},
        },
    )


@router.post('/settings/component-lookup-prompt/presets/{preset_id}/apply')
def apply_component_lookup_prompt_preset_route(request: Request, preset_id: str):
    require_admin_access(request)
    preset = get_prompt_preset(preset_id, DEFAULT_COMPONENT_LOOKUP_SYSTEM_PROMPT)
    if not preset:
        return render(
            request,
            'settings.html',
            {
                **build_settings_context(),
                'settings_notice': {'tone': 'danger', 'message': 'Preset introuvable.'},
            },
            status_code=404,
        )
    set_env_value('OPENAI_COMPONENT_LOOKUP_SYSTEM_PROMPT', preset['prompt'])
    return render(
        request,
        'settings.html',
        {
            **build_settings_context(),
            'settings_notice': {'tone': 'success', 'message': f"Preset '{preset['name']}' applique."},
        },
    )


@router.post('/settings/component-lookup-prompt/presets/{preset_id}/update')
def update_component_lookup_prompt_preset_route(
    request: Request,
    preset_id: str,
    preset_name: str = Form(''),
    preset_prompt: str = Form(''),
):
    require_admin_access(request)
    if preset_id == 'default':
        return render(
            request,
            'settings.html',
            {
                **build_settings_context(),
                'settings_notice': {'tone': 'danger', 'message': 'Le preset par defaut ne peut pas etre modifie ici.'},
            },
            status_code=400,
        )
    name = preset_name.strip()
    prompt = preset_prompt.strip()
    if not name or not prompt:
        return render(
            request,
            'settings.html',
            {
                **build_settings_context(),
                'settings_notice': {'tone': 'danger', 'message': 'Le nom et le prompt du preset sont obligatoires.'},
            },
            status_code=400,
        )
    update_prompt_preset(preset_id, name, prompt)
    return render(
        request,
        'settings.html',
        {
            **build_settings_context(),
            'settings_notice': {'tone': 'success', 'message': 'Preset mis a jour.'},
        },
    )


@router.post('/settings/component-lookup-prompt/presets/{preset_id}/delete')
def delete_component_lookup_prompt_preset_route(request: Request, preset_id: str):
    require_admin_access(request)
    if preset_id == 'default':
        return render(
            request,
            'settings.html',
            {
                **build_settings_context(),
                'settings_notice': {'tone': 'danger', 'message': 'Le preset par defaut ne peut pas etre supprime.'},
            },
            status_code=400,
        )
    delete_prompt_preset(preset_id)
    return render(
        request,
        'settings.html',
        {
            **build_settings_context(),
            'settings_notice': {'tone': 'success', 'message': 'Preset supprime.'},
        },
    )


@router.get('/settings/backups/export.zip')
def export_backup_archive(request: Request, db: Session = Depends(get_db)):
    require_admin_access(request)
    archive_bytes, filename = build_backup_archive(db)
    headers = {'Content-Disposition': f'attachment; filename="{filename}"'}
    return StreamingResponse(iter([archive_bytes]), media_type='application/zip', headers=headers)


@router.post('/settings/backups/restore')
async def restore_backup_archive_route(
    request: Request,
    restore_mode: str = Form('merge'),
    backup_archive: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    require_admin_access(request)
    if backup_archive is None or not backup_archive.filename:
        return render(
            request,
            'settings.html',
            {
                **build_settings_context(),
                'settings_notice': {'tone': 'danger', 'message': 'Choisis une archive .zip avant de lancer la restauration.'},
            },
            status_code=400,
        )

    mode = 'replace' if restore_mode == 'replace' else 'merge'
    archive_bytes = await backup_archive.read()
    try:
        summary = restore_backup_archive(db, archive_bytes, mode=mode)
    except ValueError as exc:
        return render(
            request,
            'settings.html',
            {
                **build_settings_context(),
                'settings_notice': {'tone': 'danger', 'message': str(exc)},
            },
            status_code=400,
        )
    except Exception as exc:  # noqa: BLE001 - user-facing restore summary
        return render(
            request,
            'settings.html',
            {
                **build_settings_context(),
                'settings_notice': {'tone': 'danger', 'message': f'La restauration a echoue: {exc}'},
            },
            status_code=500,
        )

    return render(
        request,
        'settings.html',
        {
            **build_settings_context(),
            'settings_notice': build_restore_notice(summary),
        },
    )
