"""Sổ phỏng đoán trong ngày: mọi danh sách số hệ thống công bố cho MỘT kỳ, đóng băng trước giờ quay.

Trang Live đọc sổ này để đặt từng danh sách cạnh kết quả đang về và trả lời câu hỏi
"hôm nay các phỏng đoán thực tế trúng bao nhiêu so với xác suất đã công bố".

Vì sao phải có sổ riêng
------------------------

Nhiều tệp nguồn KHÔNG mang ngày trong tên (``data/ml/predict_next_*_ml_top10.csv``,
``data/forecast/multi_hit/vip.json``, ``data/forecast/agents/report.json``…) và bị ghi đè ngay khi pipeline
chạy cho kỳ sau, khoảng 19 giờ — tức trong lúc người đọc còn đang đối chiếu kỳ vừa quay.
Đọc thẳng các tệp ấy sau giờ quay là chấm danh sách của kỳ KHÁC. Sổ chụp đúng thứ đang
hiện trên các trang, chỉ được ghi TRƯỚC 18:10 giờ Việt Nam của kỳ đích
(``fun_draw_ledger.cutoff_utc``, cùng giờ khoá với bảng mô phỏng) và đóng băng từ đó.

Mỗi nguồn phải tự khai đúng kỳ đích (cột ``predict_for_date``, khoá ``target_date`` hay
ngày trong tên tệp). Nguồn nói kỳ khác thì bị BỎ, ghi lý do vào ``missing`` — thà thiếu
một hàng còn hơn đặt danh sách hôm qua cạnh kết quả hôm nay.

Luật trúng của từng mục
------------------------

Mỗi mục mang ``rule`` mà trang chấm trên kết quả đang về (``src/web/assets/live-scorecard.js``):

* ``{"on": "loto", "numbers": S, "need": t}`` — tổng số nháy của các số trong S ≥ t.
  Một số LOTO là ``S = {n}, t = 1``; Lô VIP là ``t = 2``; cầu lộn cộng gộp nháy hai chiều.
* ``{"on": "loto", "numbers": S, "all": true}`` — mọi số trong S cùng về (xiên).
* ``{"on": "special", "numbers": S}`` — hai số cuối giải Đặc Biệt thuộc S.
* ``{"on": "special_digit", "digits": D}`` — hàng chục hoặc hàng đơn vị của hai số cuối
  Đặc Biệt thuộc D (cầu Đặc Biệt "chạm" của ``bridge_rules``).

``base`` là xác suất CHÍNH XÁC của đúng sự kiện ấy khi kỳ quay công bằng (27 giải, hai số
cuối đều trên 00–99; Đặc Biệt đều trên 100 số) — mốc "chọn bừa". ``prob`` là xác suất mà
nguồn đã công bố cho sự kiện ấy, hoặc ``None`` khi nguồn chỉ xếp hạng.

Vị trí cầu (schema 2, 02-11-2026)
---------------------------------

Mười bốn danh sách sinh ra từ CẶP VỊ TRÍ chữ số trên bảng kết quả — ba ô "cầu đẹp nhất", bảy trang
soi cầu, bốn bảng soi đường. Mỗi mục của chúng mang ``bridges`` (các cầu báo mục ấy: vị trí ``a``,
``b`` theo cách đánh số 0–106 của ``position_bridges``, độ dài ``streak``; soi đường thêm ``lag`` và
kỳ gốc ``base``) và ``bridge_total`` (tổng số cầu, vì một số soi đường có tới ~100 đường). Danh
sách mang ``bridge`` (kiểu, luật tô ô về, chuỗi kỳ để vẽ đường cầu) và sổ mang ``draws`` — kết quả
đúng các kỳ ấy — để trang Live vẽ lại đường cầu khi người đọc bấm vào một số.

Cầu được TÍNH LẠI từ chính ảnh chụp mà trang đã dựng (``draws`` trong ``latest.json``) và phải ra
đúng số cầu trang đã công bố; lệch thì danh sách ấy không mang vị trí — thà không vẽ còn hơn vẽ
một cầu trang không hề in. Cầu Kèo KHÔNG có vị trí: đặc trưng "cầu" của nó đếm số lần một số được
ghép từ MỌI cặp vị trí trong 30 kỳ (``ml_features._path_support_matrix``), không phải một cầu cụ thể.
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime
from math import comb
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pandas as pd

from core.atomic_io import atomic_write_text
from core.calendar_alignment import known_non_draw_days
from evaluation.fun_draw_ledger import VN, cutoff_utc, show_data_at
from forecast.multi_hit_forecast import next_draw_date
from core.xsmb_domain import LOTO_DRAWS_PER_DAY
from soi_cau import bridge_rules
from soi_cau.position_bridges import WIDTHS

LOGGER = logging.getLogger(__name__)
#: 2 (02-11-2026): danh sách cầu mang vị trí cầu và sổ mang ``draws`` (xem docstring).
SCHEMA = 2
OUT = Path("evaluation") / "prediction_board"
#: Số mục tối đa lấy từ một bảng xếp hạng (các trang soi cầu liệt kê theo số cầu).
TOP = 10
#: Số cầu tối đa ghi cho MỘT mục (cầu dài nhất trước); tổng thật ghi ở ``bridge_total``.
BRIDGES_PER_ITEM = 12
#: Số kỳ cuối của chuỗi mà trang Live vẽ được đường cầu: cầu chạy dài hơn thì vẽ đoạn cuối.
PATH_DRAWS = 8


# --- Mốc chọn bừa ------------------------------------------------------------------


def _binomial_tail(trials: int, p: float, need: int) -> float:
    return float(sum(comb(trials, k) * p**k * (1 - p) ** (trials - k) for k in range(need, trials + 1)))


def base_probability(rule: dict) -> float:
    """Xác suất chính xác của sự kiện ``rule`` dưới kỳ quay công bằng."""
    if rule["on"] == "special":
        return len(set(rule["numbers"])) / 100
    if rule["on"] == "special_digit":
        return 1 - (1 - len(set(rule["digits"])) / 10) ** 2
    size = len(set(rule["numbers"]))
    if rule.get("all"):
        # Bao hàm – loại trừ: P(mọi số trong S cùng về) với 27 lượt rút độc lập.
        return float(sum((-1) ** j * comb(size, j) * (1 - j / 100) ** LOTO_DRAWS_PER_DAY
                         for j in range(size + 1)))
    # Tổng số nháy của S là nhị thức(27, |S|/100).
    return _binomial_tail(LOTO_DRAWS_PER_DAY, size / 100, int(rule["need"]))


def _item(label: str, rule: dict, prob: float | None = None) -> dict:
    return {"label": label, "rule": rule, "prob": None if prob is None else float(prob),
            "base": base_probability(rule)}


def _number(value: Any) -> str:
    text = str(value).strip()
    if not text.isdigit() or len(text) > 2:
        raise ValueError(f"số hai chữ số không hợp lệ: {value!r}")
    return text.zfill(2)


def _loto(n: str, prob: float | None = None, need: int = 1) -> dict:
    return _item(n, {"on": "loto", "numbers": [n], "need": need}, prob)


def _special(n: str, prob: float | None = None) -> dict:
    return _item(n, {"on": "special", "numbers": [n]}, prob)


def _csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False)


def _float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if 0.0 <= number <= 1.0 else None


class Skip(Exception):
    """Nguồn không có danh sách của đúng kỳ đích."""


def _require(found: str | None, target: str, what: str) -> None:
    if found != target:
        raise Skip(f"{what} ghi kỳ {found or 'không rõ'}, không phải {target}")


# --- Các nguồn ----------------------------------------------------------------------


def _ranked(path: Path, target: str, mode: str, *, date_column: str | None) -> list[dict]:
    if not path.exists():
        raise Skip(f"chưa có {path.name}")
    frame = _csv(path)
    if date_column is not None:
        dates = set(frame[date_column]) if date_column in frame else set()
        _require(next(iter(dates)) if len(dates) == 1 else None, target, path.name)
    make = _loto if mode == "loto" else _special
    return [make(_number(row["number"]), _float(row.get("prob"))) for row in frame.head(TOP).to_dict("records")]


def _ensemble(data: Path, target: str, mode: str) -> list[dict]:
    return _ranked(data / "forecast" / "predict" / f"predict_next_{mode}_top10_{target}.csv", target, mode, date_column=None)


def _cau_keo(data: Path, target: str, mode: str) -> list[dict]:
    return _ranked(data / "ai_ml" / "daily" / f"cau_keo_{mode}_top10_{target}.csv", target, mode,
                   date_column="predict_for_date")


def _ml(data: Path, target: str, mode: str) -> list[dict]:
    return _ranked(data / "ml" / f"predict_next_{mode}_ml_top10.csv", target, mode,
                   date_column="predict_for_date")


def _path(data: Path, target: str, mode: str, kind: str) -> list[dict]:
    # Tệp soi đường mang NGÀY DỮ LIỆU (``anchor_date`` của manifest) và dự báo kỳ kế tiếp của
    # ngày ấy — khác các tệp ``predict_next_*`` khác, vốn mang ngày quay.
    manifest = _json(data / "soi_cau" / "path_ui" / f"path_manifest_{mode}.json")
    anchor = str(manifest.get("anchor_date", ""))[:10]
    if not anchor:
        raise Skip(f"path_manifest_{mode}.json không ghi ngày dữ liệu")
    _require(next_draw_date(anchor, known_non_draw_days()), target,
             f"soi đường (dữ liệu tới {anchor})")
    return _ranked(data / "soi_cau" / "path_ui" / f"predict_next_{mode}_{kind}_{anchor}.csv", target, mode,
                   date_column=None)


def _json(path: Path) -> dict:
    if not path.exists():
        raise Skip(f"chưa có {path.name}")
    return json.loads(path.read_text(encoding="utf-8"))


def _vip(data: Path, target: str) -> list[dict]:
    report = _json(data / "forecast" / "multi_hit" / "vip.json")
    _require(report.get("target_date"), target, "vip.json")
    return [_loto(_number(pick["number"]), _float(pick.get("probability")), need=2)
            for pick in report.get("picks", [])]


def _pairs(data: Path, target: str) -> list[dict]:
    report = _json(data / "forecast" / "multi_hit" / "vip.json")
    _require(report.get("target_date"), target, "vip.json")
    items = []
    for pick in (report.get("pairs") or {}).get("picks", []):
        a, b = (_number(n) for n in pick["pair"])
        items.append(_item(f"{a} + {b}", {"on": "loto", "numbers": [a, b], "all": True}))
    return items


def _agents(data: Path, target: str, mode: str) -> list[dict]:
    report = _json(data / "forecast" / "agents" / "report.json")
    _require(report.get("target_date"), target, "forecast/agents/report.json")
    make = _loto if mode == "loto" else _special
    rows = report.get("modes", {}).get(mode, {}).get("candidate_top5", [])
    return [make(_number(row["number"]), _float(row.get("candidate_probability"))) for row in rows]


def _best_bridges(data: Path, target: str, key: str) -> list[dict]:
    report = _json(data / "soi_cau" / "position_bridges" / "latest.json")
    _require(report.get("target_date"), target, "soi_cau/position_bridges/latest.json")
    mode = report["modes"][key]
    items = []
    for bridge in mode.get("best", [])[:TOP]:
        numbers = sorted({_number(n) for n in bridge["numbers"]})
        label = " · ".join(_number(n) for n in bridge["numbers"])
        if mode.get("db"):
            rule = {"on": "special", "numbers": numbers}
        else:
            # Lộn thì CỘNG GỘP nháy của cả hai chiều; số bóng của số kép chỉ hiện kèm.
            rule = {"on": "loto", "numbers": numbers, "need": int(mode.get("nhay", 1))}
        items.append(_item(f"{label} ({bridge['streak']} ngày)", rule))
    return items


def _bridge_page(data: Path, target: str, key: str) -> list[dict]:
    report = _json(data / "soi_cau" / "bridge_pages" / "latest.json")
    _require(report.get("target_date"), target, "soi_cau/bridge_pages/latest.json")
    rule_set = report["rules"][key]
    if rule_set.get("weekday"):
        weekday = pd.Timestamp(target).weekday()
        if rule_set.get("default_weekday") != weekday:
            raise Skip(f"bảng theo thứ {rule_set.get('default_weekday')} không phải thứ của kỳ {target}")
    kind = rule_set["kind"]
    items = []
    for group in rule_set.get("groups", [])[:TOP]:
        numbers = sorted({_number(n) for n in str(group["key"]).split(",")})
        count = int(group.get("bridges", 0))
        if kind == "dac-biet":
            digits = sorted({int(d) for n in numbers for d in n})
            label = "chạm " + ", ".join(str(d) for d in digits)
            rule = {"on": "special_digit", "digits": digits}
        elif kind == "bo-so":
            label = f"bộ {numbers[0]}"
            rule = {"on": "special", "numbers": numbers}
        else:
            label = " · ".join(numbers)
            # ``hai-nhay``: n về ≥ 2 nháy HOẶC n và số lộn cùng về — đúng bằng tổng nháy ≥ 2.
            rule = {"on": "loto", "numbers": numbers, "need": 2 if kind == "hai-nhay" else 1}
        items.append(_item(f"{label} ({count} cầu)", rule))
    return items


def _fun_draw(data: Path, target: str) -> list[dict]:
    report = _json(data / "forecast" / "predict" / "fun_draw_next.json")
    _require(report.get("target_date"), target, "fun_draw_next.json")
    items = []
    for row in report.get("rows", []):
        suffix = _number(row["suffix"])
        prob = _float(row.get("model_prob"))
        items.append(_special(suffix, prob) if row.get("mode") == "de" else _loto(suffix, prob))
    return items


#: (mã, nhóm, tiêu đề, trang, loại, nguồn). Thứ tự là thứ tự hiện trên trang Live.
SOURCES: tuple[tuple[str, str, str, str, str, Callable[[Path, str], list[dict]]], ...] = (
    ("ensemble-de", "Trang chủ", "Tổ hợp xác suất · Top 10 Đặc Biệt", "index.html", "de",
     lambda d, t: _ensemble(d, t, "de")),
    ("ensemble-loto", "Trang chủ", "Tổ hợp xác suất · Top 10 LOTO", "index.html", "loto",
     lambda d, t: _ensemble(d, t, "loto")),
    ("cau-keo-de", "Trang chủ · Live", "Cầu Kèo · Top 10 Đặc Biệt", "live.html", "de",
     lambda d, t: _cau_keo(d, t, "de")),
    ("cau-keo-loto", "Trang chủ · Live", "Cầu Kèo · Top 10 LOTO", "live.html", "loto",
     lambda d, t: _cau_keo(d, t, "loto")),
    ("ml-de", "Dự báo ML", "ML · Top 10 Đặc Biệt", "ml_top10_de.html", "de", lambda d, t: _ml(d, t, "de")),
    ("ml-loto", "Dự báo ML", "ML · Top 10 LOTO", "ml_top10_loto.html", "loto", lambda d, t: _ml(d, t, "loto")),
    ("agents-de", "Độ tin cậy", "Hệ ba tác tử · 5 số Đặc Biệt", "do-tin-cay.html", "de",
     lambda d, t: _agents(d, t, "de")),
    ("agents-loto", "Độ tin cậy", "Hệ ba tác tử · 5 số LOTO", "do-tin-cay.html", "loto",
     lambda d, t: _agents(d, t, "loto")),
    ("vip", "Lô VIP", "Lô VIP · 5 con về ≥ 2 nháy", "lo-vip-nhieu-nhay.html", "loto2", _vip),
    ("xien", "Lô VIP", "Xiên 2 · 5 cặp cùng về", "lo-vip-nhieu-nhay.html", "pair", _pairs),
    ("best-lo", "Cầu đẹp nhất", "Cầu Lotto", "soi-cau-vi-tri.html", "loto",
     lambda d, t: _best_bridges(d, t, "lo")),
    ("best-nhay2", "Cầu đẹp nhất", "Cầu 2 nháy", "soi-cau-vi-tri.html", "loto2",
     lambda d, t: _best_bridges(d, t, "nhay2")),
    ("best-db", "Cầu đẹp nhất", "Cầu Đặc Biệt", "soi-cau-vi-tri.html", "de",
     lambda d, t: _best_bridges(d, t, "db")),
    *(
        (f"bridge-{key}", "Soi cầu", title, slug, kind, (lambda k: lambda d, t: _bridge_page(d, t, k))(key))
        for key, title, slug, kind in (
            ("loto", "Cầu LOTO", "soi-cau-loto.html", "loto"),
            ("hai-nhay", "Cầu LOTO hai nháy", "soi-cau-hai-nhay.html", "loto2"),
            ("bach-thu", "Cầu LOTO bạch thủ", "soi-cau-bach-thu.html", "loto"),
            ("loto-theo-thu", "Cầu LOTO theo thứ", "soi-cau-loto-theo-thu.html", "loto"),
            ("dac-biet", "Cầu Đặc Biệt (chạm)", "soi-cau-dac-biet.html", "de"),
            ("dac-biet-theo-thu", "Cầu Đặc Biệt theo thứ (chạm)", "soi-cau-dac-biet-theo-thu.html", "de"),
            ("bo-so", "Cầu Đặc Biệt theo bộ số", "soi-cau-dac-biet-bo-so.html", "de"),
        )
    ),
    *(
        (f"path-{mode}-{kind}", "Soi cầu theo đường",
         f"Đường cầu {label} · Top 10 {'LOTO' if mode == 'loto' else 'Đặc Biệt'}",
         f"soi-path-{mode}-{kind}.html", mode, (lambda m, k: lambda d, t: _path(d, t, m, k))(mode, kind))
        for mode in ("de", "loto") for kind, label in (("active", "đang chạy"), ("stable", "ổn định"))
    ),
    ("fun-draw", "Trang chủ", "Bảng mô phỏng · 27 giải", "index.html", "mixed", _fun_draw),
)


# --- Vị trí cầu ---------------------------------------------------------------------


def decode_draw(text: str) -> tuple[str, list[str]]:
    """``YYYY-MM-DD`` + 27 giải nối liền (đúng độ rộng ``WIDTHS``) → (ngày, 27 giá trị)."""
    day, rest = text[:10], text[10:]
    if len(rest) != sum(WIDTHS) or not rest.isdigit():
        raise ValueError(f"kỳ đã nhúng sai khuôn: {text[:24]!r}")
    values, k = [], 0
    for width in WIDTHS:
        values.append(rest[k:k + width])
        k += width
    return day, values


def _digits(values: list[str]) -> list[int]:
    return [int(ch) for ch in "".join(values)]


def _formed(values: list[str], a: int, b: int) -> int:
    digits = _digits(values)
    return 10 * digits[a] + digits[b]


def _arrays(draws: dict[str, list[str]]):  # type: ignore[no-untyped-def]
    """Như ``position_bridges.load_draws`` nhưng từ kỳ đã nhúng: ngày, chữ số (T, 107), giá trị (T, 27)."""
    import numpy as np

    dates = sorted(draws)
    digits = np.array([_digits(draws[d]) for d in dates], dtype=np.int8)
    values = np.array([[int(v) for v in draws[d]] for d in dates], dtype=np.int64)
    return dates, digits, values


def _ranked_bridges(bridges: list[dict]) -> list[dict]:
    return sorted(bridges, key=lambda r: (-r["streak"], r.get("lag", 0), r["a"], r["b"]))[:BRIDGES_PER_ITEM]


def _attach(item: dict, bridges: list[dict]) -> None:
    item["bridges"] = _ranked_bridges(bridges)
    item["bridge_total"] = len(bridges)


def _position_bridges(data: Path, entry: dict, key: str, draws: dict[str, list[str]]) -> None:
    report = _json(data / "soi_cau" / "position_bridges" / "latest.json")
    embedded = {row["date"]: [str(v) for v in row["values"]] for row in report.get("draws", [])}
    if not embedded:
        raise Skip("latest.json không nhúng kỳ quay")
    mode = report["modes"][key]
    series = sorted(embedded)
    last = embedded[series[-1]]
    best = mode.get("best", [])[:TOP]
    if len(best) != len(entry["items"]):
        raise Skip("số cầu khác số mục")
    for item, bridge in zip(entry["items"], best, strict=True):
        a, b = int(bridge["a"]), int(bridge["b"])
        n = _formed(last, a, b)
        rev = 10 * (n % 10) + n // 10
        if {_number(x) for x in bridge["numbers"]} != {f"{n:02d}", f"{rev:02d}"}:
            raise Skip(f"cầu {a}x{b} không ghép ra {bridge['numbers']} ở kỳ {series[-1]}")
        _attach(item, [{"a": a, "b": b, "streak": int(bridge["streak"])}])
    # ``query``: đúng tham số trang soi cầu vị trí đọc (``readParams``), để liên kết mở đúng chế độ ấy.
    entry["bridge"] = {"type": "position", "mark": "special-lon" if mode.get("db") else "loto-lon",
                       "series": series[-PATH_DRAWS:],
                       "query": {"limit": int(mode.get("limit", 5)), "exactlimit": 0,
                                 "lon": 1 if mode.get("lon", True) else 0, "nhay": int(mode.get("nhay", 1)),
                                 "db": 1 if mode.get("db") else 0}}
    draws.update({d: embedded[d] for d in entry["bridge"]["series"]})


#: Luật tô ô "về" ở kỳ sau của từng kiểu cầu trang soi cầu (``bridge_rules``).
_RULE_MARK = {"loto": "loto-lon", "hai-nhay": "loto-lon", "bach-thu": "loto",
              "dac-biet": "special-touch", "bo-so": "bo"}


def _rule_bridges(data: Path, entry: dict, key: str, target: str, draws: dict[str, list[str]]) -> None:
    report = _json(data / "soi_cau" / "bridge_pages" / "latest.json")
    embedded = dict(decode_draw(text) for text in report.get("draws", []))
    if not embedded:
        raise Skip("latest.json không nhúng kỳ quay")
    rule = report["rules"][key]
    dates, digits, values = _arrays(embedded)
    weekday = pd.Timestamp(target).weekday() if rule.get("weekday") else None
    dates, digits, values = bridge_rules.weekday_subset(dates, digits, values, weekday)
    found = bridge_rules.find(rule["kind"], digits, values, count=int(rule["count"]))["bridges"]
    grouped: dict[str, list[dict]] = {}
    for bridge in found:
        n = int(bridge["number"])
        if rule["kind"] == "bo-so":
            group = ",".join(bridge_rules.bo_members(int(bridge_rules.BO_ID[n])))
        else:
            group = ",".join(sorted({f"{n:02d}", f"{10 * (n % 10) + n // 10:02d}"}))
        grouped.setdefault(group, []).append({"a": bridge["a"], "b": bridge["b"], "streak": bridge["streak"]})
    groups = rule.get("groups", [])[:TOP]
    for item, group in zip(entry["items"], groups, strict=True):
        bridges = grouped.get(group["key"], [])
        if len(bridges) != int(group.get("bridges", -1)):
            raise Skip(f"tính lại ra {len(bridges)} cầu cho {group['key']}, trang in {group.get('bridges')}")
        _attach(item, bridges)
    entry["bridge"] = {"type": "rule", "mark": _RULE_MARK[rule["kind"]], "series": dates[-PATH_DRAWS:]}
    draws.update({d: embedded[d] for d in entry["bridge"]["series"]})


def _path_bridges(data: Path, entry: dict, mode: str, kind: str, draws: dict[str, list[str]]) -> None:
    from datetime import date, timedelta

    manifest = _json(data / "soi_cau" / "path_ui" / f"path_manifest_{mode}.json")
    anchor = str(manifest.get("anchor_date", ""))[:10]
    paths_file = data / "soi_cau" / "path_ui" / f"paths_{mode}_{kind}.csv"
    if not paths_file.exists():
        raise Skip(f"chưa có {paths_file.name}")
    embedded = dict(decode_draw(text) for text in _json(data / "soi_cau" / "bridge_pages" / "latest.json")
                    .get("draws", []))
    support = {_number(row["number"]): int(float(row.get("support_paths_count") or -1)) for row in _csv(
        data / "soi_cau" / "path_ui" / f"predict_next_{mode}_{kind}_{anchor}.csv").to_dict("records")}
    # Cùng luật với ``path_prob.predict_from_fitted_paths_full``: kỳ gốc = ngày dữ liệu + 1 − độ trễ (lịch).
    following = date.fromisoformat(anchor) + timedelta(days=1)
    by_number: dict[str, list[dict]] = {}
    for row in _csv(paths_file).to_dict("records"):
        lag, i, j = int(row["lag"]), int(row["i"]), int(row["j"])
        base = (following - timedelta(days=lag)).isoformat()
        if base not in embedded:
            continue
        by_number.setdefault(f"{_formed(embedded[base], i, j):02d}", []).append(
            {"a": i, "b": j, "streak": int(row["current_streak"]), "lag": lag, "base": base})
    for item in entry["items"]:
        number = item["rule"]["numbers"][0]
        bridges = by_number.get(number, [])
        if len(bridges) != support.get(number):
            raise Skip(f"tính lại ra {len(bridges)} đường cho {number}, trang in {support.get(number)}")
        _attach(item, bridges)
        draws.update({b["base"]: embedded[b["base"]] for b in item["bridges"]})
    entry["bridge"] = {"type": "path", "mark": "loto" if mode == "loto" else "special",
                       "next": following.isoformat()}


def attach_bridges(data_dir: Path, target: str, lists: list[dict]) -> dict[str, list[str]]:
    """Gắn vị trí cầu cho các danh sách cầu; trả về kết quả các kỳ cần để vẽ đường cầu.

    Lỗi ở một danh sách chỉ làm danh sách ấy không có vị trí (bảng đối chiếu vẫn đủ).
    """
    draws: dict[str, list[str]] = {}
    for entry in lists:
        kept = {d: v for d, v in draws.items()}
        list_id = entry["id"]
        try:
            if list_id.startswith("best-"):
                _position_bridges(data_dir, entry, list_id.removeprefix("best-"), draws)
            elif list_id.startswith("bridge-"):
                _rule_bridges(data_dir, entry, list_id.removeprefix("bridge-"), target, draws)
            elif list_id.startswith("path-"):
                _, mode, kind = list_id.split("-")
                _path_bridges(data_dir, entry, mode, kind, draws)
        except (Skip, KeyError, ValueError) as reason:
            LOGGER.warning("Danh sách %s không mang vị trí cầu: %s", list_id, reason)
            for item in entry["items"]:
                item.pop("bridges", None)
                item.pop("bridge_total", None)
            entry.pop("bridge", None)
            draws = kept
    return dict(sorted(draws.items()))


def _vector(data: Path, target: str, mode: str) -> list[float] | None:
    path = data / "forecast" / "predict" / f"predict_next_{mode}_all_{target}.csv"
    if not path.exists():
        return None
    frame = _csv(path)
    probs = {_number(row["number"]): _float(row["prob"]) for row in frame.to_dict("records")}
    vector = [probs.get(f"{n:02d}") for n in range(100)]
    return None if any(p is None for p in vector) else [float(p) for p in vector]


def build_board(data_dir: Path, target: str, *, now: datetime) -> dict:
    """Gom mọi danh sách của kỳ ``target`` đang có trong ``data_dir``."""
    lists, missing = [], []
    for key, group, title, page, kind, source in SOURCES:
        try:
            items = source(data_dir, target)
        except Skip as reason:
            missing.append({"id": key, "title": title, "reason": str(reason)})
            continue
        if not items:
            missing.append({"id": key, "title": title, "reason": "danh sách rỗng"})
            continue
        lists.append({"id": key, "group": group, "title": title, "page": page, "kind": kind, "items": items})
    vectors = {mode: _vector(data_dir, target, mode) for mode in ("loto", "de")}
    draws = attach_bridges(data_dir, target, lists)
    return {
        "schema": SCHEMA,
        "target_date": target,
        "generated_at": now.astimezone(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "locks_at": cutoff_utc(target).astimezone(VN).isoformat(timespec="minutes"),
        "lists": lists,
        "vectors": {mode: v for mode, v in vectors.items() if v is not None},
        "draws": draws,
        "missing": missing,
    }


def write_board(data_dir: Path, target: str, *, now: datetime) -> Path | None:
    """Ghi sổ của kỳ ``target`` nếu còn TRƯỚC giờ khoá; sau giờ khoá sổ đóng băng.

    Sau giờ khoá không ghi đè sổ đã có, cũng không tạo sổ mới: một sổ dựng khi kỳ quay đã
    bắt đầu không còn là phỏng đoán "trước khi có kết quả".
    """
    path = data_dir / OUT / f"{target}.json"
    if now >= cutoff_utc(target):
        LOGGER.info("Sổ phỏng đoán kỳ %s đã khoá lúc %s; giữ nguyên", target, cutoff_utc(target))
        return None
    board = build_board(data_dir, target, now=now)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, json.dumps(board, ensure_ascii=False, separators=(",", ":")) + "\n")
    LOGGER.info("Sổ phỏng đoán kỳ %s: %d danh sách, thiếu %d", target, len(board["lists"]),
                len(board["missing"]))
    return path


def source_files(target: str) -> list[str]:
    """Mọi tệp (tương đối ``data/``) mà các nguồn của kỳ ``target`` đọc."""
    files = [
        "forecast/multi_hit/vip.json", "forecast/agents/report.json", "soi_cau/position_bridges/latest.json",
        "soi_cau/bridge_pages/latest.json", "forecast/predict/fun_draw_next.json",
    ]
    for mode in ("loto", "de"):
        files += [
            f"forecast/predict/predict_next_{mode}_top10_{target}.csv",
            f"forecast/predict/predict_next_{mode}_all_{target}.csv",
            f"ai_ml/daily/cau_keo_{mode}_top10_{target}.csv",
            f"ml/predict_next_{mode}_ml_top10.csv",
            f"soi_cau/path_ui/path_manifest_{mode}.json",
            *(f"soi_cau/path_ui/paths_{mode}_{kind}.csv" for kind in ("active", "stable")),
        ]
    return files


def _anchored_files(root: Path) -> list[str]:
    """Tệp soi đường của ngày dữ liệu ghi trong manifest đã lấy về (xem ``_path``)."""
    files = []
    for mode in ("loto", "de"):
        manifest = root / "soi_cau" / "path_ui" / f"path_manifest_{mode}.json"
        if manifest.exists():
            anchor = str(json.loads(manifest.read_text(encoding="utf-8")).get("anchor_date", ""))[:10]
            files += [f"soi_cau/path_ui/predict_next_{mode}_{kind}_{anchor}.csv" for kind in ("active", "stable")]
    return files


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                          text=True).stdout


def backfill_from_git(repo: Path, data_dir: Path, target: str, ref: str = "HEAD") -> Path | None:
    """Dựng lại sổ của một kỳ ĐÃ khoá từ đúng các tệp đã commit TRƯỚC giờ khoá của nó.

    Cùng luật với ``fun_draw_ledger.backfill_from_git``: bản cuối cùng commit trước 18:10 là
    bản người đọc đã thấy trước kỳ quay. Sổ dựng lại mang ``backfilled_from`` (commit nguồn)
    và không bao giờ đè sổ đã có.
    """
    path = data_dir / OUT / f"{target}.json"
    if path.exists():
        return None
    sha = _git(repo, "rev-list", "-1", f"--before={cutoff_utc(target).isoformat()}", ref).strip()
    if not sha:
        return None
    with TemporaryDirectory() as tmp:
        root = Path(tmp) / "data"

        def fetch(paths: list[str]) -> None:
            for rel in paths:
                try:
                    text = show_data_at(repo, sha, rel)
                except subprocess.CalledProcessError:
                    continue
                (root / rel).parent.mkdir(parents=True, exist_ok=True)
                (root / rel).write_text(text, encoding="utf-8")

        fetch(source_files(target))
        fetch(_anchored_files(root))
        stamp = datetime.fromisoformat(_git(repo, "show", "-s", "--format=%cI", sha).strip())
        board = build_board(root, target, now=stamp)
    board["backfilled_from"] = sha[:12]
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, json.dumps(board, ensure_ascii=False, separators=(",", ":")) + "\n")
    LOGGER.info("Dựng lại sổ kỳ %s từ commit %s: %d danh sách", target, sha[:12], len(board["lists"]))
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--target", default=None, help="kỳ đích; mặc định kỳ quay kế tiếp sau dữ liệu")
    parser.add_argument("--backfill-from-git", action="store_true",
                        help="dựng lại sổ của kỳ đã khoá (mặc định kỳ vừa quay) từ lịch sử git")
    parser.add_argument("--repo", type=Path, default=Path("."))
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    last = str(pd.read_csv(args.data_dir / "xsmb.csv", usecols=["date"])["date"].max())[:10]
    if args.backfill_from_git:
        backfill_from_git(args.repo, args.data_dir, args.target or last)
        return 0
    target = args.target or next_draw_date(last, known_non_draw_days())
    write_board(args.data_dir, target, now=datetime.now(UTC))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
