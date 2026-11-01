import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { JSDOM } from 'jsdom';

const root = new URL('../../', import.meta.url);
const slugs = ['cau-dac-biet-theo-bo-so', 'chu-ky-dac-biet', 'lo-gan', 'giai-db-ngay-mai'];
const special12 = new Set([5, 35, 70, 125, 190, 260, 330, 365, 395, 415]);
const special21 = new Set([50, 150, 250, 380, 418]);
const loto12 = new Set([20, 100, 300, 402, 412]);
const loto21 = new Set([40, 160, 401, 410, 418]);
// Calendar gaps ensure a 30-draw preset cannot silently become 30 calendar days.
const draws = Array.from({length: 420}, (_, i) => ({
  d: new Date(Date.UTC(2025, 0, 1 + i + Math.floor(i / 12))).toISOString().slice(0, 10),
  s: special12.has(i) ? '00012' : special21.has(i) ? '00021' : [10, 400].includes(i) ? '00003' : '00099',
  // Repeated numbers within one draw still count as one hit for gap tables.
  n: [...Array(2).fill(loto12.has(i) ? '12' : loto21.has(i) ? '21' : '99'), ...Array(25).fill('99')],
}));
const fixtures = {full: draws, short: draws.slice(-7), empty: []};
const build = `import json,sys
from pages.build_stat_pages import PAGES,render_page
fixtures=json.load(sys.stdin)
slugs={"cau-dac-biet-theo-bo-so","chu-ky-dac-biet","lo-gan","giai-db-ngay-mai"}
print(json.dumps({key:{p.slug:render_page(p,rows,generated="2026-10-19T10:00:00Z") for p in PAGES if p.slug in slugs} for key,rows in fixtures.items()}))`;
const pages = JSON.parse(execFileSync(process.env.CODEX_PRIMARY_RUNTIME_PYTHON || 'python3', ['-c', build], {
  cwd: fileURLToPath(root), env: {...process.env, PYTHONPATH: 'src'},
  input: JSON.stringify(fixtures), encoding: 'utf8', maxBuffer: 8 * 1024 * 1024,
}));
const source = readFileSync(new URL('src/web/templates/stat_pages.js', root), 'utf8');

function setup(t, slug, fixture = 'full') {
  const errors = [];
  const html = process.env.APP_STAT_ENGINE
    ? pages[fixture][slug].replace(source, readFileSync(process.env.APP_STAT_ENGINE, 'utf8'))
    : pages[fixture][slug];
  const dom = new JSDOM(html, {
    url: `https://example.test/${slug}.html`, runScripts: 'dangerously', pretendToBeVisual: true,
    beforeParse(w) {
      w.addEventListener('error', event => errors.push(String(event.error)));
      w.ResizeObserver = class {observe() {}};
      w.HTMLElement.prototype.scrollIntoView = function () {};
      w.matchMedia = () => ({matches: false, addEventListener() {}});
    },
  });
  t.after(() => {dom.window.close(); assert.deepEqual(errors, []);});
  assert.deepEqual(errors, []);
  return dom;
}

function choose(dom, count) {
  const button = dom.window.document.querySelector(`.sp-chips [data-days="${count}"]`);
  assert.ok(button, `Missing preset ${count}`);
  button.click();
  assert.equal(dom.window.document.querySelectorAll('.sp-chips .on').length, 1);
  assert.ok(button.classList.contains('on'));
}

function checkRange(dom, expected) {
  const dates = Array.from(dom.window.eval('selected().map(row => row.d)'));
  assert.equal(dates.length, expected.length);
  assert.deepEqual(dates, expected.map(row => row.d));
  const count = dom.window.document.getElementById('sp-count').textContent;
  assert.match(count, new RegExp(`^${expected.length} kỳ`));
  if (expected.length) {
    assert.ok(count.includes(expected[0].d), count);
    assert.ok(count.includes(expected.at(-1).d), count);
  }
}

function rowFor(dom, id, number, column = 0) {
  const row = [...dom.window.document.querySelectorAll(`#${id} tbody tr`)]
    .find(row => row.cells[column]?.textContent.trim() === number);
  assert.ok(row, `Missing ${number} in ${id}`);
  return [...row.cells].map(cell => cell.textContent.trim());
}

const viDate = iso => iso.split('-').reverse().join('-');
// Hand-checked outcomes for the marked draws above; independent of the production helpers.
// Gan LOTO chỉ đếm kỳ trượt giữa hai lần về: chỉ số 402 và 412 có 9 kỳ trượt.
// Cột chu kỳ Đặc Biệt báo khoảng cách hai lần về, là phép đo khác.
const outcomes = {
  30: {specialHits: 2, specialGap: 20, lotoHits: 2, lotoGap: 9, pairHits: 5, pairGap: 7},
  60: {specialHits: 3, specialGap: 30, lotoHits: 2, lotoGap: 9, pairHits: 5, pairGap: 7},
  90: {specialHits: 4, specialGap: 35, lotoHits: 2, lotoGap: 9, pairHits: 5, pairGap: 7},
  180: {specialHits: 5, specialGap: 70, lotoHits: 3, lotoGap: 101, pairHits: 6, pairGap: 100},
  365: {specialHits: 8, specialGap: 70, lotoHits: 4, lotoGap: 199, pairHits: 8, pairGap: 139},
  0: {specialHits: 10, specialGap: 70, lotoHits: 5, lotoGap: 199, pairHits: 10, pairGap: 139},
};

for (const slug of slugs) {
  test(`${slug}: every preset updates the actual draws and statistics, then restores all history`, t => {
    const dom = setup(t, slug);
    checkRange(dom, draws);
    // The second 30 and All exercise moving backwards after a long window.
    for (const size of [30, 60, 90, 180, 365, 30, 0]) {
      choose(dom, size);
      const selected = size ? draws.slice(-size) : draws;
      const wanted = outcomes[size];
      checkRange(dom, selected);
      // The overview explicitly cites all history and calls this helper without an argument.
      assert.deepEqual(Array.from(dom.window.eval('(() => {const g=specialGaps(); return [g.n,g.hits[12],g.maxGap[12],g.current[12]];})()')),
        [420, 10, 70, 4]);
      if (slug === 'cau-dac-biet-theo-bo-so') {
        assert.deepEqual(rowFor(dom, 'sp-grid', '12'),
          ['12', draws[415].d, '4', String(wanted.specialGap), String(wanted.specialHits)]);
      } else if (slug === 'chu-ky-dac-biet') {
        assert.deepEqual(rowFor(dom, 'sp-grid', '12', 1).slice(1),
          ['12', '4', String(wanted.specialGap), String(wanted.specialHits)]);
      } else if (slug === 'lo-gan') {
        assert.deepEqual(rowFor(dom, 'sp-grid', '12'),
          ['12', viDate(draws[412].d), '7', String(wanted.lotoGap), String(wanted.lotoHits)]);
        assert.deepEqual(rowFor(dom, 'sp-pair-gan', '12 - 21'),
          ['12 - 21', viDate(draws[418].d), '1', String(wanted.pairGap), String(wanted.pairHits)]);
        assert.deepEqual(rowFor(dom, 'sp-max-lo', '12'), ['12', '199 kỳ']);
        assert.deepEqual(rowFor(dom, 'sp-max-hi', '99'), ['99', '0 kỳ']);
      } else {
        const matches = selected.filter(row => row.s.endsWith('99')).slice().reverse();
        assert.deepEqual([...dom.window.document.querySelectorAll('#sp-grid tr[data-trigger-date]')].map(row => row.dataset.triggerDate), matches.map(row => row.d));
        assert.equal(dom.window.document.getElementById('sp-tomorrow-number').value, '99');
      }
    }
    choose(dom, 30);
    const count = dom.window.document.getElementById('sp-count').textContent;
    dom.window.document.querySelector('#sp-grid .cell[data-key]').click();
    assert.ok(dom.window.document.querySelectorAll('.marked').length > 0);
    dom.window.document.getElementById('sp-clear-marks').click();
    assert.equal(dom.window.document.querySelectorAll('.marked').length, 0);
    assert.equal(dom.window.document.getElementById('sp-count').textContent, count);
    checkRange(dom, draws.slice(-30));
  });

  test(`${slug}: presets larger than a short dataset keep every available draw`, t => {
    const dom = setup(t, slug, 'short');
    for (const size of [30, 60, 90, 180, 365, 0]) {
      choose(dom, size);
      checkRange(dom, fixtures.short);
      if (slug === 'cau-dac-biet-theo-bo-so') {
        assert.deepEqual(rowFor(dom, 'sp-grid', '12'), ['12', draws[415].d, '4', '—', '1']);
      } else if (slug === 'chu-ky-dac-biet') {
        assert.deepEqual(rowFor(dom, 'sp-grid', '12', 1).slice(1), ['12', '4', '—', '1']);
      } else if (slug === 'lo-gan') {
        assert.deepEqual(rowFor(dom, 'sp-grid', '99'), ['99', viDate(draws[419].d), '0', '0', '7']);
      } else {
        assert.equal(dom.window.document.querySelectorAll('#sp-grid tr[data-trigger-date]').length, fixtures.short.filter(row => row.s.endsWith('99')).length);
      }
    }
  });

  test(`${slug}: empty data stays empty for every preset without invalid statistics`, t => {
    const dom = setup(t, slug, 'empty');
    for (const size of [30, 60, 90, 180, 365, 0]) {
      choose(dom, size);
      checkRange(dom, []);
      assert.doesNotMatch(dom.window.document.getElementById('sp-grid').textContent, /NaN|Infinity|undefined/);
    }
  });
}
