from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from build_fun_prediction import (
    BLOCK_ID,
    STYLE_ID,
    build_fun_draw,
    inject_into_html,
    load_prediction_inputs,
    write_artifacts,
)


def _write_prediction_fixture(root: Path) -> None:
    pred = root / "predict"
    pred.mkdir(parents=True)
    numbers = np.arange(100)
    loto_prob = np.linspace(0.10, 0.30, 100)
    de_prob = np.linspace(0.005, 0.015, 100)
    de_prob = de_prob / de_prob.sum()

    pd.DataFrame({"number": numbers, "prob": loto_prob}).to_csv(
        pred / "predict_next_loto_all_2026-09-02.csv", index=False
    )
    pd.DataFrame({"number": numbers, "prob": de_prob}).to_csv(
        pred / "predict_next_de_all_2026-09-02.csv", index=False
    )

    base = {"anchor_date": "2026-09-01", "target_date": "2026-09-02"}
    (pred / "picks_loto.json").write_text(
        json.dumps({**base, "meta": {"active": True, "trust": 0.15}}),
        encoding="utf-8",
    )
    (pred / "picks_de.json").write_text(
        json.dumps({**base, "meta": {"active": False, "trust": 0.0}}),
        encoding="utf-8",
    )


def test_fun_draw_is_deterministic_and_has_complete_prize_structure(tmp_path: Path) -> None:
    data = tmp_path / "data"
    _write_prediction_fixture(data)
    inputs = load_prediction_inputs(data)

    a = build_fun_draw(inputs)
    b = build_fun_draw(inputs)
    assert a == b
    assert a["anchor_date"] == "2026-09-01"
    assert a["target_date"] == "2026-09-02"
    assert len(a["groups"]) == 8
    assert len(a["rows"]) == 27

    widths = {
        "special": 5,
        "prize1": 5,
        "prize2": 5,
        "prize3": 5,
        "prize4": 4,
        "prize5": 4,
        "prize6": 3,
        "prize7": 2,
    }
    for group in a["groups"]:
        for item in group["values"]:
            assert len(item["value"]) == widths[group["key"]]
            assert item["value"][-2:] == item["suffix"]
            assert 0.0 <= item["model_prob"] <= 1.0

    special = a["groups"][0]["values"][0]
    assert special["mode"] == "de"
    assert all(row["mode"] == "loto" for row in a["rows"][1:])
    assert a["top_loto"][0]["number"] == "99"
    assert a["top_de"][0]["number"] == "99"


def test_fun_draw_seed_changes_when_target_snapshot_changes(tmp_path: Path) -> None:
    data = tmp_path / "data"
    _write_prediction_fixture(data)
    inputs = load_prediction_inputs(data)
    changed = replace(inputs, target_date="2026-09-03")
    assert build_fun_draw(inputs)["seed"] != build_fun_draw(changed)["seed"]


def test_fun_draw_seed_changes_when_probability_snapshot_changes(tmp_path: Path) -> None:
    data = tmp_path / "data"
    _write_prediction_fixture(data)
    inputs = load_prediction_inputs(data)
    changed_loto = inputs.loto.copy()
    changed_loto.loc[0, "prob"] += 0.001
    changed = replace(inputs, loto=changed_loto)
    assert build_fun_draw(inputs)["seed"] != build_fun_draw(changed)["seed"]


def test_artifact_write_replaces_both_snapshots_without_partial_files(tmp_path: Path) -> None:
    data = tmp_path / "data"
    _write_prediction_fixture(data)
    inputs = load_prediction_inputs(data)
    first = build_fun_draw(inputs)
    write_artifacts(first, data)

    second = replace(inputs, target_date="2026-09-03")
    second_payload = build_fun_draw(second)
    json_path, csv_path = write_artifacts(second_payload, data)
    assert json.loads(json_path.read_text(encoding="utf-8"))["target_date"] == "2026-09-03"
    csv = pd.read_csv(csv_path, dtype={"value": str})
    assert csv.iloc[0]["value"] == second_payload["rows"][0]["value"]
    assert not list((data / "predict").glob(".fun-draw-*"))


def test_artifacts_and_html_injection_are_idempotent(tmp_path: Path) -> None:
    data = tmp_path / "data"
    docs = tmp_path / "docs"
    docs.mkdir()
    _write_prediction_fixture(data)
    payload = build_fun_draw(load_prediction_inputs(data))

    json_path, csv_path = write_artifacts(payload, data)
    assert json_path.is_file()
    assert csv_path.is_file()
    assert len(pd.read_csv(csv_path)) == 27

    page = docs / "index.html"
    page.write_text(
        "<!doctype html><html><head><style>body{}</style></head><body>"
        "<section id='ket-qua' class='section card'><h3>Kết quả thực</h3></section>"
        "</body></html>",
        encoding="utf-8",
    )

    assert inject_into_html(page, payload)
    assert inject_into_html(page, payload)
    text = page.read_text(encoding="utf-8")
    assert text.count(f'id="{BLOCK_ID}"') == 1
    assert text.count(f'id="{STYLE_ID}"') == 1
    assert "Dự đoán vui" in text
    assert "Không phải kết quả thật" in text
    assert "Lô tô ngày mai" in text
    assert "Đặc biệt ngày mai" in text
