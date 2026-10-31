from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_markdown_dashboard_builder_runs_on_repository_data(tmp_path: Path) -> None:
    # Ghi ra tệp tạm: dựng thẳng vào DASHBOARD.md của kho thì mỗi lần chạy
    # pytest là cây làm việc bẩn.
    dashboard = tmp_path / "DASHBOARD.md"
    subprocess.run(
        [
            sys.executable,
            "src/pages/build_markdown_dashboard_v3.py",
            "--output",
            str(dashboard),
        ],
        check=True,
    )

    assert dashboard.is_file()
    text = dashboard.read_text(encoding="utf-8")

    required = [
        "# ✨ VLA · TRUNG TÂM PHÂN TÍCH XSMB",
        "Giao diện cân đối · chú giải rõ ràng",
        "## 🎟️ Kết quả ngày và kỳ tiếp theo",
        "## 🔮 Khu vực xác suất",
        "## 🔥 Ma trận nhiệt tần suất 00–99",
        "## ⏳ Gan và nhịp",
        "## 🤖 AI/ML và động lực",
        "## 🧬 Markov · chuyển tiếp · phụ thuộc",
        "## 🧩 Cấu trúc và cặp số",
        "## 📆 Bảng Đặc Biệt và quan hệ có điều kiện",
        "## 🧪 Mức ý nghĩa và nghiên cứu",
        "Màu | Khoảng giá trị | Ý nghĩa",
        "Đối tượng | Giá trị | So sánh / căn cứ | Ý nghĩa | Thanh so sánh",
        "Độ nâng so với nền",
        "lịch 7 cột",
        "Đồng xuất hiện Phi",
        "Phòng chiến lược",
        "q (FDR)",
        "Kiểm toán và liên kết chi tiết",
    ]
    for marker in required:
        assert marker in text, marker

    # Heatmaps must always explain their color scale and standard analytical
    # tables must expose a dedicated interpretation column.
    assert text.count("Đầu\\Đuôi") >= 12
    assert text.count("Màu | Khoảng giá trị | Ý nghĩa") >= 12
    assert text.count("| Ý nghĩa | Thanh so sánh |") >= 20
    assert text.count("▰") >= 20
    assert text.count("🟪") >= 10

    # Prevent the previous bottom-page layout failure: the 31-column monthly
    # board is replaced by calendar-shaped 7-column tables and lag panels render.
    assert "| month_key | 01 | 02 | 03 | 04 | 05 |" not in text
    assert "Multi-lag dependency Loto\n_Chưa có dữ liệu._" not in text
    assert "Multi-lag dependency Đặc Biệt\n_Chưa có dữ liệu._" not in text

    assert "Complete Data Catalog" not in text
    assert len(text) > 70_000


def test_redirected_build_reports_the_path_it_actually_wrote(tmp_path: Path) -> None:
    """Ghi một nơi mà báo cáo một nơi khác là nói dối người gọi.

    Bản đầu của ``--output`` ghi đúng chỗ mới nhưng dòng cuối vẫn in và
    ``stat()`` đường dẫn mặc định. Hai hậu quả: lệnh in ra kích thước của một
    tệp cũ chẳng liên quan, và nếu DASHBOARD.md của kho không tồn tại thì nó
    ném FileNotFoundError SAU KHI đã ghi xong — bản dựng chuyển hướng hỏng vì
    một tệp nó không hề đụng tới.
    """
    output = tmp_path / "board.md"
    result = subprocess.run(
        [sys.executable, "src/pages/build_markdown_dashboard_v3.py", "--output", str(output)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert str(output) in result.stdout, result.stdout
    assert "DASHBOARD.md" not in result.stdout, (
        "báo cáo đường dẫn mặc định trong khi ghi ra chỗ khác"
    )


def test_the_conditional_table_puts_the_raw_rate_beside_its_baseline_in_evidence_order(tmp_path: Path) -> None:
    # Bản cũ xếp lại theo tỉ lệ thô và gắn "Có mẫu lịch sử tương đối tốt hơn" cho mọi ô ≥ 10 kỳ.
    import pandas as pd

    from pages.build_markdown_dashboard_v3 import _conditional

    path = tmp_path / "conditional.csv"
    pd.DataFrame(
        [
            {"prev_special_2d": "37", "next_loto": "52", "count": 3, "base_count": 4, "conditional_rate": 0.75,
             "baseline_rate": 0.24, "posterior_rate": 0.2401, "lift": 1.0004, "p_value": 0.04, "q_value_fdr": 1.0},
            {"prev_special_2d": "42", "next_loto": "96", "count": 30, "base_count": 60, "conditional_rate": 0.5,
             "baseline_rate": 0.24, "posterior_rate": 0.2450, "lift": 1.0208, "p_value": 1e-5, "q_value_fdr": 0.03},
        ]
    ).to_csv(path, index=False)
    text = _conditional(path)
    rows = [line for line in text.splitlines() if line.startswith("| 1 ") or line.startswith("| 2 ")]
    assert "`42` → **`96`**" in rows[0] and "Qua FDR 5%" in rows[0] and "30/60" in rows[0]
    assert "`37` → **`52`**" in rows[1] and "Chưa có bằng chứng lệch khỏi mức nền" in rows[1]
    assert "| Mức nền |" in text and "24.00%" in rows[1]
    assert text.startswith("> Xếp theo p tăng dần") and "1 ô lệch khỏi mức nền" in text
