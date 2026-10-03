"""Danh mục nguồn và bằng chứng suy luận cho các con số trên trang xuất bản.

Mỗi trang mang một khối JSON ``#app-evidence-data`` do :func:`registry` sinh
ra; ``assets/app-evidence.js`` đọc nó khi người xem rê chuột hoặc nhấp vào
một con số. Khối gồm:

* ``page``: nguồn và các bước tính mặc định của cả trang;
* ``sections``: ghi đè cho từng khối (khớp bằng bộ chọn CSS ``match``) khi một
  trang gộp nhiều loại số liệu, như trang chủ;
* ``values``: bằng chứng của một giá trị cụ thể, cho phần tử khai
  ``data-evidence="<id>"``.

Hình dạng khớp đúng giao diện ``CitationEvidence`` mà chủ dự án đặc tả
(``sources`` + ``reasoningTrace``); ``id`` và ``value`` do trình duyệt điền
lúc tương tác vì chúng là của từng con số chứ không của trang.

Hai ràng buộc của kho áp lên MỌI chuỗi ở đây, vì chúng đi thẳng ra trình
duyệt (``tests/test_shipped_pages_are_clean.py``):

* không nêu nơi dữ liệu được lấy về hay lưu ở đâu — "nguồn" ở đây là bộ dữ
  liệu và phép tính, mô tả bằng lời, không phải tên miền hay đường dẫn tệp;
* không chứa tên kho.

``reasoningTrace.promptUsed`` của đặc tả không áp dụng: không con số nào ở
đây do mô hình ngôn ngữ sinh ra, nên không có lời nhắc nào để khai.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import NotRequired, TypedDict

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_VERSION = 1


class Source(TypedDict):
    title: str
    snippet: str
    url: NotRequired[str]
    page: NotRequired[int]


class ReasoningTrace(TypedDict):
    steps: list[str]
    confidenceScore: NotRequired[float]


class Evidence(TypedDict):
    sources: list[Source]
    reasoningTrace: ReasoningTrace


class Section(Evidence):
    match: str
    title: str


def _ngay(value: str) -> str:
    """``2026-10-03`` → ``03-10-2026``; chuỗi lạ giữ nguyên."""
    parts = str(value)[:10].split("-")
    return "-".join(reversed(parts)) if len(parts) == 3 else str(value)


def _so(n: int) -> str:
    """4224 → ``4 224``, đúng cách trang viết số."""
    return f"{n:,}".replace(",", " ")


@lru_cache(maxsize=4)
def facts(data_dir: str) -> dict[str, str]:
    """Các số đo của dữ liệu đang có, để nguồn ghi đúng phạm vi thật.

    Thiếu tệp nào thì bỏ khoá ấy; chuỗi nguồn khi đó nói chung chung chứ
    không bịa một con số.
    """
    base = Path(data_dir)
    out: dict[str, str] = {}
    draws = base / "xsmb.csv"
    if draws.exists():
        dates = pd.read_csv(draws, usecols=["date"])["date"].astype(str).sort_values()
        if len(dates):
            out.update(draws=_so(len(dates)), first=_ngay(dates.iloc[0]), last=_ngay(dates.iloc[-1]))
    predicted = sorted((base / "predict").glob("predict_next_loto_all_*.csv"))
    if predicted:
        out["target"] = _ngay(predicted[-1].stem.rsplit("_", 1)[-1])
    quality = base / "model_quality" / "report.json"
    if quality.exists():
        try:
            covers = json.loads(quality.read_text(encoding="utf-8")).get("covers_through")
        except ValueError:
            covers = None
        if covers:
            out["quality_through"] = _ngay(str(covers))
    return out


# --- Nguồn dùng chung -----------------------------------------------------


def _ket_qua(f: dict[str, str]) -> Source:
    scope = (
        f"{f['draws']} kỳ quay, {f['first']} → {f['last']}. " if "draws" in f else ""
    )
    return {
        "title": "Sổ kết quả XSMB đã lưu",
        "snippet": scope + "Mỗi kỳ 27 giải, từ Đặc Biệt (5 chữ số) đến giải bảy (2 chữ số).",
        "url": "so-ket-qua-truyen-thong.html",
    }


_LOTO: Source = {
    "title": "Quy ước LOTO",
    "snippet": "LOTO của một kỳ là hai chữ số cuối của cả 27 giải; một số về k lần trong kỳ là k nháy.",
}

_DAC_BIET: Source = {
    "title": "Quy ước Đặc Biệt",
    "snippet": "Đặc Biệt là giải 5 chữ số; số Đặc Biệt hai chữ số là hai chữ số cuối của giải ấy.",
}


def _du_bao(f: dict[str, str]) -> Source:
    target = f" cho kỳ {f['target']}" if "target" in f else ""
    return {
        "title": "Dự báo đã công bố trước kỳ quay",
        "snippet": (
            f"Vector xác suất 100 số{target}: tổ hợp các thành phần ML, cầu, thống kê và hai "
            "nhánh đường đi, rồi hiệu chỉnh."
        ),
        "url": "dashboard.html",
    }


def _cham(f: dict[str, str]) -> Source:
    through = f" Số liệu đến {f['quality_through']}." if "quality_through" in f else ""
    return {
        "title": "Sổ chấm kỹ năng ngoài mẫu",
        "snippet": (
            "Chấm chính vector xác suất đã công bố với kết quả thật, so với dự báo hằng số "
            "(Đặc Biệt 1/100, LOTO theo tần suất các kỳ trước)." + through
        ),
        "url": "model-quality.html",
    }


def _ml(mode: str = "loto") -> Source:
    """Nguồn thành phần ML, trỏ về đúng trang top của chế độ đang xem."""
    return {
        "title": "Mô hình ML thành phần",
        "snippet": (
            "Cây tăng cường có hiệu chỉnh Platt, học lại theo cửa sổ 2 000 ngày gần nhất; "
            "không có kỹ năng thẩm định thì xác suất co hẳn về tỉ lệ nền."
        ),
        "url": "ml_top10_de.html" if mode == "de" else "ml_top10_loto.html",
    }


_CAU: Source = {
    "title": "Bộ dò cầu vị trí",
    "snippet": (
        "107 vị trí chữ số trên bảng kết quả (Đặc Biệt 0–4 … giải bảy 99–106); một cầu ghép "
        "chữ số ở hai vị trí và chạy theo kỳ quay."
    ),
    "url": "soi-cau-vi-tri.html",
}

_NULL: Source = {
    "title": "Phân phối null 10 000 lịch sử ngẫu nhiên",
    "snippet": (
        "Mô phỏng lịch sử cùng độ dài để biết tín hiệu mạnh nhất của một chuỗi hoàn toàn "
        "ngẫu nhiên lớn tới đâu."
    ),
    "url": "do-tin-cay.html",
}

_LIVE: Source = {
    "title": "Bảng kết quả đang quay",
    "snippet": (
        "Cập nhật từng giải trong phiên quay; giải chưa chốt có thể còn đổi cho tới khi "
        "phiên kết thúc và kết quả được lưu vào sổ."
    ),
}

_MO_PHONG: Source = {
    "title": "Bảng mô phỏng và sổ nhật ký của nó",
    "snippet": (
        "Hai chữ số cuối rút ngẫu nhiên theo xác suất mô hình, phần đầu là số ngẫu nhiên; "
        "mỗi kỳ bảng hiện trước 18:10 được ghi lại và chấm với kết quả thật."
    ),
}

#: Câu nhắc chung cho mọi xác suất dự báo — đúng với số đo của kho, nên ghi ra.
_GHI_CHU_DU_BAO = (
    "Kỳ quay đã kiểm là ngẫu nhiên: kỹ năng ngoài mẫu đo được nằm quanh 0, nên xác suất "
    "này không cao hơn đáng kể mức nền."
)


def _ev(sources: list[Source], steps: list[str], confidence: float | None = None) -> Evidence:
    trace: ReasoningTrace = {"steps": steps}
    if confidence is not None:
        trace["confidenceScore"] = confidence
    return {"sources": sources, "reasoningTrace": trace}


def _sec(match: str, title: str, ev: Evidence) -> Section:
    return {"match": match, "title": title, **ev}  # type: ignore[typeddict-item]


# --- Theo nhóm trang ------------------------------------------------------


def _thong_ke(f: dict[str, str], *extra: str) -> Evidence:
    return _ev(
        [_ket_qua(f), _LOTO, _DAC_BIET],
        [
            "Đọc sổ kết quả đã lưu (chỉ các kỳ đã quay xong).",
            *extra,
            "Trình duyệt tính lại theo bộ lọc đang chọn trên trang; đổi bộ lọc thì con số đổi theo.",
        ],
    )


def _cau(f: dict[str, str], *extra: str) -> Evidence:
    return _ev(
        [_ket_qua(f), _CAU],
        [
            "Đọc sổ kết quả đã lưu và đánh số 107 vị trí chữ số của mỗi kỳ.",
            "Với mỗi cặp vị trí a < b, ghép số 10·d[a] + d[b] ở từng kỳ.",
            *extra,
            "Cầu chạy N ngày khi N bước liên tiếp gần nhất đều trúng. Đây là thống kê mô tả; "
            "độ dài cầu đã được đo trên toàn lịch sử ở mục «Cầu dài có đáng tin hơn?».",
        ],
    )


def _du_bao_ev(f: dict[str, str], *extra: str, mode: str = "loto") -> Evidence:
    return _ev(
        [_du_bao(f), _ml(mode), _cham(f)],
        [
            "Mỗi thành phần cho một vector xác suất 100 số, chỉ dùng các kỳ trước kỳ đích.",
            "Trộn theo trọng số mặc định (hoặc vector đã học khi nó thắng mặc định ngoài mẫu), "
            "rồi hiệu chỉnh xác suất.",
            *extra,
            _GHI_CHU_DU_BAO,
        ],
    )


def _trang_chu(f: dict[str, str]) -> tuple[Evidence, list[Section]]:
    page = _ev([_ket_qua(f), _LOTO, _DAC_BIET], ["Đọc sổ kết quả đã lưu.", "Mỗi khối trên trang có cách tính riêng, ghi trong khối ấy."])
    sections = [
        _sec("#live", "Kết quả trực tiếp", _ev([_LIVE, _ket_qua(f)], ["Hiển thị giải đang quay theo đúng thứ tự giải.", "Khi phiên kết thúc, kết quả được lưu vào sổ."])),
        _sec("#ket-qua", "Bảng kết quả", _ev([_ket_qua(f), _LOTO], ["Lấy kỳ quay đã lưu theo ngày đang chọn.", "Bảng LOTO đầu – đuôi tách hai chữ số cuối của 27 giải."])),
        _sec("#ma-tran-ngay, #db-tuan-thang", "Bảng theo ngày", _thong_ke(f, "Xếp kết quả đã lưu theo ngày, tuần và tháng.")),
        _sec("#ai-ml", "Dự báo AI/ML", _du_bao_ev(f, "Số hiển thị là xác suất (hoặc thứ hạng) của số ấy cho kỳ kế tiếp.")),
        _sec("#mo-phong, #du-doan-vui", "Bảng mô phỏng", _ev([_MO_PHONG, _du_bao(f)], ["Rút hai chữ số cuối theo xác suất mô hình bằng hạt giống cố định của kỳ.", "Phần đầu là số ngẫu nhiên, không mang thông tin.", "Sổ nhật ký chấm bảng đã hiện với kết quả thật."])),
        _sec("#tan-suat-cap, #tan-suat-loto, #tan-suat-de", "Tần suất", _thong_ke(f, "Đếm số lần mỗi số (hoặc cặp) về trong khung thời gian của bảng.")),
        _sec("#gan-nhip", "Gan và nhịp", _thong_ke(f, "Gan = số kỳ kể từ lần về gần nhất; nhịp = khoảng cách giữa hai lần về liên tiếp.")),
        _sec("#cap-lon", "Cặp lộn", _thong_ke(f, "Cặp lộn là hai số đảo chữ số (12 ↔ 21); số kép (11, 22…) xét riêng.")),
        _sec("#dau-duoi-tong", "Đầu · đuôi · tổng", _thong_ke(f, "Đầu = chữ số hàng chục, đuôi = hàng đơn vị, tổng = (đầu + đuôi) mod 10.")),
        _sec("#duong-cau", "Vị trí đường cầu", _cau(f, "Ô cầu đẹp nhất xếp theo độ dài cầu, rồi theo số cầu cùng báo một số.")),
        _sec("#backtest", "Kiểm định AI/ML", _ev([_cham(f), _du_bao(f)], ["Chấm dự báo của từng kỳ với kết quả thật của chính kỳ ấy.", "So với dự báo hằng số trên cùng các kỳ; hiệu từng kỳ cho điểm z."])),
    ]
    return page, sections


def _thong_ke_tong(f: dict[str, str]) -> tuple[Evidence, list[Section]]:
    page = _thong_ke(f, "Dựng các bảng tần suất, gan, đầu đuôi và cặp từ cùng một sổ kết quả.")
    sections = [
        _sec("#ai-ml, #can-cu-cau", "Cầu-kèo AI/ML", _du_bao_ev(f, "Điểm xếp hạng gộp tín hiệu cầu và mô hình cho từng số.")),
        _sec("#gan-nhip", "Gan và nhịp", _thong_ke(f, "Gan = số kỳ kể từ lần về gần nhất; nhịp = khoảng cách giữa hai lần về.")),
        _sec("#dieu-kien", "Điều kiện lịch sử", _thong_ke(f, "Lọc các kỳ thoả điều kiện rồi đếm kết cục ở kỳ kế tiếp; mẫu nhỏ thì dao động lớn.")),
    ]
    return page, sections


def _catalog(f: dict[str, str]) -> dict[str, tuple[Evidence, list[Section]]]:
    """Trang → (bằng chứng mặc định, ghi đè theo khối). Phủ MỌI trang xuất bản."""
    tk = lambda *extra: (_thong_ke(f, *extra), [])  # noqa: E731
    cau = lambda *extra: (_cau(f, *extra), [])  # noqa: E731
    home = _trang_chu(f)
    return {
        "index.html": home,
        "landing.html": home,
        "landing_desktop.html": home,
        "live.html": (_ev([_LIVE, _ket_qua(f)], ["Hiển thị giải đang quay theo đúng thứ tự giải.", "Dự đoán trong ngày dùng vector đã công bố trước giờ quay; " + _GHI_CHU_DU_BAO]), [
            _sec("#live-predictions", "Dự đoán trong ngày", _du_bao_ev(f, "Số hiển thị là dự báo đã lưu cho đúng ngày quay đang xem, không phải kết quả.")),
        ]),
        "so-ket-qua-truyen-thong.html": (_ev([_ket_qua(f), _LOTO], ["Lấy đúng kỳ quay đã lưu theo bộ lọc ngày.", "Bảng LOTO đầu – đuôi tách hai chữ số cuối của 27 giải."]), []),
        "statistics.html": _thong_ke_tong(f),
        "bang-dac-biet.html": tk("Giải Đặc Biệt đủ 5 chữ số theo tuần: hàng là tuần, cột là thứ."),
        "bang-dac-biet-thang.html": tk("Trọn một năm: hàng là ngày trong tháng, cột là tháng."),
        "bang-dac-biet-nam.html": tk("Một tháng soi qua mọi năm: hàng là năm, cột là ngày trong tháng."),
        "chu-ky-dac-biet.html": tk("Số kỳ chưa về của từng con 00–99 ở giải Đặc Biệt, và chu kỳ dài nhất trong lịch sử."),
        "cau-dac-biet-theo-bo-so.html": tk("Điểm rơi của từng bộ số ở giải Đặc Biệt: lần về gần nhất, khoảng cách và số lần."),
        "giai-db-ngay-mai.html": tk("Xếp hạng tham khảo cho kỳ kế tiếp, dựng từ chu kỳ và tần suất lịch sử — không phải dự báo đã kiểm định."),
        "tan-suat-loto.html": tk("Ma trận con lô × từng kỳ: mỗi ô là số nháy của con lô ở kỳ ấy."),
        "tan-suat-cap-loto.html": tk("Ma trận 50 họ cặp × từng kỳ; kèm bảng đồng xuất hiện."),
        "cap-lon-loto.html": tk("45 cặp lộn thật (đảo hai chữ số), kèm 10 số kép liệt kê riêng."),
        "cau-giai-dac-biet.html": tk("Tần suất hai số cuối giải Đặc Biệt theo Đầu, cặp lộn kèm số lần, ba kỳ gần nhất."),
        "giai-dac-biet-theo-tong.html": tk("Tổng = (Đầu + Đuôi) mod 10. Gan theo tổng, chuyển tổng và chẵn lẻ hôm sau."),
        "dau-duoi-loto.html": tk("Phân bố chữ số đầu và chữ số đuôi của toàn bộ LOTO trong dải đã chọn."),
        "lo-gan.html": tk("Số kỳ chưa về của từng con LOTO, gan cực đại trong lịch sử, và cặp lô gan."),
        "thong-ke-tong-hop.html": tk("Bảng tổng hợp đa chiều: tần suất, chu kỳ gan, đầu đuôi và tổng trên cùng một dải."),
        "soi-cau-vi-tri.html": cau("Lộn thì cộng gộp nháy của cả hai chiều; số kép chỉ là một số (số bóng chỉ hiện kèm)."),
        "soi-cau-loto.html": cau("Bước trúng: n hoặc số lộn của n về ở kỳ kế tiếp (≥ 1 nháy, cộng cả hai chiều)."),
        "soi-cau-hai-nhay.html": cau("Bước trúng: n về ≥ 2 nháy, hoặc n và số lộn (khác n) cùng về ở kỳ kế tiếp."),
        "soi-cau-bach-thu.html": cau("Bước trúng: đúng n về ở kỳ kế tiếp (không tính số lộn)."),
        "soi-cau-dac-biet.html": cau("Bước trúng: một chữ số của n trùng hàng chục hoặc hàng đơn vị hai số cuối Đặc Biệt kỳ kế tiếp."),
        "soi-cau-dac-biet-bo-so.html": cau("Bước trúng: n của kỳ sau cùng bộ với n của kỳ trước; cầu báo Đặc Biệt kỳ sau rơi vào bộ ấy."),
        "soi-cau-dac-biet-theo-thu.html": cau("Như cầu Đặc Biệt, nhưng chỉ trên các kỳ cùng một thứ trong tuần."),
        "soi-cau-loto-theo-thu.html": cau("Như cầu LOTO, nhưng chỉ trên các kỳ cùng một thứ trong tuần."),
        "soi-path-loto-active.html": cau("Ngày neo, số ngày cầu chạy và trạng thái ghi ở đầu trang."),
        "soi-path-loto-stable.html": cau("Ngày neo, số ngày cầu chạy và trạng thái ghi ở đầu trang."),
        "soi-path-de-active.html": cau("Ngày neo, số ngày cầu chạy và trạng thái ghi ở đầu trang."),
        "soi-path-de-stable.html": cau("Ngày neo, số ngày cầu chạy và trạng thái ghi ở đầu trang."),
        "dashboard.html": (_du_bao_ev(f, "Trọng số là phần đóng góp của từng thành phần vào tổ hợp."), []),
        "ml_top10_loto.html": (_du_bao_ev(f, "10 số LOTO có xác suất thành phần ML cao nhất."), []),
        "ml_top10_de.html": (_du_bao_ev(f, "10 số Đặc Biệt có xác suất thành phần ML cao nhất.", mode="de"), []),
        "model-quality.html": (_ev([_cham(f), _du_bao(f)], ["Chấm vector xác suất đã công bố của từng kỳ với kết quả thật.", "Phân rã Brier thành phần hiệu chỉnh và phần phân biệt.", "Kỹ năng = 1 − điểm mô hình / điểm dự báo hằng số; 0 là ngang hằng số."]), []),
        "do-tin-cay.html": (_ev([_NULL, _ket_qua(f), _cham(f)], ["Đo tín hiệu mạnh nhất của từng họ (Bayes, Markov, cầu) trên lịch sử thật.", "Tin cậy = tỉ lệ lịch sử ngẫu nhiên có tín hiệu mạnh nhất còn yếu hơn — không phải hậu nghiệm từng con.", "Ba tầng: High khi cả ba > 85%, Medium khi hai trong ba ≥ 60%, còn lại Low/Noise."]), []),
        "research-lab.html": (_ev([_ket_qua(f), _NULL], ["Mỗi giả thuyết kiểm trên tập giữ lại theo thời gian, có kiểm soát nhiều phép thử.", "Kết quả tách khỏi bộ dự báo vận hành cho tới khi vượt mọi cổng."]), []),
        "tao-phoi-tuan.html": (_ev([_ket_qua(f), _DAC_BIET], ["Lấy giải Đặc Biệt đã lưu, xếp Thứ Hai → Chủ Nhật theo tuần.", "Tách 3 chữ số đầu và 2 chữ số cuối theo tuỳ chọn của phôi."]), []),
    }


def registry(page_name: str, data_dir: Path | None = None) -> dict:
    """Khối bằng chứng của một trang, hoặc ``{}`` nếu trang không có mục.

    Trang lạ (ví dụ trang dựng trong phép kiểm) vẫn nhận bằng chứng chung
    của sổ kết quả, để không có con số nào mở ra một ngăn kéo rỗng.
    """
    f = facts(str(data_dir or ROOT / "data"))
    page, sections = _catalog(f).get(page_name, (_thong_ke(f), []))
    return {"schema": SCHEMA_VERSION, "page": page, "sections": sections, "values": {}}


def covered_pages() -> set[str]:
    return set(_catalog({}).keys())


def registry_json(page_name: str, data_dir: Path | None = None) -> str:
    """JSON an toàn để đặt trong ``<script type="application/json">``.

    ``<`` được thoát thành ``\\u003c`` để không chuỗi nào đóng được thẻ
    script sớm, và ``&`` thành ``\\u0026`` cho lượt chuẩn hoá HTML phía sau.
    """
    text = json.dumps(registry(page_name, data_dir), ensure_ascii=False, separators=(",", ":"))
    return text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")


# --- Bằng chứng theo từng giá trị ----------------------------------------


def _pct(x: float) -> str:
    return f"{x * 100:.3f}%".replace(".", ",")


def _vi(x: float, digits: int = 3) -> str:
    return f"{x:.{digits}f}".replace(".", ",")


def _legacy_trust(row: dict) -> bool:
    """Dòng có model_trust tính theo luật cũ (trước ``TRUST_POLICY_VERSION`` hiện hành)."""
    from ml_train import TRUST_POLICY_VERSION

    version = pd.to_numeric(pd.Series([row.get("trust_policy_version")]), errors="coerce").iloc[0]
    return pd.isna(version) or int(version) != TRUST_POLICY_VERSION


def ml_row_evidence(df: pd.DataFrame, mode: str, data_dir: Path | None = None) -> list[tuple[str, dict]]:
    """Bằng chứng tính toán cho từng hàng của bảng top ML, theo thứ tự hàng.

    Đọc đúng các cột ``ml_predict`` ghi ra: xác suất thô, ``model_trust`` và
    ``quality_pass``. Với LOTO, tỉ lệ nền suy ra chính xác từ phép trộn
    ``p = trust·thô + (1 − trust)·nền``; Đặc Biệt còn chuẩn hoá sau khi trộn
    nên chỉ ghi hai bước, không bịa một con số nền.
    """
    f = facts(str(data_dir or ROOT / "data"))
    label = "LOTO" if mode == "loto" else "Đặc Biệt"
    out: list[tuple[str, dict]] = []
    needed = {"number", "prob", "raw_model_prob", "model_trust"}
    if df.empty or not needed.issubset(df.columns):
        return out
    for row in df.to_dict("records"):
        n, p, raw, trust = int(row["number"]), float(row["prob"]), float(row["raw_model_prob"]), float(row["model_trust"])
        steps = [f"Thành phần ML cho số {n:02d} xác suất thô {_pct(raw)}."]
        if trust <= 0.0:
            steps.append(f"Độ tin model_trust = 0 (không có kỹ năng thẩm định): p = tỉ lệ nền = {_pct(p)}.")
        elif trust >= 1.0:
            steps.append(f"Độ tin model_trust = 1: dùng nguyên xác suất thô, p = {_pct(p)}.")
        elif mode == "loto":
            base = (p - trust * raw) / (1.0 - trust)
            steps.append(
                f"Co về tỉ lệ nền: p = trust·thô + (1 − trust)·nền = {_vi(trust)} × {_pct(raw)} + "
                f"{_vi(1 - trust)} × {_pct(base)} = {_pct(p)}."
            )
        else:
            steps.append(
                f"Co về tỉ lệ nền với trust = {_vi(trust)}, rồi chuẩn hoá để 100 số cộng lại 100%: "
                f"p = {_pct(p)}."
            )
        if "quality_pass" in row:
            passed = str(row["quality_pass"]).strip().lower() in {"true", "1"}
            steps.append(
                "Lần học này có kỹ năng dương trên khối thẩm định chưa chạm."
                if passed
                else "Lần học này không có kỹ năng dương trên khối thẩm định chưa chạm (quality_pass = False)."
            )
        steps.append(f"Độ tin cậy hiển thị bên dưới chính là model_trust = {_vi(trust)}.")
        if _legacy_trust(row):
            steps.append(
                "Tệp dự báo này được tạo theo luật trust CŨ (sàn 0,35 — vẫn trộn 35% mô hình thô "
                "khi không có kỹ năng), đã bỏ ngày 03-10-2026. Theo luật hiện hành, độ tin bằng "
                "20 × kỹ năng thẩm định và bằng 0 khi không có kỹ năng; lượt học lại kế tiếp "
                "sẽ thay tệp này."
            )
        steps.append(_GHI_CHU_DU_BAO)
        out.append((
            f"ml-{mode}-{n:02d}",
            {
                "title": f"Số {n:02d} · ML {label}",
                "sources": [_ml(mode), _du_bao(f), _cham(f)],
                "reasoningTrace": {"steps": steps, "confidenceScore": max(0.0, min(1.0, trust))},
            },
        ))
    return out


def tag_rows(table_html: str, ids: list[str]) -> str:
    """Gắn ``data-evidence-row`` cho các ``<tr>`` trong ``<tbody>``, theo thứ tự."""
    start = table_html.find("<tbody")
    if start < 0 or not ids:
        return table_html
    head, body = table_html[:start], table_html[start:]
    queue = iter(ids)

    def put(match: re.Match[str]) -> str:
        ident = next(queue, None)
        return match.group(0) if ident is None else f'<tr data-evidence-row="{ident}"'

    return head + re.sub(r"<tr(?=[\s>])", put, body)


def values_block(entries: list[tuple[str, dict]]) -> str:
    """Khối JSON ``[data-app-evidence-values]`` mà ``app-evidence.js`` gộp vào danh mục."""
    if not entries:
        return ""
    text = json.dumps(dict(entries), ensure_ascii=False, separators=(",", ":"))
    text = text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return f'<script type="application/json" data-app-evidence-values>{text}</script>'
