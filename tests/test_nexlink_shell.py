"""Nexlink shell must preserve the reference vectors, order and working targets."""
import hashlib
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
ASSETS = ROOT / 'src/assets/nexlink'
RAIL = ['home', 'crown', 'layers', 'circles', 'components', 'code',
        'clipboard', 'chart', 'robot', 'plus', 'exit']


def test_reference_vectors_are_preserved_in_the_rendered_shell():
    from nexlink_icons import nexlink_icon
    manifest = json.loads((ASSETS / 'provenance.json').read_text())
    assert manifest['source'] == 'https://nexlink.layoutdrop.com/demo/index.html'
    # These hashes were recorded directly from the reference, before implementation.
    assert manifest['sha256']['home.svg'] == 'e1abae9be24be1865761b149c227a30da5a6dce986d20b4628987d6b481ab399'
    assert manifest['sha256']['crown.svg'] == '48517fa2181c1844f19cc6bbc94a064683b8a6285adaa6caa5824817c3b945bf'
    for name, digest in manifest['sha256'].items():
        assert hashlib.sha256((ASSETS / name).read_bytes()).hexdigest() == digest
        original = ET.parse(ASSETS / name).getroot()
        rendered = ET.fromstring(nexlink_icon(name.removesuffix('.svg')))
        assert original.get('viewBox') == rendered.get('viewBox')
        for attr in ('width', 'height'):
            assert original.get(attr) == rendered.get(attr)
        assert rendered.get('aria-hidden') == 'true'
        # Only color tokens may change; geometry and duotone opacity stay exact.
        def geometry(svg):
            return [(e.tag.split('}')[-1], {k:v for k,v in e.attrib.items()
                     if k not in ('fill','stroke')}) for e in svg.iter() if e is not svg]
        assert geometry(original) == geometry(rendered), name


def test_full_reference_rail_order_and_separators():
    from app_shell import rail_html
    soup = BeautifulSoup(rail_html('index.html'), 'html.parser')
    assert [n['data-nexlink-icon'] for n in soup.select('.app-rail-list svg')] == RAIL
    assert len(soup.select('.app-rail-divider')) == 3
    assert len(soup.select('[role=tab]')) == 7
    for link in soup.select('a[href]'):
        assert (ROOT / 'docs' / link['href'].split('#')[0]).is_file()


def test_header_has_the_reference_controls_and_real_dropdown_links():
    from app_shell import header_html
    soup = BeautifulSoup(header_html('index.html'), 'html.parser')
    assert [n['data-nexlink-icon'] for n in soup.select('.app-header-inner > .app-toggle svg')] == ['chevrons']
    assert [n['data-nexlink-icon'] for n in soup.select('#app-theme svg')] == ['sun', 'moon']
    assert [n['data-nexlink-icon'] for n in soup.select('.app-header-tools > a svg, .app-header-tools > .app-dropdown > button svg')] == ['inbox', 'bell', 'calendar']
    assert soup.select_one('#app-profile-toggle[aria-expanded=false]')
    assert soup.select_one('#app-notifications-toggle[aria-expanded=false]')
    assert soup.select_one('#app-fullscreen')
    for link in soup.select('a[href]'):
        assert (ROOT / 'docs' / link['href'].split('#')[0]).is_file()
