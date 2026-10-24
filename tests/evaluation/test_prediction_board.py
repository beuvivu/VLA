"""Sổ phỏng đoán trong ngày (``src/evaluation/prediction_board.py``) cho bảng đối chiếu trang Live."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

from evaluation import prediction_board as pb
from evaluation.fun_draw_ledger import cutoff_utc
from core.xsmb_domain import LOTO_BASELINE_RATE

ROOT = Path(__file__).resolve().parents[2]
TARGET = "2026-10-22"  # thứ Năm: weekday() = 3
BEFORE = datetime(2026, 10, 21, 13, 0, tzinfo=UTC)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _ranked_csv(rows: list[tuple[str, float]], date: str | None = None) -> str:
    head = ("predict_for_date," if date else "") + "number,prob\n"
    return head + "".join((f"{date}," if date else "") + f"{n},{p}\n" for n, p in rows)


def _data(tmp_path: Path, target: str = TARGET) -> Path:
    """Đủ mọi nguồn của kỳ ``target``, mỗi nguồn đúng khuôn tệp thật của kho."""
    data = tmp_path / "data"
    loto = [("05", 0.24), ("75", 0.238)]
    de = [("07", 0.0104), ("54", 0.0103)]
    for mode, rows in (("loto", loto), ("de", de)):
        _write(data / "predict" / f"predict_next_{mode}_top10_{target}.csv", _ranked_csv(rows))
        _write(data / "ai_ml" / "daily" / f"cau_keo_{mode}_top10_{target}.csv", _ranked_csv(rows, target))
        _write(data / "ml" / f"predict_next_{mode}_ml_top10.csv", _ranked_csv(rows, target))
        # Soi đường mang ngày DỮ LIỆU (kỳ trước), không phải ngày quay.
        anchor = (date.fromisoformat(target) - timedelta(days=1)).isoformat()
        _write(data / "path_ui" / f"path_manifest_{mode}.json", json.dumps({"anchor_date": anchor}))
        for kind in ("active", "stable"):
            _write(data / "path_ui" / f"predict_next_{mode}_{kind}_{anchor}.csv", _ranked_csv(rows))
        base = LOTO_BASELINE_RATE if mode == "loto" else 0.01
        vector = "number,prob\n" + "".join(f"{n:02d},{base}\n" for n in range(100))
        _write(data / "predict" / f"predict_next_{mode}_all_{target}.csv", vector)
    _write(data / "multi_hit" / "vip.json", json.dumps({
        "target_date": target,
        "picks": [{"number": "18", "probability": 0.033}],
        "pairs": {"picks": [{"pair": ["34", "35"]}]},
    }))
    _write(data / "agents" / "report.json", json.dumps({"target_date": target, "modes": {
        m: {"candidate_top5": [{"number": "75", "candidate_probability": 0.24 if m == "loto" else 0.0123}]}
        for m in ("de", "loto")}}))
    _write(data / "position_bridges" / "latest.json", json.dumps({"target_date": target, "modes": {
        "lo": {"nhay": 1, "db": False, "best": [{"numbers": ["29", "92"], "streak": 10}]},
        "nhay2": {"nhay": 2, "db": False, "best": [{"numbers": ["66"], "shadow": "11", "streak": 3}]},
        "db": {"nhay": 1, "db": True, "best": [{"numbers": ["49", "94"], "streak": 1}]},
    }}))
    rules = {key: {"kind": kind, "weekday": weekday, "default_weekday": 3 if weekday else None,
                   "groups": [{"key": group, "bridges": 4}]}
             for key, kind, weekday, group in (
                 ("loto", "loto", False, "29,92"), ("hai-nhay", "hai-nhay", False, "05,50"),
                 ("bach-thu", "bach-thu", False, "07,70"), ("loto-theo-thu", "loto", True, "67,76"),
                 ("dac-biet", "dac-biet", False, "46,64"), ("dac-biet-theo-thu", "dac-biet", True, "78,87"),
                 ("bo-so", "bo-so", False, "03,08,30,35,53,58,80,85"))}
    _write(data / "bridge_pages" / "latest.json", json.dumps({"target_date": target, "rules": rules}))
    _write(data / "predict" / "fun_draw_next.json", json.dumps({"target_date": target, "rows": [
        {"suffix": "34", "mode": "de", "model_prob": 0.0099},
        {"suffix": "6", "mode": "loto", "model_prob": 0.237},
    ]}))
    return data


def _lists(board: dict) -> dict[str, dict]:
    return {entry["id"]: entry for entry in board["lists"]}


def test_every_published_source_of_the_day_is_on_the_board(tmp_path: Path) -> None:
    board = pb.build_board(_data(tmp_path), TARGET, now=BEFORE)
    assert board["missing"] == []
    assert [entry["id"] for entry in board["lists"]] == [source[0] for source in pb.SOURCES]
    lists = _lists(board)
    assert lists["ensemble-loto"]["items"][0] == {
        "label": "05", "rule": {"on": "loto", "numbers": ["05"], "need": 1}, "prob": 0.24,
        "base": pytest.approx(LOTO_BASELINE_RATE)}
    assert lists["cau-keo-de"]["items"][0]["rule"] == {"on": "special", "numbers": ["07"]}
    assert lists["vip"]["items"][0]["rule"]["need"] == 2
    assert lists["xien"]["items"][0]["rule"] == {"on": "loto", "numbers": ["34", "35"], "all": True}
    # Cầu lộn cộng gộp nháy hai chiều; số bóng của số kép chỉ hiện kèm, không tính.
    assert lists["best-lo"]["items"][0]["rule"] == {"on": "loto", "numbers": ["29", "92"], "need": 1}
    assert lists["best-nhay2"]["items"][0]["rule"] == {"on": "loto", "numbers": ["66"], "need": 2}
    assert lists["best-db"]["items"][0]["rule"] == {"on": "special", "numbers": ["49", "94"]}
    assert lists["bridge-hai-nhay"]["items"][0]["rule"]["need"] == 2
    assert lists["bridge-dac-biet"]["items"][0]["rule"] == {"on": "special_digit", "digits": [4, 6]}
    assert lists["bridge-bo-so"]["items"][0]["rule"]["numbers"] == ["03", "08", "30", "35", "53", "58", "80", "85"]
    fun = lists["fun-draw"]["items"]
    assert [item["rule"]["on"] for item in fun] == ["special", "loto"]
    assert fun[1]["label"] == "06", "số 0 đứng đầu phải giữ"
    assert len(board["vectors"]["loto"]) == len(board["vectors"]["de"]) == 100


def test_fair_draw_baselines_match_the_repository_constants() -> None:
    """Mốc chọn bừa là xác suất CHÍNH XÁC của đúng sự kiện; đối chiếu với số đã có của kho."""
    vip = json.loads((ROOT / "data" / "multi_hit" / "vip.json").read_text(encoding="utf-8"))
    assert pb.base_probability({"on": "loto", "numbers": ["18"], "need": 1}) == pytest.approx(LOTO_BASELINE_RATE)
    assert pb.base_probability({"on": "loto", "numbers": ["18"], "need": 2}) == pytest.approx(vip["base_theory"])
    assert pb.base_probability({"on": "loto", "numbers": ["34", "35"], "all": True}) == pytest.approx(
        vip["pairs"]["base_theory"])
    assert pb.base_probability({"on": "loto", "numbers": ["29", "92"], "need": 1}) == pytest.approx(1 - 0.98**27)
    assert pb.base_probability({"on": "special", "numbers": ["49", "94"]}) == pytest.approx(0.02)
    assert pb.base_probability({"on": "special_digit", "digits": [4, 6]}) == pytest.approx(1 - 0.8**2)


@pytest.mark.parametrize("ids,break_source", [
    (("ml-de", "ml-loto"), lambda d: (d / "ml" / "predict_next_de_ml_top10.csv").write_text(
        _ranked_csv([("07", 0.01)], "2026-10-21"), encoding="utf-8")),
    (("vip", "xien"), lambda d: (d / "multi_hit" / "vip.json").write_text(
        json.dumps({"target_date": "2026-10-21", "picks": [{"number": "18"}]}), encoding="utf-8")),
    (("path-loto-active",), lambda d: (d / "path_ui" / "predict_next_loto_active_2026-10-21.csv").unlink()),
    # Tệp soi đường mang ngày trùng kỳ đích là dự báo cho kỳ SAU kỳ đích, dù tệp có đủ.
    (("path-de-active", "path-de-stable"), lambda d: (
        (d / "path_ui" / "path_manifest_de.json").write_text(json.dumps({"anchor_date": TARGET}), encoding="utf-8"),
        (d / "path_ui" / f"predict_next_de_active_{TARGET}.csv").write_text(
            _ranked_csv([("99", 0.0101)]), encoding="utf-8"),
    )),
])
def test_a_source_that_belongs_to_another_draw_is_left_out(tmp_path: Path, ids, break_source) -> None:
    """Tệp không ghi ngày bị ghi đè cho kỳ sau: đặt nó cạnh kết quả là chấm danh sách của kỳ khác."""
    data = _data(tmp_path)
    break_source(data)
    board = pb.build_board(data, TARGET, now=BEFORE)
    missing = {entry["id"] for entry in board["missing"]}
    assert ids[0] in missing
    assert ids[0] not in _lists(board)


def test_weekday_bridges_must_be_for_the_weekday_of_the_draw(tmp_path: Path) -> None:
    """Sổ ghi đúng kỳ thứ Sáu nhưng bảng theo thứ dựng cho thứ Năm: hai trang theo thứ bị bỏ."""
    friday = "2026-10-23"
    board = pb.build_board(_data(tmp_path, friday), friday, now=BEFORE)
    missing = {entry["id"]: entry["reason"] for entry in board["missing"]}
    assert set(missing) == {"bridge-loto-theo-thu", "bridge-dac-biet-theo-thu"}
    assert all("thứ" in reason for reason in missing.values())
    assert "bridge-loto" in _lists(board), "bảng không theo thứ vẫn giữ"


def test_the_board_freezes_at_ten_past_six_on_the_draw_day(tmp_path: Path) -> None:
    data = _data(tmp_path)
    lock = cutoff_utc(TARGET)
    path = pb.write_board(data, TARGET, now=lock - timedelta(minutes=1))
    assert path is not None and json.loads(path.read_text())["locks_at"] == f"{TARGET}T18:10+07:00"
    written = path.read_bytes()
    (data / "ml" / "predict_next_loto_ml_top10.csv").write_text(
        _ranked_csv([("99", 0.3)], TARGET), encoding="utf-8")
    assert pb.write_board(data, TARGET, now=lock) is None
    assert path.read_bytes() == written, "sau giờ khoá sổ không được đổi"
    path.unlink()
    assert pb.write_board(data, TARGET, now=lock + timedelta(hours=1)) is None
    assert not path.exists(), "sổ dựng khi đã quay không còn là phỏng đoán trước kết quả"


def test_the_board_holds_no_private_token(tmp_path: Path) -> None:
    """Trang tải sổ lúc chạy: luật riêng tư của trang áp lên cả nội dung sổ."""
    from privacy_helpers import LEAK_TOKENS

    text = json.dumps(pb.build_board(_data(tmp_path), TARGET, now=BEFORE), ensure_ascii=False)
    assert not [token for token in LEAK_TOKENS if token in text]


def test_the_pipeline_builds_the_board_after_every_page_it_reads() -> None:
    text = (ROOT / "src" / "pipeline.py").read_text(encoding="utf-8")
    board = text.index('_py("src/evaluation/prediction_board.py")')
    for builder in ("pages/build_fun_prediction.py", "pages/build_bridge_pages.py",
                    "pages/build_position_bridges.py", "pages/build_multi_hit_page.py",
                    "forecast/xsmb_agents/run_xsmb_agents.py", "ml/cau_keo_daily_top.py"):
        assert text.index(f'_py("src/{builder}"') < board, builder


def test_the_live_page_loads_the_scorecard_and_feeds_it_every_snapshot() -> None:
    page = (ROOT / "docs" / "live.html").read_text(encoding="utf-8")
    assert 'id="live-scorecard"' in page and 'id="live-scorecard-table"' in page
    assert page.index("assets/live-predictions.js") < page.index("assets/live-scorecard.js")
    assert page.index('id="live-predictions"') < page.index('id="live-scorecard"'), "bảng nằm dưới khối dự đoán"
    poll = page.index("window.LivePredictions.loadForDraw(data.draw_date, status);")
    assert page.index("window.LiveScorecard.update(data);") > poll
    assert "assets/live-scorecard.css" in page


def test_backfill_takes_the_last_commit_before_the_lock_and_never_overwrites(tmp_path: Path) -> None:
    """Dựng lại một kỳ đã khoá từ git: đúng bản người đọc thấy trước 18:10, không phải bản sau."""
    import subprocess

    repo = tmp_path / "repo"
    data = _data(repo)
    lock = cutoff_utc(TARGET)

    def commit(message: str, when: datetime) -> str:
        env = {"GIT_AUTHOR_DATE": when.isoformat(), "GIT_COMMITTER_DATE": when.isoformat(),
               "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
               "GIT_COMMITTER_EMAIL": "t@t", "PATH": "/usr/bin:/bin:/usr/local/bin"}
        subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True, env=env)
        subprocess.run(["git", "-C", str(repo), "commit", "-qm", message], check=True, env=env)
        return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], check=True, env=env,
                              capture_output=True, text=True).stdout.strip()

    subprocess.run(["git", "init", "-q", str(repo)], check=True)
    before = commit("trước giờ khoá", lock - timedelta(hours=2))
    (data / "ml" / "predict_next_loto_ml_top10.csv").write_text(
        _ranked_csv([("99", 0.3)], TARGET), encoding="utf-8")
    commit("sau giờ khoá", lock + timedelta(minutes=5))

    out = tmp_path / "out"
    path = pb.backfill_from_git(repo, out, TARGET)
    board = json.loads(path.read_text(encoding="utf-8"))
    assert board["backfilled_from"] == before[:12]
    assert [item["label"] for item in _lists(board)["ml-loto"]["items"]] == ["05", "75"]
    assert not board["missing"], "mọi nguồn, kể cả soi đường theo ngày dữ liệu, phải lấy lại được"
    assert pb.backfill_from_git(repo, out, TARGET) is None, "không đè sổ đã có"
