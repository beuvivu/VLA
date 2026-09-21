from __future__ import annotations

"""Mười trang còn lại: ML, chất lượng mô hình, soi path, nghiên cứu, landing."""

from pathlib import Path

from vla_design.blocks import (
    card,
    dataset_fallback,
    disclaimer,
    esc,
    kpi,
    kpi_row,
    source_note,
    table,
)
from vla_design.data_access import (
    decimal_text,
    first,
    integer_text,
    number_text,
    percent_text,
    read_csv_rows,
    read_json_object,
)
from vla_design.ensemble_view import weights_card
from vla_design.shell import Crumb, Page
from vla_pages.common import PREDICTION_DISCLAIMER, latest_prediction_csv, write

BASELINE = {"loto": 0.2376572856528965, "de": 0.01}


def build_ml_top10(docs_dir: Path, data_dir: Path, *, mode: str) -> Path:
    """Mười số có xác suất mô hình cao nhất, LUÔN kèm đường cơ sở.

    Cột đường cơ sở không phải trang trí: với lô tô nó là 23,766% — nghĩa là
    một con "top 10" ở 23,9% hơn đường cơ sở đúng 0,13 điểm phần trăm. Bỏ cột
    ấy đi thì con số 23,9% trông như một phát hiện.
    """
    label = "Lô tô" if mode == "loto" else "Đặc Biệt"
    nav_key = "ml-loto" if mode == "loto" else "ml-dac-biet"
    filename = f"ml_top10_{mode}.html"
    ds = latest_prediction_csv(data_dir, mode)
    base = BASELINE[mode]
    fallback = dataset_fallback(ds, empty_message="Chưa có bảng xác suất")
    if fallback:
        content = fallback
    else:
        rows = sorted(ds.rows, key=lambda r: -float(r.get("prob") or 0))[:10]
        best = float(rows[0].get("prob") or 0) if rows else 0.0
        content = (
            kpi_row(
                (
                    kpi("Cao nhất", percent_text(best, places=3), note="xác suất mô hình", tone="info"),
                    kpi("Đường cơ sở", percent_text(base, places=3), note="không có mô hình", tone="neutral"),
                    kpi("Chênh lệch", percent_text(best - base, places=3), note="tuyệt đối", tone="neutral"),
                    kpi(
                        "Chênh tương đối",
                        decimal_text((best / base - 1) * 100 if base else 0) + "%",
                        note="so với cơ sở",
                        tone="neutral",
                    ),
                )
            )
            + card(
                f"Mười số {label} đứng đầu",
                table(
                    (
                        ("hang", "#"),
                        ("so", "Số"),
                        ("xacsuat", "Xác suất mô hình"),
                        ("coso", "Đường cơ sở"),
                        ("chenh", "Chênh lệch"),
                        ("dongthuan", "Mức đồng thuận"),
                    ),
                    [
                        (
                            index + 1,
                            esc(r.get("number_str") or number_text(r.get("number"))),
                            percent_text(r.get("prob"), places=3),
                            percent_text(base, places=3),
                            percent_text(float(r.get("prob") or 0) - base, places=3),
                            esc(r.get("agreement_tier")),
                        )
                        for index, r in enumerate(rows)
                    ],
                    caption=f"Mười số {label} có xác suất mô hình cao nhất",
                    numeric=(0, 2, 3, 4),
                ),
                note=(
                    "Cột 'Chênh lệch' là thông tin duy nhất đáng đọc ở bảng này. "
                    "Mức đồng thuận 'low' nghĩa là năm thành phần của mô hình không đồng ý với nhau."
                ),
                wide_body=True,
            )
            + source_note(ds)
        )
    page = Page(
        nav_key=nav_key,
        title=f"Top 10 {label} (ML)",
        subtitle=f"Mười số {label} có xác suất mô hình cao nhất cho kỳ tới, đặt cạnh đường cơ sở.",
        crumbs=(Crumb("Dự đoán & Mô hình"),),
        wide=True,
    )
    return write(docs_dir, filename, page, disclaimer(PREDICTION_DISCLAIMER) + content)


def build_model_quality(docs_dir: Path, data_dir: Path) -> Path:
    """Chất lượng mô hình: hiệu chuẩn, độ nhọn, phân rã Murphy, kỹ năng.

    Dựng lại safeguard đã mất cùng giao diện cũ: nếu ``covers_through`` lùi sau
    kỳ mới nhất trong kho thì trang NÓI RA. Một trang chất lượng hiện số của
    tuần trước mà không báo gì là tệ hơn không có trang.
    """
    ds = read_json_object(Path(data_dir) / "model_quality" / "report.json")
    health = read_json_object(Path(data_dir) / "health.json")
    fallback = dataset_fallback(ds, empty_message="Chưa có báo cáo chất lượng")
    if fallback:
        content = fallback
    else:
        report = first(ds)
        covers = str(report.get("covers_through") or "")
        latest = str(first(health).get("latest_date") or "")
        stale = bool(covers and latest and covers < latest)
        blocks = []
        if stale:
            blocks.append(
                disclaimer(
                    f"Báo cáo này chấm đến kỳ {covers} trong khi kho đã có tới kỳ {latest}. "
                    "Số liệu dưới đây CŨ HƠN dữ liệu — chạy lại model_quality.py trước khi tin vào nó."
                )
            )
        for mode, label in (("loto", "Lô tô"), ("de", "Đặc Biệt")):
            block = report.get("modes", {}).get(mode) or {}
            if not block:
                continue
            murphy = block.get("murphy") or {}
            skill = block.get("skill") or {}
            sharp = block.get("sharpness") or {}
            rows = [
                ("Số kỳ chấm", integer_text(block.get("days"))),
                ("Độ tin cậy (reliability)", decimal_text(murphy.get("reliability"), places=6)),
                ("Độ phân giải (resolution)", decimal_text(murphy.get("resolution"), places=6)),
                ("Độ bất định (uncertainty)", decimal_text(murphy.get("uncertainty"), places=6)),
                ("Brier trực tiếp", decimal_text(murphy.get("brier_direct"), places=6)),
                ("Tỉ lệ nền", percent_text(sharp.get("base_rate"), places=3)),
                ("Độ trải so với nền", decimal_text(sharp.get("spread_vs_base"), places=6)),
                ("Kỹ năng trung bình", decimal_text(skill.get("mean"), places=6)),
                ("Sai số chuẩn", decimal_text(skill.get("stderr"), places=6)),
                (
                    "Phân biệt được với 0",
                    "có" if skill.get("distinguishable_from_zero") else "KHÔNG",
                ),
                ("Tỉ lệ kỳ tệ hơn cơ sở", percent_text(skill.get("share_worse_than_baseline"))),
            ]
            blocks.append(
                '<div class="vla-col-6">'
                + card(
                    f"Chất lượng — {label}",
                    table(
                        (("chiso", "Chỉ số"), ("giatri", "Giá trị")),
                        rows,
                        caption=f"Các chỉ số chất lượng mô hình cho {label}",
                        numeric=(1,),
                    ),
                    note=(
                        "Phân rã Murphy: Brier = độ bất định − độ phân giải + độ tin cậy. "
                        "Độ phân giải gần 0 nghĩa là mô hình gần như không phân biệt được kỳ dễ với kỳ khó."
                    ),
                    wide_body=True,
                )
                + "</div>"
            )
        content = (
            disclaimer(
                "Trang này chấm chính mô hình của kho, không dự đoán số. "
                "Độ phân giải gần 0 nghĩa là mô hình gần như không phân biệt được "
                "kỳ dễ với kỳ khó — đó là kết quả, không phải lỗi hiển thị."
            )
            + "".join(b for b in blocks if b.startswith("<aside"))
            + kpi_row(
                (
                    kpi("Chấm đến kỳ", esc(covers or "—"), note="covers_through", tone="warning" if stale else "success"),
                    kpi("Kho có tới kỳ", esc(latest or "—"), note="latest_date", tone="neutral"),
                    kpi("Hàng Brier đã chuẩn lại", integer_text(report.get("brier_rows_rescaled")), note="do đổi định nghĩa", tone="neutral"),
                    kpi("Lược đồ báo cáo", integer_text(report.get("schema_version")), note="schema_version", tone="neutral"),
                )
            )
            + f'<div class="vla-grid">{"".join(b for b in blocks if not b.startswith("<aside"))}</div>'
            + weights_card(data_dir)
            + source_note(ds, health)
        )
    page = Page(
        nav_key="chat-luong-mo-hinh",
        title="Chất lượng mô hình",
        subtitle="Hiệu chuẩn, độ nhọn, phân rã Murphy và kỹ năng so với đường cơ sở.",
        crumbs=(Crumb("Dự đoán & Mô hình"),),
        wide=True,
    )
    return write(docs_dir, "model-quality.html", page, content)


def build_path(docs_dir: Path, data_dir: Path, *, mode: str, kind: str) -> Path:
    """Soi path: các đường đi giữa hai vị trí qua các kỳ.

    Cột ``p_mean`` LUÔN đặt cạnh đường cơ sở, vì một đường có ``p_mean``
    0,263 trên nền 0,238 là chênh 0,025 — và với hàng trăm nghìn đường được
    quét, một vài đường như thế là điều chắc chắn xảy ra kể cả khi không có
    tín hiệu nào.
    """
    label_mode = "Lô tô" if mode == "loto" else "Đặc Biệt"
    label_kind = "ổn định" if kind == "stable" else "hoạt động"
    nav_key = f"path-{'loto' if mode == 'loto' else 'dac-biet'}-{'on-dinh' if kind == 'stable' else 'hoat-dong'}"
    ds = read_csv_rows(Path(data_dir) / "path_ui" / f"paths_{mode}_{kind}.csv")
    base = BASELINE[mode]
    fallback = dataset_fallback(ds, empty_message="Chưa có đường path nào")
    if fallback:
        content = fallback
    else:
        rows = sorted(ds.rows, key=lambda r: -float(r.get("p_mean") or 0))[:200]
        content = card(
            f"Hai trăm đường {label_kind} đứng đầu",
            table(
                (
                    ("lag", "Độ trễ"),
                    ("tu", "Từ"),
                    ("den", "Đến"),
                    ("luot", "Số lượt thử"),
                    ("trung", "Số lượt trúng"),
                    ("p", "Tỉ lệ trúng"),
                    ("coso", "Đường cơ sở"),
                    ("chenh", "Chênh lệch"),
                    ("chuoi", "Chuỗi dài nhất"),
                ),
                [
                    (
                        integer_text(r.get("lag")),
                        number_text(r.get("i")),
                        number_text(r.get("j")),
                        integer_text(r.get("trials")),
                        integer_text(r.get("hits")),
                        percent_text(r.get("p_mean"), places=3),
                        percent_text(base, places=3),
                        percent_text(float(r.get("p_mean") or 0) - base, places=3),
                        integer_text(r.get("max_streak")),
                    )
                    for r in rows
                ],
                caption=f"Các đường path {label_kind} của {label_mode}",
                numeric=(0, 3, 4, 5, 6, 7, 8),
            ),
            note=(
                "Đọc cột 'Số lượt thử' TRƯỚC cột tỉ lệ. Kho quét hàng trăm nghìn đường, "
                "nên vài đường có tỉ lệ cao là điều chắc chắn xảy ra kể cả khi các kỳ hoàn toàn độc lập."
            ),
            wide_body=True,
        ) + source_note(ds)
    page = Page(
        nav_key=nav_key,
        title=f"Path {label_mode} — {label_kind}",
        subtitle=f"Các đường đi {label_kind} giữa hai vị trí qua các kỳ, kèm đường cơ sở.",
        crumbs=(Crumb("Soi path"),),
        wide=True,
    )
    return write(docs_dir, f"soi-path-{mode}-{kind}.html", page, disclaimer(PREDICTION_DISCLAIMER) + content)


def build_research(docs_dir: Path, data_dir: Path) -> Path:
    """Phòng nghiên cứu: kết quả quét cầu sau hiệu chỉnh đa giả thuyết.

    Con số quan trọng nhất trang này là ``survived_fdr``. Nó bằng 0, và đó là
    kết quả — không phải chỗ trống chờ điền.
    """
    ds = read_json_object(Path(data_dir) / "research" / "bridge_scan_summary.json")
    fallback = dataset_fallback(ds, empty_message="Chưa có kết quả quét cầu")
    if fallback:
        content = fallback
    else:
        summary = first(ds)
        modes = summary.get("modes") or {}
        cards = []
        total_hypotheses = 0
        total_survived = 0
        for mode, label in (("loto", "Lô tô"), ("de", "Đặc Biệt")):
            block = modes.get(mode) or {}
            if not block:
                continue
            total_hypotheses += int(block.get("hypotheses") or 0)
            total_survived += int(block.get("survived_fdr") or 0)
            rows = [
                ("Số giả thuyết đã quét", integer_text(block.get("hypotheses"))),
                ("Số kỳ đã chấm", integer_text(block.get("days_evaluated"))),
                ("Đường cơ sở một cửa", percent_text(block.get("baseline_single_bet"))),
                ("Kỹ năng tốt nhất trong họ", decimal_text(block.get("family_max_skill"), places=6)),
                ("Chạy ít nhất 5 kỳ, chưa sàng", integer_text(block.get("running_at_least_5_unscreened"))),
                ("SỐNG SÓT SAU FDR", integer_text(block.get("survived_fdr"))),
            ]
            cards.append(
                '<div class="vla-col-6">'
                + card(
                    f"Quét cầu — {label}",
                    table(
                        (("chiso", "Chỉ số"), ("giatri", "Giá trị")),
                        rows,
                        caption=f"Kết quả quét cầu cho {label}",
                        numeric=(1,),
                    ),
                    wide_body=True,
                )
                + "</div>"
            )
        verdict = (
            "KHÔNG cầu nào sống sót sau hiệu chỉnh đa giả thuyết."
            if total_survived == 0
            else f"{total_survived} cầu sống sót sau hiệu chỉnh."
        )
        content = (
            disclaimer(
                f"Đã quét {integer_text(total_hypotheses)} giả thuyết. {verdict} "
                "Khi quét nhiều giả thuyết như vậy, vài cái đạt ngưỡng là điều chắc chắn xảy ra "
                "ngay cả trên dữ liệu ngẫu nhiên thuần — đó chính là lý do phải hiệu chỉnh."
            )
            + kpi_row(
                (
                    kpi("Giả thuyết đã quét", integer_text(total_hypotheses), note="cả hai chế độ", tone="info"),
                    kpi("Sống sót sau FDR", integer_text(total_survived), note="kết quả, không phải chỗ trống", tone="success" if total_survived == 0 else "warning"),
                    kpi("Ngưỡng q", decimal_text(summary.get("q_value")), note="mức FDR", tone="neutral"),
                    kpi("Số kỳ trong quét", integer_text(summary.get("days")), note="cửa sổ", tone="neutral"),
                )
            )
            + f'<div class="vla-grid">{"".join(cards)}</div>'
            + source_note(ds)
        )
    page = Page(
        nav_key="phong-nghien-cuu",
        title="Phòng nghiên cứu",
        subtitle="Quét cầu quy mô lớn và hiệu chỉnh đa giả thuyết — kết quả, kể cả khi kết quả là không có gì.",
        crumbs=(Crumb("Nghiên cứu"),),
        wide=True,
    )
    return write(docs_dir, "research-lab.html", page, content)


def build_landing(docs_dir: Path, data_dir: Path, *, desktop: bool) -> Path:
    """Hai biến thể trang giới thiệu, giữ lại vì chúng là URL đã tồn tại.

    Chúng KHÔNG nằm trong sidebar — ba mục dẫn tới cùng nội dung thì không mục
    nào nhận ra được là đang mở, trái mục 5.3. Giữ tệp để liên kết cũ của
    người đọc không chết.
    """
    health = read_json_object(Path(data_dir) / "health.json")
    h = first(health)
    nav_key = "landing-desktop" if desktop else "landing"
    filename = "landing_desktop.html" if desktop else "landing.html"
    content = (
        disclaimer(PREDICTION_DISCLAIMER)
        + kpi_row(
            (
                kpi("Số kỳ trong kho", integer_text(h.get("row_count")), note="dữ liệu thật", tone="info"),
                kpi("Kỳ mới nhất", esc(h.get("latest_date") or "—"), note="đã chốt", tone="success"),
                kpi("Kỳ đầu tiên", esc(h.get("first_date") or "—"), note="lịch sử", tone="neutral"),
                kpi("Ngày thiếu", integer_text(h.get("missing_count")), note="liên tục" if not h.get("missing_count") else "có lỗ hổng", tone="success" if not h.get("missing_count") else "danger"),
            )
        )
        + card(
            "Trang giới thiệu",
            '<p>Đây là một biến thể của trang chủ, giữ lại để các liên kết đã lưu không chết. '
            'Nội dung đầy đủ nằm ở <a href="index.html">trang chủ</a>.</p>',
        )
        + source_note(health)
    )
    page = Page(
        nav_key=nav_key,
        title="Giới thiệu" + (" (máy tính)" if desktop else ""),
        subtitle="Biến thể trang chủ, giữ lại cho các liên kết cũ.",
    )
    return write(docs_dir, filename, page, content)
