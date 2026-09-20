#!/usr/bin/env python3
"""Flatten matrix DOM + virtualize off-screen matrices (IntersectionObserver).

1) Flatten nested spans to data-value + CSS ::after
2) Dehydrate .matrix-grid cells to one placeholder + JSON payload
3) Inject IntersectionObserver hydrator (keeps first tiny-matrix eager for LCP)
"""
from __future__ import annotations

import html as html_lib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = [
    ROOT / "docs" / "index.html",
    ROOT / "docs" / "landing.html",
    ROOT / "docs" / "landing_desktop.html",
]

DOM_CSS = """
/* DOM perf: flat matrix cells + content-visibility + virtualize */
.tiny-matrix-cell, .matrix-cell { font-weight:950; letter-spacing:-.02em; line-height:1.15; }
.tiny-matrix-cell::after, .matrix-cell::after {
  content: attr(data-value); display:block; font-size:10px; opacity:.88; font-weight:750;
  letter-spacing:0; line-height:1.2; max-width:100%; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;
}
article.card, section.section.card {
  content-visibility: auto;
  contain-intrinsic-size: auto 280px;
}
#tong-quan, #live, #ket-qua { content-visibility: visible; contain-intrinsic-size: auto; }
.virt-placeholder {
  border-radius: 14px;
  background: linear-gradient(180deg, rgba(15,23,42,.03), rgba(15,23,42,.055));
  border: 1px dashed rgba(15,23,42,.08);
}
.is-dehydrated { content-visibility: auto; contain-intrinsic-size: auto 320px; }
"""

VIRT_JS = r"""
(function () {
  if (window.__matrixVirt) return;
  window.__matrixVirt = true;
  var ROOT_MARGIN = '280px 0px';

  function cellButton(p) {
    var b = document.createElement('button');
    b.className = p.c;
    b.setAttribute('data-number', p.n);
    if (p.m) b.setAttribute('data-mode', p.m);
    if (p.v != null && p.v !== '') b.setAttribute('data-value', p.v);
    if (p.s) b.setAttribute('style', p.s);
    if (p.t) b.title = p.t;
    b.textContent = p.n;
    b.addEventListener('click', function () {
      if (typeof showNumber === 'function') showNumber(p.m || 'loto', p.n);
    });
    return b;
  }

  function loadPayload(grid) {
    var raw = grid.getAttribute('data-virt-payload');
    if (raw) {
      try { return JSON.parse(raw); } catch (e) { return null; }
    }
    var id = grid.getAttribute('data-virt-id');
    var box = document.getElementById('virt-matrix-data');
    if (!id || !box) return null;
    try {
      var all = JSON.parse(box.textContent);
      return all[id] || null;
    } catch (e) { return null; }
  }

  function hydrate(grid) {
    if (grid.getAttribute('data-virt-hydrated') === '1') return;
    var payload = loadPayload(grid);
    if (!payload || !payload.length) return;
    var tiny = grid.classList.contains('tiny-matrix');
    var axis = tiny ? 'matrix-head' : 'matrix-axis';
    var frag = document.createDocumentFragment();
    frag.appendChild(document.createElement('div'));
    for (var i = 0; i < 10; i++) {
      var h = document.createElement('div');
      h.className = axis;
      h.textContent = String(i);
      frag.appendChild(h);
    }
    for (var head = 0; head < 10; head++) {
      var ax = document.createElement('div');
      ax.className = axis;
      ax.textContent = String(head);
      frag.appendChild(ax);
      for (var tail = 0; tail < 10; tail++) {
        var p = payload[head * 10 + tail];
        if (p) frag.appendChild(cellButton(p));
        else {
          var empty = document.createElement('div');
          empty.className = 'virt-slot';
          frag.appendChild(empty);
        }
      }
    }
    grid.replaceChildren(frag);
    grid.setAttribute('data-virt-hydrated', '1');
    grid.classList.remove('is-dehydrated');
    grid.removeAttribute('data-virt-payload');
    grid.removeAttribute('data-virt-id');
  }

  function observe() {
    var grids = document.querySelectorAll('[data-virt-payload], [data-virt-id]');
    if (!grids.length) return;
    if (!('IntersectionObserver' in window)) {
      for (var i = 0; i < grids.length; i++) hydrate(grids[i]);
      return;
    }
    var io = new IntersectionObserver(function (entries) {
      for (var i = 0; i < entries.length; i++) {
        if (entries[i].isIntersecting) {
          hydrate(entries[i].target);
          io.unobserve(entries[i].target);
        }
      }
    }, { rootMargin: ROOT_MARGIN, threshold: 0.01 });
    for (var j = 0; j < grids.length; j++) io.observe(grids[j]);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', observe);
  } else {
    observe();
  }
})();
"""

CELL_RE = re.compile(
    r'<button\b([^>]*\bclass="[^"]*(?:matrix-cell|tiny-matrix-cell)[^"]*"[^>]*)>(.*?)</button>',
    re.I | re.S,
)
ATTR_RE = re.compile(r'([\w:-]+)\s*=\s*"([^"]*)"')


def _parse_btn(attrs: str, inner: str) -> dict:
    ad = dict(ATTR_RE.findall(attrs))
    cls = ad.get("class", "matrix-cell")
    number = ad.get("data-number", "")
    if not number:
        number = re.sub(r"<[^>]+>", "", inner).strip()[:4]
    return {
        "n": number,
        "m": ad.get("data-mode", "loto"),
        "v": ad.get("data-value", ""),
        "s": ad.get("style", ""),
        "t": ad.get("title", ""),
        "c": cls,
    }


def flatten_matrix_cell(m: re.Match[str]) -> str:
    open_tag, number, value = m.group(1), m.group(2), m.group(3)
    if "data-value=" not in open_tag:
        open_tag = open_tag[:-1] + f' data-value="{value}">'
    return f"{open_tag}{number}</button>"


def flatten_tiny(m: re.Match[str]) -> str:
    open_tag, number, value = m.group(1), m.group(2), m.group(3)
    if "data-value=" not in open_tag:
        open_tag = open_tag[:-1] + f' data-value="{value}">'
    return f"{open_tag}{number}</button>"


def virtualize_matrices_safe(html: str, *, keep_first_tiny: bool = True) -> tuple[str, int]:
    count = 0
    first_tiny_kept = False
    out: list[str] = []
    i = 0
    n = len(html)
    starter = re.compile(r'<div\b[^>]*\bclass="([^"]*)"[^>]*>', re.I)

    while i < n:
        m = starter.search(html, i)
        if not m:
            out.append(html[i:])
            break
        classes = m.group(1)
        is_grid = re.search(r'(?:^|\s)matrix-grid(?:\s|$)', classes)
        is_tiny = re.search(r'(?:^|\s)tiny-matrix(?:\s|$)', classes)
        if not is_grid and not is_tiny:
            out.append(html[i : m.end()])
            i = m.end()
            continue

        start = m.start()
        open_end = m.end()
        depth = 1
        pos = open_end
        close_start = close_end = -1
        while pos < n and depth:
            next_open = html.find("<div", pos)
            next_close = html.find("</div>", pos)
            if next_close < 0:
                break
            if next_open >= 0 and next_open < next_close and re.match(r"<div\b", html[next_open:], re.I):
                depth += 1
                pos = next_open + 4
                continue
            depth -= 1
            if depth == 0:
                close_start = next_close
                close_end = next_close + len("</div>")
                break
            pos = next_close + 6
        else:
            out.append(html[i:open_end])
            i = open_end
            continue

        open_tag = html[start:open_end]
        inner = html[open_end:close_start]
        close_tag = html[close_start:close_end]
        out.append(html[i:start])

        if keep_first_tiny and is_tiny and not is_grid and not first_tiny_kept:
            first_tiny_kept = True
            out.append(open_tag + inner + close_tag)
            i = close_end
            continue

        payload = [_parse_btn(bm.group(1), bm.group(2)) for bm in CELL_RE.finditer(inner)]
        if len(payload) < 40:
            out.append(open_tag + inner + close_tag)
            i = close_end
            continue

        tiny = bool(is_tiny and not is_grid)
        kind = "tiny" if tiny else "grid"
        body = (
            f'<div class="virt-placeholder" data-virt-kind="{kind}" '
            f'style="grid-column:1/-1;min-height:{"220px" if tiny else "320px"};'
            f'display:grid;place-items:center;color:#64748b;font-size:12px;font-weight:700">'
            f'Ma trận 00–99</div>'
        )
        payload_json = html_lib.escape(json.dumps(payload, separators=(",", ":")), quote=True)

        if re.search(r'\bclass="', open_tag):
            new_open = re.sub(
                r'\bclass="([^"]*)"',
                lambda mm: f'class="{mm.group(1) if "is-dehydrated" in mm.group(1) else (mm.group(1) + " is-dehydrated").strip()}"',
                open_tag,
                count=1,
            )
        else:
            new_open = open_tag.replace("<div", '<div class="is-dehydrated"', 1)
        if "data-virt-payload=" not in new_open:
            new_open = new_open[:-1] + f' data-virt-payload="{payload_json}">'

        out.append(new_open + body + close_tag)
        count += 1
        i = close_end

    return "".join(out), count


def pack_virt_payloads(html: str) -> str:
    """Move data-virt-payload attributes into #virt-matrix-data JSON script."""
    payloads: dict[str, list] = {}
    idx = 0
    pattern = re.compile(
        r'<div\b([^>]*?)\s*data-virt-payload="([^"]*)"([^>]*)>',
        re.I,
    )

    def repl(m: re.Match[str]) -> str:
        nonlocal idx
        key = f"m{idx}"
        idx += 1
        try:
            payloads[key] = json.loads(html_lib.unescape(m.group(2)))
        except Exception:
            payloads[key] = []
        pre, post = m.group(1), m.group(3)
        pre = re.sub(r'\s*data-virt-id="[^"]*"', '', pre)
        post = re.sub(r'\s*data-virt-id="[^"]*"', '', post)
        return f'<div{pre}{post} data-virt-id="{key}">'

    html2 = pattern.sub(repl, html)
    if not payloads:
        return html
    blob = json.dumps(payloads, separators=(",", ":"))
    tag = f'<script type="application/json" id="virt-matrix-data">{blob}</script>\n'
    if 'id="virt-matrix-data"' in html2:
        html2 = re.sub(
            r'<script type="application/json" id="virt-matrix-data">.*?</script>\s*',
            tag,
            html2,
            count=1,
            flags=re.S,
        )
    else:
        html2 = html2.replace("</body>", tag + "</body>", 1)
    return html2


def optimize(html: str) -> tuple[str, dict[str, int]]:
    stats = {"matrix_cell": 0, "tiny_matrix": 0, "css": 0, "virt_grids": 0, "virt_js": 0}

    html, n1 = re.subn(
        r'(<button\b[^>]*\bclass="[^"]*matrix-cell[^"]*"[^>]*>)\s*'
        r'<span class="cell-number">([^<]*)</span>\s*'
        r'<span class="cell-value">([^<]*)</span>\s*</button>',
        flatten_matrix_cell,
        html,
        flags=re.I,
    )
    stats["matrix_cell"] = n1
    html, n2 = re.subn(
        r'(<button\b[^>]*\bclass="[^"]*tiny-matrix-cell[^"]*"[^>]*>)\s*'
        r'<b>([^<]*)</b>\s*<span>([^<]*)</span>\s*</button>',
        flatten_tiny,
        html,
        flags=re.I,
    )
    stats["tiny_matrix"] = n2

    html, nv = virtualize_matrices_safe(html, keep_first_tiny=True)
    stats["virt_grids"] = nv
    if nv:
        html = pack_virt_payloads(html)

    if "virt-placeholder" not in html or "content: attr(data-value)" not in html:
        if "</style>" in html:
            html = html.replace("</style>", DOM_CSS + "\n</style>", 1)
            stats["css"] = 1
        else:
            html = html.replace("</head>", f'<style id="dom-perf">{DOM_CSS}</style>\n</head>', 1)
            stats["css"] = 1

    if ("data-virt-id" in html or "data-virt-payload" in html) and "matrix-virt" not in html:
        html = html.replace("</body>", f'<script id="matrix-virt">{VIRT_JS}</script>\n</body>', 1)
        stats["virt_js"] = 1

    return html, stats


def main() -> None:
    changed = 0
    for path in TARGETS:
        if not path.is_file():
            continue
        original = path.read_text(encoding="utf-8")
        updated, stats = optimize(original)
        if updated != original:
            path.write_text(updated, encoding="utf-8")
            changed += 1
            print(
                f"optimized {path.name}: flat_matrix={stats['matrix_cell']} tiny={stats['tiny_matrix']} "
                f"virt_grids={stats['virt_grids']} bytes {len(original)}->{len(updated)}"
            )
        else:
            print(f"unchanged {path.name}")
    print(f"done: {changed} files")


if __name__ == "__main__":
    main()
