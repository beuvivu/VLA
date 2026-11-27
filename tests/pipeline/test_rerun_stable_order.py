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
    calls = _calls(monkeypatch)
    (registry,) = _positions(calls, "model_registry.py")
    for writer in ("ml_train.py", "cau_keo_ml.py", "cau_keo_domain_challenger.py", "learn_ensemble_weights.py",
                   "meta_predictor.py", "online_learning.py", "knowledge_base.py", "run_xsmb_agents.py",
                   "model_quality.py", "cleanup_artifacts.py"):
        assert max(_positions(calls, writer)) < registry, writer
    assert registry < min(_positions(calls, "build_model_quality.py"))
    assert "--strict" in calls[registry]


def test_the_model_registry_does_not_block_a_non_strict_run(monkeypatch) -> None:
    seen: list[tuple[list[str], dict]] = []
    monkeypatch.setattr(pipeline, "_run", lambda argv, **options: seen.append((argv, options)))
    monkeypatch.setattr(sys, "argv", ["pipeline.py", "--skip-sync"])
    pipeline.main()
    ((argv, options),) = [(a, o) for a, o in seen if any(arg.endswith("/model_registry.py") for arg in a)]
    assert "--strict" not in argv and options.get("allow_fail") is True
