"""Sổ đăng ký mô hình: MỘT tệp nói rõ mô hình nào đang chạy và nó có được phép đổi xác suất công bố không.

Trước module này, câu hỏi "thành phần ML đang là bản nào, học tới ngày nào, số đo thẩm định bao
nhiêu, có đang bị cổng giữ ở mức nền không" phải ghép từ sáu nơi: ba gói joblib, hai tệp trọng số
và hiệu chỉnh, sổ học trực tuyến, báo cáo tác tử, kho tri thức, sổ kỹ năng đã công bố. Không nơi
nào ghi lại lúc một mô hình ĐỔI ĐỊNH NGHĨA hay ĐỔI TRẠNG THÁI (từ bị cổng giữ sang có hiệu lực).

Mỗi mục của sổ có:

* ``definition`` — thứ ĐỊNH NGHĨA mô hình: loại, phiên bản lược đồ/chính sách, siêu tham số đặt
  trước, dấu vân tay danh sách đặc trưng. ``fingerprint`` là SHA-256 của khối này. Kết quả của một
  lần học (cấu hình được chọn, trọng số, ngày học) KHÔNG nằm ở đây: học lại mỗi ngày không phải là
  đổi mô hình.
* ``training`` — học tới ngày nào, cửa sổ, các lát thời gian.
* ``validation`` — số đo ngoài mẫu mà chính mô hình ghi lúc học, hoặc sổ chấm của nó.
* ``deployment`` — một trong ``DEPLOYMENTS``, đọc từ CỔNG của chính mô hình (trust, quality_pass,
  promotion, gate), không suy từ giá trị xác suất:

  - ``production``  đang góp vào xác suất công bố;
  - ``gated``       nằm trong chuỗi nhưng cổng của nó đang giữ ở mức nền / mặc định;
  - ``shadow``      chạy và được chấm mỗi kỳ, không bao giờ đổi xác suất công bố;
  - ``missing``     không đọc được hồ sơ — phải xem, vì bước dự báo coi gói hỏng là "chưa có".

Sổ lịch sử ``history.csv`` chỉ NỐI THÊM: một dòng mỗi lần ``(fingerprint, deployment)`` của một mô
hình khác dòng cuối của chính nó. Đó là nhật ký đề bạt / hạ cổng / đổi định nghĩa, và là thứ để biết
phải quay về bản nào khi cần lùi. Hai thành phần co theo ``trust`` LIÊN TỤC (ML, Cầu Kèo) chỉ được
ghi khi đổi ĐỊNH NGHĨA: trust của chúng học lại mỗi ngày và dao động quanh 0, nên "vừa qua 0" không
phải một lần đề bạt — giá trị trust từng ngày nằm trong ``registry.json`` và lịch sử git của nó.

Engine Vietlott (`vietlott/`) là dự án tự đủ và giữ sổ riêng (checkpoint có phiên bản, sổ
``ml-ledger.jsonl``, lệnh ``vietlott forecast scoreboard``); sổ này không chép lại nó.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from collections.abc import Callable
from pathlib import Path

import joblib
import numpy as np

import ml.ml_models  # noqa: F401 - đăng ký tên module cũ mà pack joblib ghi trước đợt gom còn nhắc tới
from core.atomic_io import atomic_write_text
from core.paths import REPO_ROOT
from ensemble.ensemble_components import COMPONENT_KEYS, COMPONENT_POLICY
from ensemble.ensemble_utils import load_ensemble_weights, weights_provenance
from evaluation import regional_benchmark
from evaluation.skill_monitor import evaluate as evaluate_skill
from evaluation.skill_monitor import graded_series
from ml.cau_keo_ml import trust_from_pack

SCHEMA_VERSION = 1
MODES: tuple[str, ...] = ("loto", "de")
DEPLOYMENTS: tuple[str, ...] = ("production", "gated", "shadow", "missing")
OUT_DIR = Path("evaluation") / "model_registry"
REGISTRY = OUT_DIR / "registry.json"
HISTORY = OUT_DIR / "history.csv"
HISTORY_FIELDS = ["first_seen", "model_id", "fingerprint", "deployment", "reason"]
_SCALARS = (str, int, float, bool, type(None))


def _json(value: object) -> object:
    """Giá trị JSON thuần của một trường hồ sơ; kiểu numpy thành kiểu Python, số không hữu hạn thành ``None``."""
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float):
        return round(value, 12) if np.isfinite(value) else None
    if isinstance(value, _SCALARS):
        return value
    if isinstance(value, dict):
        return {str(key): _json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json(item) for item in value]
    return type(value).__name__


def digest(value: object) -> str:
    """SHA-256 của dạng JSON chuẩn (khoá đã xếp): cùng nội dung thì cùng mã trên mọi máy."""
    canonical = json.dumps(_json(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _pick(record: dict, keys: tuple[str, ...]) -> dict:
    return {key: _json(record[key]) for key in keys if key in record}


def _file_sha256(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def _entry(model_id: str, role: str, *, artifact: Path | None, root: Path, definition: dict, training: dict,
           validation: dict, deployment: str, reason: str, continuous_trust: bool = False,
           hash_artifact: bool = True) -> dict:
    if deployment not in DEPLOYMENTS:
        raise ValueError(f"trạng thái triển khai lạ: {deployment}")
    product, _, rest = model_id.partition("/")
    mode = rest.rsplit("/", 1)[-1] if rest.rsplit("/", 1)[-1] in MODES else None
    return {
        "model_id": model_id,
        "product": product,
        "mode": mode,
        "role": role,
        "artifact": artifact.relative_to(root).as_posix() if artifact is not None else None,
        "artifact_sha256": _file_sha256(artifact) if artifact is not None and hash_artifact else None,
        "definition": definition,
        "fingerprint": digest(definition),
        "training": training,
        "validation": validation,
        "deployment": deployment,
        "deployment_reason": reason,
        # Trạng thái suy từ một trust liên tục học lại mỗi ngày: sổ lịch sử không ghi mỗi lần nó qua 0.
        "continuous_trust": continuous_trust,
    }


def _missing(model_id: str, role: str, artifact: Path, root: Path, error: Exception) -> dict:
    return _entry(model_id, role, artifact=artifact, root=root, definition={}, training={}, validation={},
                  deployment="missing", reason=f"không đọc được hồ sơ: {type(error).__name__}")


def _guarded(model_id: str, role: str, artifact: Path, root: Path, build: Callable[[], dict]) -> dict:
    """Một hồ sơ hỏng không được làm mất cả sổ: mục ấy thành ``missing``, các mục khác vẫn được ghi."""
    try:
        return build()
    except (OSError, ValueError, KeyError, TypeError, EOFError, AttributeError, ImportError, IndexError) as error:
        return _missing(model_id, role, artifact, root, error)


def _features(pack: dict) -> dict:
    names = [str(name) for name in pack.get("features", [])]
    return {"count": len(names), "sha256": digest(names)}


def _trust_status(trust: float, what: str) -> tuple[str, str]:
    if trust > 0.0:
        share = f"{trust * 100:.3g}".replace(".", ",")
        return "production", (f"trust {share}%: xác suất công bố của {what} là {share}% xác suất thô cộng phần "
                              "còn lại ở mức nền")
    return "gated", f"trust 0: kỹ năng thẩm định không dương, xác suất công bố của {what} bằng mức nền"


def ml_component(root: Path, mode: str) -> dict:
    model_id, role, path = f"xsmb/ml/{mode}", "Thành phần ML", root / "models" / f"ml_{mode}.joblib"

    def build() -> dict:
        pack = joblib.load(path)
        definition = {
            **_pick(pack, ("model_type", "feature_schema_version", "window_days", "neg_ratio",
                           "calibration_prevalence", "training_recency_half_life_days",
                           "calibration_recency_half_life_days", "trust_policy_version")),
            "features": _features(pack),
        }
        deployment, reason = _trust_status(float(pack["model_trust"]), "thành phần ML")
        return _entry(
            model_id, role, artifact=path, root=root, definition=definition,
            training=_pick(pack, ("trained_through_date", "calib_start", "selection_start", "val_start",
                                  "selected_candidate")),
            validation=_pick(pack, ("val_logloss", "val_brier", "baseline_logloss", "baseline_brier",
                                    "logloss_skill", "brier_skill", "quality_pass", "model_trust",
                                    "selection_logloss", "selection_brier")),
            deployment=deployment, reason=reason, continuous_trust=True,
        )

    return _guarded(model_id, role, path, root, build)


def cau_keo_component(root: Path, mode: str) -> dict:
    model_id, role, path = f"xsmb/cau_keo/{mode}", "Thành phần Cầu Kèo", root / "models" / f"cau_keo_{mode}.joblib"

    def build() -> dict:
        pack = joblib.load(path)
        trust, base = trust_from_pack(pack)  # lối đọc DUY NHẤT của luật tin cầu-kèo
        definition = {
            **_pick(pack, ("model_type", "neg_ratio", "calibration_prevalence", "calendar_contract",
                           "trust_policy_version")),
            "features": _features(pack),
            "component_policy": COMPONENT_POLICY.get("cau"),
        }
        deployment, reason = _trust_status(trust, "Cầu Kèo")
        return _entry(
            model_id, role, artifact=path, root=root, definition=definition,
            training=_pick(pack, ("trained_through_date", "trained_at", "calib_start", "val_start")),
            validation={**_pick(pack, ("val_logloss", "val_brier", "logloss_skill", "brier_skill")),
                        "model_trust": _json(trust), "base_rate": _json(base)},
            deployment=deployment, reason=reason, continuous_trust=True,
        )

    return _guarded(model_id, role, path, root, build)


def stacking(root: Path, mode: str) -> dict:
    model_id, role, path = f"xsmb/stacking/{mode}", "Tầng xếp chồng", root / "models" / f"meta_{mode}.joblib"

    def build() -> dict:
        pack = joblib.load(path)
        trust = float(pack.get("meta_trust") or 0.0)
        if pack.get("quality_pass") and trust > 0.0:
            deployment, reason = "production", f"qua cổng chất lượng, trust {trust:.3f}"
        else:
            deployment = "gated"
            reason = (
                f"chưa đủ lịch sử ({pack.get('history_days')}/{pack.get('minimum_history_days')} kỳ)"
                if pack.get("status") == "insufficient_history"
                else "không thắng cả tổ hợp tuyến tính lẫn dự báo hằng số trên lát thẩm định"
            )
        return _entry(
            model_id, role, artifact=path, root=root,
            definition={**_pick(pack, ("schema_version", "minimum_history_days")),
                        "components": list(COMPONENT_KEYS)},
            training=_pick(pack, ("status", "component_tier", "history_days", "tier_maturity_days",
                                  "trained_through_target_date")),
            validation=_pick(pack, ("quality_pass", "meta_trust", "logloss_skill", "brier_skill",
                                    "constant_logloss_skill", "constant_brier_skill", "validation_logloss",
                                    "baseline_validation_logloss", "constant_validation_logloss")),
            deployment=deployment, reason=reason,
        )

    return _guarded(model_id, role, path, root, build)


def ensemble_weights(root: Path, mode: str) -> dict:
    model_id, role = f"xsmb/ensemble_weights/{mode}", "Trọng số tổ hợp"
    path = root / "data" / "ensemble" / f"weights_{mode}.json"

    def build() -> dict:
        # Luật của kho: trọng số CHỈ qua load_ensemble_weights, xuất xứ và siêu dữ liệu học CHỈ qua
        # weights_provenance. Sổ không tự mở tệp trọng số; tệp chỉ được băm để biết bản nào đang có hiệu lực.
        weights = load_ensemble_weights(root / "data", mode)
        provenance = weights_provenance(root / "data", mode)
        origin = provenance["xuat_xu"]
        words = {"da_hoc": "vector đã học và đã qua cổng thẩm định ngoài mẫu",
                 "bi_tu_choi": "cổng đã đo và từ chối đề bạt: đang chạy vector mặc định",
                 "khong_co_ho_so": "không có hồ sơ hợp lệ: đang chạy vector mặc định"}
        return _entry(
            model_id, role, artifact=path, root=root,
            definition={**_pick(provenance, ("window_days", "half_life_days")),
                        "components": list(COMPONENT_KEYS), "component_policy": dict(COMPONENT_POLICY)},
            training={"weights": _json(weights.as_dict()), "days_used": provenance.get("days_used")},
            validation={"origin": origin, "gate_reason": provenance.get("ly_do"),
                        **_json(provenance.get("tham_dinh") or {})},
            # Vector đang hiệu lực (đã học hay mặc định) luôn là vector tạo ra xác suất công bố.
            deployment="production" if origin != "khong_co_ho_so" else "missing",
            reason=words[origin],
        )

    return _guarded(model_id, role, path, root, build)


def calibration(root: Path, mode: str) -> dict:
    model_id, role = f"xsmb/calibration/{mode}", "Hiệu chỉnh xác suất"
    path = root / "data" / "ensemble" / f"calibration_{mode}.json"

    def build() -> dict:
        stored = json.loads(path.read_text(encoding="utf-8"))
        selection = stored.get("selection") or {}
        chosen = selection.get("chosen", "identity")
        identity = chosen == "identity"
        return _entry(
            model_id, role, artifact=path, root=root,
            definition=_pick(stored, ("schema_version", "window_days", "half_life_days")),
            training={"params": _json(stored.get("params")), **_pick(stored, ("chronological_split",))},
            validation=_pick(selection, ("chosen", "selected", "fit_days", "holdout_days", "brier_by_candidate")),
            deployment="gated" if identity else "production",
            reason=("giữ phép đồng nhất: chưa ứng viên hiệu chỉnh nào thắng trên khối giữ riêng"
                    if identity else f"đang áp phép hiệu chỉnh «{chosen}» đã thắng trên khối giữ riêng"),
        )

    return _guarded(model_id, role, path, root, build)


def _online(root: Path, model_id: str, role: str, path: Path, *, shadow_only: bool) -> dict:
    def build() -> dict:
        state = json.loads(path.read_text(encoding="utf-8"))
        records = state.get("records") or []
        gate = (records[-1].get("gate") or {}) if records else {}
        learning = state.get("learning") or {}
        if shadow_only:
            deployment, reason = "shadow", "hệ tác tử chạy bóng: được chấm mỗi kỳ, không vào xác suất công bố"
        elif gate.get("active"):
            deployment, reason = "production", str(gate.get("reason", "cổng đề bạt đang mở"))
        else:
            deployment, reason = "shadow", str(gate.get("reason", "cổng đề bạt chưa mở"))
        return _entry(
            model_id, role, artifact=path, root=root,
            definition={"schema_version": state.get("schema_version"), "recipe": _json(state.get("recipe"))},
            training={"settled_draws": learning.get("n_settled"),
                      "history_through": (state.get("history") or {}).get("last_date"),
                      "records": len(records)},
            validation={"fast_loss": _json(learning.get("fast_loss")), "slow_loss": _json(learning.get("slow_loss")),
                        "gate_active": bool(gate.get("active", False))},
            deployment=deployment, reason=reason,
        )

    return _guarded(model_id, role, path, root, build)


def online_hedge(root: Path, mode: str) -> dict:
    return _online(root, f"xsmb/online_hedge/{mode}", "Học trực tuyến (Hedge hai trí nhớ)",
                   root / "data" / "forecast" / "online" / f"{mode}.json", shadow_only=False)


def agents(root: Path, mode: str) -> dict:
    return _online(root, f"xsmb/agents/{mode}", "Hệ ba tác tử",
                   root / "data" / "forecast" / "online" / f"agents_{mode}.json", shadow_only=True)


def knowledge_base(root: Path) -> dict:
    model_id, role, path = "xsmb/knowledge_base", "Kho tri thức", root / "data" / "forecast" / "knowledge" / "kb.json"

    def build() -> dict:
        kb = json.loads(path.read_text(encoding="utf-8"))
        rules = kb.get("rules") or []
        return _entry(
            model_id, role, artifact=path, root=root,
            definition={"version": kb.get("version"), "alpha_budget": kb.get("alpha_budget"),
                        "config": _json(kb.get("config")), "rule_config": _json(kb.get("rule_config"))},
            training={"source_date": kb.get("source_date"), "draws": kb.get("draws"),
                      "batches": len(kb.get("batches") or []), "rules": len(rules),
                      "retired": len(kb.get("retired") or [])},
            validation={"rules_by_status": _json(_count(rule.get("status", "") for rule in rules))},
            deployment="shadow",
            reason="khung mô tả và phép kiểm tiến cứu: không vào tổ hợp xác suất",
        )

    return _guarded(model_id, role, path, root, build)


def cage_bayes(root: Path) -> dict:
    """Bộ máy Bayes theo đoạn của lồng chục/đơn vị (``forecast.cage_bayes``): luôn chạy bóng.

    Lý do triển khai không mang con số (z, e đổi mỗi kỳ, mà sổ lịch sử chỉ ghi khi trạng thái hay lý do đổi).
    """
    model_id, role = "xsmb/cage_bayes", "Bộ máy Bayes theo đoạn (lồng chục, đơn vị)"
    path = root / "data" / "forecast" / "cage_bayes" / "summary.json"

    def build() -> dict:
        summary = json.loads(path.read_text(encoding="utf-8"))
        whole = summary["windows"]["all"]
        prospective = summary["prospective"]
        promotion = summary["promotion"]
        if promotion["eligible"]:
            reason = "chạy bóng: đủ điều kiện xét đưa vào tổ hợp, chờ quyết định riêng"
        else:
            reason = ("chạy bóng: chưa đủ điều kiện vào tổ hợp (cần walk-forward LOTO z ≥ 2,326 và phép kiểm "
                      "tiến cứu vượt ngưỡng)")
        return _entry(
            model_id, role, artifact=path, root=root,
            definition={"version": summary.get("version"), "config": _json(summary.get("config")),
                        "warmup": summary.get("warmup")},
            training={"data_through": summary.get("data_through"), "draws": summary.get("draws"),
                      "registered_on": prospective.get("registered_on")},
            validation={"walk_forward_draws": whole["loto"]["draws"],
                        "loto_gain_nats": _json(whole["loto"]["total"]), "loto_z": _json(whole["loto"]["z"]),
                        "de_gain_nats": _json(whole["de"]["total"]), "de_z": _json(whole["de"]["z"]),
                        "prospective_draws": prospective.get("draws"),
                        "prospective_log10_e": _json(prospective.get("log10_e")),
                        "prospective_evidence": bool(prospective.get("evidence")),
                        "eligible": bool(promotion["eligible"])},
            deployment="shadow", reason=reason,
        )

    return _guarded(model_id, role, path, root, build)


def _count(values) -> dict[str, int]:
    out: dict[str, int] = {}
    for value in values:
        out[str(value)] = out.get(str(value), 0) + 1
    return dict(sorted(out.items()))


def published_forecast(root: Path, mode: str) -> dict:
    """Vector xác suất ĐÃ CÔNG BỐ — thứ người xem nhận — với sổ chấm ngoài mẫu của chính nó."""
    model_id, role = f"xsmb/published/{mode}", "Xác suất đã công bố"
    ledger = root / "data" / "evaluation" / "model_quality" / "published_skill.csv"

    def build() -> dict:
        days, skill = graded_series(root / "data", mode)
        monitor = next((check.as_dict() for check in evaluate_skill(root / "data") if check.mode == mode), {})
        stderr = float(skill.std(ddof=1) / np.sqrt(len(skill))) if len(skill) > 1 else float("nan")
        mean = float(skill.mean()) if len(skill) else float("nan")
        return _entry(
            model_id, role, artifact=ledger, root=root,
            definition={"components": list(COMPONENT_KEYS), "component_policy": dict(COMPONENT_POLICY),
                        "level_anchor": "finalize_blend"},
            training={"first_graded": days[0] if days else None, "last_graded": days[-1] if days else None},
            validation={"graded_draws": len(days), "mean_logloss_skill": _json(mean), "stderr": _json(stderr),
                        "ci95_low": _json(mean - 1.96 * stderr), "ci95_high": _json(mean + 1.96 * stderr),
                        "monitor_state": monitor.get("state"), "monitor_alarm": monitor.get("alarm")},
            deployment="production",
            reason="vector ghi trước kỳ quay và in trên trang; chấm bằng chính tệp đã công bố",
        )

    return _guarded(model_id, role, ledger, root, build)


def regional_forecast(root: Path, region: str) -> dict:
    """Miền Trung / miền Nam: luật đang "công bố" là dự báo đều; sổ ghi vì sao chưa mô hình nào được thay nó.

    Phép chấm của miền được workflow đồng bộ miền dựng lại mỗi ngày, ngoài pipeline XSMB. Mục này vì thế
    chỉ chép KẾT LUẬN (mô hình nào thắng, ở đài nào) — thứ hiếm khi đổi — và trỏ tới tệp phép chấm cho mọi
    con số; nó không chép số đo từng ngày, vốn sẽ cũ đi giữa hai lượt pipeline.
    """
    model_id, role = f"xs{region}/forecast", "Luật xác suất của đài miền"
    path = root / "data" / regional_benchmark.OUT

    def build() -> dict:
        report = json.loads(path.read_text(encoding="utf-8"))
        block = report["regions"][region]
        edges = {mode: list(scored.get("edge", [])) for mode, scored in block["modes"].items()}
        return _entry(
            model_id, role, artifact=path, root=root, hash_artifact=False,
            definition={"law": "deu", "benchmark": _json(report["config"])},
            training={},
            validation={"regional_edge": edges,
                        "station_edges": [_pick(row, ("province", "mode", "model", "post_hoc"))
                                          for row in block.get("station_edges", [])]},
            deployment="production",
            reason=("dự báo đều: không mô hình nào thắng nó ngoài mẫu ở cấp miền; không công bố con số dự đoán"
                    if not any(edges.values()) else
                    "dự báo đều: có mô hình thắng ngoài mẫu nhưng chưa qua phép kiểm tiến cứu, nên chưa thay luật"),
        )

    return _guarded(model_id, role, path, root, build)


def collect(root: Path) -> list[dict]:
    entries = []
    for mode in MODES:
        entries += [published_forecast(root, mode), ensemble_weights(root, mode), calibration(root, mode),
                    ml_component(root, mode), cau_keo_component(root, mode), stacking(root, mode),
                    online_hedge(root, mode), agents(root, mode)]
    entries.append(knowledge_base(root))
    entries.append(cage_bayes(root))
    entries += [regional_forecast(root, region) for region in ("mt", "mn")]
    return sorted(entries, key=lambda entry: entry["model_id"])


def data_through(root: Path) -> str | None:
    """Ngày kỳ XSMB mới nhất của sổ chuẩn: mốc thời gian của cả sổ đăng ký."""
    path = root / "data" / "xsmb-2-digits.csv"
    if not path.is_file():
        return None
    with path.open("r", encoding="utf-8", newline="") as handle:
        days = [row["date"] for row in csv.DictReader(handle) if row.get("date")]
    return max(days) if days else None


def update_history(path: Path, entries: list[dict], as_of: str | None) -> list[dict]:
    """Nối một dòng cho mỗi mô hình có ``(fingerprint, deployment)`` khác dòng cuối của chính nó.

    Dòng cũ giữ nguyên từng byte. Trả các dòng vừa nối.
    """
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    last: dict[str, tuple[str, str]] = {}
    for row in csv.DictReader(io.StringIO(existing)):
        last[row["model_id"]] = (row["fingerprint"], row["deployment"])
    added = [
        {"first_seen": as_of or "", "model_id": entry["model_id"], "fingerprint": entry["fingerprint"],
         "deployment": entry["deployment"], "reason": entry["deployment_reason"]}
        for entry in entries
        if _changed(last.get(entry["model_id"]), entry)
    ]
    if added:
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=HISTORY_FIELDS, lineterminator="\n")
        if not existing:
            writer.writeheader()
        writer.writerows(added)
        atomic_write_text(path, existing + buffer.getvalue())
    return added


def _changed(last: tuple[str, str] | None, entry: dict) -> bool:
    if last is None or last[0] != entry["fingerprint"]:
        return True
    return not entry["continuous_trust"] and last[1] != entry["deployment"]


def build(root: Path) -> dict:
    entries = collect(root)
    return {
        "schema_version": SCHEMA_VERSION,
        "data_through": data_through(root),
        "summary": _count(entry["deployment"] for entry in entries),
        "models": entries,
    }


def run(root: Path) -> Path:
    """Ghi ``data/evaluation/model_registry/registry.json`` và nối ``history.csv``. Không dấu giờ ghi."""
    registry = build(root)
    out = root / "data" / REGISTRY
    out.parent.mkdir(parents=True, exist_ok=True)
    update_history(root / "data" / HISTORY, registry["models"], registry["data_through"])
    atomic_write_text(out, json.dumps(registry, ensure_ascii=False, indent=2) + "\n")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sổ đăng ký mô hình của chuỗi dự báo")
    parser.add_argument("--strict", action="store_true", help="thoát mã 1 nếu có mô hình không đọc được hồ sơ")
    args = parser.parse_args(argv)
    path = run(REPO_ROOT)
    registry = json.loads(path.read_text(encoding="utf-8"))
    print("Wrote:", path, registry["summary"])
    missing = [entry["model_id"] for entry in registry["models"] if entry["deployment"] == "missing"]
    if missing:
        print("Không đọc được hồ sơ:", ", ".join(missing))
    return int(bool(missing) and args.strict)


if __name__ == "__main__":
    raise SystemExit(main())
