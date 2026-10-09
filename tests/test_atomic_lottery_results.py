"""Kết quả thật và nhật ký nguồn phải còn nguyên khi lần ghi mới bị ngắt."""

from __future__ import annotations

import builtins
import io
import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

import atomic_io
import lottery
from dtos import Result
from excel_export import FIELD_WIDTHS
from lottery_codes import write_code_csv


OUTPUTS = [
    f"{stem}.{extension}"
    for stem in ("xsmb", "xsmb-2-digits", "xsmb-sparse")
    for extension in ("csv", "json")
] + ["source_audit.json"]


@pytest.fixture
def draw_history(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> lottery.Lottery:
    """Hai kỳ nhỏ có đủ 27 giải, gồm các mã cần giữ số 0 đầu."""
    paths = lottery.RepoPaths(tmp_path, tmp_path / "data", tmp_path / "images")
    lot = lottery.Lottery(paths=paths)
    for day, value in ((date(2026, 10, 7), 0), (date(2026, 10, 8), 3)):
        lot._data[day] = Result(date=day, **dict.fromkeys(FIELD_WIDTHS, value))
    lot.generate_dataframes()
    lot._fetch_audit = {"2026-10-08": {"accepted": True, "note": "đã kiểm"}}
    # Workbook có phép kiểm riêng; ở đây chỉ canh bảy tệp CSV/JSON của dump.
    monkeypatch.setattr(lottery, "export_excel_outputs", lambda **kwargs: None)
    return lot


class _InterruptedWriter:
    """Ghi một phần thật xuống đĩa rồi báo lỗi, như khi đĩa đầy."""

    def __init__(self, stream):
        self.stream = stream

    def __getattr__(self, name):
        return getattr(self.stream, name)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return self.stream.__exit__(*args)

    def write(self, content):
        self.stream.write(content[: max(1, len(content) // 2)])
        self.stream.flush()
        raise OSError("đĩa đầy giữa lần ghi")


def _interrupt_target_write(monkeypatch: pytest.MonkeyPatch, target: Path) -> None:
    """Chặn cả tệp ghi thẳng lẫn descriptor của tệp tạm bên cạnh đích."""
    target_fds: set[int] = set()
    original_mkstemp = atomic_io.tempfile.mkstemp

    def mkstemp(*args, **kwargs):
        fd, name = original_mkstemp(*args, **kwargs)
        temporary = Path(name)
        if temporary.parent == target.parent and temporary.name.startswith(f".{target.name}."):
            target_fds.add(fd)
        return fd, name

    def wrap_open(original):
        def open_file(file, mode="r", *args, **kwargs):
            stream = original(file, mode, *args, **kwargs)
            selected = file in target_fds if isinstance(file, int) else Path(file) == target
            if selected and "w" in mode:
                return _InterruptedWriter(stream)
            return stream
        return open_file

    monkeypatch.setattr(atomic_io.tempfile, "mkstemp", mkstemp)
    monkeypatch.setattr(builtins, "open", wrap_open(builtins.open))
    monkeypatch.setattr(io, "open", wrap_open(io.open))


def _prepare_update(lot: lottery.Lottery) -> tuple[dict[str, bytes], set[Path]]:
    lot.dump()
    data_dir = lot._paths.data_dir
    previous = {name: (data_dir / name).read_bytes() for name in OUTPUTS}
    previous_paths = set(data_dir.iterdir())
    day = date(2026, 10, 9)
    lot._data[day] = Result(date=day, **dict.fromkeys(FIELD_WIDTHS, 9))
    lot.generate_dataframes()
    lot._fetch_audit = {day.isoformat(): {"accepted": True, "note": "kỳ mới"}}
    return previous, previous_paths


@pytest.mark.parametrize("target_name", OUTPUTS)
def test_dump_preserves_complete_previous_file_on_partial_write(
    draw_history: lottery.Lottery, monkeypatch: pytest.MonkeyPatch, target_name: str
) -> None:
    previous, previous_paths = _prepare_update(draw_history)
    target = draw_history._paths.data_dir / target_name
    _interrupt_target_write(monkeypatch, target)

    with pytest.raises(OSError, match="đĩa đầy giữa lần ghi"):
        draw_history.dump()

    assert target.read_bytes() == previous[target_name]
    assert set(target.parent.iterdir()) == previous_paths


@pytest.mark.parametrize("target_name", OUTPUTS)
def test_dump_preserves_complete_previous_file_when_replace_fails(
    draw_history: lottery.Lottery, monkeypatch: pytest.MonkeyPatch, target_name: str
) -> None:
    previous, previous_paths = _prepare_update(draw_history)
    target = draw_history._paths.data_dir / target_name
    original_replace = atomic_io.os.replace

    def fail_replace(source, destination):
        if Path(destination) == target:
            raise OSError("không thể thay tệp")
        return original_replace(source, destination)

    monkeypatch.setattr(atomic_io.os, "replace", fail_replace)
    with pytest.raises(OSError, match="không thể thay tệp"):
        draw_history.dump()

    assert target.read_bytes() == previous[target_name]
    assert set(target.parent.iterdir()) == previous_paths


def test_dump_keeps_export_bytes_schema_codes_and_internal_frames(
    draw_history: lottery.Lottery, tmp_path: Path
) -> None:
    expected_dir = tmp_path / "expected"
    expected_dir.mkdir()
    frames = {
        "xsmb": draw_history.get_raw_data().copy(deep=True),
        "xsmb-2-digits": draw_history.get_2_digits_data().copy(deep=True),
        "xsmb-sparse": draw_history.get_sparse_data().copy(deep=True),
    }
    for stem, frame in frames.items():
        write_code_csv(frame, expected_dir / f"{stem}.csv", index=False)
        frame.to_json(
            expected_dir / f"{stem}.json",
            orient="records", date_format="iso", indent=2, index=False,
        )

    draw_history.dump()
    data_dir = draw_history._paths.data_dir
    for name in OUTPUTS[:-1]:
        assert (data_dir / name).read_bytes() == (expected_dir / name).read_bytes()
    for stem, actual in zip(frames, (
        draw_history.get_raw_data(), draw_history.get_2_digits_data(),
        draw_history.get_sparse_data(),
    ), strict=True):
        pd.testing.assert_frame_equal(actual, frames[stem])

    raw = pd.read_csv(data_dir / "xsmb.csv", dtype=str)
    two = pd.read_csv(data_dir / "xsmb-2-digits.csv", dtype=str)
    for field, width in FIELD_WIDTHS.items():
        assert raw[field].tolist() == ["0" * width, "3".zfill(width)]
        assert two[field].tolist() == ["00", "03"]
    records = json.loads((data_dir / "xsmb.json").read_text(encoding="utf-8"))
    assert [record["date"] for record in records] == [
        "2026-10-07T00:00:00.000", "2026-10-08T00:00:00.000",
    ]
    assert [record["special"] for record in records] == [0, 3]
    reloaded = lottery.Lottery(paths=draw_history._paths)
    reloaded.load()
    pd.testing.assert_frame_equal(reloaded.get_raw_data(), frames["xsmb"])
    assert {path.name for path in data_dir.iterdir()} == set(OUTPUTS)


def test_dump_keeps_audit_merge_retention_and_utf8_bytes(draw_history: lottery.Lottery) -> None:
    data_dir = draw_history._paths.data_dir
    data_dir.mkdir()
    first_day = date(2026, 6, 1)
    old = {
        (first_day + timedelta(days=offset)).isoformat(): {"accepted": False, "note": "cũ"}
        for offset in range(125)
    }
    audit_path = data_dir / "source_audit.json"
    audit_path.write_text(json.dumps(old, ensure_ascii=False, indent=2), encoding="utf-8")
    merged = {**old, **draw_history._fetch_audit}
    expected = dict(sorted(merged.items())[-120:])

    draw_history.dump()

    assert audit_path.read_bytes() == json.dumps(expected, ensure_ascii=False, indent=2).encode("utf-8")
    assert len(json.loads(audit_path.read_text(encoding="utf-8"))) == 120
