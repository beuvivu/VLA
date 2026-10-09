"""Học trực tuyến từ dự báo đầy đủ đã ghi trước kỳ quay.

Mỗi kỳ cập nhật toàn bộ chuyên gia bằng Brier thích hợp, không lấy thứ hạng
hay số trúng top-k thay cho xác suất. Bộ nhớ dài không bị đặt lại khi trôi dạt.
Cổng đề bạt là hàng rào thực nghiệm bảo thủ; kiểm lặp mỗi ngày KHÔNG tạo ra
bảo đảm kiểm định tuần tự hay lời hứa dự đoán được một quá trình ngẫu nhiên.
"""

from __future__ import annotations

from lottery_codes import write_code_csv

import argparse
import base64
import copy
import hashlib
import json
import zlib
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from atomic_io import atomic_write_bytes
from calendar_alignment import known_non_draw_days
from hierarchical_pooling import fit_shrinkage_to_prior
from time_policy import DEFAULT_DRAW_CUTOFF, VIETNAM_TZ, now_vietnam
from xsmb_domain import FIELD_WIDTHS, baseline_rate

SCHEMA_VERSION = 1
EXPERTS = (
    "incumbent",
    "constant",
    "bayes_30",
    "bayes_180",
    "bayes_all",
    "lag_special",
    "lag_repeat",
)
FORECAST_CUTOFF = time(18, 0)
RECIPE = {
    "family": "bayesian_lag_v1",
    "eta": 4.0,
    "discount": 0.97,
    "fixed_share": 0.03,
    "blend": 0.5,
    "min_days": 60,
    "gate_window": 180,
    "block_days": 7,
    "uncertainty_multiplier": 4.0,
    "minimum_logloss_skill": 0.002,
}
KEEP_FULL_RECORDS = 365
ARCHIVE_CHUNK = 64


def _json_bytes(value) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")


def _digest(value) -> str:
    return hashlib.sha256(_json_bytes(value)).hexdigest()


def _date(value) -> date:
    if not isinstance(value, str):
        raise ValueError("Ngày phải là chuỗi ISO YYYY-MM-DD")
    result = date.fromisoformat(value)
    if result.isoformat() != value:
        raise ValueError("Ngày phải theo ISO YYYY-MM-DD")
    return result


def _clock(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Đồng hồ phải có múi giờ (timezone-aware)")
    return value.astimezone(VIETNAM_TZ)


def _prob(mode: str, value) -> np.ndarray:
    baseline_rate(mode)
    p = np.asarray(value, dtype=np.float64)
    if p.shape != (100,) or not np.all(np.isfinite(p)) or np.any((p < 0) | (p > 1)):
        raise ValueError("Xác suất cần đủ 100 giá trị hữu hạn trong [0, 1]")
    if mode == "de" and not np.isclose(p.sum(), 1.0, rtol=0, atol=1e-9):
        raise ValueError("Phân phối Đặc Biệt phải có tổng bằng 1")
    if mode == "loto" and p.sum() > len(FIELD_WIDTHS) + 1e-9:
        raise ValueError("Tổng xác suất biên LOTO không thể vượt 27 giải")
    return p


def _labels(mode: str, values) -> np.ndarray:
    y = np.asarray(values, dtype=float)
    if y.shape != (100,) or not np.all(np.isfinite(y)) or not np.all((y == 0) | (y == 1)):
        raise ValueError("Nhãn cần đủ 100 chỉ báo nhị phân")
    if (mode == "de" and y.sum() != 1) or (
        mode == "loto" and not 1 <= y.sum() <= len(FIELD_WIDTHS)
    ):
        raise ValueError("Số nhãn dương không hợp lệ cho kỳ quay")
    return y


def proper_losses(mode: str, probability, outcome) -> dict:
    """Chấm một kỳ bằng Brier và logloss; LOTO giữ nguyên xác suất biên."""
    p, y = _prob(mode, probability), _labels(mode, outcome)
    safe = np.clip(p, 1e-12, 1 - 1e-12)
    if mode == "de":
        return {
            "brier": float(np.sum((p - y) ** 2) / 2),
            "logloss": float(-np.sum(y * np.log(safe))),
        }
    return {
        "brier": float(np.mean((p - y) ** 2)),
        "logloss": float(-np.mean(y * np.log(safe) + (1 - y) * np.log1p(-safe))),
    }


def _history(frame: pd.DataFrame) -> pd.DataFrame:
    """Chuẩn hoá kết quả; bản sao giống nhau được gộp, xung đột bị từ chối."""
    fields = [name for name, _ in FIELD_WIDTHS]
    if (
        not isinstance(frame, pd.DataFrame)
        or frame.empty
        or not set(["date", *fields]).issubset(frame.columns)
    ):
        raise ValueError("Lịch sử thiếu ngày hoặc một trong 27 giải")
    result = frame[["date", *fields]].copy()
    for value in result["date"]:
        _date(value)
    for key, width in FIELD_WIDTHS:
        values = pd.to_numeric(result[key], errors="raise").to_numpy(dtype=float)
        if (
            not np.all(np.isfinite(values))
            or np.any(values != np.floor(values))
            or np.any((values < 0) | (values >= 10**width))
        ):
            raise ValueError(f"Kết quả không hợp lệ ở cột {key}")
        result[key] = values.astype(np.int64)
    result = result.drop_duplicates().sort_values("date", kind="stable").reset_index(drop=True)
    if result["date"].duplicated().any():
        raise ValueError("Ngày trùng có kết quả xung đột (conflicting duplicate)")
    return result


def _fingerprint(frame: pd.DataFrame) -> dict:
    return {
        "count": len(frame),
        "last_date": frame.iloc[-1]["date"],
        "digest": _digest(frame.to_numpy().tolist()),
    }


def _outcomes(mode: str, frame: pd.DataFrame) -> np.ndarray:
    y = np.zeros((len(frame), 100))
    cols = ["special"] if mode == "de" else [name for name, _ in FIELD_WIDTHS]
    values = frame[cols].to_numpy(dtype=np.int64) % 100
    y[np.arange(len(frame))[:, None], values] = 1
    return y


def _posterior(mode: str, counts, trials, prior) -> np.ndarray:
    kappa = fit_shrinkage_to_prior(counts, trials, prior)
    p = (np.asarray(counts) + kappa * prior) / (np.asarray(trials) + kappa)
    p = np.clip(p, 1e-9, 1 - 1e-9)
    if mode == "de":
        p /= p.sum()
    elif p.sum() > len(FIELD_WIDTHS):
        # Điều kiện riêng từng con có thể mâu thuẫn với trần tổng số giải.
        # Chiếu theo khoảng cách bình phương về miền khả thi, không chuẩn
        # hoá biên LOTO thành phân phối categorical tổng bằng một.
        low, high = 0.0, float(p.max())
        for _ in range(50):
            shift = (low + high) / 2
            if np.maximum(p - shift, 1e-9).sum() > len(FIELD_WIDTHS):
                low = shift
            else:
                high = shift
        p = np.maximum(p - high, 1e-9)
    return _prob(mode, p)


def build_experts(mode: str, history: pd.DataFrame, incumbent, target_date: str) -> dict:
    """Bayes tần suất và điều kiện trễ chỉ dùng các hàng trước ngày đích."""
    _date(target_date)
    frame = _history(history)
    frame = frame.loc[frame["date"] < target_date].reset_index(drop=True)
    if frame.empty:
        raise ValueError("Không có lịch sử trước ngày đích")
    base = np.full(100, baseline_rate(mode))
    y = _outcomes(mode, frame)
    experts = {"incumbent": _prob(mode, incumbent).copy(), "constant": base}
    for horizon in (30, 180, "all"):
        window = y if horizon == "all" else y[-horizon:]
        experts[f"bayes_{horizon}"] = _posterior(mode, window.sum(axis=0), len(window), base)
    prior = experts["bayes_all"]
    if len(frame) < 2:
        experts.update(lag_special=prior.copy(), lag_repeat=prior.copy())
        return experts
    dates = pd.to_datetime(frame["date"]).to_numpy()
    consecutive = np.diff(dates).astype("timedelta64[D]").astype(int) == 1
    special = frame["special"].to_numpy(dtype=np.int64) % 100
    selected = consecutive & (special[:-1] == special[-1])
    experts["lag_special"] = _posterior(
        mode, y[1:][selected].sum(axis=0), int(selected.sum()), prior
    )
    same_status = (y[:-1] == y[-1]) & consecutive[:, None]
    experts["lag_repeat"] = _posterior(
        mode, (y[1:] * same_status).sum(axis=0), same_status.sum(axis=0), prior
    )
    return experts


def new_state(mode: str) -> dict:
    """Khởi tạo bộ nhớ rỗng; lịch sử sẵn có không trở thành phép kiểm ngoài mẫu."""
    baseline_rate(mode)
    return {
        "schema_version": SCHEMA_VERSION,
        "mode": mode,
        "recipe": copy.deepcopy(RECIPE),
        "history": None,
        "learning": {
            "n_settled": 0,
            "slow_loss": [0.0] * len(EXPERTS),
            "fast_loss": [0.0] * len(EXPERTS),
        },
        "records": [],
        "archive": [],
    }


def _all_records(state: dict) -> list:
    records = []
    for chunk in state["archive"]:
        raw = zlib.decompress(base64.b64decode(chunk["zlib_base64"], validate=True))
        if hashlib.sha256(raw).hexdigest() != chunk["sha256"]:
            raise ValueError("Khối lưu trữ mất toàn vẹn")
        decoded = json.loads(raw)
        if len(decoded) != chunk["count"]:
            raise ValueError("Khối lưu trữ sai số bản ghi")
        records.extend(decoded)
    return records + state["records"]


def _scores(mode: str, record: dict, labels) -> dict:
    result = {name: proper_losses(mode, record["experts"][name], labels) for name in EXPERTS}
    result.update(
        {
            name: proper_losses(mode, record[name], labels)
            for name in ("mixture", "blend", "published")
        }
    )
    return result


# Sai số làm tròn cho phép khi chấm lại một kỳ đã chốt. Cùng một vector, cùng
# nhãn, nhưng runner khác CPU chọn nhánh SIMD khác cho `np.log`/`np.mean` và lệch
# 1 ULP: ngày 04-10-2026 logloss ...7734 so với ...7733 làm sổ bị từ chối và
# pipeline hoàn tất đỏ hai ngày liền. Ngưỡng tương đối 1e-12 rộng hơn 1 ULP
# (~2e-16) bốn bậc mà vẫn hẹp hơn mọi sửa điểm có nghĩa hàng triệu lần.
SCORE_RTOL = 1e-12
SCORE_ATOL = 1e-15


def _scores_agree(computed: dict, stored: dict) -> bool:
    """Điểm chấm lại khớp điểm đã chốt, sai khác tối đa sai số làm tròn."""
    if set(computed) != set(stored):
        return False
    for name, losses in computed.items():
        if set(losses) != set(stored[name]):
            return False
        for key, value in losses.items():
            other = stored[name][key]
            if isinstance(other, bool) or not isinstance(other, (int, float)):
                return False
            if not np.isclose(value, other, rtol=SCORE_RTOL, atol=SCORE_ATOL):
                return False
    return True


def _is_scored(record: dict) -> bool:
    settlement = record["settlement"]
    return settlement is not None and settlement.get("status", "scored") == "scored"


def _validate_state(state: dict, mode: str) -> None:
    """Từ chối phiên bản lạ, vector hỏng và bộ nhớ lệch khỏi sổ đã chốt."""
    try:
        if (
            state["schema_version"] != SCHEMA_VERSION
            or isinstance(state["schema_version"], bool)
            or state["mode"] != mode
            or state["recipe"] != RECIPE
        ):
            raise ValueError("Schema hoặc cấu hình học trực tuyến không tương thích")
        _json_bytes(state)
        slow, fast, count, previous = np.zeros(len(EXPERTS)), np.zeros(len(EXPERTS)), 0, ""
        for record in _all_records(state):
            target = _date(record["target_date"])
            generated = _clock(datetime.fromisoformat(record["generated_at"]))
            anchor = record["anchor_fingerprint"]
            if (
                type(anchor["count"]) is not int
                or anchor["count"] < 1
                or _date(anchor["last_date"]) + timedelta(days=1) != target
                or not isinstance(anchor["digest"], str)
                or len(anchor["digest"]) != 64
                or any(c not in "0123456789abcdef" for c in anchor["digest"])
            ):
                raise ValueError("Dấu vân tay ngày neo (anchor) không hợp lệ")
            if record["target_date"] <= previous or generated >= datetime.combine(
                target, FORECAST_CUTOFF, VIETNAM_TZ
            ):
                raise ValueError("Thứ tự sổ hoặc thời gian dự báo không hợp lệ")
            previous = record["target_date"]
            if set(record["experts"]) != set(EXPERTS):
                raise ValueError("Sổ thiếu chuyên gia")
            for p in record["experts"].values():
                _prob(mode, p)
            for name in ("mixture", "blend", "published"):
                _prob(mode, record[name])
            weights = np.asarray([record["weights"][name] for name in EXPERTS])
            if (
                not np.all(np.isfinite(weights))
                or np.any(weights <= 0)
                or not np.isclose(weights.sum(), 1)
            ):
                raise ValueError("Trọng số sổ không hợp lệ")
            expected = sum(
                weights[i] * np.asarray(record["experts"][name]) for i, name in enumerate(EXPERTS)
            )
            if not np.allclose(record["mixture"], expected, rtol=0, atol=1e-12):
                raise ValueError("Vector tổ hợp sai so với trọng số đã đóng băng")
            expected_blend = RECIPE["blend"] * expected + (1 - RECIPE["blend"]) * np.asarray(
                record["experts"]["incumbent"]
            )
            if not np.allclose(record["blend"], expected_blend, rtol=0, atol=1e-12):
                raise ValueError("Vector trộn không đúng công thức đã đăng ký")
            chosen = record["blend"] if record["gate"]["active"] else record["experts"]["incumbent"]
            if not np.array_equal(record["published"], chosen):
                raise ValueError("Vector công bố không đúng trạng thái cổng")
            if record["settlement"] is not None:
                settlement = record["settlement"]
                if settlement.get("status", "scored") == "non_draw":
                    if (
                        settlement["calendar_date"] != record["target_date"]
                        or record["target_date"] not in known_non_draw_days()
                        or settlement["calendar_source"] != "calendar_alignment.known_non_draw_days"
                        or not isinstance(settlement["calendar_sha256"], str)
                        or len(settlement["calendar_sha256"]) != 64
                        or any(c not in "0123456789abcdef" for c in settlement["calendar_sha256"])
                        or "labels" in settlement
                        or "scores" in settlement
                        or _clock(datetime.fromisoformat(settlement["settled_at"]))
                        < datetime.combine(target, DEFAULT_DRAW_CUTOFF, VIETNAM_TZ)
                    ):
                        raise ValueError("Ngày không quay thiếu chứng cứ lịch hoặc bị gán nhãn giả")
                    continue
                if not _is_scored(record):
                    raise ValueError("Trạng thái chốt kỳ không hợp lệ")
                labels = _labels(mode, settlement["labels"])
                if not _scores_agree(_scores(mode, record, labels), settlement["scores"]):
                    raise ValueError("Điểm kỳ quay lệch khỏi vector đóng băng")
                # Bộ nhớ học dựng từ điểm ĐÃ CHỐT, đúng như `advance` đã cộng.
                losses = np.asarray([settlement["scores"][name]["brier"] for name in EXPERTS])
                slow += losses
                fast = RECIPE["discount"] * fast + losses
                count += 1
        learning = state["learning"]
        if (
            isinstance(learning["n_settled"], bool)
            or learning["n_settled"] != count
            or not np.allclose(learning["slow_loss"], slow, rtol=0, atol=1e-10)
            or not np.allclose(learning["fast_loss"], fast, rtol=0, atol=1e-10)
        ):
            raise ValueError("Bộ nhớ học không khớp sổ đã chốt")
    except (KeyError, TypeError, IndexError, OverflowError, zlib.error) as exc:
        raise ValueError("Sổ học trực tuyến bị hỏng (corrupt state)") from exc


def _weights(learning: dict) -> np.ndarray:
    memories = []
    for name in ("slow_loss", "fast_loss"):
        logits = -RECIPE["eta"] * np.asarray(learning[name])
        p = np.exp(logits - logits.max())
        memories.append(p / p.sum())
    p = (memories[0] + memories[1]) / 2
    return (1 - RECIPE["fixed_share"]) * p + RECIPE["fixed_share"] / len(EXPERTS)


def _gain_stats(gains) -> dict:
    """Sai số lấy giá trị lớn hơn giữa theo ngày và các khối bảy ngày."""
    values = np.asarray(gains, dtype=float)
    n = len(values)
    if n < 2:
        return {"mean": float(values.mean()) if n else 0.0, "lower": None, "se": None, "blocks": 0}
    day_se = float(values.std(ddof=1) / np.sqrt(n))
    blocks = [
        float(values[i : i + RECIPE["block_days"]].mean())
        for i in range(0, n - RECIPE["block_days"] + 1, RECIPE["block_days"])
    ]
    block_se = float(np.std(blocks, ddof=1) / np.sqrt(len(blocks))) if len(blocks) > 1 else day_se
    se = max(day_se, block_se)
    return {
        "mean": float(values.mean()),
        "lower": float(values.mean() - RECIPE["uncertainty_multiplier"] * se),
        "se": se,
        "blocks": len(blocks),
    }


def promotion_gate(records: list) -> dict:
    """Đề bạt đúng vector trộn đã chấm; cổng chỉ đọc kỳ đã chốt trước đó."""
    settled = [r for r in records if _is_scored(r)][-RECIPE["gate_window"] :]
    n = len(settled)
    details = {}
    passed = n >= RECIPE["min_days"]
    for candidate in ("mixture", "blend"):
        for reference in ("incumbent", "constant"):
            scores = [r["settlement"]["scores"] for r in settled]
            ll = [s[reference]["logloss"] - s[candidate]["logloss"] for s in scores]
            br = [s[reference]["brier"] - s[candidate]["brier"] for s in scores]
            stats, brier = _gain_stats(ll), _gain_stats(br)
            reference_loss = float(np.mean([s[reference]["logloss"] for s in scores])) if n else 0.0
            recent = _gain_stats(ll[-20:])
            # Suy giảm gần đây có thể hạ cổng dù trung bình dài hạn còn đẹp.
            recent_ok = n >= 20 and recent["mean"] > 0 and float(np.mean(br[-20:])) >= 0
            ok = (
                n >= RECIPE["min_days"]
                and stats["lower"] > RECIPE["minimum_logloss_skill"] * reference_loss
                and brier["lower"] >= 0
                and recent_ok
            )
            passed = passed and ok
            details[f"{candidate}_vs_{reference}"] = {
                "logloss_gain": stats,
                "brier_gain": brier,
                "recent_logloss_gain": recent,
                "pass": bool(ok),
            }
    return {
        "active": bool(passed),
        "n_observations": n,
        "minimum_observations": RECIPE["min_days"],
        "blend_fraction": RECIPE["blend"],
        "comparisons": details,
        "reason": "Đạt cổng trên dự báo thật đã chốt"
        if passed
        else "Giữ đương nhiệm; chưa đủ bằng chứng hoặc vừa suy giảm",
        "uncertainty": "Chặn thực nghiệm: max(SE theo ngày, SE khối 7 kỳ), hệ số 4; không phải bảo đảm anytime-valid khi kiểm lặp",
    }


def advance(
    state: dict, history: pd.DataFrame, incumbent, target_date: str, *, now: datetime
) -> tuple[dict, dict]:
    """Chốt kỳ cũ một lần, học đủ chuyên gia, rồi đóng băng dự báo kỳ mới."""
    local = _clock(now)
    mode = state["mode"]
    _validate_state(state, mode)
    frame, target = _history(history), _date(target_date)
    if _date(frame.iloc[-1]["date"]) > local.date() or (
        _date(frame.iloc[-1]["date"]) == local.date()
        and local.time().replace(tzinfo=None) < DEFAULT_DRAW_CUTOFF
    ):
        raise ValueError("Lịch sử chứa kết quả tương lai hoặc kỳ chưa hết giờ quay")
    old_prefix = state["history"]
    if old_prefix is not None:
        prefix = frame.loc[frame["date"] <= old_prefix["last_date"]]
        if prefix.empty or _fingerprint(prefix) != old_prefix:
            raise ValueError("Tiền tố lịch sử đã bị đổi hoặc bị cắt (history prefix)")
    existing = next((r for r in state["records"] if r["target_date"] == target_date), None)
    if existing is not None:
        if local < _clock(datetime.fromisoformat(existing["generated_at"])):
            raise ValueError("Đồng hồ lùi trước thời gian đã lưu")
        return copy.deepcopy(state), copy.deepcopy(existing)
    if target_date in set(frame["date"]):
        raise ValueError("Ngày đích đã có kết quả biết trước (known target)")
    if local >= datetime.combine(target, FORECAST_CUTOFF, VIETNAM_TZ):
        raise ValueError("Đã quá giờ lưu dự báo trước quay (cutoff 18:00 ICT)")
    if target != _date(frame.iloc[-1]["date"]) + timedelta(days=1):
        raise ValueError("Ngày đích phải tiếp ngay ngày neo của lịch sử")
    records = _all_records(state)
    if records and target_date <= records[-1]["target_date"]:
        raise ValueError("Không được thêm lại kỳ cũ đã nén trong sổ")
    _prob(mode, incumbent)
    result = copy.deepcopy(state)
    indexed = {value: i for i, value in enumerate(frame["date"])}
    y = _outcomes(mode, frame)
    for record in result["records"]:
        index = indexed.get(record["target_date"])
        if record["target_date"] >= target_date:
            continue
        if index is None:
            if record["target_date"] not in known_non_draw_days():
                raise ValueError("Thiếu kết quả dự báo cũ; ngày này chưa được khai là không quay")
            if record["settlement"] is None:
                record["settlement"] = {
                    "status": "non_draw",
                    "calendar_date": record["target_date"],
                    "calendar_source": "calendar_alignment.known_non_draw_days",
                    "calendar_sha256": _digest(sorted(known_non_draw_days())),
                    "settled_at": local.isoformat(),
                }
            continue
        if record["settlement"] is not None:
            if not _is_scored(record):
                raise ValueError("Ngày đã xác nhận không quay lại có kết quả xung đột")
            if record["settlement"]["labels"] != y[index].tolist():
                raise ValueError("Kết quả đã chốt bị sửa")
            continue
        # Nhãn thực có sẵn luôn được chấm; lịch nghỉ không được dùng để xoá
        # một lần thua. Chỉ ngày VẮNG đã khai chính thức mới được loại ở trên.
        record["settlement"] = {
            "status": "scored",
            "labels": y[index].tolist(),
            "scores": _scores(mode, record, y[index]),
            "settled_at": local.isoformat(),
        }
        learning = result["learning"]
        losses = np.asarray([record["settlement"]["scores"][name]["brier"] for name in EXPERTS])
        learning["slow_loss"] = (np.asarray(learning["slow_loss"]) + losses).tolist()
        learning["fast_loss"] = (
            RECIPE["discount"] * np.asarray(learning["fast_loss"]) + losses
        ).tolist()
        learning["n_settled"] += 1
    experts = build_experts(mode, frame, incumbent, target_date)
    weights = _weights(result["learning"])
    mixture = sum(weights[i] * experts[name] for i, name in enumerate(EXPERTS))
    blend = RECIPE["blend"] * mixture + (1 - RECIPE["blend"]) * experts["incumbent"]
    gate = promotion_gate(_all_records(result))
    record = {
        "target_date": target_date,
        "generated_at": local.isoformat(),
        "anchor_fingerprint": _fingerprint(frame),
        "experts": {key: p.tolist() for key, p in experts.items()},
        "weights": dict(zip(EXPERTS, weights.tolist(), strict=True)),
        "mixture": mixture.tolist(),
        "blend": blend.tolist(),
        "published": (blend if gate["active"] else experts["incumbent"]).tolist(),
        "gate": gate,
        "learning": copy.deepcopy(result["learning"]),
        "settlement": None,
    }
    result["records"].append(record)
    result["history"] = _fingerprint(frame)
    if len(result["records"]) > KEEP_FULL_RECORDS:
        chunk = result["records"][:ARCHIVE_CHUNK]
        if any(r["settlement"] is None for r in chunk):
            raise ValueError("Không nén kỳ chưa có kết quả; cần bổ sung lịch sử thiếu")
        raw = _json_bytes(chunk)
        result["archive"].append(
            {
                "count": len(chunk),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "zlib_base64": base64.b64encode(zlib.compress(raw, 9)).decode("ascii"),
            }
        )
        del result["records"][:ARCHIVE_CHUNK]
    return result, copy.deepcopy(record)


def save_state(path: Path, state: dict) -> None:
    """Ghi JSON nguyên tử có checksum; lỗi không đè lên sổ đang dùng."""
    _validate_state(state, state["mode"])
    atomic_write_bytes(Path(path), _json_bytes({**state, "_checksum": _digest(state)}))


def load_state(path: Path, mode: str) -> dict:
    """Không tự khởi tạo lại khi sổ cũ hỏng, tránh xoá các lần thua."""
    path = Path(path)
    if not path.exists():
        return new_state(mode)
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        checksum = state.pop("_checksum")
        if checksum != _digest(state):
            raise ValueError("Checksum sổ không khớp; mất toàn vẹn")
        _validate_state(state, mode)
        return state
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Không đọc được sổ học trực tuyến (corrupt state)") from exc


@contextmanager
def _locked(path: Path):
    """Khoá toàn lượt đọc, học, ghi để hai tiến trình không làm mất kỳ chốt."""
    import fcntl

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def _prediction_frame(path: Path, mode: str) -> tuple[pd.DataFrame, np.ndarray]:
    frame = pd.read_csv(path, float_precision="round_trip")
    if not {"number", "prob"}.issubset(frame.columns) or len(frame) != 100:
        raise ValueError("Tệp dự báo phải có đủ 100 số và cột xác suất")
    numbers = pd.to_numeric(frame["number"], errors="raise").to_numpy(dtype=float)
    if not np.array_equal(np.sort(numbers), np.arange(100)):
        raise ValueError("Tệp dự báo cần mỗi số 00..99 đúng một lần")
    frame["number"] = numbers.astype(int)
    vector = frame.sort_values("number")["prob"].to_numpy(dtype=float)
    return frame, _prob(mode, vector)


def run_online(
    mode: str, data_dir: Path, out_dir: Path | None = None, *, now: datetime | None = None
) -> dict:
    """Ghép sau dự báo gốc; giữ CSV đủ 100 số nguyên byte ở lượt shadow đầu."""
    data_dir = Path(data_dir)
    out_dir = Path(out_dir) if out_dir is not None else data_dir / "predict"
    state_path = data_dir / "online" / f"{mode}.json"
    local = _clock(now or now_vietnam())
    with _locked(state_path.with_suffix(".lock")):
        frame = _history(pd.read_csv(data_dir / "xsmb.csv", dtype={"date": str}))
        target = (_date(frame.iloc[-1]["date"]) + timedelta(days=1)).isoformat()
        prediction_path = out_dir / f"predict_next_{mode}_all_{target}.csv"
        published_frame, incumbent = _prediction_frame(prediction_path, mode)
        state = load_state(state_path, mode)
        updated, record = advance(state, frame, incumbent, target, now=local)
        report = {
            "schema_version": SCHEMA_VERSION,
            "mode": mode,
            "target_date": target,
            "generated_at": record["generated_at"],
            "status": "active" if record["gate"]["active"] else "shadow",
            "n_settled": updated["learning"]["n_settled"],
            "weights": record["weights"],
            "gate": record["gate"],
            "anchor_fingerprint": record["anchor_fingerprint"],
            "recipe": RECIPE,
            "memory": {
                "slow": "Tích luỹ toàn bộ kỳ đã chốt",
                "fast_discount": RECIPE["discount"],
                "fixed_share": RECIPE["fixed_share"],
            },
            "provenance": "Dự báo đủ 100 số đã đóng băng trước 18:00 ICT; không đánh giá hồi cứu",
            "journal_sha256": _digest(updated),
        }
        # Sổ ghi trước artifact: nếu tiến trình ngắt, chạy lại khôi phục chính vector này.
        save_state(state_path, updated)
        final = np.asarray(record["published"])
        changed = not np.array_equal(incumbent, final)
        if changed:
            published_frame["prob"] = final[published_frame["number"].to_numpy()]
            published_frame["online_active"] = record["gate"]["active"]
            published_frame["online_generated_at"] = record["generated_at"]
            published_frame["online_blend"] = RECIPE["blend"] if record["gate"]["active"] else 0.0
            published_frame = published_frame.sort_values(
                "prob", ascending=False, kind="stable"
            ).reset_index(drop=True)
            atomic_write_bytes(prediction_path, write_code_csv(published_frame, index=False).encode("utf-8"))
        if mode == "loto":
            from pick_diversity import diversified_order

            order = diversified_order(final, 10)
            ranked = published_frame.set_index("number", drop=False).loc[order].copy()
        else:
            ranked = published_frame.sort_values("prob", ascending=False, kind="stable").copy()
        ranked["number_str"] = ranked["number"].map(lambda number: f"{number:02d}")
        for n in (4, 8, 10):
            top_path = out_dir / f"predict_next_{mode}_top{n}_{target}.csv"
            # Khôi phục cả tệp top nếu lần trước ngắt sau khi đã ghi tệp đủ số.
            atomic_write_bytes(top_path, write_code_csv(ranked.head(n), index=False).encode("utf-8"))
        picks_path = out_dir / f"picks_{mode}.json"
        picks = json.loads(picks_path.read_text(encoding="utf-8")) if picks_path.exists() else {}
        picks.update(
            mode=mode, anchor_date=frame.iloc[-1]["date"], target_date=target, online=report
        )
        for n in (4, 8, 10):
            picks[f"top{n}"] = ranked.head(n)["number_str"].tolist()
        atomic_write_bytes(picks_path, _json_bytes(picks))
        atomic_write_bytes(data_dir / "research" / f"online_{mode}_report.json", _json_bytes(report))
        return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Học liên tục từ dự báo đã đóng băng và cổng đề bạt bảo thủ"
    )
    parser.add_argument("--mode", choices=["de", "loto"], required=True)
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--out-dir", default="data/predict")
    args = parser.parse_args()
    report = run_online(args.mode, Path(args.data_dir), Path(args.out_dir))
    print(
        f"[online] {args.mode}: {report['status']}; kỳ đã chốt={report['n_settled']}; {report['gate']['reason']}"
    )


if __name__ == "__main__":
    main()
