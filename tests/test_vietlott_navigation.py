"""Vietlott có phân hệ riêng, đích thực và thống kê đúng cửa sổ công bố."""
from bs4 import BeautifulSoup
from app_shell import rail_html, panel_html
from ui_theme import SITE_NAV_SECTIONS
from vietlott_navigation_content import statistics, overview_sections


def test_vietlott_is_independent_and_keeps_every_product():
    rail = BeautifulSoup(rail_html('vietlott-mega-645.html'), 'html.parser')
    active = rail.select_one('[aria-selected=true]')
    assert active['aria-label'] == 'Vietlott'
    assert active['data-app-module'] == 'vietlott'
    groups = dict(SITE_NAV_SECTIONS)
    assert all(not href.startswith('vietlott') for _, items in groups['Kết quả'] for href, _, _ in items)
    links = [href for _, items in groups['Vietlott'] for href, _, _ in items]
    assert len([href for href in links if href.startswith('vietlott-')]) == 7
    assert len(links) == 18


def test_every_vietlott_anchor_exists_even_when_no_data():
    soup = BeautifulSoup(overview_sections({}), 'html.parser')
    nav = BeautifulSoup(panel_html('vietlott.html'), 'html.parser')
    links = nav.select('[data-app-module=vietlott] a[href*="#"]')
    assert len(links) == 10
    for link in links:
        assert soup.find(id=link['href'].split('#')[1]), link['href']
    assert 'không phải heartbeat trực tiếp' in soup.get_text()
    assert 'chỉ đọc' in soup.get_text()


def test_statistics_count_draw_presence_ignore_bonus_and_include_zeroes():
    result = statistics([{'numbers': [1, 1, 2], 'bonus': 3}, {'numbers': [1, 4], 'bonus': 2}], 5)
    assert result['counts'][1] == 2
    assert result['counts'][2] == 1
    assert result['counts'][3] == 0
    assert result['pairs'] == [((1, 2), 1), ((1, 4), 1)]
    assert result['hot'][0] == 1
    assert result['cold'][:2] == [3, 5]
    assert result['count'] == 2


def test_model_checkpoint_comes_from_the_engine_that_made_the_forecast():
    dashboard = {'products': [{'product': 'mega645', 'next_forecast': {
        'engine': 'ml', 'registered': True, 'target_id': 501, 'based_on_id': 500, 'components': []}}],
        'analysis': {'mega645': {'draws': 999, 'last_id': 999, 'last_date': '2026-10-07', 'evidence': {}}}}
    soup = BeautifulSoup(overview_sections(dashboard), 'html.parser')
    table = soup.find(id='vl-models').find_parent('section')
    row = next(tr for tr in table.select('tbody tr') if 'Mega 6/45' in tr.get_text())
    assert row.select('td')[-1].get_text() == '500'
