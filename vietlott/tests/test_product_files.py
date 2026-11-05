"""Tệp của kho sản phẩm: ghi nguyên tử và tất định (05-11-2026).

* ``exclusions.json`` được MỌI lần nạp sản phẩm đọc (``load_exclusions``). Trước bản vá nó được ghi
  thẳng bằng ``write_text``: chết giữa chừng để lại JSON cụt và mọi sản phẩm ngừng nạp được.
* ``write_jsonl`` nén gzip với ``mtime=0`` để tệp tất định, nhưng ``GzipFile`` lấy tên từ tệp tạm, nên
  header mang một tên ngẫu nhiên và hai lần ghi cùng nội dung ra hai tệp khác nhau.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from vietlott_engine.core import products
from vietlott_engine.core.products import read_jsonl, write_jsonl
from vietlott_engine.crawler.product_store import ProductStore

ROWS = [{"id": 1, "date": "2026-11-01", "result": list(range(1, 21))},
        {"id": 2, "date": "2026-11-01", "result": list(range(41, 61))}]


def _gzip_name(data: bytes) -> str | None:
    """Tên ghi trong header gzip (cờ FNAME), hoặc None."""
    return data[10:data.index(b"\0", 10)].decode("latin-1") if data[3] & 8 else None


def test_a_compressed_history_is_byte_stable_and_names_itself(tmp_path: Path) -> None:
    path = tmp_path / "keno.jsonl.gz"
    write_jsonl(path, ROWS)
    first = path.read_bytes()
    write_jsonl(path, ROWS)
    assert path.read_bytes() == first
    assert _gzip_name(first) == "keno.jsonl"
    assert gzip.decompress(first).decode("utf-8").splitlines()[0].startswith('{"id":1,')
    assert read_jsonl(path) == ROWS


def test_an_interrupted_exclusions_write_keeps_the_previous_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = ProductStore(tmp_path / "data", None)
    assert store.add_exclusions([{"product": "keno", "draw_id": 275986}]) == 1
    path = store.dir / "exclusions.json"
    before = path.read_text(encoding="utf-8")

    def crash(*_args: object) -> None:
        raise OSError("máy chết trước khi tệp mới vào chỗ")

    monkeypatch.setattr(products.os, "replace", crash)
    with pytest.raises(OSError):
        store.add_exclusions([{"product": "bingo18", "draw_id": 83123}])
    assert path.read_text(encoding="utf-8") == before
    assert json.loads(before) == [{"product": "keno", "draw_id": 275986}]
    assert sorted(p.name for p in store.dir.iterdir()) == ["exclusions.json"], "không để lại tệp tạm"
    monkeypatch.undo()
    assert store.exclusions() == {"keno": {275986}}
