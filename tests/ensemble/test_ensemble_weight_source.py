from __future__ import annotations


import json
from pathlib import Path

import pytest

from ensemble.ensemble_utils import (
    DEFAULT_ENSEMBLE_WEIGHTS,
    MIN_WEIGHTS_SCHEMA,
    load_ensemble_weights,
)

KEYS = ("w_ml", "w_cau", "w_stat", "w_active", "w_stable")
REPO = Path(__file__).resolve().parents[2]


def _write(tmp_path: Path, mode: str, blob: object) -> Path:
    directory = tmp_path / "ensemble"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"weights_{mode}.json").write_text(
        json.dumps(blob, ensure_ascii=False), encoding="utf-8"
    )
    return tmp_path


def test_no_module_rebuilds_weights_from_a_raw_json_blob() -> None:
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
    data_dir = _write(tmp_path, "de", {
        "schema_version": MIN_WEIGHTS_SCHEMA,
        "weights": {"w_ml": 2.0, "w_cau": 2.0, "w_stat": 2.0,
                    "w_active": 2.0, "w_stable": 2.0},
    })
    got = load_ensemble_weights(data_dir, "de")
    assert got.as_dict() != DEFAULT_ENSEMBLE_WEIGHTS.as_dict()
    for key in KEYS:
        assert getattr(got, key) == pytest.approx(0.2), key


def test_the_dashboard_card_shows_the_weights_that_are_actually_in_force() -> None:
    from pages.build_dashboard import _effective_weights

    for mode in ("loto", "de"):
        card = _effective_weights(REPO / "data", mode)
        effective = load_ensemble_weights(REPO / "data", mode)
        assert card["weights"] == effective.as_dict(), mode
        assert card["nguon"], mode


def test_the_card_states_the_provenance_the_stored_record_actually_supports() -> None:
    from pages.build_dashboard import _effective_weights

    for mode in ("loto", "de"):
        card = _effective_weights(REPO / "data", mode)
        stored = json.loads(
            (REPO / "data" / "ensemble" / f"weights_{mode}.json").read_text(encoding="utf-8")
        )
        promoted = bool(stored.get("promotion", {}).get("promoted"))
        says_default = card["xuat_xu"] in {"mac_dinh_dat_tay", "bi_tu_choi"}

        assert says_default != promoted, f"{mode}: xuất xứ '{card['nguon']}' trái với hồ sơ đề bạt"
        if promoted:
            assert card["weights"] != DEFAULT_ENSEMBLE_WEIGHTS.as_dict(), mode
        else:
            assert card["weights"] == DEFAULT_ENSEMBLE_WEIGHTS.as_dict(), mode
            assert card.get("ly_do"), f"{mode}: từ chối mà không nêu lý do"


def test_a_refused_promotion_is_not_reported_as_a_broken_file(tmp_path: Path) -> None:
    from pages.build_dashboard import _effective_weights

    ens = tmp_path / "ensemble"
    ens.mkdir(parents=True)

    def card_for(blob: dict | None) -> dict:
        path = ens / "weights_loto.json"
        if blob is None:
            path.unlink(missing_ok=True)
        else:
            path.write_text(json.dumps(blob), encoding="utf-8")
        return _effective_weights(tmp_path, "loto")

    refused = card_for(
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
    missing = card_for(None)

    assert refused["weights"] == missing["weights"] == DEFAULT_ENSEMBLE_WEIGHTS.as_dict()
    assert refused["nguon"] != missing["nguon"]
    assert "0.20%" in refused["ly_do"]
    assert refused["tham_dinh"]["so_ky_tham_dinh"] == 8
    assert "tham_dinh" not in missing


def test_a_promoted_vector_is_reported_as_learned(tmp_path: Path) -> None:
    from pages.build_dashboard import _effective_weights

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

    card = _effective_weights(tmp_path, "de")
    assert "mac dinh" not in card["nguon"]
    assert card["weights"]["w_cau"] == pytest.approx(0.6)
    assert card["days_used"] == 2
    assert card["tham_dinh"]["loi_tuong_doi"] == pytest.approx(0.108)


def test_dashboard_weight_card_accepts_missing_optional_day_list(tmp_path: Path) -> None:
    from pages.build_dashboard import _effective_weights
    from ensemble.ensemble_utils import weights_provenance
    path = tmp_path / 'ensemble' / 'weights_loto.json'
    path.parent.mkdir()
    path.write_text(json.dumps({'schema_version':7, 'weights':DEFAULT_ENSEMBLE_WEIGHTS.as_dict(),
        'days_used':None, 'promotion':{'promoted':False, 'reason':'chưa vượt cổng'}}))
    canonical = weights_provenance(tmp_path, 'loto')
    card = _effective_weights(tmp_path, 'loto')
    assert card['weights'] == canonical['weights']
    assert card['xuat_xu'] == canonical['xuat_xu'] == 'bi_tu_choi'
    assert card['days_used'] == canonical['days_used'] == 0


def test_legacy_learned_weight_card_keeps_optional_training_metadata(tmp_path: Path) -> None:
    from pages.build_dashboard import _effective_weights
    path = tmp_path / 'ensemble' / 'weights_loto.json'
    path.parent.mkdir()
    metadata = {'learned_at_utc':'2026-09-01T00:00:00Z', 'window_days':120,
                'half_life_days':30, 'metric':'logloss'}
    path.write_text(json.dumps({'schema_version':7,
        'weights':{'w_ml':.1, 'w_cau':.6, 'w_stat':.1, 'w_active':.1, 'w_stable':.1},
        'days_used':['2026-09-01', '2026-09-02'], **metadata}))
    card = _effective_weights(tmp_path, 'loto')
    assert card['xuat_xu'] == 'da_hoc_chua_co_cong'
    assert all(card.get(key) == value for key, value in metadata.items())
    assert card.get('days_used') == 2
