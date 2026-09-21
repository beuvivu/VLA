from __future__ import annotations

"""Trọng số tổ hợp phải có MỘT nguồn sự thật duy nhất.

Trước đây hai nơi tự đọc ``data/ensemble/weights_<mode>.json`` theo hai cách:
``predict_nextday_2d`` canh ``schema_version >= 5`` và đòi có ``w_stat``, còn
``model_quality`` đọc thẳng không canh gì. Tệp trên đĩa là bản cũ 3 thành phần
không có ``schema_version``, nên hai nơi nhận hai vector khác nhau — lệch 0,75,
tức ba phần tư khối lượng trọng số.

Hệ quả là trang Chất lượng mô hình chấm hiệu chuẩn, độ nhọn và phân rã Murphy
cho một mô hình KHÔNG được xuất bản. Đây là lớp lỗi im lặng: không ngoại lệ,
không cảnh báo, chỉ là hai con số không nói về cùng một thứ.
"""

import json
from pathlib import Path

import pytest

from ensemble_utils import (
    DEFAULT_ENSEMBLE_WEIGHTS,
    MIN_WEIGHTS_SCHEMA,
    load_ensemble_weights,
    weights_provenance,
)

KEYS = ("w_ml", "w_cau", "w_stat", "w_active", "w_stable")
REPO = Path(__file__).resolve().parents[1]


def _write(tmp_path: Path, mode: str, blob: object) -> Path:
    directory = tmp_path / "ensemble"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"weights_{mode}.json").write_text(
        json.dumps(blob, ensure_ascii=False), encoding="utf-8"
    )
    return tmp_path


def test_no_module_rebuilds_weights_from_a_raw_json_blob() -> None:
    """Chỉ ``ensemble_utils`` được phép suy trọng số ra từ JSON.

    Bản trước của phép kiểm này chỉ đòi tệp CÓ CHỨA chuỗi
    ``load_ensemble_weights`` — mà một dòng ``import`` đã đủ làm nó xanh. Đột
    biến trả ``model_quality`` về đọc thô đã lọt qua nguyên vẹn. Nên ở đây
    ghim ĐẶC TÍNH thật: dựng ``EnsembleWeights`` từ các khoá ``w_*`` bóc ra
    khỏi một blob là việc của một nơi duy nhất.
    """
    offenders = []
    for path in sorted((REPO / "src").rglob("*.py")):
        if path.name == "ensemble_utils.py":
            continue
        source = path.read_text(encoding="utf-8")
        builds = "EnsembleWeights(" in source and '.get("w_' in source
        if builds:
            offenders.append(path.relative_to(REPO).as_posix())
    assert not offenders, (
        "các tệp này tự suy trọng số ra từ JSON thô thay vì gọi "
        f"load_ensemble_weights(): {offenders}"
    )


def test_every_reader_of_the_weights_path_goes_through_the_shared_loader() -> None:
    """Đọc tệp để lấy SIÊU DỮ LIỆU thì được; lấy trọng số thì không.

    ``weights_provenance`` cũng đọc blob để lấy ``learned_at_utc``/``metric``
    và khối ``promotion``, nên phép kiểm không cấm việc mở tệp — nó đòi tệp nào
    mở thì phải THẬT SỰ gọi hàm chung để lấy TRỌNG SỐ, chứ không chỉ nhắc tên
    nó trong dòng import.

    (Trước đây câu này nói về ``build_dashboard``; module ấy đã bị xóa cùng
    tầng trình bày và logic xuất xứ chuyển về ``ensemble_utils``.)
    """
    import re as _re

    offenders = []
    for path in sorted((REPO / "src").rglob("*.py")):
        if path.name == "ensemble_utils.py":
            continue
        source = path.read_text(encoding="utf-8")
        if not ('f"weights_{mode}.json"' in source or '"weights_loto.json"' in source):
            continue
        calls = _re.findall(r"load_ensemble_weights\s*\(", source)
        if not calls:
            offenders.append(path.relative_to(REPO).as_posix())
    assert not offenders, (
        "các tệp này mở tệp trọng số nhưng không hề GỌI load_ensemble_weights(): "
        f"{offenders}"
    )


def test_the_shipped_weights_file_is_read_the_same_way_everywhere() -> None:
    """Đọc tệp THẬT trong kho: mọi nơi phải nhận đúng một vector."""
    first = load_ensemble_weights(REPO / "data", "loto")
    again = load_ensemble_weights(REPO / "data", "loto")
    assert first.as_dict() == again.as_dict()
    total = sum(getattr(first, k) for k in KEYS)
    assert total == pytest.approx(1.0), f"trọng số phải chuẩn hoá về 1, thấy {total}"


@pytest.mark.parametrize(
    ("label", "blob"),
    [
        ("thiếu schema_version", {"weights": {k: 0.2 for k in KEYS}}),
        ("schema quá cũ", {"schema_version": MIN_WEIGHTS_SCHEMA - 1,
                           "weights": {k: 0.2 for k in KEYS}}),
        ("schema là bool", {"schema_version": True, "weights": {k: 0.2 for k in KEYS}}),
        ("thiếu w_stat", {"schema_version": MIN_WEIGHTS_SCHEMA,
                          "weights": {"w_ml": 1.0}}),
        ("weights không phải dict", {"schema_version": MIN_WEIGHTS_SCHEMA, "weights": 7}),
        ("gốc là danh sách", [1, 2, 3]),
    ],
)
def test_an_unusable_file_falls_back_to_the_declared_default(
    tmp_path: Path, label: str, blob: object
) -> None:
    """Tệp không dùng được phải rơi về mặc định KHAI BÁO, không về 0 hay rác."""
    data_dir = _write(tmp_path, "loto", blob)
    got = load_ensemble_weights(data_dir, "loto")
    assert got.as_dict() == DEFAULT_ENSEMBLE_WEIGHTS.as_dict(), label


def test_a_missing_file_falls_back_to_the_declared_default(tmp_path: Path) -> None:
    assert (
        load_ensemble_weights(tmp_path, "loto").as_dict()
        == DEFAULT_ENSEMBLE_WEIGHTS.as_dict()
    )


def test_corrupt_json_does_not_crash_the_pipeline(tmp_path: Path) -> None:
    directory = tmp_path / "ensemble"
    directory.mkdir(parents=True)
    (directory / "weights_loto.json").write_text("{ khong phai json", encoding="utf-8")
    assert (
        load_ensemble_weights(tmp_path, "loto").as_dict()
        == DEFAULT_ENSEMBLE_WEIGHTS.as_dict()
    )


def test_a_valid_file_is_honoured_and_normalised(tmp_path: Path) -> None:
    """Chốt chặn ngược: cổng canh không được chặn cả tệp HỢP LỆ."""
    data_dir = _write(tmp_path, "de", {
        "schema_version": MIN_WEIGHTS_SCHEMA,
        "weights": {"w_ml": 2.0, "w_cau": 2.0, "w_stat": 2.0,
                    "w_active": 2.0, "w_stable": 2.0},
    })
    got = load_ensemble_weights(data_dir, "de")
    assert got.as_dict() != DEFAULT_ENSEMBLE_WEIGHTS.as_dict()
    for key in KEYS:
        assert getattr(got, key) == pytest.approx(0.2), key


def test_the_provenance_report_shows_the_weights_that_are_actually_in_force() -> None:
    """Hai chỗ cạnh nhau không được nói hai bộ trọng số khác nhau.

    Báo cáo xuất xứ từng hiện nguyên văn tệp trên đĩa, mà tệp ấy bị
    ``load_ensemble_weights`` LOẠI. Nên nó ghi ``w_ml 0,9987`` trong khi danh
    sách gợi ý — dựng từ chính phép dự đoán — ghi ``w_ml 0,25``.
    """
    for mode in ("loto", "de"):
        got = weights_provenance(REPO / "data", mode)
        assert got["weights"] == load_ensemble_weights(REPO / "data", mode).as_dict(), mode
        assert got["xuat_xu"] in {"da_hoc", "bi_tu_choi", "khong_co_ho_so"}, mode


def test_the_provenance_matches_the_stored_record_not_the_values() -> None:
    """Xuất xứ phải khớp KHỐI ``promotion`` trên đĩa, không suy từ giá trị.

    Bản trước đoán xuất xứ bằng cách so trọng số với mặc định. Kể từ khi bộ
    học có cổng đề bạt thì phép đoán ấy nói sai: một tệp hợp lệ, lược đồ 7,
    mang đúng mặc định vì cổng đã TỪ CHỐI lại bị báo là "tệp trọng số thiếu
    hoặc sai lược đồ" — đổ lỗi cho tệp trong khi tệp không có lỗi gì.
    """
    for mode in ("loto", "de"):
        got = weights_provenance(REPO / "data", mode)
        stored = json.loads(
            (REPO / "data" / "ensemble" / f"weights_{mode}.json").read_text(encoding="utf-8")
        )
        promoted = bool(stored.get("promotion", {}).get("promoted"))

        assert (got["xuat_xu"] == "da_hoc") == promoted, f"{mode}: {got['xuat_xu']}"
        if promoted:
            assert got["weights"] != DEFAULT_ENSEMBLE_WEIGHTS.as_dict(), mode
        else:
            assert got["weights"] == DEFAULT_ENSEMBLE_WEIGHTS.as_dict(), mode
            assert got["ly_do"], f"{mode}: từ chối mà không nêu lý do"


def test_a_refused_promotion_is_not_reported_as_a_broken_file(tmp_path: Path) -> None:
    """Tệp lành mà cổng từ chối KHÁC tệp hỏng, và báo cáo phải phân biệt được.

    Hai trạng thái này cho cùng một bộ trọng số hiển thị, nên nếu báo cáo nói
    giống nhau thì người đọc không thể biết hệ thống đã ĐO rồi từ chối hay
    chưa đo được gì.
    """
    ens = tmp_path / "ensemble"
    ens.mkdir(parents=True)

    def report_for(blob: dict | None) -> dict:
        path = ens / "weights_loto.json"
        if blob is None:
            path.unlink(missing_ok=True)
        else:
            path.write_text(json.dumps(blob), encoding="utf-8")
        return weights_provenance(tmp_path, "loto")

    refused = report_for(
        {
            "schema_version": 7,
            "weights": DEFAULT_ENSEMBLE_WEIGHTS.as_dict(),
            "days_used": ["2026-09-01"],
            "promotion": {
                "promoted": False,
                "reason": "biên thắng +0.0055% chưa đạt sàn 0.20%",
                "train_days": 12,
                "validation_days": 8,
                "validation_logloss": {"mac_dinh": 4.6},
                "relative_gain": 5.5e-05,
            },
        }
    )
    missing = report_for(None)

    assert refused["weights"] == missing["weights"] == DEFAULT_ENSEMBLE_WEIGHTS.as_dict()
    assert refused["xuat_xu"] == "bi_tu_choi"
    assert missing["xuat_xu"] == "khong_co_ho_so"
    assert "0.20%" in refused["ly_do"]
    assert refused["tham_dinh"]["so_ky_tham_dinh"] == 8
    assert "tham_dinh" not in missing


def test_a_promoted_vector_is_reported_as_learned(tmp_path: Path) -> None:
    """Đề bạt thật thì báo cáo phải nói đã học, kèm số đo ngoài mẫu."""
    ens = tmp_path / "ensemble"
    ens.mkdir(parents=True)
    (ens / "weights_de.json").write_text(
        json.dumps(
            {
                "schema_version": 7,
                "weights": {"w_ml": 0.1, "w_cau": 0.6, "w_stat": 0.1, "w_active": 0.1, "w_stable": 0.1},
                "days_used": ["2026-09-01", "2026-09-02"],
                "promotion": {
                    "promoted": True,
                    "reason": "thắng đường cơ sở ngoài mẫu",
                    "train_days": 24,
                    "validation_days": 16,
                    "validation_logloss": {"mac_dinh": 4.6, "ung_vien": 4.1},
                    "relative_gain": 0.108,
                },
            }
        ),
        encoding="utf-8",
    )

    got = weights_provenance(tmp_path, "de")
    assert got["xuat_xu"] == "da_hoc"
    assert got["weights"]["w_cau"] == pytest.approx(0.6)
    assert got["days_used"] == 2
    assert got["tham_dinh"]["loi_tuong_doi"] == pytest.approx(0.108)


def test_corrupt_json_is_reported_as_no_record_not_as_learned(tmp_path: Path) -> None:
    """Tệp hỏng phải rơi về "không có hồ sơ", không được im lặng thành đã học."""
    ens = tmp_path / "ensemble"
    ens.mkdir(parents=True)
    (ens / "weights_loto.json").write_text("{ khong phai json", encoding="utf-8")

    got = weights_provenance(tmp_path, "loto")
    assert got["xuat_xu"] == "khong_co_ho_so"
    assert got["weights"] == DEFAULT_ENSEMBLE_WEIGHTS.as_dict()
