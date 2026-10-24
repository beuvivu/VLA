"""Bố cục ``data/`` sau khi gom thư mục dẫn xuất theo gói sinh ra chúng (24-10-2026).

Bảng chuyển là ``core.paths.DATA_MOVES`` (tên cũ → ``<nhóm>/<tên>``). Gốc ``data/`` chỉ còn
sổ chuẩn, tệp có người đọc từ bên ngoài kho bằng địa chỉ cố định, và thư mục đã mang tên gói.

Đường dẫn cũ hỏng LẶNG LẼ: phần lớn bước pipeline coi tệp vắng là "chưa có dữ liệu" và đi
tiếp, nên một chỗ còn ghi ``data_dir / "predict"`` chỉ làm trang thiếu một khối. Trang Live đọc
sổ phỏng đoán bằng đường dẫn mã hoá base64 (luật riêng tư cấm viết thẳng), nên phép thay chuỗi
không thấy nó — luật dưới đây giải mã trước khi soi.
"""

from __future__ import annotations

import ast
import base64
import binascii
import re
import subprocess
from pathlib import Path

from core.paths import DATA_MOVES, legacy_data_path

ROOT = Path(__file__).resolve().parents[2]
#: Nhóm chức năng dưới ``data/``: trùng tên gói ``src/`` sinh ra dữ liệu ấy.
GROUPS = {rel.split("/")[0] for rel in DATA_MOVES.values()}
#: Thư mục ở gốc ``data/`` không thuộc nhóm nào, kèm lý do.
ROOT_DIRS = {
    "ai_ml": "trang Live đọc ai_ml/daily bằng địa chỉ thô cố định",
    "ensemble": "đã mang tên gói ensemble",
    "ml": "đã mang tên gói ml",
    "excel": "bản xuất Excel của sổ chuẩn",
    "regions": "sổ chuẩn XSMT/XSMN",
    "vietlott": "lưu trữ sqlite cũ, không còn được ghi",
}
#: Tệp được nhắc tên cũ có chủ ý.
EXEMPT = {
    "tests/privacy_helpers.py": "vẫn chặn tiền tố cũ cho bản sao còn sót",
    "tests/repo/test_data_layout.py": "mẫu dựng sẵn của chính luật",
}
#: Kiểm kê đóng băng ở ngày lập; ghi đường dẫn của thời điểm ấy.
FROZEN_SNAPSHOTS = {"documentation/qa/2026-10-09-python-dependencies.json"}
_NAMES = "|".join(sorted(DATA_MOVES, key=len, reverse=True))
_RETIRED = re.compile(rf"(?<![\w/.-])data/({_NAMES})(?![\w-])")
_B64 = re.compile(r"(?<![A-Za-z0-9+/])[A-Za-z0-9+/]{8,}={0,2}(?![A-Za-z0-9+/=])")
#: Vế trái của phép ghép mà KHÔNG phải thư mục dữ liệu (``documentation/history``, ``scripts/reference``).
_NOT_DATA_LEFT = re.compile(r"documentation|scripts|\bsrc\b|tests|vietlott|docs", re.I)
#: Hằng số đường dẫn: tên kết thúc bằng một trong các đuôi này.
_PATH_CONSTANT = re.compile(r"(?:DIR|OUT|LEDGER|PATH|ROOT)$")


def _decoded(text: str) -> list[str]:
    """Chuỗi base64 trong ``text`` giải được thành chữ UTF-8."""
    out = []
    for match in _B64.finditer(text):
        token = match.group(0)
        if len(token) % 4:
            continue
        try:
            out.append(base64.b64decode(token, validate=True).decode("utf-8"))
        except (binascii.Error, UnicodeDecodeError):
            continue
    return out


def retired_mentions(text: str) -> list[str]:
    """``data/<tên cũ>`` viết thẳng hoặc giấu trong base64."""
    found = [m.group(0) for m in _RETIRED.finditer(text)]
    for plain in _decoded(text):
        found += [f"base64:{m.group(0)}" for m in _RETIRED.finditer(plain)]
    return found


def missing_encoded_paths(text: str, root: Path) -> list[str]:
    """Đường dẫn ``data/…`` giấu trong base64 mà kho không có."""
    return [plain for plain in _decoded(text) if plain.startswith("data/") and not (root / plain).exists()]


def _head(value: object) -> str | None:
    return value.split("/")[0] if isinstance(value, str) else None


def retired_joins(source: str) -> list[str]:
    """Đường dẫn tương đối với ``data/`` còn bắt đầu bằng tên cũ.

    Ba dạng: ``x / "predict"`` (vế trái chưa có nhóm và không phải thư mục khác của kho),
    ``Path("predict")`` và hằng số đường dẫn ``OUT_DIR = "predict"``.
    """
    bad = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div) and isinstance(node.right, ast.Constant):
            head = _head(node.right.value)
            left = ast.get_source_segment(source, node.left) or ""
            grouped = head in DATA_MOVES and re.search(rf"[\"']{DATA_MOVES[head].split('/')[0]}[\"']\)?\s*$", left)
            if head in DATA_MOVES and not grouped and not _NOT_DATA_LEFT.search(left):
                bad.append(f"{node.lineno}: {left} / {node.right.value!r}")
        elif isinstance(node, ast.Call) and getattr(node.func, "id", None) == "Path" and node.args \
                and isinstance(node.args[0], ast.Constant) and _head(node.args[0].value) in DATA_MOVES:
            bad.append(f"{node.lineno}: Path({node.args[0].value!r})")
        elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Constant) \
                and _head(node.value.value) in DATA_MOVES \
                and any(isinstance(t, ast.Name) and _PATH_CONSTANT.search(t.id) for t in node.targets):
            bad.append(f"{node.lineno}: {node.value.value!r}")
    return bad


def data_root_offenders(top_level: set[str]) -> list[str]:
    """Thư mục ở gốc ``data/`` không phải nhóm, không có lý do, hoặc là tên đã chuyển."""
    return sorted(
        f"{name}: đã chuyển tới data/{DATA_MOVES[name]}" if name in DATA_MOVES else f"{name}: chưa thuộc nhóm nào"
        for name in top_level
        if name not in GROUPS and name not in ROOT_DIRS
    )


def _tracked(root: Path) -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True, text=True, check=True)
    return out.stdout.split()


def _text_files(root: Path) -> list[tuple[str, str]]:
    out = []
    for rel in _tracked(root):
        if rel.startswith(("vietlott/", "data/")) or rel in FROZEN_SNAPSHOTS or rel in EXEMPT:
            continue
        try:
            out.append((rel, (root / rel).read_text(encoding="utf-8")))
        except (UnicodeDecodeError, OSError):
            continue
    return out


def test_the_data_root_holds_only_groups_and_declared_directories() -> None:
    tracked = _tracked(ROOT)
    top = {rel.split("/")[1] for rel in tracked if rel.startswith("data/") and rel.count("/") >= 2}
    assert not data_root_offenders(top)
    empty = [rel for rel in DATA_MOVES.values() if not any(p.startswith(f"data/{rel}/") for p in tracked)]
    assert not empty, f"bảng chuyển trỏ thư mục không có tệp nào: {empty}"


def test_nothing_in_the_repository_names_a_retired_data_directory() -> None:
    files = _text_files(ROOT)
    assert len(files) > 500, "tập quét rỗng thì phép kiểm không thể đỏ"
    bad = [f"{rel}: {hit}" for rel, text in files for hit in retired_mentions(text)]
    assert not bad, "\n".join(bad)


def test_every_encoded_data_path_points_at_something_that_exists() -> None:
    bad = [f"{rel}: {path}" for rel, text in _text_files(ROOT) for path in missing_encoded_paths(text, ROOT)]
    assert not bad, "\n".join(bad)


def test_no_python_joins_a_retired_name_onto_the_data_directory() -> None:
    files = [(rel, text) for rel, text in _text_files(ROOT) if rel.endswith(".py")]
    assert len(files) > 300
    bad = [f"{rel}:{hit}" for rel, text in files for hit in retired_joins(text)]
    assert not bad, "\n".join(bad)


def test_legacy_paths_map_each_moved_file_back_to_where_old_commits_keep_it() -> None:
    assert legacy_data_path("forecast/predict/fun_draw_next.json") == "predict/fun_draw_next.json"
    assert legacy_data_path("soi_cau/path_ui") == "path_ui"
    assert legacy_data_path("ml/predict_next_de_ml_all.csv") is None, "thư mục không chuyển"
    assert legacy_data_path("stats/predict/x.csv") is None, "sai nhóm thì không phải chỗ chuyển"
    assert legacy_data_path("xsmb.csv") is None
    assert set(DATA_MOVES) & set(ROOT_DIRS) == set()


def test_the_layout_rules_catch_each_retired_spelling(tmp_path: Path) -> None:
    old = "data/" + "predict"
    assert retired_mentions(f"đọc `{old}/picks_de.json` mỗi ngày") == [f"{old}"]
    assert retired_mentions(f'path = "{old}"') == [old]
    assert not retired_mentions("data/forecast/predict/picks_de.json, data/predictions_today.json, data/ml/x")
    assert not retired_mentions("vietlott/data/forecast/x, data/history_extra")
    encoded = base64.b64encode(("data/" + "prediction_board/").encode()).decode()
    assert retired_mentions(f"var E = {{ p: '{encoded}' }};") == ["base64:data/prediction_board"]

    (tmp_path / "data" / "evaluation" / "prediction_board").mkdir(parents=True)
    good = base64.b64encode(b"data/evaluation/prediction_board/").decode()
    assert not missing_encoded_paths(f"p: '{good}'", tmp_path)
    assert missing_encoded_paths(f"p: '{encoded}'", tmp_path) == ["data/prediction_board/"]

    sample = "\n".join([
        'a = data_dir / "predict" / "x.csv"',
        'b = data_dir / "forecast" / "predict"',
        'c = ROOT / "scripts" / "reference"',
        'OUT = Path("confidence")',
        'OUT_DIR = "multi_hit"',
        'family = "markov"',
        'd = Path("research") / "hypotheses"',
    ])
    assert sorted(hit.split(":")[0] for hit in retired_joins(sample)) == ["1", "4", "5"]

    assert data_root_offenders({"stats", "forecast", "ai_ml", "ml"}) == []
    assert data_root_offenders({"predict", "misc"}) == [
        "misc: chưa thuộc nhóm nào", "predict: đã chuyển tới data/forecast/predict"]
