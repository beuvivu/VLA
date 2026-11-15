"""Pipeline ba tác tử: cùng sổ học, căn cứ XAI và công bố shadow minh bạch.

Từ 15-11-2026 module này mang luôn bộ nhớ (`knowledge.py`) và kiểm hồi cứu (`benchmark.py`) cũ.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import datetime, time, timedelta
from functools import cached_property
from pathlib import Path

import numpy as np
import pandas as pd

from core.atomic_io import atomic_write_text
from core.calendar_alignment import known_non_draw_days, missing_calendar_dates
from core.time_policy import VIETNAM_TZ, now_vietnam
from core.xsmb_domain import baseline_rate
from ensemble.pick_diversity import diversified_order
from forecast import online_learning as online
from forecast.knowledge_base import ContextMemory
from forecast.online_learning import _history, _outcomes

from .algorithms import AGENT_POLICY, LABELS, AlgorithmEnsemble, EnsembleResult


# --- Bộ nhớ (trước 15-11-2026: xsmb_agents/knowledge.py) ------------------------------------------
#
# Adapter bộ nhớ: tiền tố lịch sử, ngữ cảnh và luật của kho hiện hữu.

class KnowledgeBaseManager:
    """Chuẩn hóa một tiền tố duy nhất cho mọi tác tử; không nhìn nhãn đích."""

    def __init__(self, frame: pd.DataFrame, *, target_date: str | None = None) -> None:
        if target_date is not None:
            # Lọc TRƯỚC khi chuẩn hóa để cả dữ liệu tương lai hỏng cũng không
            # thay đổi kết quả hoặc làm lộ thông tin cho dự báo quá khứ.
            frame = frame.loc[frame["date"].astype(str) < target_date]
        self.frame = _history(frame)
        gaps = set(missing_calendar_dates(self.frame["date"])) - known_non_draw_days()
        if gaps:
            raise ValueError(f"Thiếu kết quả trong lịch sử (gap): {sorted(gaps)[:3]}")

    @cached_property
    def outcomes(self) -> dict[str, np.ndarray]:
        """Chỉ báo theo kỳ: một lớp Đặc Biệt, tối đa 27 con LOTO."""
        return {mode: _outcomes(mode, self.frame) for mode in ("de", "loto")}

    @cached_property
    def memories(self) -> dict[str, ContextMemory]:
        """Vectơ 300 chiều dùng lại bộ truy xuất và khoảng bỏ chồng cửa sổ."""
        return {mode: ContextMemory(y) for mode, y in self.outcomes.items()}

    def retrieve(self, mode: str, *, at: int | None = None, k: int = 20) -> list[dict]:
        """K ngữ cảnh quá khứ đã biết kết quả, trước khoảng cách 30 kỳ."""
        t = len(self.frame) if at is None else at
        idx, similarities = self.memories[mode].neighbours(t, k)
        return [{"date": str(self.frame.iloc[int(i)]["date"]), "index": int(i),
                 "similarity": float(s)} for i, s in zip(idx, similarities, strict=True)]

    def analog_probability(self, mode: str, t: int) -> np.ndarray:
        """Đặc trưng truy xuất có co về nền; chưa là xác suất công bố."""
        idx, _ = self.memories[mode].neighbours(t, 20)
        y = self.outcomes[mode]
        return (y[idx].sum(axis=0) + 100 * baseline_rate(mode)) / (len(idx) + 100)

    def short_memory(self, mode: str) -> dict:
        """Tần suất hai cửa sổ gần nhất; số kỳ thực được ghi cùng mẫu số."""
        y = self.outcomes[mode]
        return {str(w): {"draws": min(w, len(y)), "rates": y[-w:].mean(axis=0).tolist()}
                for w in (10, 30)}

    def matching_rules(self, document: dict) -> list[dict]:
        """Chỉ truy xuất luật đã đăng ký; ảnh chụp cũ không thành bằng chứng mới."""
        current = self.outcomes["loto"][-1]
        return [{"id": r["id"], "text": r["text"], "status": r["status"],
                 "then": int(r["then"])} for r in document.get("rules", [])
                if r.get("status") != "het-han" and current[int(r["if"])]]


# --- Bộ máy dự báo (trước 15-11-2026: xsmb_agents/engine.py) --------------------------------------
#
# Pipeline ba tác tử: cùng sổ học, căn cứ XAI và công bố shadow minh bạch.

def retire_superseded_ledgers(online_dir: Path) -> list[Path]:
    """Cất nguyên sổ ba tác tử của định nghĩa đã nghỉ; sổ của định nghĩa đang chạy bắt đầu rỗng.

    Mỗi định nghĩa tác tử có SỔ RIÊNG (họ ``online.AGENT_RECIPE``): trí nhớ Hedge, bước chọn
    η/độ quên và cổng đề bạt không được thừa hưởng điểm do một bộ dự báo khác kiếm được. Sổ cũ chỉ
    được ĐỔI TÊN thành ``agents_<mode>.<họ>.json`` — từng byte giữ nguyên, không chấm lại. Kiểm cả
    hai sổ trước khi đổi tên cái nào; họ lạ (ví dụ của một bản triển khai mới hơn) hay bản cất đã
    có đều làm dừng sạch.
    """
    plan = []
    for mode in ("de", "loto"):
        path = Path(online_dir) / f"agents_{mode}.json"
        if not path.exists():
            continue
        try:
            family = json.loads(path.read_text(encoding="utf-8"))["recipe"]["family"]
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise ValueError("Không đọc được sổ ba tác tử (corrupt state)") from exc
        if family == online.AGENT_RECIPE["family"]:
            continue
        if family not in online.RETIRED_AGENT_FAMILIES:
            raise ValueError(f"Sổ ba tác tử mang định nghĩa không được đăng ký: {family!r}")
        target = path.with_name(f"agents_{mode}.{family}.json")
        if target.exists():
            raise ValueError(f"Đã có bản cất {target.name}; không ghi đè")
        plan.append((path, target))
    for path, target in plan:
        os.replace(path, target)
    return [target for _, target in plan]


class MetaLearner:
    """Adapter lõi Hedge hiện hữu; không có vòng chấm hoặc sổ học thứ hai."""

    def __init__(self, mode: str, path: Path) -> None:
        self.mode, self.path = mode, Path(path)
        self.state = online.load_state(self.path, mode, profile="agents")
        # Sổ đúng họ chỉ chứa bản ghi của định nghĩa đang chạy; kiểm cả khối lưu trữ ngay khi nạp,
        # trước mọi advance/save.
        if any(record.get("agent_policy") != AGENT_POLICY for record in online._all_records(self.state)):
            raise ValueError("Định nghĩa tác tử trong sổ không khớp họ sổ")

    def advance(self, frame: pd.DataFrame, incumbent: np.ndarray, target_date: str,
                predictions: dict[str, np.ndarray], *, now: datetime) -> dict:
        """Chốt mỗi kết quả đúng một lần và ghi trọng số đã chọn cho kỳ mới."""
        self.state, record = online.advance(self.state, frame, incumbent, target_date,
                                            now=now, expert_predictions=predictions)
        return record

    def save(self, *, forecast_target: str | None = None,
             clock: Callable[[], datetime] | None = None) -> None:
        """Kiểm checksum, cấu trúc và điểm trước khi thay sổ nguyên tử."""
        online.save_state(self.path, self.state, forecast_target=forecast_target, clock=clock)

    def confidence_matrix(self) -> dict:
        """Loss của từng tầng, cỡ mẫu thật và hiệu quả so với nền."""
        settled = [r for r in online._all_records(self.state) if online._is_scored(r)]
        rows = {}
        for name in online.AGENT_EXPERTS:
            scores = [r["settlement"]["scores"] for r in settled]
            recent = scores[-30:]
            gain = online._gain_stats([s["constant"]["logloss"] - s[name]["logloss"]
                                       for s in recent])
            rows[name] = {
                "draws": len(scores), "recent_draws": len(recent),
                "brier": float(np.mean([s[name]["brier"] for s in scores])) if scores else None,
                "logloss": float(np.mean([s[name]["logloss"] for s in scores])) if scores else None,
                "recent_gain": gain,
            }
        return rows

    def calibration_bands(self, probabilities: list[float] | np.ndarray) -> list[dict | None]:
        """Sai số hiệu chuẩn theo nhóm, SE khối theo kỳ; thiếu mẫu trả null.

        Đây là khoảng xấp xỉ cho nhóm xác suất tương tự, không phải chứng
        minh về một con cụ thể hay xác suất mô hình đúng. Giải nén sổ một
        lần cho cả vector; các con cùng nhóm dùng chung sai số và cỡ mẫu.
        """
        width = .01 if self.mode == "de" else .05
        buckets = np.floor(np.asarray(probabilities, dtype=float) / width)
        residuals = {bucket: [] for bucket in np.unique(buckets)}
        for record in online._all_records(self.state):
            if not online._is_scored(record):
                continue
            p = np.asarray(record["experts"]["incumbent"])
            y = np.asarray(record["settlement"]["labels"])
            historical_buckets = np.floor(p / width)
            for bucket, values in residuals.items():
                selected = historical_buckets == bucket
                if selected.any():
                    values.append(float((y[selected] - p[selected]).mean()))
        stats_by_bucket = {bucket: online._gain_stats(values)
                           for bucket, values in residuals.items() if len(values) >= 60}
        bands = []
        for probability, bucket in zip(probabilities, buckets, strict=True):
            stats = stats_by_bucket.get(bucket)
            if stats is None:
                bands.append(None)
                continue
            center, radius = float(probability) + stats["mean"], 1.96 * stats["se"]
            bands.append({"lower": max(0.0, center - radius), "upper": min(1.0, center + radius),
                          "draws": len(residuals[bucket]), "method": "Xấp xỉ 95% theo nhóm, SE khối 7 kỳ",
                          "per_number_guarantee": False})
        return bands


class PredictiveEngine:
    """Điều phối ba lớp trên dữ liệu chuẩn, sổ tiến cứu và artifact hiện hữu."""

    def run(self, data_dir: Path, *, now: datetime | None = None) -> dict:
        """Chạy dưới một khóa; ngắt giữa chừng được khôi phục từ sổ đóng băng."""
        data_dir = Path(data_dir)
        # Đồng hồ thật được đọc SAU khi lấy khóa và SAU huấn luyện. ``now``
        # chỉ là đồng hồ cố định được tiêm cho kiểm thử/tái hiện có chủ đích.
        clock = (lambda: online._clock(now)) if now is not None else (
            lambda: online._clock(now_vietnam()))
        with online._locked(data_dir / "forecast" / "agents" / "engine.lock"):
            return self._run_locked(data_dir, clock)

    def _run_locked(self, data_dir: Path, clock: Callable[[], datetime]) -> dict:
        now = clock()
        raw = pd.read_csv(data_dir / "xsmb.csv", dtype=str)
        knowledge = KnowledgeBaseManager(raw)
        frame = knowledge.frame
        anchor = str(frame.iloc[-1]["date"])
        target = (online._date(anchor) + timedelta(days=1)).isoformat()
        kb_path = data_dir / "forecast" / "knowledge" / "kb.json"
        document = json.loads(kb_path.read_text(encoding="utf-8")) if kb_path.exists() else {}
        # Luật được update bởi knowledge_base.py trong cùng lượt pipeline;
        # snapshot cũ chỉ được nêu là cũ, không nâng trạng thái hay cộng xác suất.
        matches = knowledge.matching_rules(document)
        modes = {}
        # Cất sổ của định nghĩa đã nghỉ, rồi nạp (và kiểm) CẢ HAI sổ trước khi chốt kỳ nào: sổ Đặc
        # Biệt không được ghi xong rồi mới phát hiện sổ LOTO mang định nghĩa không hiểu được.
        retire_superseded_ledgers(data_dir / "forecast" / "online")
        learners = {mode: MetaLearner(mode, data_dir / "forecast" / "online" / f"agents_{mode}.json")
                    for mode in ("de", "loto")}
        for mode in ("de", "loto"):
            path = data_dir / "forecast" / "predict" / f"predict_next_{mode}_all_{target}.csv"
            prediction_frame, incumbent = online._prediction_frame(path, mode)
            for column, expected in (("target_date", target), ("anchor_date", anchor)):
                if column in prediction_frame and set(prediction_frame[column].astype(str)) != {expected}:
                    raise ValueError("Dự báo sản xuất không khớp ngày neo/ngày đích")
            learner = learners[mode]
            existing = next((r for r in learner.state["records"] if r["target_date"] == target), None)
            if existing is not None:
                result = EnsembleResult({name: np.asarray(existing["experts"][name])
                                         for name in ("statistical", "probabilistic", "pattern")},
                                        existing["agent_diagnostics"])
            else:
                # Kiểm giờ và tiền tố trước tác vụ huấn luyện tốn thời gian.
                if now >= datetime.combine(online._date(target), online.FORECAST_CUTOFF,
                                           online.VIETNAM_TZ):
                    raise ValueError("Đã quá cutoff 18:00 ICT, không tạo dự báo hồi cứu")
                result = AlgorithmEnsemble(knowledge).predict(mode, incumbent)
            record = learner.advance(frame, incumbent, target, result.probabilities, now=clock())
            if existing is None:
                record["agent_policy"] = AGENT_POLICY
                record["agent_diagnostics"] = result.diagnostics
                record["knowledge_snapshot"] = {
                    "short_term": knowledge.short_memory(mode),
                    "similar_contexts": knowledge.retrieve(mode),
                    "matching_rules": matches if mode == "loto" else [],
                    "rule_snapshot_date": document.get("source_date"),
                }
                learner.state["records"][-1] = record
            if existing is None and clock() >= datetime.combine(
                    online._date(target), online.FORECAST_CUTOFF, online.VIETNAM_TZ):
                raise ValueError("Đã quá cutoff 18:00 ICT trước khi ghi sổ")
            learner.save(forecast_target=target if existing is None else None, clock=clock)
            modes[mode] = self.explain(learner, record)
        report = {"schema_version": 1, "anchor_date": anchor, "target_date": target,
                  "generated_at": min(item["generated_at"] for item in modes.values()),
                  "status": "shadow", "modes": modes}
        # Khoá XẾP THEO TÊN. Kỳ đã có trong sổ được nạp lại từ sổ (ghi bằng `sort_keys`), kỳ mới thì dựng
        # tại chỗ theo thứ tự chèn: không xếp thì lượt chạy lại ghi cùng nội dung với thứ tự khoá khác
        # (11-11-2026: 271 dòng của báo cáo và cả tệp `xsmb-agents.json` đổi mà không giá trị nào đổi).
        atomic_write_text(data_dir / "forecast" / "agents" / "report.json",
                          json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False, sort_keys=True) + "\n")
        return report

    @staticmethod
    def explain(learner: MetaLearner, record: dict) -> dict:
        """Vết chứng cứ cộng được về đúng vector; phân biệt công bố và ứng viên."""
        mode = learner.mode
        base = baseline_rate(mode)
        incumbent = np.asarray(record["experts"]["incumbent"])
        candidate = np.asarray(record["mixture"])
        matrix = learner.confidence_matrix()
        n = matrix["constant"]["draws"]
        risks = ["Kỳ quay công bằng không có quy luật đảm bảo dự đoán trúng.",
                 "Ngữ cảnh và luật trễ có thể giống nhau chỉ do ngẫu nhiên; nhiều giả thuyết làm tăng nhiễu.",
                 "Các xác suất ứng viên đang được kiểm song song, chưa thay xác suất công bố."]
        if n < 60:
            risks.append(f"Chỉ có {n}/60 kỳ tiến cứu tối thiểu để ước lượng sai số hiệu chuẩn.")
        pattern = record["agent_diagnostics"]["pattern"]
        if pattern.get("status") == "fitted" and not pattern["converged"]:
            risks.append("Mạng mẫu hình chưa hội tụ trong giới hạn huấn luyện; cần đọc cùng loss tiến cứu.")
        if pattern.get("status") == "fitted" and pattern.get("trust") == 0:
            risks.append("Mạng mẫu hình chưa hơn mức nền trên 30 kỳ thẩm định nên độ tin bằng 0: "
                         "tác tử này phát đúng mức nền.")
        calibration_bands = learner.calibration_bands(incumbent)
        items = []
        for number in range(100):
            contributions = [{"agent": name, "label": LABELS[name], "weight": record['weights'][name],
                              "probability": float(record["experts"][name][number]),
                              "delta": record['weights'][name] * (record["experts"][name][number] - base)}
                             for name in online.AGENT_EXPERTS]
            lead = max(contributions, key=lambda row: abs(row["delta"]))
            items.append({"number": f"{number:02d}",
                          "published_probability": float(incumbent[number]),
                          "candidate_probability": float(candidate[number]),
                          "hit_probability_percent": float(100 * incumbent[number]),
                          "contributions": contributions,
                          "calibration_band": calibration_bands[number],
                          "reasoning_path": [
                              f"Chỉ dùng lịch sử đến {record['anchor_fingerprint']['last_date']}.",
                              "Tần suất làm tiên nghiệm cho Markov/đồ thị; mạng đọc đặc trưng chuỗi và ngữ cảnh tương tự.",
                              f"Đóng góp ứng viên mạnh nhất: {lead['label']}, trọng số {lead['weight']:.4f}.",
                              "Nền + tổng đóng góp = xác suất ứng viên; xác suất công bố lấy từ vector đã đóng băng.",
                          ], "risk_factors": risks})
        top = (diversified_order(incumbent, 5) if mode == "loto"
               else np.lexsort((np.arange(100), -incumbent))[:5].tolist())
        candidate_top = (diversified_order(candidate, 5) if mode == "loto"
                         else np.lexsort((np.arange(100), -candidate))[:5].tolist())
        return {"generated_at": record["generated_at"], "n_settled": n,
                "agent_policy": record["agent_policy"],
                "weights": record["weights"], "tuning": record["tuning"],
                "gate": record["gate"], "diagnostics": record["agent_diagnostics"],
                "knowledge": record["knowledge_snapshot"], "confidence_matrix": matrix,
                "top5": [items[i] for i in top],
                "candidate_top5": [items[i] for i in candidate_top], "items": items}


# --- Kiểm hồi cứu (trước 15-11-2026: xsmb_agents/benchmark.py) ------------------------------------
#
# Kiểm hồi cứu theo tiền tố; không ghi vào bất kỳ sổ tiến cứu nào.

def walk_forward(frame: pd.DataFrame, *, last: int = 60,
                 prediction_dir: Path | None = None) -> dict:
    """Dựng từng kỳ từ đúng tiền tố, học loss kỳ trước rồi chấm kỳ hiện tại.

    Đồng hồ lịch sử chỉ tồn tại trong bộ nhớ, không ghi/giả timestamp của
    dự báo thật. Mô hình đã thiết kế sau khi xem lịch sử: số đo này chỉ chẩn
    đoán, không phải bằng chứng tiến cứu hoặc giấy phép đề bạt.
    """
    knowledge = KnowledgeBaseManager(frame)
    clean = knowledge.frame
    if not isinstance(last, int) or isinstance(last, bool) or not 1 <= last <= len(clean) - 3:
        raise ValueError("Số kỳ kiểm phải từ 1 đến số kỳ lịch sử trừ 3")
    modes = {}
    for mode in ("de", "loto"):
        state = online.new_state(mode, profile="agents")
        losses = {name: [] for name in (*online.AGENT_EXPERTS, "mixture")}
        dates, recorded = [], 0
        for t in range(len(clean) - last, len(clean)):
            past = clean.iloc[:t]
            target = str(clean.iloc[t]["date"])
            if online._date(target) != online._date(str(past.iloc[-1]["date"])) + timedelta(days=1):
                continue
            incumbent = np.full(100, baseline_rate(mode))
            path = (prediction_dir / f"predict_next_{mode}_all_{target}.csv"
                    if prediction_dir is not None else None)
            if path is not None and path.exists():
                published, incumbent = online._prediction_frame(path, mode)
                for column, expected in (("target_date", target), ("anchor_date", past.iloc[-1]["date"])):
                    if column in published and set(published[column].astype(str)) != {expected}:
                        raise ValueError("Artifact đối chứng sai ngày đích/ngày neo")
                recorded += 1
            ensemble = AlgorithmEnsemble(KnowledgeBaseManager(past)).predict(mode, incumbent)
            state, record = online.advance(state, past, incumbent, target,
                now=datetime.combine(online._date(target), time(0), VIETNAM_TZ),
                expert_predictions=ensemble.probabilities)
            actual = knowledge.outcomes[mode][t]
            for name in losses:
                probability = record["mixture"] if name == "mixture" else record["experts"][name]
                losses[name].append(online.proper_losses(mode, probability, actual))
            dates.append(target)
        measured = {}
        for name, scores in losses.items():
            gain = [a["logloss"] - b["logloss"]
                    for a, b in zip(losses["constant"], scores, strict=True)]
            measured[name] = {
                "brier": float(np.mean([s["brier"] for s in scores])) if scores else None,
                "logloss": float(np.mean([s["logloss"] for s in scores])) if scores else None,
                "gain_vs_constant": online._gain_stats(gain),
            }
        modes[mode] = {"draws": len(dates), "first_date": dates[0] if dates else None,
                       "last_date": dates[-1] if dates else None,
                       "incumbent_recorded_draws": recorded,
                       "incumbent_missing_uses_constant": len(dates) - recorded,
                       "agents": measured}
    return {"schema_version": 1, "evidence_type": "retrospective_diagnostic",
            "prospective_draws": 0, "promotion_allowed": False,
            "input_fingerprint": online._fingerprint(clean), "requested_draws": last,
            "modes": modes}
