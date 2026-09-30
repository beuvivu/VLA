"""Sổ nhật ký bảng mô phỏng: khoá sau giờ quay, chấm đúng/lộn/LOTO, hiện trên trang."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

import fun_draw_ledger as L
from build_fun_prediction import BLOCK_ID, inject_into_html
from xsmb_domain import FIELD_WIDTH_MAP, PRIZE_FIELDS


def _payload(target: str, special: str, loto: list[str] | None = None) -> dict:
    loto = loto or ["00"] * 26
    values = iter(loto)
    groups = [
        {
            "key": "special",
            "label": "Đặc Biệt",
            "values": [
                {
                    "field": "special",
                    "value": special,
                    "suffix": special[-2:],
                    "mode": "de",
                    "model_prob": 0.01,
                    "model_prob_percent": 1.0,
                }
            ],
        }
    ]
    sizes = [
        ("prize1", 1, 5),
        ("prize2", 2, 5),
        ("prize3", 6, 5),
        ("prize4", 4, 4),
        ("prize5", 6, 4),
        ("prize6", 3, 3),
        ("prize7", 4, 2),
    ]
    for key, count, width in sizes:
        items = []
        for _ in range(count):
            s = next(values)
            items.append(
                {
                    "field": key,
                    "value": ("0" * (width - 2)) + s,
                    "suffix": s,
                    "mode": "loto",
                    "model_prob": 0.2,
                    "model_prob_percent": 20.0,
                }
            )
        groups.append({"key": key, "label": key, "values": items})
    return {"target_date": target, "anchor_date": "2026-09-29", "groups": groups}


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text).astimezone(timezone.utc)


def _row(target: str, special: str, when: str, loto: list[str] | None = None) -> dict:
    return L.simulation_row(
        _payload(target, special, loto), None, source="t", recorded_at=_utc(when)
    )


def _xsmb(path: Path, rows: dict[str, list[str]]) -> None:
    frame = pd.DataFrame(
        [{"date": d, **dict(zip(PRIZE_FIELDS, v, strict=True))} for d, v in rows.items()]
    )
    frame.to_csv(path, index=False)


def _prizes(special: str, loto_tails: list[str]) -> list[str]:
    """27 giải: Đặc Biệt ``special`` và 26 giải còn lại có đuôi ``loto_tails``."""
    tails = iter(loto_tails)
    return [special] + [("1" * (FIELD_WIDTH_MAP[f] - 2)) + next(tails) for f in PRIZE_FIELDS[1:]]


def test_cutoff_is_ten_past_six_in_the_evening_vietnam_time() -> None:
    assert L.cutoff_utc("2026-10-01") == datetime(2026, 10, 1, 11, 10, tzinfo=timezone.utc)


def test_a_board_is_recorded_before_the_cutoff_and_the_last_one_before_it_wins() -> None:
    frame = L.empty_ledger()
    frame = L.record(
        frame, _row("2026-10-01", "11111", "2026-09-30T20:00+07:00"), _utc("2026-09-30T20:00+07:00")
    )
    frame = L.record(
        frame, _row("2026-10-01", "22222", "2026-10-01T18:09+07:00"), _utc("2026-10-01T18:09+07:00")
    )
    assert frame["special"].tolist() == ["22222"]


def test_a_board_written_after_the_cutoff_never_replaces_the_one_shown_at_draw_time() -> None:
    frame = L.empty_ledger()
    frame = L.record(
        frame, _row("2026-10-01", "11111", "2026-09-30T20:00+07:00"), _utc("2026-09-30T20:00+07:00")
    )
    frame = L.record(
        frame, _row("2026-10-01", "33333", "2026-10-01T18:10+07:00"), _utc("2026-10-01T18:10+07:00")
    )
    frame = L.record(
        frame, _row("2026-10-02", "44444", "2026-10-02T19:00+07:00"), _utc("2026-10-02T19:00+07:00")
    )
    assert frame["special"].tolist() == ["11111"]


def test_scoring_separates_exact_reversed_and_counts_loto_positions() -> None:
    frame = L.empty_ledger()
    loto = ["42"] * 3 + ["99"] * 23
    for target, special in [
        ("2026-09-28", "00142"),
        ("2026-09-29", "00124"),
        ("2026-09-30", "00144"),
    ]:
        frame = L.record(
            frame,
            _row(target, special, "2026-09-27T20:00+07:00", loto),
            _utc("2026-09-27T20:00+07:00"),
        )
    actual = _prizes("95242", ["42"] + ["07"] * 25)
    results = {"2026-09-28": actual, "2026-09-29": actual, "2026-09-30": actual}
    scored = L.score(frame, results).set_index("target_date")
    assert scored.loc["2026-09-28", ["exact", "reversed"]].tolist() == ["1", "0"]
    assert scored.loc["2026-09-29", ["exact", "reversed"]].tolist() == ["0", "1"]
    assert scored.loc["2026-09-30", ["exact", "reversed"]].tolist() == ["0", "0"]
    # Ba vị trí mô phỏng mang 42, và 42 có về; 99 không về.
    assert scored.loc["2026-09-28", "loto_hits"] == "3"
    total = L.summarize(scored.reset_index())
    assert (total["days"], total["exact"], total["reversed"]) == (3, 1, 1)
    assert abs(total["expected_exact"] - 0.03) < 1e-12


def test_a_double_number_is_never_a_reversed_hit() -> None:
    frame = L.record(
        L.empty_ledger(),
        _row("2026-09-30", "00144", "2026-09-29T20:00+07:00"),
        _utc("2026-09-29T20:00+07:00"),
    )
    scored = L.score(frame, {"2026-09-30": _prizes("12344", ["07"] * 26)})
    assert scored[["exact", "reversed"]].iloc[0].tolist() == ["1", "0"]
    assert L.summarize(scored)["expected_reversed"] == 0.0


def test_update_writes_a_ledger_that_survives_a_reread(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    _xsmb(data / "xsmb.csv", {"2026-09-30": _prizes("95242", ["07"] * 26)})
    L.update(
        data,
        _payload("2026-09-30", "27124"),
        {n: (n + 1) / 5050 for n in range(100)},
        _utc("2026-09-29T20:22+07:00"),
    )
    frame = L.read_ledger(data)
    assert frame["special"].tolist() == ["27124"]
    assert frame["reversed"].tolist() == ["1"]
    # Hạng 1 là xác suất cao nhất: 99 đứng đầu, 24 đứng thứ 76.
    assert frame["model_rank"].tolist() == ["76"]


def test_backfill_applies_the_same_cutoff_to_git_history(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "data" / "predict").mkdir(parents=True)

    def run(*args: str, **env: str) -> None:
        subprocess.run(
            ["git", "-C", str(repo), *args],
            check=True,
            capture_output=True,
            env={**os.environ, **env},
        )

    run("init", "-q")
    run("config", "user.email", "t@example.invalid")
    run("config", "user.name", "t")
    target = repo / "data" / "predict" / "fun_draw_next.json"
    for special, stamp in [
        ("11111", "2026-09-29T20:00:00+07:00"),
        ("22222", "2026-09-30T18:00:00+07:00"),
        ("33333", "2026-09-30T19:00:00+07:00"),
    ]:
        target.write_text(json.dumps(_payload("2026-09-30", special)), encoding="utf-8")
        run("add", "-A")
        run("commit", "-qm", special, GIT_COMMITTER_DATE=stamp, GIT_AUTHOR_DATE=stamp)
    data = tmp_path / "data"
    data.mkdir()
    _xsmb(data / "xsmb.csv", {"2026-09-30": _prizes("95222", ["07"] * 26)})
    frame = L.backfill_from_git(repo, data)
    assert frame["special"].tolist() == ["22222"]
    assert frame["exact"].tolist() == ["1"]


def test_the_page_shows_the_tally_and_the_latest_rows(tmp_path: Path) -> None:
    frame = L.empty_ledger()
    for target, special in [
        ("2026-09-29", "26460"),
        ("2026-09-30", "27124"),
        ("2026-10-01", "54130"),
    ]:
        frame = L.record(
            frame, _row(target, special, "2026-09-28T20:00+07:00"), _utc("2026-09-28T20:00+07:00")
        )
    frame = L.score(
        frame,
        {"2026-09-29": _prizes("05651", ["07"] * 26), "2026-09-30": _prizes("95242", ["07"] * 26)},
    )
    page = tmp_path / "index.html"
    page.write_text(
        "<!doctype html><html><head></head><body><section id='mo-phong'></section></body></html>",
        encoding="utf-8",
    )
    payload = _payload("2026-10-01", "54130")
    payload.update(method="m", disclaimer="d")
    assert inject_into_html(page, payload, frame)
    soup = BeautifulSoup(page.read_text(encoding="utf-8"), "html.parser")
    block = soup.select_one(f"#{BLOCK_ID} .fun-ledger")
    assert block is not None
    rows = [[td.get_text(strip=True) for td in tr.select("td")] for tr in block.select("tbody tr")]
    assert rows == [
        ["01/10", "54130", "—", "Chưa quay", "—"],
        ["30/09", "27124", "95242", "Trúng lộn", "0/26"],
        ["29/09", "26460", "05651", "Trượt", "0/26"],
    ]
    assert "is-hit" in block.select("tbody tr")[1]["class"]
    tally = block.select_one(".fun-ledger-tally").get_text(" ", strip=True)
    assert "2 kỳ" in tally and "trúng lộn 1 lần" in tally
