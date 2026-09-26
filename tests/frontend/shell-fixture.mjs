import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { JSDOM } from 'jsdom';

const root = new URL('../../', import.meta.url);
const build = `import json
from pathlib import Path
from app_shell import wrap_page
from ui_theme import SITE_NAV, LANDING_SECTIONS, SITE_SEARCH_EXTRAS
html = wrap_page('<html><head></head><body><section id="backtest">Nội dung thật</section></body></html>', 'index.html')
targets = sorted({href for _, items in SITE_NAV for href, _, _ in items} | {'index.html#' + key for key, _, _ in LANDING_SECTIONS} | {href for href, _, _ in SITE_SEARCH_EXTRAS})
pages = sorted(page.name for page in Path('docs').glob('*.html') if page.name != 'landing.html')
print(json.dumps({'html': html, 'twice': wrap_page(html, 'index.html'), 'targets': targets, 'pages': pages}))`;
export const fixture = JSON.parse(execFileSync('python3', ['-c', build], {
  cwd: fileURLToPath(root), env: { ...process.env, PYTHONPATH: 'src', PYTHONDONTWRITEBYTECODE: '1' }, encoding: 'utf8',
}));

export function setup({ narrow = false, hash = '', mediaThrows = false } = {}) {
  const dom = new JSDOM(fixture.html, {
    url: `https://example.test/index.html${hash}`, runScripts: 'outside-only',
  });
  dom.window.matchMedia = query => ({ matches: query.includes('max-width') && narrow });
  if (mediaThrows) dom.window.matchMedia = () => { throw new Error('media unavailable'); };
  // JSDOM chưa có lớp modal native; giữ tác dụng open/close để kiểm thử mã điều khiển.
  dom.window.HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  dom.window.HTMLDialogElement.prototype.close = function () {
    this.open = false;
    this.dispatchEvent(new dom.window.Event('close'));
  };
  dom.window.eval(readFileSync(process.env.APP_SHELL_SCRIPT || new URL('src/assets/app-shell.js', root), 'utf8'));
  return dom;
}

export function type(dom, id, value) {
  const input = dom.window.document.getElementById(id);
  input.value = value;
  input.dispatchEvent(new dom.window.Event('input', { bubbles: true }));
}

export function key(dom, value, options = {}, target = dom.window.document.activeElement) {
  const event = new dom.window.KeyboardEvent('keydown', { key: value, bubbles: true, cancelable: true, ...options });
  target.dispatchEvent(event);
  return event;
}
