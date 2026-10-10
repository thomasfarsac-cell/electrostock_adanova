from __future__ import annotations

from fastapi import Request
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import get_current_user, is_auth_enabled
from app.config import APP_NAME
from app.db import SessionLocal
from app.models import User, Workshop
from app.security.permissions import ROLE_LABELS, has_admin_access, has_stock_write_access
from app.services.env_settings import get_env_value
from app.utils import parse_optional_int

templates = Jinja2Templates(directory='templates')

THEMES = (
    {'id': 'sober_dark', 'label': 'Sombre sobre', 'description': 'Interface sombre fonctionnelle.'},
    {'id': 'sober_light', 'label': 'Clair sobre', 'description': 'Interface claire et lisible.'},
    {'id': 'maker_blue', 'label': 'Bleu maker', 'description': 'Bleu propre pour fablab.'},
    {'id': 'creative_purple', 'label': 'Violet crÃ©atif', 'description': 'Ambiance crÃ©ative et jeune.'},
    {'id': 'neon_green', 'label': 'Vert nÃ©on', 'description': 'Style technique et contraste.'},
    {'id': 'warm_orange', 'label': 'Orange atelier', 'description': 'Chaleureux et associatif.'},
    {'id': 'brick_fun', 'label': 'Briques colorÃ©es', 'description': 'Couleurs vives, ludiques et lisibles.'},
    {'id': 'pastel_soft', 'label': 'Pastel doux', 'description': 'Palette pastel calme et accueillante.'},
    {'id': 'fairground_fun', 'label': 'Fête foraine', 'description': 'Rouge, jaune et bleu festifs, avec contraste fort.'},
    {'id': 'retro_terminal', 'label': 'Terminal rétro', 'description': 'Noir, vert terminal et lignes techniques.'},
    {'id': 'ocean_breeze', 'label': 'Océan', 'description': 'Bleus profonds, turquoise et cartes claires.'},
    {'id': 'industrial_workshop', 'label': 'Atelier industriel', 'description': 'Acier sombre, orange securite et contraste professionnel.'},
)
THEME_IDS = {item['id'] for item in THEMES}
DEFAULT_THEME_ID = 'sober_dark'
WORKSHOP_COOKIE_NAME = 'electrostock_workshop'


def user_display_name(user: User | None) -> str:
    if not user:
        return ''
    return (user.display_name or user.username or '').strip()


def normalize_theme_id(theme_id: str | None) -> str:
    value = (theme_id or '').strip()
    return value if value in THEME_IDS else DEFAULT_THEME_ID


def theme_label(theme_id: str | None) -> str:
    normalized = normalize_theme_id(theme_id)
    for theme in THEMES:
        if theme['id'] == normalized:
            return theme['label']
    return THEMES[0]['label']


def list_active_workshops(db: Session) -> list[Workshop]:
    return db.scalars(
        select(Workshop)
        .where(Workshop.is_active.is_(True))
        .order_by(Workshop.sort_order.asc(), Workshop.name.asc())
    ).all()


def get_selected_workshop_id(request: Request, db: Session) -> int | None:
    current_user = get_current_user(request)
    if current_user and current_user.active_workshop_id:
        workshop = db.get(Workshop, current_user.active_workshop_id)
        if workshop and workshop.is_active:
            return workshop.id

    cookie_value = (request.cookies.get(WORKSHOP_COOKIE_NAME) or '').strip()
    if cookie_value == 'all':
        return None
    cookie_id = parse_optional_int(cookie_value)
    if cookie_id:
        workshop = db.get(Workshop, cookie_id)
        if workshop and workshop.is_active:
            return workshop.id
    return None


def get_selected_workshop(request: Request, db: Session) -> Workshop | None:
    selected_id = get_selected_workshop_id(request, db)
    return db.get(Workshop, selected_id) if selected_id else None


def workshop_template_context(request: Request, db: Session) -> dict:
    active_workshops = list_active_workshops(db)
    active_id = get_selected_workshop_id(request, db)
    active_workshop = db.get(Workshop, active_id) if active_id else None
    return {
        'workshops_for_toolbar': active_workshops,
        'active_workshop': active_workshop,
        'active_workshop_id': active_id,
        'active_workshop_is_all': active_id is None,
        'requires_workshop_choice': active_id is None,
    }


def render(request: Request, template_name: str, context: dict, status_code: int = 200):
    current_user = get_current_user(request)
    app_display_name = get_env_value('APP_DISPLAY_NAME', APP_NAME).strip() or APP_NAME
    organization_name = get_env_value('APP_ORGANIZATION_NAME', '').strip()
    logo_path = get_env_value('APP_LOGO_PATH', '').strip()
    base_context = {
        'request': request,
        'app_name': app_display_name,
        'organization_name': organization_name,
        'brand_logo_path': logo_path,
        'auth_enabled': is_auth_enabled(),
        'current_user': current_user,
        'current_user_display_name': user_display_name(current_user),
        'current_user_role_label': ROLE_LABELS.get(current_user.role, current_user.role) if current_user else '',
        'current_theme_id': normalize_theme_id(current_user.theme_id if current_user else None),
        'current_theme_class': f"theme-{normalize_theme_id(current_user.theme_id if current_user else None)}",
        'can_manage_users': has_admin_access(request),
        'can_manage_stock': has_stock_write_access(request),
        #'persistent_notice': 'Mode dÃ©mo atelier : certaines donnÃ©es de test sont prÃ©sentes et lâ€™interface peut Ã©voluer sans garantie.',
    }
    with SessionLocal() as toolbar_db:
        base_context.update(workshop_template_context(request, toolbar_db))
    base_context.update(context)
    return templates.TemplateResponse(template_name, base_context, status_code=status_code)
