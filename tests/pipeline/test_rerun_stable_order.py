"""Thứ tự bước để lượt hằng ngày ghi ĐÚNG thứ mà lượt chạy lại trên cùng dữ liệu sẽ ghi (11-11-2026).

Lượt chạy lại sau khi gộp PR #222 không có kỳ quay mới vẫn commit 57 tệp. Ba nhóm trong đó không phải
nhiễu mà là bản HẰNG NGÀY sai, vì một bước đọc tệp mà bước khác chỉ ghi SAU nó:

- `DASHBOARD.md` in bảng mô phỏng của kỳ đã quay (`build_fun_prediction` ghi bảng kỳ mới sau nó);
- bảng 50 cặp LOTO thiếu điểm Cầu Kèo (`pair_stats.py` chạy trước Cầu Kèo, chỉ thấy ngày neo cũ);
- trang Chất lượng và Độ tin cậy chấm 47 kỳ, rồi bước dọn ở cuối lượt xoá kỳ cũ nhất.

Phép kiểm chạy điều phối THẬT (`pipeline.main`) với bộ ghi lời gọi thay lệnh con.
"""
from __future__ import annotations

import sys

import pipeline


def _calls(monkeypatch) -> list[list[str]]:
    calls: list[list[str]] = []
    monkeypatch.setattr(pipeline, "_run", lambda argv, **options: calls.append(argv))
    monkeypatch.setattr(sys, "argv", ["pipeline.py", "--skip-sync", "--strict"])
    pipeline.main()
    return calls


def _positions(calls: list[list[str]], script: str) -> list[int]:
    """Vị trí mọi lời gọi tới tệp ``script`` (tên trần: phép kiểm không gọi trình dựng nào)."""
    found = [i for i, argv in enumerate(calls) if any(arg.endswith(f"/{script}") for arg in argv)]
    assert found, f"{script} không còn được gọi"
    return found


def test_the_markdown_dashboard_is_built_after_the_simulation_it_prints(monkeypatch) -> None:
    calls = _calls(monkeypatch)
    simulation = _positions(calls, "build_fun_prediction.py")[-1]
    assert min(_positions(calls, "build_markdown_dashboard_v3.py")) > simulation


def test_the_fifty_pair_table_is_rebuilt_after_the_last_writer_of_the_cau_keo_table(monkeypatch) -> None:
    calls = _calls(monkeypatch)
    writers = [_positions(calls, script)[-1] for script in (
        "cau_keo_ml.py", "cau_keo_domain_challenger.py")]
    assert max(_positions(calls, "cap_loto_50_stats.py")) > max(writers)


def test_artifacts_are_pruned_before_the_published_forecasts_are_graded(monkeypatch) -> None:
    calls = _calls(monkeypatch)
    pruning = _positions(calls, "cleanup_artifacts.py")
    assert len(pruning) == 1
    for grader in ("model_quality.py", "confidence_matrix.py",
                   "build_model_quality.py", "build_confidence_page.py"):
        assert pruning[0] < min(_positions(calls, grader)), grader


def test_the_model_registry_runs_after_every_writer_of_a_model_record_and_before_its_page(monkeypatch) -> None:
    """Sổ đăng ký đọc cổng của mọi mô hình vừa học: chạy trước một bộ ghi hồ sơ thì sổ mô tả kỳ hôm trước."""
    calls = _calls(monkeypatch)
    (registry,) = _positions(calls, "model_registry.py")
    for writer in ("ml_train.py", "cau_keo_ml.py", "cau_keo_domain_challenger.py", "learn_ensemble_weights.py",
                   "meta_predictor.py", "online_learning.py", "knowledge_base.py", "run_xsmb_agents.py",
                   "model_quality.py", "cleanup_artifacts.py"):
        assert max(_positions(calls, writer)) < registry, writer
    assert registry < min(_positions(calls, "build_model_quality.py"))
    # Lượt --strict phải dừng khi có hồ sơ không đọc được.
    assert "--strict" in calls[registry]


def test_the_model_registry_does_not_block_a_non_strict_run(monkeypatch) -> None:
    seen: list[tuple[list[str], dict]] = []
    monkeypatch.setattr(pipeline, "_run", lambda argv, **options: seen.append((argv, options)))
    monkeypatch.setattr(sys, "argv", ["pipeline.py", "--skip-sync"])
    pipeline.main()
    ((argv, options),) = [(a, o) for a, o in seen if any(arg.endswith("/model_registry.py") for arg in a)]
    assert "--strict" not in argv and options.get("allow_fail") is True
