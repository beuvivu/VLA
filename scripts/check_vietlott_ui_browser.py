"""Kiểm tra Vietlott thật: responsive, màu, đối chiếu và bộ số nháp trên Chromium."""
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
from threading import Thread

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'ui-browser-artifacts'
PAGES = ('vietlott.html', 'vietlott-lotto-535.html', 'vietlott-mega-645.html',
         'vietlott-power-655.html', 'vietlott-max-3d.html', 'vietlott-max-3d-pro.html',
         'vietlott-keno.html', 'vietlott-bingo18.html')
COMPARISON_CASES = {
    'vietlott-mega-645.html': {
        'product': 'mega645', 'prediction': '01 02 03 04 05 06',
        'actual': '01 02 03 07 08 09', 'hits': 3, 'total': 6,
        'accuracy': '50%', 'tier': 'Giải ba', 'matched': ['01', '02', '03'],
    },
    'vietlott-power-655.html': {
        'product': 'power655', 'prediction': '01 02 03 04 05 06',
        'actual': '01 02 03 04 05 07', 'actual_bonus': '06',
        'hits': 5, 'total': 6, 'accuracy': '83,33%', 'tier': 'Jackpot 2',
        'matched': ['01', '02', '03', '04', '05'], 'bonus': '06',
    },
    'vietlott-lotto-535.html': {
        'product': 'lotto535', 'prediction': '01 02 03 04 05',
        'actual': '06 07 08 09 10', 'predicted_bonus': '03', 'actual_bonus': '03',
        'hits': 0, 'total': 5, 'accuracy': '0%', 'tier': 'Khuyến khích',
        'matched': [], 'bonus': '03',
    },
}


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *_args):
        pass


def assert_no_page_overflow(page, label):
    sizes = page.evaluate('''() => ({viewport: innerWidth,
        html: document.documentElement.scrollWidth, body: document.body.scrollWidth})''')
    assert sizes['html'] <= sizes['viewport'] + 1, (label, sizes)
    assert sizes['body'] <= sizes['viewport'] + 1, (label, sizes)


def check_single_line_sequences(page, label):
    """Main numbers must stay together, including inside horizontally scrollable tables."""
    rows = page.locator('.vl-number-sequence, .vl-comparison-balls').evaluate_all('''elements =>
        elements.map(el => ({text: el.textContent, balls: [...el.querySelectorAll('.vl-ball')]
            .map(ball => {const r = ball.getBoundingClientRect(); return r.top + r.height / 2;})}))''')
    for row in rows:
        if len(row['balls']) > 1:
            assert max(row['balls']) - min(row['balls']) <= 1, (label, row)


def check_max_prize_alignment(page, label):
    """A Max prize label sits beside its own number row, even when that row scrolls."""
    rows = page.locator('.vl-3d > div').evaluate_all('''elements => elements.map(el => {
        const label = el.querySelector('.vl-prize-label, small');
        const sequence = el.querySelector('.vl-number-sequence') || el.querySelector(':scope > span');
        if (!label || !sequence) return {error: 'missing prize label or number sequence'};
        const a = label.getBoundingClientRect(), b = sequence.getBoundingClientRect();
        return {label: label.textContent, numbers: sequence.textContent,
            visible: a.width > 0 && a.height > 0 && getComputedStyle(label).visibility === 'visible',
            labelY: a.top + a.height / 2, sequenceY: b.top + b.height / 2,
            labelRight: a.right, sequenceLeft: b.left,
            balls: sequence.querySelectorAll('.vl-ball').length};
    })''')
    for row in rows:
        assert 'error' not in row, (label, row)
        assert row['visible'], (label, 'Max prize label hidden', row)
        assert abs(row['labelY'] - row['sequenceY']) <= 1, (label, 'Max prize label moved above its numbers', row)
        assert row['labelRight'] <= row['sequenceLeft'] + 1, (label, 'Max prize label overlaps its numbers', row)
        assert row['balls'] > 0, (label, 'Max result missing number balls', row)


def check_latest_bonus_visible(page, name, width, label):
    """Compact Power/Lotto results expose the bonus without horizontal scrolling on phones."""
    if name not in ('vietlott-power-655.html', 'vietlott-lotto-535.html') or width not in (320, 390):
        return
    sequences = page.locator('section[aria-labelledby="vl-latest"] .vl-number-sequence')
    expect(sequences).to_have_count(1)
    expect(sequences.locator('.vl-ball--bonus')).to_be_visible()
    rows = sequences.evaluate_all('''elements => elements.map(el => {
        const clip = el.getBoundingClientRect(), balls = [...el.querySelectorAll('.vl-ball')];
        const bonus = el.querySelector('.vl-ball--bonus'), b = bonus?.getBoundingClientRect();
        return {text: el.textContent, bonus: b ? {left: b.left, right: b.right} : null,
            left: clip.left, right: clip.right, viewport: innerWidth,
            scrollWidth: el.scrollWidth, clientWidth: el.clientWidth,
            fontSizes: balls.map(ball => parseFloat(getComputedStyle(ball).fontSize))};
    })''')
    for row in rows:
        assert row['bonus'], (label, 'latest result has no bonus ball', row)
        assert row['bonus']['left'] >= row['left'] - 1, (label, row)
        assert row['bonus']['right'] <= min(row['right'], row['viewport']) + 1, (label, 'latest bonus clipped', row)
        assert row['scrollWidth'] <= row['clientWidth'] + 1, (label, 'latest result requires horizontal scroll', row)
        assert min(row['fontSizes']) >= 12, (label, 'compact numbers too small to read', row)


def check_bonus_palette(scope, label):
    """A matched bonus keeps the rose fill and ink; only its match outline may change."""
    styles = scope.locator('.vl-ball--bonus, .vl-ball--bonus-hit').evaluate_all('''elements =>
        elements.map(el => {
            const actual = getComputedStyle(el);
            const reference = document.createElement('span'); reference.className = 'vl-ball vl-ball--bonus';
            el.parentElement.append(reference);
            const expected = getComputedStyle(reference);
            const values = {text: el.textContent, classes: el.className,
                ink: actual.color, fill: actual.backgroundImage,
                roseInk: expected.color, roseFill: expected.backgroundImage};
            reference.remove(); return values;
        })''')
    for style in styles:
        assert style['ink'] == style['roseInk'], (label, 'bonus ink lost rose meaning', style)
        assert style['fill'] == style['roseFill'], (label, 'bonus fill became a main-number hit', style)


def check_jackpots(page, label):
    """Large amounts remain one line and scroll within their own card if necessary."""
    values = page.locator('.vl-jackpot-value')
    originals = values.all_text_contents()
    try:
        for value in values.all():
            value.evaluate('el => {el.textContent = "999.999.999.999.999 ₫";}')
        assert_no_page_overflow(page, (label, 'long jackpot'))
        lines = values.evaluate_all('''elements => elements.map(el => {
            const range = document.createRange(); range.selectNodeContents(el);
            const rects = [...range.getClientRects()].filter(r => r.width && r.height);
            const r = el.getBoundingClientRect();
            return {text: el.textContent, tops: rects.map(r => r.top),
                left: r.left, right: r.right, viewport: innerWidth,
                overflow: getComputedStyle(el).overflowX,
                clipped: el.scrollWidth > el.clientWidth + 1};
        })''')
        for line in lines:
            assert line['tops'] and max(line['tops']) - min(line['tops']) <= 1, (label, line)
            assert line['left'] >= -1 and line['right'] <= line['viewport'] + 1, (label, line)
            if line['clipped']:
                assert line['overflow'] in ('auto', 'scroll'), (label, line)
    finally:
        for value, original in zip(values.all(), originals, strict=True):
            value.evaluate('(el, text) => {el.textContent = text;}', original)


def check_ball_contrast(page, scope, label):
    """Check actual computed sky/rose/green text against each solid gradient endpoint."""
    colors = scope.locator('.vl-ball').evaluate_all(r'''elements => elements.map(el => {
        const style = getComputedStyle(el);
        const canvas = document.createElement('canvas'); canvas.width = canvas.height = 1;
        const ctx = canvas.getContext('2d');
        const rgb = color => {
            ctx.clearRect(0, 0, 1, 1); ctx.fillStyle = color;
            ctx.fillRect(0, 0, 1, 1); return [...ctx.getImageData(0, 0, 1, 1).data];
        };
        const text = rgb(style.color).slice(0, 3);
        const gradientColors = style.backgroundImage.match(/rgba?\([^)]*\)|color\([^)]*\)/g) || [];
        const stops = gradientColors.map(rgb).filter(color => color[3] === 255)
            .map(color => color.slice(0, 3));
        return {classes: el.className, text, stops, background: style.backgroundImage};
    })''')

    def luminance(rgb):
        channels = [channel / 255 for channel in rgb]
        linear = [channel / 12.92 if channel <= .04045 else ((channel + .055) / 1.055) ** 2.4
                  for channel in channels]
        return sum(channel * weight for channel, weight in zip(linear, (.2126, .7152, .0722), strict=True))

    for color in colors:
        assert color['stops'], (label, 'missing opaque gradient endpoints', color)
        ink = luminance(color['text'])
        ratios = [(max(ink, luminance(stop)) + .05) / (min(ink, luminance(stop)) + .05)
                  for stop in color['stops']]
        assert min(ratios) >= 4.5, (label, color, ratios)


def check_reduced_motion(page, button, label):
    assert page.evaluate('matchMedia("(prefers-reduced-motion: reduce)").matches')
    button.click()
    button.hover()
    motion_script = '''el => ({transform: getComputedStyle(el).transform,
        transition: getComputedStyle(el).transitionDuration,
        shimmer: getComputedStyle(el, '::before').animationName,
        ripple: el.querySelectorAll('.vl-button-ripple').length})'''
    page.mouse.down()
    try:
        active = button.evaluate(motion_script)
    finally:
        page.mouse.up()
    for motion in (active, button.evaluate(motion_script)):
        assert motion['transform'] == 'none', (label, motion)
        assert all(float(value.strip().removesuffix('s')) == 0
                   for value in motion['transition'].split(',')), (label, motion)
        assert motion['shimmer'] == 'none' and motion['ripple'] == 0, (label, motion)


def check_registered_comparisons(page, label):
    """Registered tickets keep their own score and never turn pending draws into zero hits."""
    for summary in page.locator('.vl-comparison-summary').all():
        expect(summary.locator('.vl-comparison-stat')).to_have_count(4)
        for stat in summary.locator('.vl-comparison-stat').all():
            box = stat.bounding_box()
            assert box['width'] > 0 and box['x'] >= -1, (label, box)
            assert box['x'] + box['width'] <= page.viewport_size['width'] + 1, (label, box)
    for table in page.locator('.vl-comparison-table').all():
        expect(table.locator('thead th')).to_have_count(6)
        rows = table.locator('tbody tr')
        cursor = 0
        while cursor < rows.count():
            first = rows.nth(cursor)
            metadata = first.locator(':scope > .vl-comparison-meta')
            expect(metadata).to_have_count(3)
            span = metadata.first.evaluate('el => el.rowSpan')
            assert span >= 1 and cursor + span <= rows.count(), (label, 'draw rowspans escape their ticket group')
            target = first.get_attribute('data-vl-comparison-target')
            status = first.get_attribute('data-vl-comparison-status')
            assert target and status in ('matched', 'pending', 'date_mismatch'), (label, target, status)
            expect(first.locator('th')).to_have_text(f'#{target}')
            for cell in metadata.all():
                assert cell.evaluate('el => el.rowSpan') == span, (label, 'metadata spans different ticket groups')
            for index in range(span):
                row = rows.nth(cursor + index)
                expect(row).to_have_attribute('data-vl-comparison-target', target)
                expect(row).to_have_attribute('data-vl-comparison-status', status)
                expect(row).to_have_attribute('data-vl-comparison-ticket', str(index + 1))
                if index:
                    expect(row.locator(':scope > .vl-comparison-meta, :scope > th')).to_have_count(0)
                check_registered_ticket_row(row, status, index + 1, label)
            cursor += span


def check_registered_ticket_row(row, status, ticket_number, label):
    """One visual row ties the ticket, its actual result and its score together."""
    prediction_cell = row.locator('.vl-comparison-prediction')
    actual_cell = row.locator('.vl-comparison-result')
    score_cell = row.locator('.vl-comparison-score-cell')
    for cell in (prediction_cell, actual_cell, score_cell):
        expect(cell).to_have_count(1)
    if not prediction_cell.locator('.vl-comparison-ticket').count():
        expect(prediction_cell).to_have_text('—')
        expect(actual_cell).to_contain_text(re.compile(r'Chưa.*đối chiếu'))
        expect(score_cell).to_contain_text('—')
        expect(row.locator('.vl-ball--match, .vl-ball--bonus-hit')).to_have_count(0)
        return
    if status in ('pending', 'date_mismatch'):
        expect(actual_cell).to_contain_text('Chưa đối chiếu')
        expect(score_cell).to_contain_text('—')
        expect(row.locator('.vl-ball--match, .vl-ball--bonus-hit')).to_have_count(0)
        return
    ticket = prediction_cell.locator('.vl-comparison-ticket')
    actual = actual_cell.locator('.vl-comparison-actual')
    score = score_cell.locator('.vl-comparison-score')
    for part in (ticket, actual, score):
        expect(part).to_have_count(1)
    expect(ticket).to_have_attribute('data-vl-ticket', str(ticket_number))
    expect(actual.locator('small').first).to_have_text(f'Đối chiếu vé {ticket_number}')
    expect(score.locator('small').first).to_contain_text(f'Vé {ticket_number}')
    expect(score_cell.locator('.vl-comparison-tier')).to_have_count(1)
    tops = [part.bounding_box()['y'] for part in (ticket, actual, score)]
    assert max(tops) - min(tops) <= 1, (label, ticket_number, 'ticket/result/score drifted vertically', tops)
    centers = [part.locator('.vl-ball').first.evaluate('''el => {
        const r = el.getBoundingClientRect(); return r.top + r.height / 2;}''') for part in (ticket, actual)]
    assert abs(centers[0] - centers[1]) <= 1, (label, ticket_number, 'prediction and actual balls misaligned', centers)
    pair = re.search(r'(\d+)\s*/\s*(\d+)', score.locator('strong').inner_text())
    if pair:
        hits, total = map(int, pair.groups())
        expect(ticket.locator('.vl-ball--match')).to_have_count(hits)
        # Power's selected bonus match remains one of its six chosen main numbers.
        separate_bonus = ticket.locator('.vl-plus').count()
        expect(ticket.locator('.vl-ball')).to_have_count(total + separate_bonus)


def check_manual_comparison(page, name, width, theme):
    case = COMPARISON_CASES[name]
    label = (name, width, theme)
    form = page.locator(f'form[data-vl-comparison-widget="{case["product"]}"]')
    expect(form).to_have_count(1)
    prediction = form.locator('[data-vl-prediction]')
    actual = form.locator('[data-vl-actual]')
    submit = form.locator('[data-vl-comparison-submit]')
    output = form.locator('[data-vl-comparison-output]')
    status = form.locator('[data-vl-comparison-status]')
    expect(status).to_have_attribute('aria-live', 'polite')
    for field in form.locator('input').all():
        assert field.bounding_box()['height'] >= 44, (label, 'comparison input target')
    prediction.fill(case['prediction'])
    actual.fill(case['actual'])
    for key in ('predicted_bonus', 'actual_bonus'):
        if key in case:
            form.locator(f'[data-vl-{key.replace("_", "-")}]').fill(case[key])
    # Native form submission must work without a pointer, from a text input.
    actual.focus()
    page.keyboard.press('Enter')
    expect(output).to_be_visible()
    expect(output.locator('.vl-comparison-score')).to_contain_text(
        re.compile(rf'{case["hits"]}\s*/\s*{case["total"]}'))
    expect(output.locator('.vl-comparison-score')).to_contain_text(case['accuracy'])
    expect(output.locator('.vl-comparison-tier')).to_have_text(case['tier'])
    matches = output.locator('.vl-ball--match')
    expect(matches).to_have_count(2 * len(case['matched']))
    assert sorted(matches.all_text_contents()) == sorted(case['matched'] * 2), label
    bonus = output.locator('.vl-ball--bonus-hit')
    expect(bonus).to_have_count(2 if 'bonus' in case else 0)
    if 'bonus' in case:
        assert bonus.all_text_contents() == [case['bonus']] * 2, label
    check_single_line_sequences(page, label)
    check_bonus_palette(output, label)
    check_ball_contrast(page, output, label)
    assert_no_page_overflow(page, (label, 'comparison result'))
    check_reduced_motion(page, submit, label)
    if width in (390, 1440):
        page.locator('.vl-comparison-widget').screenshot(
            path=str(OUT / f'{name[:-5]}-comparison-{width}-{theme}.png'),
            style='[data-app-effects] { visibility: hidden !important; }')

    if 'actual_bonus' in case:
        # Main accuracy is useful without a bonus, but the prize remains unknown.
        form.locator('[data-vl-actual-bonus]').fill('')
        submit.click()
        expect(output).to_be_visible()
        expect(output.locator('.vl-comparison-score')).to_contain_text(case['accuracy'])
        expect(output.locator('.vl-comparison-tier')).to_have_attribute('data-vl-comparison-tier', 'unknown')
        expect(output.locator('.vl-comparison-tier')).to_have_text('Chưa đủ số đặc biệt để phân hạng')
        expect(output.locator('.vl-ball--bonus-hit')).to_have_count(0)
        expect(output.locator('.vl-comparison-bonus-status')).to_contain_text('chưa đủ dữ liệu')
        form.locator('[data-vl-actual-bonus]').fill(case['actual_bonus'])
        submit.click()
        expect(output.locator('.vl-comparison-tier')).to_have_text(case['tier'])

    # Bad submissions must remove an earlier result instead of displaying stale wins.
    invalids = ('01 01 ' + ' '.join(str(n) for n in range(2, case['total'])),
                '01 02', '01 02 03 04 99' + (' 06' if case['total'] == 6 else ''))
    for invalid in invalids:
        prediction.fill(invalid)
        submit.click()
        expect(output).to_be_hidden()
        expect(output).to_have_text('')
        expect(status).not_to_have_text('')
        expect(form.locator('.vl-ball--match, .vl-ball--bonus-hit')).to_have_count(0)
    prediction.fill(case['prediction'])
    actual.fill('01 invalid')
    submit.click()
    expect(output).to_be_hidden()
    expect(output).to_have_text('')
    expect(status).not_to_have_text('')
    actual.fill('')
    if 'actual_bonus' in case:
        form.locator('[data-vl-actual-bonus]').fill('')
    submit.click()
    expect(prediction).to_have_value(case['prediction'])
    expect(output).to_be_hidden()
    expect(output).to_have_text('')
    expect(status).to_contain_text('Chờ kết quả')
    assert '0%' not in status.inner_text(), (label, 'unknown result scored as zero')
    assert_no_page_overflow(page, (label, 'pending comparison'))


def main():
    OUT.mkdir(exist_ok=True)
    server = ThreadingHTTPServer(('127.0.0.1', 0), partial(QuietHandler, directory=str(ROOT / 'docs')))
    Thread(target=server.serve_forever, daemon=True).start()
    checks = []
    options = {}
    if os.environ.get('UI_CHROMIUM_EXECUTABLE'):
        options['executable_path'] = os.environ['UI_CHROMIUM_EXECUTABLE']
    if os.environ.get('UI_CHROMIUM_ARGS_FILE'):
        options['args'] = json.loads(Path(os.environ['UI_CHROMIUM_ARGS_FILE']).read_text())
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(**options)
            context = browser.new_context(reduced_motion='reduce', accept_downloads=True)
            for width in (320, 390, 768, 1440):
                for theme in ('light', 'dark'):
                    context.clear_cookies()
                    for name in PAGES:
                        page = context.new_page()
                        page.set_viewport_size({'width': width, 'height': 900})
                        page.emulate_media(color_scheme=theme)
                        errors = []
                        page.on('pageerror', lambda error, found=errors: found.append(str(error)))
                        page.goto(f'http://127.0.0.1:{server.server_port}/{name}', wait_until='networkidle')
                        page.evaluate('localStorage.removeItem("app-theme")')
                        page.reload(wait_until='networkidle')
                        page.evaluate('document.fonts.ready')
                        assert page.evaluate('document.documentElement.classList.contains("dark")') == (theme == 'dark')
                        label = (name, width, theme)
                        assert_no_page_overflow(page, label)
                        check_single_line_sequences(page, label)
                        check_max_prize_alignment(page, label)
                        check_latest_bonus_visible(page, name, width, label)
                        check_bonus_palette(page, label)
                        check_jackpots(page, label)
                        check_registered_comparisons(page, label)
                        assert 'Inter var' in page.locator('.vl-hero h1').evaluate('el => getComputedStyle(el).fontFamily')
                        assert page.evaluate('(font) => document.fonts.check(font)', '750 16px "Inter var"')
                        assert 'Instrument Sans' in page.locator('.app-header').evaluate('el => getComputedStyle(el).fontFamily')
                        for button in page.locator('.vl-button, .vl-pick, .vl-product').all():
                            if button.is_visible():
                                assert button.bounding_box()['height'] >= 44, (name, width)
                        if name in COMPARISON_CASES:
                            check_manual_comparison(page, name, width, theme)
                        if name in ('vietlott-mega-645.html', 'vietlott-power-655.html'):
                            board = page.locator('[data-vl-picks]')
                            for number in range(1, 7):
                                board.locator(f'[data-vl-number="{number}"]').click()
                            expect(board.locator('[aria-pressed="true"]')).to_have_count(6)
                            board.locator('[data-vl-number="7"]').click(force=True)
                            expect(board.locator('[aria-pressed="true"]')).to_have_count(6)
                            review = board.locator('[data-vl-review]')
                            review.click()
                            expect(board.locator('dialog')).to_be_visible()
                            expect(board.locator('[data-vl-preview]')).to_have_text('01 · 02 · 03 · 04 · 05 · 06')
                            with page.expect_download() as download:
                                board.locator('[data-vl-download]').click()
                            assert download.value.suggested_filename.endswith('-bo-so-nhap.txt')
                            text = Path(download.value.path()).read_text(encoding='utf-8')
                            assert 'BỘ SỐ NHÁP' in text and '01 02 03 04 05 06' in text
                            page.keyboard.press('Escape')
                            expect(board.locator('dialog')).not_to_be_visible()
                            expect(review).to_be_focused()
                            page.locator('#app-theme').click()
                            expect(board.locator('[aria-pressed="true"]')).to_have_count(6)
                            assert page.evaluate('document.documentElement.classList.contains("dark")') == (theme == 'light')
                            page.locator('#app-theme').click()
                            board.locator('[data-vl-clear]').click()
                            expect(review).to_be_disabled()
                            board.locator('[data-vl-random]').click()
                            expect(board.locator('[aria-pressed="true"]')).to_have_count(6)
                            board.locator('[data-vl-clear]').click()
                            board.locator('[data-vl-number="1"]').focus()
                            page.keyboard.press('ArrowRight')
                            expect(board.locator('[data-vl-number="2"]')).to_be_focused()
                            page.keyboard.press('Space')
                            expect(board.locator('[data-vl-number="2"]')).to_have_attribute('aria-pressed', 'true')
                        if name == 'vietlott.html' or (width in (390, 1440) and name == 'vietlott-mega-645.html'):
                            page.evaluate('scrollTo({top:0,behavior:"instant"})')
                            page.wait_for_function('scrollY === 0')
                            page.screenshot(path=str(OUT / f'{name[:-5]}-{width}-{theme}.png'))
                        assert not errors, (name, errors)
                        checks.append({'page': name, 'width': width, 'theme': theme, 'ok': True,
                                       'manual_comparison': name in COMPARISON_CASES})
                        page.close()
            browser.close()
    finally:
        server.shutdown()
    (OUT / 'vietlott-ui.json').write_text(json.dumps(checks, ensure_ascii=False, indent=2))
    print(f'{len(checks)} trạng thái Vietlott: font/theme, responsive, đối chiếu và bộ số nháp đạt')


if __name__ == '__main__':
    main()
