"""Kho tri thức có kiểm chứng: luật, bộ nhớ ngữ cảnh, và lời giải thích cho từng con số.

Yêu cầu ngày 13-10-2026 (thiết kế hệ suy luận và tự học) có bốn phần. Ba phần đã có trong kho:
truyền kết quả thống kê làm tiên nghiệm cho mô hình xác suất và bầu chọn có trọng số
(``online_learning``: Bayes tần suất 30/180/toàn bộ, điều kiện trễ, Hedge hai trí nhớ), vòng
phản hồi tự chỉnh trọng số (``online_learning.advance``, ``skill_monitor``), suy luận Bayes/Markov
có độ tin cậy hiệu chỉnh đa kiểm (``confidence_matrix``). Module này lấp phần còn thiếu:

1. **Kho luật (rule-based).** Mọi quy luật — đã đo ở nơi khác hay vừa tự khai phá — có một mục
   chung: định nghĩa, ngày đăng ký, số đo và TRẠNG THÁI suy từ số đo.
2. **Tự khai phá tri thức.** Mỗi ``DISCOVERY_EVERY`` kỳ, khai phá một lô luật trễ "a về hôm nay
   → b về ngày mai" có lift cao nhất trên lịch sử đến ngày đăng ký. Lift trong mẫu KHÔNG phải
   bằng chứng (chọn 20 trong 10 000 luật thì luật đẹp nhất luôn đẹp). Luật chỉ được chấm trên
   các kỳ SAU ngày đăng ký, bằng e-process; "có bằng chứng" khi e-value đạt ``N/α`` với N là
   số luật từng đăng ký (Bonferroni trên e-value, đúng dù xem lại mỗi ngày). Quá ``HORIZON`` kỳ
   chưa đạt thì "hết hạn".
3. **Bộ nhớ ngữ cảnh (vector memory).** Mỗi kỳ là một vectơ ngữ cảnh (tần suất 30 kỳ, độ gan,
   kỳ trước). Truy vấn ``NEIGHBOURS`` ngữ cảnh quá khứ giống nhất (cosine) và xem kỳ ngay sau
   chúng ra gì: chuyên gia "tương tự quá khứ" (dự báo tương tự — analog forecasting). Được chấm
   walk-forward so với hằng số trước khi được tin.
4. **Giải thích từng con (``explain``).** Xác suất đã công bố, đóng góp của từng chuyên gia theo
   trọng số Hedge hiện hành, mức tin đã hiệu chỉnh đa kiểm, luật đang "bắn" và ngữ cảnh tương tự.

Với máy quay công bằng không thuật toán nào nâng được xác suất trúng; số đo của kho (03-10, 04-10,
08-10, 12-10-2026) đều ra ngang hằng số. Vì thế mọi "độ tin cậy" ở đây suy từ phép kiểm, và mặc
định là THẤP cho tới khi dữ liệu tiến cứu nói khác. Module là KHUNG THÁCH ĐẤU: không đổi tổ hợp
xác suất của pipeline.

    python src/knowledge_base.py            # cập nhật data/knowledge/
"""

from __future__ import annotations

import argparse
import json
import math
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from atomic_io import atomic_write_text
from multi_hit_vip import counts_matrix, draws_from_frame
from xsmb_domain import baseline_rate

OUT_DIR = "knowledge"
KB_FILE = "kb.json"
VERSION = 1
#: Vectơ ngữ cảnh: cửa sổ tần suất, số ngữ cảnh láng giềng, độ mạnh tiên nghiệm kéo về nền.
WINDOW = 30
NEIGHBOURS = 50
PRIOR = 50.0
#: Kiểm walk-forward chuyên gia tương tự-quá-khứ trên chừng này kỳ cuối; top-k để đếm trúng.
EVAL_DRAWS = 1000
TOP_K = 10
#: Khai phá: một lô mới khi lô gần nhất cũ hơn chừng này kỳ; mỗi lô chừng này luật.
DISCOVERY_EVERY = 30
RULES_PER_BATCH = 20
MIN_SUPPORT = 200          # số lần tiền đề "a về" tối thiểu trong lịch sử khai phá
SHRINK = 100.0             # độ mạnh Beta khi ước lượng tỉ lệ điều kiện trong mẫu
HORIZON = 180              # số kỳ tiến cứu tối đa của một luật
ALPHA = 0.01
#: Lưới cược của e-process cho luật: y − μ ≥ −μ > −0,3, nên mọi λ ≤ 2 giữ vốn dương.
RULE_BETS = (0.1, 0.25, 0.5, 1.0, 2.0)

EXPERT_LABELS = {
    "incumbent": "Tổ hợp sản xuất",
    "constant": "Hằng số (mức nền)",
    "bayes_30": "Bayes tần suất 30 kỳ",
    "bayes_180": "Bayes tần suất 180 kỳ",
    "bayes_all": "Bayes tần suất toàn lịch sử",
    "lag_special": "Điều kiện trễ: cùng Đặc Biệt kỳ trước",
    "lag_repeat": "Điều kiện trễ: cùng trạng thái kỳ trước (Markov bậc 1)",
}
TIER_WORD = {"High": "Cao", "Medium": "Trung bình", "Low/Noise": "Thấp / nhiễu"}


# --------------------------------------------------------------------------- dữ liệu


def load_history(data_dir: Path) -> tuple[np.ndarray, list[str]]:
    """(ma trận có mặt T × 100, nhãn ngày): con j về ít nhất một nháy ở kỳ t."""
    frame = pd.read_csv(Path(data_dir) / "xsmb-2-digits.csv", dtype=str)
    draws, labels = draws_from_frame(frame)
    return counts_matrix(draws) >= 1, list(labels)



# --------------------------------------------------------------------------- bộ nhớ ngữ cảnh


def _zscore_rows(block: np.ndarray) -> np.ndarray:
    mean = block.mean(axis=1, keepdims=True)
    std = block.std(axis=1, keepdims=True)
    return np.divide(block - mean, std, out=np.zeros_like(block), where=std > 0)


def context_vectors(present: np.ndarray, window: int = WINDOW) -> np.ndarray:
    """Vectơ ngữ cảnh của mọi kỳ t = 0..T (hàng T là kỳ kế tiếp), chỉ đọc các kỳ trước t.

    Ba khối 100 chiều, mỗi khối chuẩn hoá chéo 100 con rồi ghép và chuẩn hoá độ dài 1 (để tích
    vô hướng là cosine): tần suất trong ``window`` kỳ trước, độ "nóng" exp(−gan/window), và con
    đã về ở kỳ ngay trước.
    """
    present = np.asarray(present, dtype=float)
    total, n = present.shape
    cum = np.vstack([np.zeros((1, n)), np.cumsum(present, axis=0)])
    rows = np.arange(total + 1)
    start = np.maximum(rows - window, 0)
    span = np.maximum(rows - start, 1)[:, None]
    freq = (cum[rows] - cum[start]) / span
    heat = np.zeros((total + 1, n))
    last_seen = np.full(n, -np.inf)
    for t in range(total + 1):
        heat[t] = np.exp(-(t - last_seen) / window)
        if t < total:
            last_seen[present[t] > 0] = t
    previous = np.vstack([np.zeros((1, n)), present])
    ctx = np.hstack([_zscore_rows(freq), _zscore_rows(heat), _zscore_rows(previous)])
    norm = np.linalg.norm(ctx, axis=1, keepdims=True)
    return np.divide(ctx, norm, out=np.zeros_like(ctx), where=norm > 0).astype(np.float32)


class ContextMemory:
    """Kho vectơ ngữ cảnh và kết quả ngay sau mỗi ngữ cảnh; truy vấn láng giềng gần nhất.

    Ngữ cảnh s có "kết quả" là chính kỳ s (vectơ s chỉ đọc các kỳ trước s). Khi dự báo kỳ t, chỉ
    các s < t mới có kết quả đã biết. Láng giềng lấy trong [window, t − window): ngữ cảnh của
    ``window`` kỳ ngay trước t chung phần lớn cửa sổ tần suất với t, nên "giống" chỉ vì gần về
    thời gian. Bỏ chúng thì láng giềng là những giai đoạn độc lập thật sự tương tự.
    """

    def __init__(self, present: np.ndarray, window: int = WINDOW):
        self.present = np.asarray(present, dtype=bool)
        self.window = window
        self.ctx = context_vectors(self.present, window)

    def neighbours(self, t: int, k: int = NEIGHBOURS) -> tuple[np.ndarray, np.ndarray]:
        """(chỉ số, độ tương tự) của ``k`` ngữ cảnh quá khứ giống kỳ t nhất, giảm dần."""
        pool = np.arange(self.window, max(self.window, t - self.window))
        if pool.size == 0:
            return pool, np.zeros(0, dtype=np.float32)
        sims = self.ctx[pool] @ self.ctx[t]
        k = min(k, pool.size)
        top = np.argpartition(-sims, k - 1)[:k]
        order = top[np.lexsort((pool[top], -sims[top]))]
        return pool[order], sims[order]

    def predict(self, t: int, k: int = NEIGHBOURS, prior: float = PRIOR) -> tuple[np.ndarray, np.ndarray]:
        """P(con về ở kỳ t) theo các kỳ ngay sau ngữ cảnh tương tự, co về nền bằng ``prior`` kỳ ảo."""
        base = baseline_rate("loto")
        idx, _ = self.neighbours(t, k)
        hits = self.present[idx].sum(axis=0) if idx.size else np.zeros(self.present.shape[1])
        return (hits + prior * base) / (idx.size + prior), idx


def _vn(x: float, digits: int = 2) -> str:
    """Số kiểu Việt Nam: dấu phẩy thập phân."""
    return f"{x:.{digits}f}".replace(".", ",")


def _finite(x: float) -> float | None:
    return float(x) if math.isfinite(x) else None


def _bernoulli_logloss(p: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).sum())


def evaluate_analog(present: np.ndarray, labels: list[str], last: int = EVAL_DRAWS) -> dict:
    """Walk-forward: chuyên gia tương tự-quá-khứ so với hằng số và Bayes tần suất 30 kỳ.

    Mỗi kỳ t chấm log-loss Bernoulli trên 100 con (tổng). Kỹ năng = 1 − LL/LL(hằng số); z từ hiệu
    từng kỳ. Top-k trúng so với chọn bừa k con trong CÙNG kỳ (k·dₜ/100).
    """
    memory = ContextMemory(present)
    total = len(present)
    first = max(3 * memory.window, total - last)
    base = baseline_rate("loto")
    constant = np.full(present.shape[1], base)
    rows = []
    for t in range(first, total):
        y = present[t].astype(float)
        analog, _ = memory.predict(t)
        recent = present[t - WINDOW:t].sum(axis=0)
        bayes30 = (recent + PRIOR * base) / (WINDOW + PRIOR)
        top = np.argsort(-analog, kind="stable")[:TOP_K]
        rows.append((
            _bernoulli_logloss(analog, y), _bernoulli_logloss(bayes30, y), _bernoulli_logloss(constant, y),
            int(present[t, top].sum()), TOP_K * int(present[t].sum()) / present.shape[1],
        ))
    arr = np.asarray(rows)
    n = len(arr)

    def versus(col: int) -> dict:
        diff = arr[:, 2] - arr[:, col]                   # dương = tốt hơn hằng số
        se = float(diff.std(ddof=1) / math.sqrt(n)) if n > 1 else float("nan")
        return {"logloss": float(arr[:, col].mean()), "skill": float(1 - arr[:, col].sum() / arr[:, 2].sum()),
                "gain_per_draw": float(diff.mean()), "z": _finite(diff.mean() / se) if se > 0 else None}

    hits, expected = arr[:, 3], arr[:, 4]
    gap = hits - expected
    se = float(gap.std(ddof=1) / math.sqrt(n)) if n > 1 else float("nan")
    return {
        "first_date": labels[first], "last_date": labels[total - 1], "draws": n,
        "constant_logloss": float(arr[:, 2].mean()),
        "analog": versus(0), "bayes_30": versus(1),
        "top_k": {"k": TOP_K, "hits": int(hits.sum()), "expected": float(expected.sum()),
                  "rate": float(hits.sum() / (n * TOP_K)), "random_rate": float(expected.sum() / (n * TOP_K)),
                  "z": _finite(gap.mean() / se) if se > 0 else None},
    }


# --------------------------------------------------------------------------- luật: khai phá và chấm


def mine_lag_rules(present: np.ndarray, upto: int, k: int = RULES_PER_BATCH,
                   min_support: int = MIN_SUPPORT) -> list[dict]:
    """Khai phá ``k`` luật "a về kỳ t−1 → b về kỳ t" có lift cao nhất trên các kỳ < ``upto``.

    Tỉ lệ điều kiện được co Beta về tỉ lệ nền của b (``SHRINK`` lần quan sát ảo), để luật có ít
    lần xảy ra không nổi lên chỉ nhờ may.
    """
    x = present[: upto - 1].astype(float)
    y = present[1:upto].astype(float)
    co = x.T @ y                                        # co[a, b] = số lần a về rồi b về kỳ sau
    support = x.sum(axis=0)
    rate_b = y.mean(axis=0)
    shrunk = (co + SHRINK * rate_b[None, :]) / (support[:, None] + SHRINK)
    lift = shrunk / np.where(rate_b > 0, rate_b, 1)[None, :]
    lift[support < min_support, :] = -np.inf
    flat = np.argsort(-lift, axis=None, kind="stable")[:k]
    rules = []
    for idx in flat:
        if not np.isfinite(lift.flat[idx]):
            break                                       # hết luật đủ số lần xảy ra: thà ít còn hơn bịa
        a, b = divmod(int(idx), present.shape[1])
        rules.append({"if": a, "then": b, "support": int(support[a]), "together": int(co[a, b]),
                      "rate": float(co[a, b] / support[a]), "base": float(rate_b[b]), "lift": float(lift[a, b])})
    return rules


def score_rule(rule: dict, present: np.ndarray, labels: list[str], horizon: int = HORIZON) -> dict:
    """Chấm TIẾN CỨU một luật trên các kỳ sau ngày đăng ký, bằng e-process một phía.

    Luật "bắn" ở kỳ t khi a về ở kỳ t−1. Khi máy quay công bằng, biết dₜ con khác nhau về ở kỳ t
    thì P(b về) = dₜ/100 đúng, nên tích các hệ số cược 1 + λ·(1[b về] − dₜ/100) là martingale
    không âm; trung bình trên lưới λ cũng vậy. Ville: P(có lúc e ≥ 1/α) ≤ α.
    """
    after = [t for t, d in enumerate(labels) if d > rule["registered_at"]]
    window = after[:horizon]
    a, b = rule["if"], rule["then"]
    lam = np.asarray(RULE_BETS)[:, None]
    fired_y, fired_mu = [], []
    for t in window:
        if t == 0 or not present[t - 1, a]:
            continue
        fired_y.append(float(present[t, b]))
        fired_mu.append(float(present[t].sum()) / present.shape[1])
    y, mu = np.asarray(fired_y), np.asarray(fired_mu)
    if y.size:
        paths = np.cumprod(1.0 + lam * (y - mu)[None, :], axis=1).mean(axis=0)
        e_now, e_max = float(paths[-1]), float(max(1.0, paths.max()))
    else:
        e_now = e_max = 1.0
    return {"draws_after": len(window), "fired": int(y.size), "hits": int(y.sum()),
            "expected": float(mu.sum()), "e_value": e_now, "e_max": e_max, "p_anytime": 1.0 / e_max}


def rule_status(score: dict, n_registered: int, horizon: int = HORIZON, alpha: float = ALPHA) -> str:
    """Trạng thái suy từ số đo: có bằng chứng / đang kiểm / hết hạn. Ngưỡng Bonferroni trên e-value."""
    if score["e_max"] >= n_registered / alpha:
        return "co-bang-chung"
    if score["draws_after"] >= horizon:
        return "het-han"
    return "dang-kiem"


STATUS_WORD = {"co-bang-chung": "Có bằng chứng", "dang-kiem": "Đang kiểm tiến cứu", "het-han": "Hết hạn, không đạt"}
#: Trạng thái của phép kiểm tiến cứu đã đăng ký → trạng thái trong kho.
HYPOTHESIS_STATUS = {"dang_thu": "dang-kiem", "xac_nhan": "co-bang-chung", "bac_bo": "khong-dat"}


def rule_config() -> dict:
    """Mọi tham số định nghĩa một luật và cách chấm nó. Khác bản đã ghi thì đó là một thí nghiệm KHÁC."""
    return {"version": VERSION, "discovery_every": DISCOVERY_EVERY, "rules_per_batch": RULES_PER_BATCH,
            "min_support": MIN_SUPPORT, "shrink": SHRINK, "horizon": HORIZON, "alpha": ALPHA,
            "rule_bets": list(RULE_BETS)}


def carry_over(previous: dict | None) -> tuple[dict | None, list[dict]]:
    """Tách kho đã ghi thành (phần được chấm tiếp, các thí nghiệm đã nghỉ).

    Luật của kho ghi bằng phiên bản hay cấu hình khác KHÔNG được chấm lại bằng cách chấm mới: ngưỡng,
    lưới cược hay chân trời đổi giữa chừng là xem dữ liệu rồi mới chọn phép kiểm. Chúng được cất
    nguyên vẹn vào ``retired`` (với cấu hình và kỳ chấm cuối của chúng) và lô mới đăng ký ngay.
    """
    if not previous:
        return None, []
    retired = list(previous.get("retired", []))
    if previous.get("rule_config") == rule_config():
        return previous, retired
    if previous.get("rules"):
        retired.append({"rule_config": previous.get("rule_config"), "version": previous.get("version"),
                        "last_scored": previous.get("source_date"), "threshold_e": previous.get("threshold_e"),
                        "batches": previous.get("batches", []), "rules": previous["rules"]})
    return None, retired


def update_rules(previous: dict | None, present: np.ndarray, labels: list[str]) -> dict:
    """Giữ nguyên mọi luật đã đăng ký (định nghĩa, ngày, số trong mẫu), chấm lại, thêm lô mới khi đến hạn."""
    batches = list((previous or {}).get("batches", []))
    rules = list((previous or {}).get("rules", []))
    index = {d: t for t, d in enumerate(labels)}
    last_reg = batches[-1]["registered_at"] if batches else None
    due = last_reg is None or (last_reg in index and len(labels) - 1 - index[last_reg] >= DISCOVERY_EVERY)
    if due:
        registered_at = labels[-1]
        mined = mine_lag_rules(present, len(labels))
        ids = []
        for r in mined:
            rid = f"tre-{r['if']:02d}-{r['then']:02d}-{registered_at}"
            ids.append(rid)
            rules.append({"id": rid, "kind": "lag", "registered_at": registered_at,
                          "text": f"{r['if']:02d} về hôm nay → {r['then']:02d} về kỳ sau",
                          "in_sample": {k: r[k] for k in ("support", "together", "rate", "base", "lift")},
                          "if": r["if"], "then": r["then"]})
        batches.append({"registered_at": registered_at, "draws": len(labels), "rules": ids})
    n = len(rules)
    for rule in rules:
        score = score_rule(rule, present, labels)
        rule["prospective"] = score
        rule["status"] = rule_status(score, n)
    return {"batches": batches, "rules": rules, "threshold_e": n / ALPHA}


# --------------------------------------------------------------------------- tri thức đã đo ở nơi khác


def _read(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def measured_knowledge(data_dir: Path) -> list[dict]:
    """Gom kết luận của các phép đo đã có trong kho thành mục tri thức có trạng thái."""
    data_dir = Path(data_dir)
    out = []
    conf = _read(data_dir / "confidence" / "report.json")
    if conf:
        for fam in conf.get("families", []):
            out.append({"id": f"ho-{fam['key']}", "kind": "measured", "title": fam["label"],
                        "status": "co-bang-chung" if fam["p"] < ALPHA else "khong-hon-ngau-nhien",
                        "summary": f"tín hiệu mạnh nhất so với 10 000 lịch sử công bằng: p = {fam['p']:.3g}"})
        # Hai phép kiểm TIẾN CỨU đã đăng ký tự chốt trạng thái (hot_tail_test, digit_sum_hypothesis);
        # kho chỉ đọc lại, không tự suy. Tiến độ tính theo cỡ mẫu đã đăng ký (min_draws), không theo
        # cửa sổ đặc trưng (window).
        for key, ident, title in (("hot_tail", "gia-thuyet-duoi-nong", "Giả thuyết đuôi nóng"),
                                  ("digit_sum", "gia-thuyet-tong-bong-cham", "Giả thuyết tổng – bóng – chạm")):
            hyp = conf.get(key) or {}
            if not hyp:
                continue
            summary = f"{hyp.get('draws', 0)}/{hyp.get('min_draws')} kỳ tiến cứu đã đăng ký"
            if hyp.get("z") is not None:
                summary += f", z = {_vn(float(hyp['z']))}"
            out.append({"id": ident, "kind": "hypothesis", "title": title,
                        "status": HYPOTHESIS_STATUS.get(hyp.get("state"), "dang-kiem"), "summary": summary})
    vip = _read(data_dir / "multi_hit" / "vip.json")
    if vip:
        level = vip.get("confidence", "Low")
        out.append({"id": "bo-loc-lo-nhieu-nhay", "kind": "challenger", "title": "Bộ lọc lô ≥ 2 nháy",
                    "status": "co-bang-chung" if level in ("High", "Medium") else "chua-co-bang-chung",
                    "summary": f"hồi cứu {vip['backtest']['rate']:.4f} so với chọn bừa {vip['backtest']['random_rate']:.4f}"})
        pairs = vip.get("pairs")
        if pairs:
            out.append({"id": "cap-xien-2", "kind": "challenger", "title": "Cặp xiên 2 cùng về",
                        "status": "co-bang-chung" if pairs["confidence"] in ("High", "Medium") else "chua-co-bang-chung",
                        "summary": f"hồi cứu {pairs['backtest']['rate']:.4f} so với chọn bừa {pairs['backtest']['random_rate']:.4f}"})
    for mode in ("loto", "de"):
        online = _read(data_dir / "research" / f"online_{mode}_report.json")
        if online:
            gate = online.get("gate", {})
            out.append({"id": f"tu-hoc-{mode}", "kind": "self-learning",
                        "title": f"Tự học trực tuyến ({'LOTO' if mode == 'loto' else 'Đặc Biệt'})",
                        "status": "dang-dung" if gate.get("active") else "bong-mo",
                        "summary": f"{online.get('n_settled', 0)} kỳ đã chốt; {gate.get('reason', '')}"})
    return out


# --------------------------------------------------------------------------- dự đoán kèm độ tin cậy và giải thích


def _latest_record(data_dir: Path, mode: str) -> dict | None:
    state = _read(Path(data_dir) / "online" / f"{mode}.json")
    if not state or not state.get("records"):
        return None
    return state["records"][-1]


def explain(number: int, mode: str, *, record: dict, confidence_row: dict | None,
            rules: list[dict], analog: dict | None) -> dict:
    """Dự đoán chuyên sâu cho MỘT con: xác suất, đóng góp từng chuyên gia, độ tin cậy, lý do.

    * Xác suất là đúng con số đã công bố (``record["published"]``), không tính lại.
    * Đóng góp của chuyên gia e = wₑ·(pₑ − nền): phần nó kéo hỗn hợp khỏi mức nền. Tổng đóng góp
      cộng nền bằng đúng hỗn hợp Hedge (``record["mixture"]``).
    * Độ tin cậy là tầng đã hiệu chỉnh đa kiểm của ``confidence_matrix``, không phải hậu nghiệm thô.
    """
    base = baseline_rate(mode)
    weights = record["weights"]
    contributions = []
    for name, probs in record["experts"].items():
        w = float(weights.get(name, 0.0))
        p = float(probs[number])
        contributions.append({"expert": name, "label": EXPERT_LABELS.get(name, name), "weight": w,
                              "prob": p, "delta": w * (p - base)})
    contributions.sort(key=lambda c: -abs(c["delta"]))
    published = float(record["published"][number])
    tier = (confidence_row or {}).get("tier", "Low/Noise")
    firing = [r for r in rules if r["then"] == number]
    reasons = [f"Xác suất đã công bố {_vn(published * 100)}% so với mức nền {_vn(base * 100)}% "
               f"(×{_vn(published / base, 3)})."]
    top = contributions[0]
    if abs(top["delta"]) > 0:
        reasons.append(f"Nguồn kéo mạnh nhất: {top['label']} ({_vn(top['prob'] * 100)}%, trọng số "
                       f"{_vn(top['weight'], 3)}).")
    reasons.append(f"Độ tin cậy {TIER_WORD.get(tier, tier)} (đã hiệu chỉnh đa kiểm trên 10 000 lịch sử công bằng).")
    if not record.get("gate", {}).get("active"):
        reasons.append("Tự học trực tuyến đang ở chế độ bóng mờ: chưa thắng hằng số đủ chắc để được dùng.")
    for r in firing:
        reasons.append(f"Luật «{r['text']}» đang bắn — {STATUS_WORD.get(r['status'], r['status'])} "
                       f"(e = {_vn(r['prospective']['e_value'])}).")
    if analog is not None:
        reasons.append(f"Ngữ cảnh tương tự quá khứ: {analog['hits']}/{analog['k']} kỳ giống nhất có con này về "
                       f"ở kỳ sau (nền {_vn(base * 100, 1)}%).")
    return {"number": f"{number:02d}", "mode": mode, "probability": published, "base": base,
            "x_base": published / base, "mixture": float(record["mixture"][number]),
            "contributions": contributions, "confidence": {"tier": tier, "components": {
                k: (confidence_row or {}).get(k) for k in ("c_bayes", "c_markov", "c_cau")}},
            "online_active": bool(record.get("gate", {}).get("active")),
            "rules": [{"id": r["id"], "text": r["text"], "status": r["status"]} for r in firing],
            "analog": analog, "reasons": reasons}


def insights(data_dir: Path, mode: str, rules: list[dict], memory: ContextMemory | None,
             labels: list[str], k: int = TOP_K) -> dict | None:
    """Lời giải thích cho ``k`` con xác suất cao nhất của bản công bố hiện hành."""
    record = _latest_record(data_dir, mode)
    if record is None:
        return None
    conf = _read(Path(data_dir) / "confidence" / "report.json") or {}
    rows = {(r["mode"], int(r["number"])): r for r in conf.get("matrix", [])}
    published = np.asarray(record["published"], dtype=float)
    order = np.argsort(-published, kind="stable")[:k]
    active = [r for r in rules if r["status"] != "het-han"]
    firing = []
    neighbours = None
    if mode == "loto" and memory is not None:
        t = len(memory.present)
        last = memory.present[-1]
        firing = [r for r in active if last[r["if"]]]
        neighbours, _ = memory.neighbours(t)
    items = []
    for number in order:
        analog = None
        if neighbours is not None and neighbours.size:
            hits = int(memory.present[neighbours, number].sum())
            analog = {"k": int(neighbours.size), "hits": hits,
                      "similar_dates": [labels[s] for s in neighbours[:3]]}
        items.append(explain(int(number), mode, record=record, confidence_row=rows.get((mode, int(number))),
                             rules=firing, analog=analog))
    return {"mode": mode, "target_date": record["target_date"], "items": items}


# --------------------------------------------------------------------------- ghi


def run(data_dir: Path) -> Path:
    data_dir = Path(data_dir)
    present, labels = load_history(data_dir)
    out = data_dir / OUT_DIR
    kb_path = out / KB_FILE
    previous, retired = carry_over(_read(kb_path))
    rules = update_rules(previous, present, labels)
    memory = ContextMemory(present)
    payload = {
        "version": VERSION,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "source_date": labels[-1],
        "draws": len(labels),
        "config": {"window": WINDOW, "neighbours": NEIGHBOURS, "prior": PRIOR},
        "rule_config": rule_config(),
        **rules,
        "retired": retired,
        "measured": measured_knowledge(data_dir),
        "analog": evaluate_analog(present, labels),
        "insights": {mode: insights(data_dir, mode, rules["rules"], memory, labels) for mode in ("loto", "de")},
    }
    out.mkdir(parents=True, exist_ok=True)
    atomic_write_text(kb_path, json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    return kb_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--data-dir", default="data")
    args = parser.parse_args(argv)
    print("[OK] kho tri thức ->", run(Path(args.data_dir)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
