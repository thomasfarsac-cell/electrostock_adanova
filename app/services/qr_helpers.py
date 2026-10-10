from __future__ import annotations

from app.models import Component, Location
from app.services.component_labels import make_qr_png as make_component_label_qr_png


def build_qr_payload(component: Component) -> str:
    return f'C:{component.id}'


def build_location_qr_payload(location: Location) -> str:
    return f'L:{location.id}'


def make_qr_png(payload: str) -> bytes:
    return make_component_label_qr_png(payload, 'L')
