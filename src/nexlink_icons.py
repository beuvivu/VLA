"""Exact vectors from the requested Nexlink shell; no hand-drawn substitutes."""
from functools import lru_cache
from html import escape
import json
from pathlib import Path
import re

_ASSETS = Path(__file__).with_name('assets') / 'nexlink'
_NAMES = frozenset(name.removesuffix('.svg') for name in
                   json.loads((_ASSETS / 'provenance.json').read_text())['sha256'])


@lru_cache(maxsize=None)
def _source(name: str) -> str:
    if name not in _NAMES:
        raise ValueError(f'Unknown Nexlink icon: {name}')
    svg = (_ASSETS / f'{name}.svg').read_text().strip()
    # Preserve every path, primitive and opacity. Only adapt theme color tokens.
    svg = svg.replace('var(--bs-heading-color)', 'currentColor')
    svg = svg.replace('var(--bs-primary)', 'currentColor').replace('#1C274C', 'currentColor')
    return re.sub(r' class="[^"]*"', '', svg, count=1)


def nexlink_icon(name: str, css_class: str = 'app-ic app-nexlink-ic') -> str:
    return _source(name).replace('<svg ',
        f'<svg class="{escape(css_class, quote=True)}" data-nexlink-icon="{escape(name, quote=True)}" '
        'aria-hidden="true" focusable="false" ', 1)


_NAVIGATION = {
    'truc-tiep': 'inbox-in', 'hom-nay': 'house-blank', 'so-ket-qua': 'calendar-lines',
    'ma-tran': 'table', 'tan-suat': 'growth-chart-invest', 'gan-nhip': 'calendar',
    'cap-lon': 'arrows', 'cau-chay': 'growth-chart-invest', 'cau-on-dinh': 'review',
    'cau-de-chay': 'flux-capacitor', 'cau-de-on-dinh': 'chart-pie-alt',
    'vi-tri-cau': 'map-marker', 'ai-ml': 'circle-user', 'top-loto': 'list',
    'top-de': 'star', 'chat-luong': 'review', 'theo-ngay': 'calendar',
    'theo-thang': 'calendar-lines', 'theo-nam': 'calendar', 'chu-ky': 'arrows',
    'bo-so': 'tab-folder', 'ngay-mai': 'calendar-lines', 'cap-loto': 'flux-capacitor',
    'cap-lon-loto': 'arrows', 'cau-giai-db': 'marker', 'theo-tong': 'percent-100',
    'dau-duoi': 'table-list', 'lo-gan': 'calendar', 'tong-hop': 'chart-pie-alt',
    'nghien-cuu': 'sliders-h-square', 'kiem-dinh': 'form',
}


def navigation_icon(key: str) -> str:
    """Use the same Flaticon Rounded outlines as Nexlink's expanded sidebar."""
    return nexlink_icon(_NAVIGATION[key])
