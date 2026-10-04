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
    """Ghi đè cho một khối: khớp bằng bộ chọn CSS ``match`` HOẶC bằng tiêu đề
    khối ``heading`` (tiền tố của h2/h3), cho trang mà thẻ không mang id."""

    title: str
    match: NotRequired[str]
    heading: NotRequired[str]


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
    # Siêu dữ liệu trọng số CHỈ qua weights_provenance (luật của kho), không mở tệp.
    from ensemble_utils import weights_provenance

    spec = weights_provenance(base, "loto")
    if spec.get("window_days") and spec.get("half_life_days"):
        out.update(weight_window=str(spec["window_days"]), weight_half_life=str(spec["half_life_days"]))
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


def _trong_so(f: dict[str, str]) -> Source:
    window = (
        f"Học trên cửa sổ {f['weight_window']} ngày gần nhất, nửa chu kỳ phân rã {f['weight_half_life']} ngày; "
        if "weight_window" in f else ""
    )
    return {
        "title": "Trọng số tổ hợp và hiệu chỉnh đã lưu",
        "snippet": window + "khối học trọng số và khối hiệu chỉnh tách theo thời gian, không chồng nhau.",
        "url": "dashboard.html",
    }


_MO_PHONG_RUI_RO: Source = {
    "title": "Mô phỏng kỳ kế tiếp",
    "snippet": "10 000 kỳ giả lập, mỗi kỳ 27 giải rút đều trong 00–99; so nhóm số đang công bố với kết cục giả lập.",
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

_CAU_KEO: Source = {
    "title": "Mô hình cầu-kèo AI/ML",
    "snippet": (
        "Cây tăng cường hiệu chỉnh Platt học trên cặp (kỳ t, số) → số ấy có về ở kỳ t + 1, "
        "kèm các tín hiệu cầu, xác suất có điều kiện, tần suất và gan tính từ các kỳ trước."
    ),
    "url": "statistics.html",
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


def _sec_heading(heading: str, title: str, ev: Evidence) -> Section:
    return {"heading": heading, "title": title, **ev}  # type: ignore[typeddict-item]


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


def _du_bao_ev(f: dict[str, str], *extra: str, mode: str = "both") -> Evidence:
    """``mode="both"`` cho khối gộp LOTO lẫn Đặc Biệt: trích nguồn ML của cả hai."""
    models = [_ml("loto"), _ml("de")] if mode == "both" else [_ml(mode)]
    return _ev(
        [_du_bao(f), *models, _cham(f)],
        [
            "Mỗi thành phần cho một vector xác suất 100 số, chỉ dùng các kỳ trước kỳ đích.",
            "Trộn theo trọng số mặc định (hoặc vector đã học khi nó thắng mặc định ngoài mẫu), "
            "rồi hiệu chỉnh xác suất.",
            *extra,
            _GHI_CHU_DU_BAO,
        ],
    )


def _cau_keo_ev(f: dict[str, str], *extra: str) -> Evidence:
    """Điểm cầu-kèo (``cau_keo_ml._add_ai_judgement``): thứ hạng 0–100, KHÔNG phải xác suất."""
    return _ev(
        [_CAU_KEO, _ket_qua(f), _CAU],
        [
            "Mỗi tín hiệu của 100 số được chuẩn hoá min–max về 0–1 trong chính kỳ ấy.",
            "LOTO: điểm = 100 × (0,38·xác suất mô hình + 0,18·hỗ trợ đường cầu + 0,14·tỉ lệ về sau "
            "Đặc Biệt hôm nay + 0,13·tỉ lệ về sau LOTO hôm nay + 0,10·tần suất 30 ngày "
            "+ 0,04·cùng thứ + 0,03·xu hướng 7/30 ngày).",
            "Đặc Biệt: điểm = 100 × (0,42·xác suất mô hình + 0,18·tỉ lệ về sau Đặc Biệt hôm nay "
            "+ 0,16·hỗ trợ đường cầu + 0,10·gan + 0,08·cùng thứ + 0,06·tỉ lệ về sau LOTO hôm nay).",
            "Trọng số các tín hiệu đặt cố định, không học; điểm chỉ so được giữa các số trong cùng "
            "một kỳ, không phải xác suất đã hiệu chuẩn.",
            *extra,
        ],
    )


def _trang_chu(f: dict[str, str]) -> tuple[Evidence, list[Section]]:
    page = _ev([_ket_qua(f), _LOTO, _DAC_BIET], ["Đọc sổ kết quả đã lưu.", "Mỗi khối trên trang có cách tính riêng, ghi trong khối ấy."])
    sections = [
        _sec("#live", "Kết quả trực tiếp", _ev([_LIVE, _ket_qua(f)], ["Hiển thị giải đang quay theo đúng thứ tự giải.", "Khi phiên kết thúc, kết quả được lưu vào sổ."])),
        _sec("#ket-qua", "Bảng kết quả", _ev([_ket_qua(f), _LOTO], ["Lấy kỳ quay đã lưu theo ngày đang chọn.", "Bảng LOTO đầu – đuôi tách hai chữ số cuối của 27 giải."])),
        _sec("#ma-tran-ngay, #db-tuan-thang", "Bảng theo ngày", _thong_ke(f, "Xếp kết quả đã lưu theo ngày, tuần và tháng.")),
        _sec("#ai-ml", "Điểm cầu-kèo ngày mai", _cau_keo_ev(f, "Số trên mỗi thanh là điểm của số ấy; thanh dài hơn chỉ nghĩa là xếp trên trong kỳ này.")),
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
        _sec("#ai-ml", "Cầu-kèo AI/ML", _cau_keo_ev(f, "Cột xác suất là xác suất của riêng mô hình cầu-kèo (Đặc Biệt chuẩn hoá tổng 100 số bằng 1), không phải xác suất tổ hợp đã công bố.")),
        _sec_heading("Kiểm định cầu-kèo", "Kiểm định cầu-kèo", _ev([_CAU_KEO, _ket_qua(f)], [
            "Học trên các kỳ trước lát kiểm định, rồi dự báo từng ngày của lát kiểm định gần nhất (ngày đầu ghi ở cột ngày bắt đầu).",
            "Mỗi dòng là một nhóm K số điểm cao nhất: số ngày kiểm, số ngày có ít nhất một số trong nhóm về và tỉ lệ ấy, số lượt về trung bình mỗi ngày.",
            "Brier và logloss chấm xác suất của mô hình cầu-kèo trên cùng lát kiểm định; nhỏ hơn là tốt hơn.",
        ])),
        _sec("#can-cu-cau", "Căn cứ cầu", _cau_keo_ev(f, "Các cột đường cầu đếm số đường cầu vị trí ghép ra số ấy (đang chạy, ổn định) và đường mạnh nhất; cột xác suất là của riêng mô hình cầu-kèo.")),
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
            # Trang tải dự báo theo ngày quay LÚC CHẠY, nên không ghi ngày lúc dựng trang.
            _sec("#live-predictions", "Dự đoán trong ngày", _du_bao_ev(
                {k: v for k, v in f.items() if k != "target"},
                "Số hiển thị là dự báo đã lưu cho đúng ngày quay ghi ở đầu khối, không phải kết quả.",
            )),
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
        "dashboard.html": (_du_bao_ev(f, "Số trong bảng xác suất và danh sách gợi ý là xác suất (hoặc thứ hạng) của số ấy cho kỳ kế tiếp."), [
            _sec_heading("Trọng số", "Trọng số tổ hợp và cổng thẩm định", _ev([_trong_so(f), _cham(f)], [
                "Mỗi thành phần đóng góp theo một trọng số; mặc định là vector cố định.",
                "Vector học từ các ngày gần đây chỉ được dùng khi thắng vector MẶC ĐỊNH trên lát kiểm ngoài mẫu (ngày chưa dùng để học) với biên ≥ 0,20%.",
                "Các số trong khối là trọng số, hoặc chỉ số của cổng: logloss/Brier từng vector, số ngày học/kiểm, biên thắng và khoảng tin cậy.",
            ])),
            _sec_heading("Hiệu chỉnh", "Hiệu chỉnh xác suất", _ev([_trong_so(f), _cham(f)], [
                "Sau khi trộn, xác suất được hiệu chỉnh bằng tham số học trên một khối ngày RIÊNG, nằm sau khối dùng để học trọng số (hai khối không chồng nhau).",
                "Các số trong khối là tham số hiệu chỉnh hoặc logloss/Brier trên khối hiệu chỉnh.",
            ])),
        ]),
        "ml_top10_loto.html": (_du_bao_ev(f, "10 số LOTO có xác suất thành phần ML cao nhất.", mode="loto"), []),
        "ml_top10_de.html": (_du_bao_ev(f, "10 số Đặc Biệt có xác suất thành phần ML cao nhất.", mode="de"), []),
        "model-quality.html": (_ev([_cham(f), _du_bao(f)], [
            "Chấm vector xác suất đã công bố của từng kỳ với kết quả thật.",
            "Mỗi khối trên trang có cách tính riêng, ghi trong khối ấy.",
        ]), [
            _sec_heading("Đã sửa một lỗi đơn vị", "Sửa đơn vị Brier", _ev([_cham(f)], [
                "Đếm số dòng Brier Đặc Biệt trong lịch sử đã lưu từng ghi theo trung bình 100 lớp và đã được đổi sang tổng 100 lớp như các dòng mới.",
                "Dòng cũ được nhận ra bằng bất biến toán học của đơn vị, không bằng mốc ngày cứng.",
            ])),
            _sec_heading("Nguồn của các con số", "Nguồn chấm", _ev([_cham(f), _du_bao(f)], [
                "Số lớn là số kỳ đã chấm: vector đã công bố trước kỳ quay so với kết quả thật (hoặc bản dựng lại khi chưa đủ kỳ đã công bố).",
                "Kỹ năng một kỳ = 1 − logloss mô hình / logloss dự báo hằng số; dòng bộ theo dõi là trung bình các kỳ gần nhất kèm khoảng ± z × sai số chuẩn.",
                "Bộ theo dõi báo động khi khoảng ấy rời 0 theo hướng nào cũng vậy.",
            ])),
            _sec_heading("Vì sao kỹ năng gần bằng 0", "Phân rã Brier", _ev([_cham(f)], [
                "Chia mọi ô (kỳ × số) thành 10 nhóm theo phân vị của xác suất dự báo — đúng các nhóm của biểu đồ hiệu chỉnh.",
                "Độ tin cậy = trung bình có trọng số (dự báo − thực tế)² theo nhóm; độ phân giải = trung bình có trọng số (thực tế nhóm − tỉ lệ chung)²; độ bất định = tỉ lệ chung × (1 − tỉ lệ chung).",
                "Tin cậy − phân giải + bất định bằng đúng Brier của dự báo đã gộp nhóm; Brier đo trực tiếp lệch một phần dư do chia nhóm.",
            ])),
            _sec_heading("Độ hiệu chỉnh", "Độ hiệu chỉnh", _ev([_cham(f)], [
                "Chia mọi ô (kỳ × số) thành 10 nhóm theo phân vị của xác suất dự báo.",
                "Mỗi nhóm: số ô, xác suất dự báo trung bình, tỉ lệ về thực tế, và khoảng Wilson 95% của tỉ lệ ấy.",
            ])),
            _sec_heading("Độ sắc", "Độ sắc", _ev([_cham(f)], [
                "Chia khoảng [nhỏ nhất, lớn nhất] của mọi xác suất dự báo thành 24 khoảng đều; mỗi cột là số ô (kỳ × số) rơi vào khoảng ấy.",
                "Độ lệch chuẩn của xác suất dự báo, và tỉ số của nó với tỉ lệ nền, đo mô hình dám rời nền bao xa.",
            ])),
            _sec_heading("Kỹ năng theo thời gian", "Kỹ năng theo thời gian", _ev([_cham(f)], [
                "Kỹ năng từng kỳ = 1 − logloss mô hình / logloss dự báo hằng số; 0 là ngang hằng số.",
                "Đường tích luỹ là trung bình các kỳ tới ngày ấy; dải là ±1,96 × sai số chuẩn của trung bình.",
                "Tỉ lệ «tệ hơn đường cơ sở» đếm số kỳ có kỹ năng âm.",
            ])),
        ]),
        "do-tin-cay.html": (_ev([_NULL, _ket_qua(f), _cham(f)], [
            "Đọc sổ kết quả đã lưu và phân phối null của 10 000 lịch sử ngẫu nhiên cùng độ dài.",
            "Mỗi khối trên trang có cách tính riêng, ghi trong khối ấy.",
        ]), [
            _sec_heading("Kết luận cho kỳ kế tiếp", "Kết luận cho kỳ kế tiếp", _ev([_NULL, _ket_qua(f)], [
                "Xếp từng con 00–99 vào ba tầng theo luật ở khối «Luật ba tầng», rồi đếm số con ở tầng Cao · Trung bình · Thấp/nhiễu.",
                "«Thành phần mạnh nhất» là tin cậy lớn nhất của ba họ Bayes, Markov, cầu trên cả 100 con.",
                "Thẻ Đối chứng: số lịch sử công bằng đã giả lập, số kỳ mỗi lịch sử, và số kỳ thật trong sổ.",
            ])),
            _sec_heading("Luật ba tầng", "Luật ba tầng", _ev([_NULL], [
                "Tin cậy của một thành phần = tỉ lệ lịch sử công bằng mà tín hiệu mạnh nhất của cả họ còn yếu hơn nó, tức 1 − p đã hiệu chỉnh cho việc soi nhiều con cùng lúc.",
                "High khi cả ba thành phần vượt ngưỡng cao; Medium khi ít nhất hai thành phần đạt ngưỡng giữa; còn lại Low/Noise.",
                "Các tỉ lệ ở đoạn cuối đếm số lịch sử ngẫu nhiên có ít nhất một con đạt hậu nghiệm Bayes vượt mức ghi bên cạnh.",
            ])),
            _sec_heading("Ma trận suy luận", "Ma trận suy luận", _ev([_NULL, _ket_qua(f), _CAU], [
                "Bayes: hậu nghiệm xác suất về của con ấy cao hơn tỉ lệ nền → tin cậy so với phân phối null.",
                "Markov: điểm z của xác suất về theo đúng trạng thái kỳ trước của con ấy → tin cậy.",
                "Cầu: tỉ lệ trúng của cầu vị trí tốt nhất ghép ra con ấy từ kỳ vừa quay → tin cậy.",
                "Score là thành phần yếu nhất (tầng Cao) hoặc mạnh thứ hai (tầng khác).",
            ])),
            _sec_heading("Các trục cầu kèo so với ngẫu nhiên", "Các trục cầu kèo so với ngẫu nhiên", _ev([_NULL, _ket_qua(f)], [
                "Mỗi trục là một họ tín hiệu; «Thật» là tín hiệu mạnh nhất của họ trên lịch sử thật, so với trung vị của nó trên các lịch sử ngẫu nhiên.",
                "p = tỉ lệ lịch sử công bằng có tín hiệu mạnh nhất của họ ≥ tín hiệu thật (có sàn vì số lịch sử hữu hạn).",
                "Soi k họ cùng lúc nên ngưỡng Bonferroni là 0,05 / k; chỉ dòng có p dưới ngưỡng ấy mới là khác ngẫu nhiên.",
            ])),
            _sec_heading("Kiểm ngoài mẫu", "Kiểm ngoài mẫu", _ev([_ket_qua(f)], [
                "Chọn nhóm tín hiệu mạnh nhất (10 con Bayes, 10 con Markov, 50 cặp, 20 cầu…) chỉ trên các kỳ 2015–2023; cột «Trong mẫu» là tỉ lệ trúng của nhóm ấy trên chính các kỳ đã dùng để chọn.",
                "Chấm đúng tín hiệu ấy trên các kỳ từ 2024 tới nay (số trúng / số lần), so với tỉ lệ nền.",
                "z = Σ(trúng − kỳ vọng theo nền) / căn của tổng bình phương độ lệch từng kỳ — phương sai ước lượng theo từng kỳ quay vì các lượt trúng trong một kỳ không độc lập; |z| < 2 nghĩa là không phân biệt được với nền.",
            ])),
            _sec_heading("Giả thuyết kỳ quay bị sắp đặt", "Giả thuyết kỳ quay bị sắp đặt", _ev([_NULL, _ket_qua(f)], [
                "Mỗi dòng là một dấu vết có thể khai thác; số đo tính trên kết quả công bố thật.",
                "Dòng χ² lấy p từ phân phối χ² với số bậc tự do ghi kèm; hai dòng đếm «né» lấy p Monte Carlo hai phía trên các lịch sử công bằng, không nhỏ hơn 1/(N + 1).",
                "p (Holm) hiệu chỉnh Holm cho cả bốn dấu vết kiểm cùng lúc.",
            ])),
            _sec_heading("Rủi ro / lợi nhuận", "Rủi ro / lợi nhuận", _ev([_MO_PHONG_RUI_RO], [
                "Giả lập 10 000 kỳ kế tiếp, mỗi kỳ 27 giải rút đều trong 00–99 (hạt giống theo ngày đích); không dùng mô hình nào.",
                "Đếm số con trong nhóm 10 con LOTO đang công bố có về ở mỗi kỳ giả lập → tỉ lệ ở bảng; trung bình lượt về mỗi kỳ.",
                "Hoà vốn: mỗi con kỳ vọng 27/100 lượt về mỗi kỳ, nên mức trả phải ≥ 100/27 ≈ 3,70 lần tiền đặt cho mỗi lượt về; Đặc Biệt một giải, xác suất 1/100, hoà vốn 100 lần.",
            ])),
            _sec_heading("Vòng phản hồi", "Vòng phản hồi", _ev([_cham(f), _du_bao(f)], [
                "Chấm vector xác suất đã công bố trước kỳ quay với kết quả thật; cặp số là điểm mô hình / điểm dự báo hằng số.",
                "Bộ theo dõi báo động khi kỹ năng ngoài mẫu rời vùng 0 theo HƯỚNG NÀO CŨNG VẬY (z = 3, cửa sổ 60 kỳ).",
            ])),
            _sec_heading("Giả thuyết đang kiểm tiến cứu", "Giả thuyết đuôi nóng", _ev([_ket_qua(f)], [
                "Giả thuyết đăng ký ngày 28-09-2026, TRƯỚC khi có dữ liệu kiểm: chạy từ kỳ 29-09-2026, 180 kỳ, kiểm một phía α = 0,01.",
                "Tham số không được sửa sau khi đăng ký; số trên thẻ là tiến độ và kết quả tích luỹ tới kỳ gần nhất.",
            ])),
        ]),
        "research-lab.html": (_ev([_ket_qua(f)], [
            "Đọc các báo cáo nghiên cứu dựng từ sổ kết quả đã lưu.",
            "Mỗi khối trên trang có cách tính riêng, ghi trong khối ấy; không khối nào nối vào bộ dự báo vận hành.",
        ]), [
            _sec(".rl-metrics", "Tóm tắt các họ giả thuyết", _ev([_ket_qua(f)], [
                "Mỗi thẻ đếm số giả thuyết của một họ và số giả thuyết qua cổng của họ ấy (cổng ghi ngay trên thẻ: đủ điều kiện vận hành, cổng nghiên cứu, hay FDR < 0,05).",
                "Thẻ cầu bóng so độ nâng tốt nhất trên tập huấn luyện với trung bình độ nâng tốt nhất khi dịch vòng chuỗi kết quả theo thời gian; p = tỉ lệ lượt dịch vòng có độ nâng tốt nhất ≥ thật.",
                "Thẻ Đặc Biệt → LOTO: hai số cuối Đặc Biệt kỳ gần nhất, số ô có điều kiện và số ô có q < 0,05.",
            ])),
            _sec_heading("Chẩn đoán tính ngẫu nhiên", "Chẩn đoán tính ngẫu nhiên", _ev([_ket_qua(f)], [
                "Mỗi dòng là một phép kiểm định trên toàn bộ lịch sử: thống kê và p thô.",
                "q là p đã hiệu chỉnh Benjamini–Hochberg FDR trên nhóm phép kiểm chính; «Có» khi q < 0,05.",
            ])),
            _sec_heading("Gan tổng / chạm", "Gan tổng / chạm", _ev([_ket_qua(f), _LOTO], [
                "Thống kê mô tả, không phải phép kiểm và không dùng làm xác suất.",
                "Chạm d: số ngày kể từ kỳ gần nhất có một LOTO chứa chữ số d (hàng chục hoặc đơn vị). Tổng s: như vậy với LOTO có tổng hai chữ số bằng s (0–18, không lấy mod 10).",
                "«Lần cuối» là ngày của kỳ ấy; bảng xếp từ gan dài nhất xuống.",
            ])),
            _sec_heading("Kiểm tra tương thích cũ", "Kiểm tra tương thích cũ", _ev([_ket_qua(f)], [
                "Các kiểm định từ phiên bản cũ, giữ riêng vì chúng hỏi câu hỏi thống kê khác bộ kiểm hiện đại.",
                "Mỗi dòng ghi thống kê, p và phương pháp; dòng ACF đếm số độ trễ đã kiểm và số độ trễ có FDR < 0,05.",
            ])),
            _sec_heading("Đặc Biệt", "Đặc Biệt → LOTO ngày kế", _ev([_ket_qua(f), _LOTO, _DAC_BIET], [
                "Chỉ dùng cặp ngày lịch liên tiếp có hai số cuối Đặc Biệt hôm trước đúng bằng số ghi ở tiêu đề.",
                "Cỡ mẫu = số cặp ngày như vậy; số lần trúng = số lần con ấy về LOTO ngày kế; p thô = trúng / cỡ mẫu.",
                "p EB co p thô về xác suất nền biên (Bayes thực nghiệm) để mẫu nhỏ không bị phóng đại; q là BH-FDR trên mọi ô.",
            ])),
            _sec_heading("Cầu bóng", "Cầu bóng trên 107 ô chữ số", _ev([_ket_qua(f), _CAU], [
                "Chọn các đường cầu có độ nâng cao nhất trên tập huấn luyện; q là BH-FDR chỉ trên tập huấn luyện.",
                "Chấm lại đúng những đường ấy trên tập kiểm định rồi tập giữ lại theo thời gian, chưa từng dùng để chọn; độ nâng = tỉ lệ trúng / tỉ lệ nền.",
            ])),
            _sec_heading("Phòng chiến lược", "Phòng chiến lược", _ev([_ket_qua(f)], [
                "Mỗi chiến lược chọn số bằng một luật cố định; độ chính xác và độ nâng (so với tỉ lệ nền chỉ tính trên tập huấn luyện) chấm trên tập giữ lại theo thời gian.",
                "q là BH-FDR trên tập giữ lại; «ĐẠT» khi q ≤ 0,05, độ nâng ≥ 1,03, hiệu ứng đủ lớn và ít nhất 100 lượt chọn trên tập giữ lại — vẫn chưa phải đủ điều kiện vận hành.",
            ])),
            _sec_heading("Họ vị trí chéo độ trễ", "Họ vị trí chéo độ trễ", _ev([_ket_qua(f), _CAU], [
                "Mỗi quy tắc ghép chữ số ở vị trí A (trễ A ngày) với vị trí B (trễ B ngày; −1 là không dùng) bằng phép biến đổi ghi ở cột đầu.",
                "Độ nâng chấm trên tập giữ lại chưa chạm; «CẦN XEM XÉT» khi q (BH-FDR, tập huấn luyện) ≤ 0,05 và độ nâng ở cả tập kiểm định lẫn tập giữ lại ≥ 1,03 — chỉ là đáng xem tiếp, không nối vào vận hành.",
            ])),
            _sec_heading("Tường lửa nghiên cứu", "Tường lửa nghiên cứu", _ev([_ket_qua(f)], [
                "Mô tả quy trình chung: quét 27 × 27 vị trí giải cho hai họ đuôi–đuôi và đầu–đuôi, rồi chia huấn luyện / kiểm định / giữ lại theo thời gian.",
                "FDR chỉ áp trên tập huấn luyện; phép kiểm thực tế dịch vòng với thống kê cực đại kiểm soát việc dò dữ liệu trên cả họ.",
            ])),
        ]),
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
        # Đặc Biệt là đúng một trong 100 lớp: ml_predict chuẩn hoá SAU khi trộn,
        # ở MỌI mức trust — kể cả 1, khi xác suất thô cộng lại khác 100%.
        norm = ", rồi chuẩn hoá để 100 số cộng lại 100%" if mode == "de" else ""
        if trust <= 0.0:
            steps.append(f"Độ tin model_trust = 0 (không có kỹ năng thẩm định): mọi số nhận tỉ lệ nền{norm}: p = {_pct(p)}.")
        elif trust >= 1.0:
            steps.append(f"Độ tin model_trust = 1: dùng xác suất thô{norm}: p = {_pct(p)}.")
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


def tag_rows(table_html: str, ids: list[str], cols: tuple[int, ...] = ()) -> str:
    """Gắn ``data-evidence-row`` cho các ``<tr>`` trong ``<tbody>``, theo thứ tự.

    ``cols``: chỉ số cột (0 là cột đầu) dùng bằng chứng của hàng; cột khác —
    ví dụ cột hạng "#" — rơi về bằng chứng của trang. Rỗng là mọi cột.
    """
    start = table_html.find("<tbody")
    if start < 0 or not ids:
        return table_html
    head, body = table_html[:start], table_html[start:]
    queue = iter(ids)

    def put(match: re.Match[str]) -> str:
        ident = next(queue, None)
        if ident is None:
            return match.group(0)
        limit = f' data-evidence-cols="{",".join(map(str, cols))}"' if cols else ""
        return f'<tr data-evidence-row="{ident}"{limit}'

    return head + re.sub(r"<tr(?=[\s>])", put, body)


def values_block(entries: list[tuple[str, dict]]) -> str:
    """Khối JSON ``[data-app-evidence-values]`` mà ``app-evidence.js`` gộp vào danh mục."""
    if not entries:
        return ""
    text = json.dumps(dict(entries), ensure_ascii=False, separators=(",", ":"))
    text = text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return f'<script type="application/json" data-app-evidence-values>{text}</script>'
