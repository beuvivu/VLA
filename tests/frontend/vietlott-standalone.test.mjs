import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { JSDOM } from 'jsdom';

const assets = new URL('../../vietlott/scripts/site_assets/', import.meta.url);

function dashboard(product, ticket) {
  const groups = [
    { label: product === 'max3dpro' ? 'Đặc biệt' : 'Nhất', numbers: [ticket.hits ? '038' : '111', '091'] },
    { label: product === 'max3dpro' ? 'Nhất' : 'Nhì', numbers: [ticket.hits > 1 ? '038' : '232', '504', '975', '346'] },
    { label: 'Nhì', numbers: ['989', '690', '066', '206', '904', '115'] },
    { label: 'Ba', numbers: ['610', '570', '216', '577', '913', '985', '577', '286'] },
  ];
  const result = {
    draw_id: 788, draw_date: '2026-10-06T00:00:00+07:00', time_precision: 'day',
    numbers: groups.flatMap(group => group.numbers), bonus: null, facts: {}, source: 'fixture',
    official_url: 'https://example.test/results',
    prizes: groups,
  };
  const snapshot = {
    schema_version: 1, generated_at: '2026-10-07T00:00:00+07:00', warnings: [],
    stats: { products: 1, results: 1, registered_next: 0, compared_draws: 1 },
    products: [{
      product, schedule: '18:00', latest: result, draws: [result], prize_catalogue: [], next_forecast: null,
      comparisons: [{ status: 'matched', target_id: 788, target_date: '2026-10-06',
        made_at: '2026-10-05T20:00:00+07:00', engine: 'ml', registered: true, result, tickets: [ticket] }],
    }],
  };
  const markup = readFileSync(new URL('index.html', assets), 'utf8')
    .replace('__DASHBOARD_JSON__', JSON.stringify(snapshot));
  const dom = new JSDOM(markup, { url: 'https://example.test/', runScripts: 'outside-only' });
  dom.window.fetch = async () => ({ ok: false });
  dom.window.eval(readFileSync(new URL('dashboard.js', assets), 'utf8'));
  return dom;
}

for (const [hits, groups] of [[1, ['Đặc biệt']], [2, ['Đặc biệt', 'Nhất']], [0, []]]) {
  test(`Pro: ${hits} lần xuất hiện của bộ ba không được gọi là hạng giải vé cặp`, t => {
    const dom = dashboard('max3dpro', { numbers: [0, 3, 8], symbol: '038', hits,
      tiers: [], matched_groups: groups, prize_status: 'requires_pair' });
    t.after(() => dom.window.close());
    const caption = dom.window.document.querySelector('.match-caption').textContent;
    assert.ok(caption.includes(`Xuất hiện ${hits} lần`));
    assert.ok(caption.includes('Chưa phân hạng: cần vé cặp'));
    if (groups.length) assert.ok(caption.includes(`Nhóm có số trùng: ${groups.join(', ')}`));
    else assert.ok(!caption.includes('Nhóm có số trùng:'));
    assert.ok(!caption.includes('chưa đạt hạng giải'));
  });
}

test('Max 3D giữ nguyên các hạng giải của bộ ba trùng nhiều nhóm', t => {
  const dom = dashboard('max3d', { numbers: [0, 3, 8], symbol: '038', hits: 2, tiers: ['Nhất', 'Nhì'] });
  t.after(() => dom.window.close());
  const caption = dom.window.document.querySelector('.match-caption').textContent;
  assert.equal(caption, 'Trùng 2 lần · Nhất, Nhì');
});
