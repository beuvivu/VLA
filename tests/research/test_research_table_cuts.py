"""Hai bảng nghiên cứu đầy đủ ra khỏi git; trang đọc bản cắt (phương án 3, 07-11-2026).

Hai bảng đầy đủ là `crosslag_rules.csv` (5 832 quy tắc) và `loto_nextday_given_special_long.csv`
(10 000 ô). Gần như mọi số trong chúng đổi mỗi kỳ, nên đo ngày 06-11-2026 chúng chiếm 24% phần tăng
của kho (`documentation/plans/2026-11-05-dung-luong-kho.md`).

Nay chúng vẫn được ghi ra đĩa và lên artifact của `update-data.yml`, nhưng nằm trong `.gitignore`.
Trang Phòng nghiên cứu đọc hai bản cắt mà git theo dõi. Các phép dưới đây buộc bốn điều:
- trang dựng từ bản cắt trùng trang dựng từ bảng đầy đủ;
- bản cắt giữ mọi dòng đáng xem;
- bảng đầy đủ không vào git;
- workflow vẫn lưu bảng đầy đủ.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from pages.build_research_lab import _conditional_table, _crosslag_table, build
from research import conditional_nextday, crosslag_positional_lab as crosslag

ROOT = Path(__file__).resolve().parents[2]
CROSS_DIR = Path("data/research/crosslag_positional")
CONDITIONAL_DIR = Path("data/stats/conditional")
FULL_TABLES = (CROSS_DIR / crosslag.FULL_TABLE, CONDITIONAL_DIR / conditional_nextday.LONG_TABLE)
CUT_TABLES = (CROSS_DIR / crosslag.CUT_TABLE, CONDITIONAL_DIR / conditional_nextday.CURRENT_TABLE)


def _rules(n: int, seed: int, gate: int = 0) -> pd.DataFrame:
    """Bảng quy tắc giả, đủ cột cho trang và cho bản cắt; độ nâng làm tròn để có nhiều dòng hoà."""
    rng = np.random.default_rng(seed)
    table = pd.DataFrame({
        "rule": [f"r{i:05d}" for i in range(n)],
        "operator": rng.choice(["concat", "lon", "bo", "cham", "tong"], n),
        "position_a_name": [f"a{i % 27}" for i in range(n)],
        "position_b_name": [f"b{i % 13}" for i in range(n)],
        "lag_a_days": 1,
        "lag_b_days": rng.choice([1, 2], n),
        "holdout_lift": rng.normal(1, 0.1, n).round(2),
        "validation_lift": rng.normal(1, 0.1, n).round(2),
        "train_p_value": rng.uniform(0, 1, n),
        "train_q_value_fdr": rng.uniform(0, 1, n).round(1),
        "research_gate_pass": np.arange(n) < gate,
        "production_eligible": False,
    })
    return table.sample(frac=1, random_state=seed).reset_index(drop=True)


def _long(seed: int) -> pd.DataFrame:
    """Bảng dài giả 100 × 100, làm tròn để có dòng hoà như bảng thật (cùng trials, cùng hits)."""
    rng = np.random.default_rng(seed)
    special, number = np.meshgrid(np.arange(100), np.arange(100), indexing="ij")
    hits = rng.integers(0, 20, special.size)
    trials = np.repeat(rng.integers(30, 60, 100), 100)
    p_eb = ((hits + 60 * 0.24) / (trials + 60)).round(3)
    return pd.DataFrame({
        "special": special.ravel(), "number": number.ravel(), "trials": trials, "hits": hits,
        "p_raw": hits / trials, "p_eb": p_eb, "q_value_fdr": rng.uniform(0.5, 1, special.size).round(2),
        "fdr_05": False, "prior_strength": 60.0,
    })


def test_the_crosslag_page_reads_the_same_rows_from_the_cut() -> None:
    for seed in range(5):
        full = _rules(2_000, seed)
        assert _crosslag_table(crosslag.cut_table(full)) == _crosslag_table(full), seed


def test_the_cut_keeps_every_gate_pass_and_the_strongest_training_rules() -> None:
    """Quy tắc qua cổng giữ hết, kể cả khi nhiều hơn `CUT_ROWS`; p huấn luyện nhỏ nhất cũng giữ,
    dù chúng nằm sâu trong thứ tự của trang."""
    full = _rules(2_000, seed=7, gate=crosslag.CUT_ROWS + 50)
    full.loc[full["research_gate_pass"], "holdout_lift"] = 0.5   # qua cổng nhưng đứng cuối mọi thứ khác
    cut = set(crosslag.cut_table(full)["rule"])
    assert set(full.loc[full["research_gate_pass"], "rule"]) <= cut
    strongest = full.sort_values("train_p_value", kind="stable")["rule"].head(crosslag.CUT_ROWS)
    assert set(strongest) <= cut
    assert len(cut) <= 3 * crosslag.CUT_ROWS + 50


def test_the_crosslag_writer_puts_the_page_rows_in_the_tracked_file(tmp_path: Path) -> None:
    full = _rules(800, seed=3)
    out = tmp_path / "data" / CROSS_DIR.relative_to("data")
    full_path, cut_path, report_path = crosslag.write_outputs(full, {"hypotheses": len(full)}, out)
    assert cut_path.name == crosslag.CUT_TABLE
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["cut_rows"] == len(pd.read_csv(cut_path)) < len(full)
    full_path.unlink()   # bản checkout không có bảng đầy đủ: trang phải dựng từ tệp git theo dõi
    page = build(tmp_path / "data", tmp_path / "docs").read_text(encoding="utf-8")
    assert _crosslag_table(full) in page


def test_the_conditional_page_reads_the_same_rows_from_the_current_cut(tmp_path: Path) -> None:
    """Trang chỉ hiện trạng thái Đặc Biệt hiện tại; bản cắt của trạng thái ấy cho đúng 10 dòng ấy."""
    long_df = _long(seed=11)
    for special in (0, 7, 77, 99):
        cut = conditional_nextday.current_special_rows(long_df, special, 20)
        assert _conditional_table(cut, f"{special:02d}") == _conditional_table(long_df, f"{special:02d}")
    out = tmp_path / "data" / CONDITIONAL_DIR.relative_to("data")
    written = conditional_nextday.write_tables(long_df, out_dir=out, anchor_date="2026-11-06",
                                               current_special=77, top=20, prior_learned=False)
    (long_path,) = [path for path in written if path.name == conditional_nextday.LONG_TABLE]
    long_path.unlink()   # bản checkout không có bảng dài: trang phải dựng từ tệp git theo dõi
    page = build(tmp_path / "data", tmp_path / "docs").read_text(encoding="utf-8")
    assert _conditional_table(long_df, "77") in page


def test_the_full_tables_stay_out_of_git_and_the_cuts_stay_in() -> None:
    def git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=False)

    for path in FULL_TABLES:
        assert git("check-ignore", "-q", str(path)).returncode == 0, f"{path} phải nằm trong .gitignore"
        assert git("ls-files", "--error-unmatch", str(path)).returncode != 0, f"{path} vẫn được git theo dõi"
    for path in CUT_TABLES:
        assert git("check-ignore", "-q", str(path)).returncode != 0, f"{path} không được bị bỏ qua"
        assert git("ls-files", "--error-unmatch", str(path)).returncode == 0, f"{path} phải được git theo dõi"


def test_the_pipeline_run_uploads_both_full_tables() -> None:
    workflow = yaml.safe_load((ROOT / ".github/workflows/update-data.yml").read_text(encoding="utf-8"))
    steps = workflow["jobs"]["update"]["steps"]
    pipeline = next(i for i, step in enumerate(steps) if "src/pipeline.py" in step.get("run", ""))
    uploads = [step for step in steps[pipeline + 1:]
               if str(step.get("uses", "")).startswith("actions/upload-artifact@")]
    assert len(uploads) == 1
    (upload,) = uploads
    assert upload.get("if") == "always()"
    assert set(upload["with"]["path"].split()) == {str(path) for path in FULL_TABLES}
    # Bước nghiên cứu được phép hỏng: thiếu tệp không được làm đỏ lượt chốt kết quả.
    assert upload["with"]["if-no-files-found"] == "ignore"
