from __future__ import annotations

from app.config import APP_NAME, OPENAI_COMPONENT_LOOKUP_MODEL
from app.services.ai_component_lookup_v2 import (
    DEFAULT_COMPONENT_LOOKUP_SYSTEM_PROMPT,
    build_component_lookup_prompts,
    is_web_search_enabled,
)
from app.services.env_settings import get_env_value, mask_secret
from app.services.prompt_presets import list_prompt_presets


def build_settings_context():
    api_key = get_env_value('OPENAI_API_KEY', '').strip()
    app_display_name = get_env_value('APP_DISPLAY_NAME', APP_NAME).strip() or APP_NAME
    organization_name = get_env_value('APP_ORGANIZATION_NAME', '').strip()
    logo_path = get_env_value('APP_LOGO_PATH', '').strip()
    prompt_preview = build_component_lookup_prompts(
        part_number='HSN-2510SR',
        categories=['Affichage > Afficheurs LED', 'Passifs > Resistances'],
        manufacturers=['Broadcom', 'Kingbright', 'Lite-On'],
        packages=['SIP', 'DIP', '0805'],
        custom_fields=[{'name': 'Tension', 'unit': 'V'}, {'name': 'Couleur', 'unit': ''}],
    )
    current_prompt = get_env_value('OPENAI_COMPONENT_LOOKUP_SYSTEM_PROMPT', '').strip() or prompt_preview[0]
    return {
        'app_display_name_setting': app_display_name,
        'organization_name_setting': organization_name,
        'brand_logo_path_setting': logo_path,
        'openai_api_key_masked': mask_secret(api_key, visible_prefix=13),
        'openai_api_key_present': bool(api_key),
        'openai_lookup_model': get_env_value('OPENAI_COMPONENT_LOOKUP_MODEL', OPENAI_COMPONENT_LOOKUP_MODEL).strip() or OPENAI_COMPONENT_LOOKUP_MODEL,
        'openai_lookup_web_search': is_web_search_enabled(),
        'component_lookup_system_prompt_current': current_prompt,
        'component_lookup_prompt_presets': list_prompt_presets(DEFAULT_COMPONENT_LOOKUP_SYSTEM_PROMPT),
    }
