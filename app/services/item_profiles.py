from __future__ import annotations

import json

from app.models import Workshop


DEFAULT_WORKSHOP_SLUG = 'electronics'
ITEM_PROFILE_FIELDS = (
    'part_number',
    'manufacturer',
    'package',
    'datasheet_url',
    'minimum_quantity',
    'keywords',
    'description',
    'notes',
)
DEFAULT_ITEM_FIELD_PROFILE = {
    'part_number': {'visible': True, 'label': 'Référence'},
    'manufacturer': {'visible': True, 'label': 'Marque / fabricant'},
    'package': {'visible': True, 'label': 'Format / conditionnement'},
    'datasheet_url': {'visible': True, 'label': 'Fiche technique / lien'},
    'minimum_quantity': {'visible': True, 'label': 'Stock mini'},
    'keywords': {'visible': True, 'label': 'Mots-clés'},
    'description': {'visible': True, 'label': 'Description'},
    'notes': {'visible': True, 'label': 'Notes'},
}
ITEM_PROFILE_TEMPLATES = {
    'electronics': {
        'label': 'Électronique',
        'fields': {
            **DEFAULT_ITEM_FIELD_PROFILE,
            'manufacturer': {'visible': True, 'label': 'Fabricant'},
            'package': {'visible': True, 'label': 'Boîtier'},
            'datasheet_url': {'visible': True, 'label': 'Datasheet / fiche technique'},
            'minimum_quantity': {'visible': True, 'label': 'Stock minimum'},
        },
    },
    'three_d_printing': {
        'label': 'Impression 3D',
        'fields': {
            **DEFAULT_ITEM_FIELD_PROFILE,
            'manufacturer': {'visible': True, 'label': 'Marque'},
            'package': {'visible': True, 'label': 'Format / bobine'},
            'datasheet_url': {'visible': True, 'label': 'Fiche matériau / lien'},
            'minimum_quantity': {'visible': True, 'label': 'Seuil minimum'},
        },
    },
    'creative': {
        'label': 'Création',
        'fields': {
            **DEFAULT_ITEM_FIELD_PROFILE,
            'manufacturer': {'visible': True, 'label': 'Marque / fournisseur'},
            'package': {'visible': True, 'label': 'Conditionnement'},
            'datasheet_url': {'visible': False, 'label': 'Lien ressource'},
            'minimum_quantity': {'visible': True, 'label': 'Seuil minimum'},
        },
    },
    'mechanical': {
        'label': 'Mécanique',
        'fields': {
            **DEFAULT_ITEM_FIELD_PROFILE,
            'part_number': {'visible': True, 'label': 'Référence outil'},
            'manufacturer': {'visible': True, 'label': 'Marque'},
            'package': {'visible': True, 'label': 'Type / format'},
            'datasheet_url': {'visible': True, 'label': 'Fiche technique / lien'},
            'minimum_quantity': {'visible': True, 'label': 'Stock minimum'},
        },
    },
    'consumables': {
        'label': 'Consommables',
        'fields': {
            **DEFAULT_ITEM_FIELD_PROFILE,
            'manufacturer': {'visible': True, 'label': 'Fournisseur / marque'},
            'package': {'visible': True, 'label': 'Conditionnement'},
            'datasheet_url': {'visible': True, 'label': 'FDS / lien sécurité'},
            'minimum_quantity': {'visible': True, 'label': 'Seuil de réapprovisionnement'},
        },
    },
    'library_collection': {
        'label': 'Bibliothèque / collection',
        'fields': {
            **DEFAULT_ITEM_FIELD_PROFILE,
            'part_number': {'visible': True, 'label': 'Référence / code'},
            'manufacturer': {'visible': True, 'label': 'Auteur / éditeur / marque'},
            'package': {'visible': True, 'label': 'Format / édition'},
            'datasheet_url': {'visible': False, 'label': 'Lien ressource'},
            'minimum_quantity': {'visible': False, 'label': 'Quantité mini'},
        },
    },
}
ITEM_PROFILE_TEMPLATE_OPTIONS = tuple(
    {'id': template_id, 'label': data['label']}
    for template_id, data in ITEM_PROFILE_TEMPLATES.items()
) + ({'id': 'custom', 'label': 'Personnalisé'},)



def default_item_profile_for_workshop(workshop: Workshop | None) -> dict:
    template_id = 'electronics' if workshop and workshop.slug == DEFAULT_WORKSHOP_SLUG else 'custom'
    base = ITEM_PROFILE_TEMPLATES.get(template_id, {'fields': DEFAULT_ITEM_FIELD_PROFILE})['fields']
    return {
        'template': template_id,
        'fields': {
            field: dict(base[field])
            for field in ITEM_PROFILE_FIELDS
        }
    }


def merge_item_profile(workshop: Workshop | None) -> dict:
    profile = default_item_profile_for_workshop(workshop)
    raw = (workshop.item_profile_json if workshop else '') or ''
    if raw.strip():
        try:
            saved = json.loads(raw)
        except json.JSONDecodeError:
            saved = {}
        saved_template = str(saved.get('template') or '').strip() if isinstance(saved, dict) else ''
        if saved_template in ITEM_PROFILE_TEMPLATES or saved_template == 'custom':
            profile['template'] = saved_template
        saved_fields = saved.get('fields') if isinstance(saved, dict) else {}
        if isinstance(saved_fields, dict):
            for field in ITEM_PROFILE_FIELDS:
                saved_config = saved_fields.get(field)
                if not isinstance(saved_config, dict):
                    continue
                label = str(saved_config.get('label') or '').strip()
                if label:
                    profile['fields'][field]['label'] = label[:80]
                if 'visible' in saved_config:
                    profile['fields'][field]['visible'] = bool(saved_config.get('visible'))
    return profile


def normalize_item_profile_fields(fields: dict) -> dict:
    normalized = {}
    for field in ITEM_PROFILE_FIELDS:
        raw = fields.get(field) if isinstance(fields, dict) else {}
        raw = raw if isinstance(raw, dict) else {}
        label = str(raw.get('label') or DEFAULT_ITEM_FIELD_PROFILE[field]['label']).strip()
        normalized[field] = {
            'visible': bool(raw.get('visible', True)),
            'label': (label or DEFAULT_ITEM_FIELD_PROFILE[field]['label'])[:80],
        }
    return normalized


def infer_item_profile_template(fields: dict, selected_template: str = '') -> str:
    normalized = normalize_item_profile_fields(fields)
    for template_id, template in ITEM_PROFILE_TEMPLATES.items():
        if normalized == normalize_item_profile_fields(template['fields']):
            return template_id
    return selected_template if selected_template == 'custom' else 'custom'


def item_field_visible(profile: dict, field: str) -> bool:
    return bool(profile.get('fields', {}).get(field, {}).get('visible', True))


def item_field_label(profile: dict, field: str) -> str:
    fallback = DEFAULT_ITEM_FIELD_PROFILE.get(field, {}).get('label', field)
    return str(profile.get('fields', {}).get(field, {}).get('label') or fallback)


def item_profile_settings_rows(profile: dict) -> list[dict]:
    return [
        {
            'key': field,
            'visible': item_field_visible(profile, field),
            'label': item_field_label(profile, field),
        }
        for field in ITEM_PROFILE_FIELDS
    ]


def build_item_profile_from_form(form_data) -> dict:
    fields = {
            field: {
                'visible': str(form_data.get(f'item_field_{field}_visible', '')).lower() in {'1', 'true', 'on', 'yes'},
                'label': (str(form_data.get(f'item_field_{field}_label', '')).strip() or DEFAULT_ITEM_FIELD_PROFILE[field]['label'])[:80],
            }
            for field in ITEM_PROFILE_FIELDS
        }
    selected_template = str(form_data.get('item_profile_template', '')).strip()
    return {
        'template': infer_item_profile_template(fields, selected_template),
        'fields': normalize_item_profile_fields(fields),
    }

