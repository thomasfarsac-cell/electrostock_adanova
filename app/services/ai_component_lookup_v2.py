from __future__ import annotations

import json
from urllib import error, request

from app.config import OPENAI_COMPONENT_LOOKUP_MODEL, OPENAI_COMPONENT_LOOKUP_TIMEOUT, OPENAI_RESPONSES_API_URL
from app.services.env_settings import get_env_value

DEFAULT_COMPONENT_LOOKUP_SYSTEM_PROMPT = (
    "Tu aides a pre-remplir une fiche de composant electronique pour un stock atelier. "
    "Retourne uniquement du JSON conforme au schema fourni. "
    "Quand une information est incertaine, laisse null ou une chaine vide plutot que d'inventer. "
    "Si c'est utile, tu peux utiliser le web pour chercher les informations techniques les plus fiables. "
    "Privilegie les datasheets fabricants et distributeurs reconnus. "
    "La designation doit etre claire, complete et exploitable directement dans la fiche, idealement du type: "
    "'HSN-2510SR Afficheur bargraph LED 10 segments rouge'. "
    "La description doit etre multi-ligne, pratique, en 3 a 8 lignes selon le composant, avec les caracteristiques utiles a l'utilisateur. "
    "Choisis une categorie et un fabricant uniquement parmi les listes fournies quand il y a une correspondance claire. "
    "Tu peux proposer un boitier meme s'il n'existe pas encore localement. "
    "N'utilise jamais ni ne propose d'emplacement de stock physique: l'emplacement est choisi par l'utilisateur. "
    "Le champ notes doit rappeler a l'utilisateur de verifier les donnees avant enregistrement."
)


def is_ai_component_lookup_enabled() -> bool:
    return bool(get_env_value('OPENAI_API_KEY', '').strip())


def is_web_search_enabled() -> bool:
    return get_env_value('OPENAI_COMPONENT_LOOKUP_USE_WEB_SEARCH', 'true').strip().lower() in {'1', 'true', 'yes', 'on'}


def build_component_lookup_prompts(
    part_number: str,
    categories: list[str],
    manufacturers: list[str],
    packages: list[str],
    custom_fields: list[dict[str, str]],
    system_prompt_override: str | None = None,
):
    system_prompt = (
        (system_prompt_override or '').strip()
        or get_env_value('OPENAI_COMPONENT_LOOKUP_SYSTEM_PROMPT', '').strip()
        or DEFAULT_COMPONENT_LOOKUP_SYSTEM_PROMPT
    )
    user_prompt = json.dumps(
        {
            'part_number': part_number,
            'available_category_paths': categories,
            'available_manufacturers': manufacturers,
            'available_packages': packages,
            'available_custom_fields': custom_fields,
            'instructions': [
                "Renseigne le maximum d'informations utiles pour la fiche.",
                "La designation doit inclure la reference si cela aide la lisibilite.",
                "Les mots-cles doivent etre courts, utiles a la recherche interne, et sans doublons.",
                "La description doit etre detaillee, lisible, et contenir des retours a la ligne.",
                "Ne propose un minimum_quantity que si c'est raisonnablement estimable; sinon null.",
                "Si une valeur de champ personnalise est pertinente, ajoute-la dans custom_fields.",
                "Ajoute dans warnings les points a verifier par l'utilisateur.",
                "Ajoute dans sources les URLs ou domaines utilises quand ils existent.",
            ],
        },
        ensure_ascii=True,
    )
    return system_prompt, user_prompt


def _nullable_string_schema():
    return {'anyOf': [{'type': 'string'}, {'type': 'null'}]}


def _nullable_integer_schema():
    return {'anyOf': [{'type': 'integer'}, {'type': 'null'}]}


def _response_schema():
    return {
        'type': 'object',
        'properties': {
            'name': _nullable_string_schema(),
            'category_path': _nullable_string_schema(),
            'manufacturer_name': _nullable_string_schema(),
            'package_name': _nullable_string_schema(),
            'minimum_quantity': _nullable_integer_schema(),
            'datasheet_url': _nullable_string_schema(),
            'keywords': {
                'type': 'array',
                'items': {'type': 'string'},
            },
            'description': _nullable_string_schema(),
            'notes': _nullable_string_schema(),
            'custom_fields': {
                'type': 'array',
                'items': {
                    'type': 'object',
                    'properties': {
                        'name': {'type': 'string'},
                        'value': {'type': 'string'},
                    },
                    'required': ['name', 'value'],
                    'additionalProperties': False,
                },
            },
            'sources': {
                'type': 'array',
                'items': {'type': 'string'},
            },
            'warnings': {
                'type': 'array',
                'items': {'type': 'string'},
            },
            'confidence': {
                'type': 'string',
                'enum': ['low', 'medium', 'high'],
            },
        },
        'required': [
            'name',
            'category_path',
            'manufacturer_name',
            'package_name',
            'minimum_quantity',
            'datasheet_url',
            'keywords',
            'description',
            'notes',
            'custom_fields',
            'sources',
            'warnings',
            'confidence',
        ],
        'additionalProperties': False,
    }


def _extract_output_text(payload: dict) -> str:
    output_text = payload.get('output_text')
    if output_text:
        return output_text

    for item in payload.get('output', []):
        for content in item.get('content', []):
            text = content.get('text')
            if text:
                return text
    return ''


def lookup_component_details(
    part_number: str,
    categories: list[str],
    manufacturers: list[str],
    packages: list[str],
    custom_fields: list[dict[str, str]],
    system_prompt_override: str | None = None,
) -> dict:
    api_key = get_env_value('OPENAI_API_KEY', '').strip()
    if not api_key:
        raise RuntimeError("La recherche IA n'est pas configuree. Ajoutez OPENAI_API_KEY dans les parametres.")

    system_prompt, user_prompt = build_component_lookup_prompts(
        part_number=part_number,
        categories=categories,
        manufacturers=manufacturers,
        packages=packages,
        custom_fields=custom_fields,
        system_prompt_override=system_prompt_override,
    )

    body = {
        'model': OPENAI_COMPONENT_LOOKUP_MODEL,
        'input': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_prompt},
        ],
        'text': {
            'format': {
                'type': 'json_schema',
                'name': 'component_lookup',
                'strict': True,
                'schema': _response_schema(),
            }
        },
    }
    if is_web_search_enabled():
        body['tools'] = [{'type': 'web_search_preview'}]

    req = request.Request(
        OPENAI_RESPONSES_API_URL,
        data=json.dumps(body).encode('utf-8'),
        headers={
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        },
        method='POST',
    )

    try:
        with request.urlopen(req, timeout=OPENAI_COMPONENT_LOOKUP_TIMEOUT) as response:
            payload = json.loads(response.read().decode('utf-8'))
    except error.HTTPError as exc:
        detail = exc.read().decode('utf-8', errors='ignore')
        raise RuntimeError(f"OpenAI a renvoye une erreur HTTP {exc.code}. {detail[:400]}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"Impossible de joindre l'API OpenAI: {exc.reason}") from exc

    output_text = _extract_output_text(payload).strip()
    if not output_text:
        raise RuntimeError("La reponse OpenAI ne contient aucun resultat exploitable.")

    try:
        return json.loads(output_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError("La reponse OpenAI n'a pas pu etre interpretee en JSON.") from exc
