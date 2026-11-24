"""Bộ máy Bayes theo đoạn cho lồng chục và lồng đơn vị XSMB: thích nghi khi máy quay lệch, đứng yên khi máy đều.

Vì sao có module này
--------------------
Mọi thành phần học của kho (ML, Cầu Kèo, xếp chồng, trọng số tổ hợp) đều đứng ở mức nền. Điều ấy đúng với
một máy quay công bằng: không mô hình nào đoán được kỳ quay đều. Nhưng kỳ quay KHÔNG luôn đều. Ngày
23-11-2026 kho xác nhận độ lệch lồng đơn vị 20-04 → 24-11-2024 nằm trong kết quả công bố: 306 kỳ trùng
từng ô với hai nơi ghi khác (``documentation/research/2026-11-23-dai-quay-mien-bac.md``). Biết đúng phân
bố của đợt ấy thì xác suất LOTO hơn hằng số khoảng 24 nat trong 306 kỳ. Mô hình bật theo báo động có sẵn
(``stats.xsmb_venue_effects.adaptive_cage_benchmark``) chỉ thu được chừng 0,07 nat. Chỗ có thể kiếm lời
thật là một máy quay bắt đầu lệch, và module này nhắm đúng chỗ ấy.

Thuật toán
----------
1. **Mô hình quan sát.** Mỗi kỳ, lồng đơn vị cho 27 chữ số (chữ số cuối của 27 giải), lồng chục cho 27 chữ
   số (chữ số áp cuối). Trong một ĐOẠN máy quay ổn định, chữ số của một lồng là đa thức với xác suất
   ``θ``, và ``θ`` có tiên nghiệm Dirichlet tâm ở phân bố đều với độ co ``κ`` (số chữ số giả).
2. **Phát hiện điểm đổi Bayes trực tuyến** (BOCPD, Adams & MacKay 2007). Sau mỗi kỳ, đoạn hiện tại kết
   thúc với xác suất ``H`` (tốc độ đổi). Hậu nghiệm trên độ dài đoạn ``r`` cập nhật chính xác; dự báo cho
   kỳ tới là trung bình theo ``r`` của dự báo hậu nghiệm Dirichlet–đa thức của đoạn dài ``r``. Một đoạn
   mới bắt đầu ở tiên nghiệm, nên khi máy trở lại đều thì dự báo về lại đều.
3. **Trung bình mô hình.** Mỗi cặp ``(κ, H)`` của lưới ``CONFIG`` là một chuyên gia. Thêm chuyên gia thứ
   ``0`` là chính dự báo đều. Trọng số cập nhật bằng hợp lý chữ số của kỳ vừa quay, rồi **chia sẻ cố
   định** (fixed-share, Herbster & Warmuth 1998): mỗi kỳ một phần ``share`` trọng số trả về tiên nghiệm,
   nên mô hình theo kịp cả khi máy chuyển từ lệch về đều rồi lệch lại.

Bảo đảm. Với log-loss trên chữ số, tổng log-loss của hỗn hợp sau ``T`` kỳ không vượt tổng log-loss của dự
báo đều cộng ``−ln π₀ − T·ln(1 − share)``, với MỌI dãy kết quả (cận tất định, không cần giả định gì). Với
``CONFIG`` hiện tại, 4 000 kỳ máy đều tốn tối đa ``ln 2 + 4 000 · 0,0005 ≈ 2,7`` nat, tức 0,0007 nat mỗi kỳ.
``fixed_share_bound`` tính cận ấy và phép kiểm ghim nó. Thước chấm LOTO (100 log-loss nhị phân) không có
cận tất định, nhưng đi cùng chiều.

Hợp lệ và trung thực
--------------------
* Dự báo cho kỳ ``t`` chỉ đọc các kỳ trước ``t``: ``walk_forward`` cập nhật SAU khi chấm.
* Tham số của ``CONFIG`` chọn SAU khi đã thấy đợt 2024, nên điểm walk-forward trên lịch sử chỉ là MÔ TẢ.
  Kết quả không nhạy với lưới (bốn biến thể cho LOTO +5,8 → +8,5 nat), nhưng bằng chứng thật là phép kiểm
  TIẾN CỨU: ``CONFIG`` đóng băng cùng ``VERSION``, và ``prospective`` chỉ chấm các kỳ SAU ngày đăng ký.
* Phép kiểm tiến cứu nhân tỉ số ``p_hỗn hợp(chữ số của kỳ t | kỳ trước t) / p_đều(chữ số)``. Dưới giả thuyết
  máy đều, kỳ vọng mỗi thừa số bằng 1, nên tích là một martingale không âm. Xác suất nó TỪNG vượt
  ``1/ALPHA`` không quá ``ALPHA`` (bất đẳng thức Ville), dù xem lúc nào.
* Mô hình CHẠY BÓNG (``evaluation.model_registry``): được chấm mỗi kỳ, không đổi xác suất công bố. Nó chỉ
  đủ điều kiện xét đưa vào tổ hợp khi walk-forward LOTO đạt ``z ≥ PROMOTE_Z`` VÀ phép kiểm tiến cứu vượt
  ngưỡng. Việc đưa vào là một quyết định riêng, không tự động.

Đổi bất kỳ giá trị nào của ``CONFIG`` thì tăng ``VERSION``: lần chạy sau cất đăng ký cũ vào ``retired`` và
đăng ký lại từ ngày dữ liệu mới nhất. Không chấm lại các kỳ cũ bằng luật mới.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import numpy as np
from scipy.special import gammaln

from core.atomic_io import atomic_write_text
from core.paths import REPO_ROOT
from core.xsmb_domain import LOTO_BASELINE_RATE, LOTO_DRAWS_PER_DAY
from stats.xsmb_venue_effects import CAGE_OF_DIGIT, Draws, load

SCHEMA_VERSION = 1
#: Đổi bất kỳ giá trị nào của ``CONFIG`` thì tăng số này (phép kiểm tiến cứu đăng ký lại).
VERSION = 1
#: Lưới chuyên gia và tham số trộn. ``kappas``: độ co Dirichlet của một lồng (số chữ số giả; 1 000 chữ số
#: ≈ 37 kỳ). ``hazards``: xác suất một đoạn kết thúc sau mỗi kỳ (1/250 ≈ 8 tháng, 1/1 000 ≈ 2,7 năm).
#: ``share``: phần trọng số trả về tiên nghiệm mỗi kỳ. ``prior_uniform``: tiên nghiệm của dự báo đều.
#: ``max_run``: độ dài đoạn tối đa được nhớ riêng (đoạn dài hơn dùng ``max_run`` kỳ gần nhất).
CONFIG: dict[str, object] = {
    "kappas": (300.0, 1000.0, 3000.0),
    "hazards": (1 / 250, 1 / 1000),
    "share": 5e-4,
    "prior_uniform": 0.5,
    "max_run": 1500,
}
#: Lồng được mô hình hoá: 0 = đơn vị, 1 = chục (hai chữ số làm nên con LOTO và 2 số cuối Đặc Biệt).
CAGES = (0, 1)
ALPHA = 0.01
#: z một phía cho α = 0,01 (cùng ngưỡng với ``stats.xsmb_venue_effects``).
PROMOTE_Z = 2.326
#: Số kỳ đầu chỉ để học, không chấm (cùng mốc với mô hình lồng thích nghi có sẵn).
WARMUP = 365
#: Cửa sổ của trạng thái «đoạn mới bắt đầu gần đây».
RECENT_RUN = 60
LAST_DRAWS = 730

OUT_DIR = Path("forecast") / "cage_bayes"
SUMMARY = "summary.json"
REGISTRY = Path("research") / "hypotheses" / "cage_bayes.json"
LEDGER = Path("research") / "hypotheses" / "cage_bayes.csv"
LEDGER_FIELDS = ["date", "version", "log_e", "log_e_total"]
_UNIFORM_LOG = math.log(0.1)
_SPECIAL_BASE = 0.01


# ---------------------------------------------------------------------------- dữ liệu
def cage_counts(draws: Draws) -> np.ndarray:
    """Số lần ra của mỗi chữ số ở lồng đơn vị và lồng chục, mỗi kỳ: mảng ``(n, 2, 10)``."""
    out = np.zeros((draws.n, len(CAGES), 10))
    rows = np.arange(draws.n)
    for slot, cage in enumerate(CAGES):
        for position in np.flatnonzero(CAGE_OF_DIGIT == cage):
            np.add.at(out[:, slot, :], (rows, draws.digits[:, position].astype(np.int64)), 1.0)
    return out


def loto_outcome(draws: Draws) -> np.ndarray:
    """Con LOTO nào về ở mỗi kỳ: mảng 0/1 ``(n, 100)``."""
    out = np.zeros((draws.n, 100))
    np.put_along_axis(out, draws.loto, 1.0, axis=1)
    return out


# ---------------------------------------------------------------------------- mô hình
def dirichlet_multinomial_log(alpha: np.ndarray, counts: np.ndarray) -> np.ndarray:
    """``ln p(counts | alpha)`` của Dirichlet–đa thức, BỎ hệ số đa thức (nó triệt tiêu với dự báo đều).

    ``alpha`` có trục cuối là 10 chữ số; ``counts`` phát sóng theo các trục trước.
    """
    total_alpha = alpha.sum(axis=-1)
    total = counts.sum(axis=-1)
    return (gammaln(total_alpha) - gammaln(total_alpha + total)
            + (gammaln(alpha + counts) - gammaln(alpha)).sum(axis=-1))


@dataclass
class Forecast:
    """Dự báo cho MỘT kỳ, trước khi quay."""

    loto: np.ndarray          # (100,) xác suất mỗi con về ít nhất một lần
    special: np.ndarray       # (100,) phân bố 2 số cuối Đặc Biệt
    digits: np.ndarray        # (2, 10) phân bố chữ số của lồng đơn vị, lồng chục (trung bình hỗn hợp)
    uniform_weight: float     # trọng số của chuyên gia «dự báo đều»
    recent_change: float      # xác suất (theo các chuyên gia BOCPD) đoạn hiện tại bắt đầu trong RECENT_RUN kỳ


@dataclass
class CageBayes:
    """Hỗn hợp chia sẻ cố định của dự báo đều và các chuyên gia BOCPD ``(κ, H)``.

    Thống kê của mọi độ dài đoạn ``r`` là tổng ``r`` kỳ gần nhất, CHUNG cho mọi chuyên gia; mỗi chuyên gia
    chỉ khác tiên nghiệm (``κ``) và hậu nghiệm trên ``r`` (theo ``H``).
    """

    config: dict = field(default_factory=lambda: dict(CONFIG))

    def __post_init__(self) -> None:
        kappas = np.asarray(self.config["kappas"], dtype=float)
        hazards = np.asarray(self.config["hazards"], dtype=float)
        if kappas.ndim != 1 or hazards.ndim != 1 or not kappas.size or not hazards.size:
            raise ValueError("lưới κ và H phải là dãy khác rỗng")
        if (kappas <= 0).any() or ((hazards <= 0) | (hazards >= 1)).any():
            raise ValueError("κ phải dương, H phải trong (0, 1)")
        self.share = float(self.config["share"])
        self.prior_uniform = float(self.config["prior_uniform"])
        if not (0 < self.share < 1 and 0 < self.prior_uniform < 1):
            raise ValueError("share và prior_uniform phải trong (0, 1)")
        self.max_run = int(self.config["max_run"])
        self.alpha0 = kappas / 10.0                                  # (K,)
        self.log_h = np.log(hazards)                                 # (H,)
        self.log_stay = np.log1p(-hazards)                           # (H,)
        self.stats = np.zeros((1, len(CAGES), 10))                   # (R, 2, 10): r = 0 là đoạn rỗng
        self.log_run = np.zeros((kappas.size, hazards.size, 1))      # (K, H, R), mỗi (k, h) chuẩn hoá
        experts = kappas.size * hazards.size
        self.log_prior = np.log(np.concatenate([[self.prior_uniform],
                                                np.full(experts, (1 - self.prior_uniform) / experts)]))
        self.log_weight = self.log_prior.copy()

    @property
    def experts(self) -> int:
        return self.log_weight.size

    def _alpha(self) -> np.ndarray:
        return self.alpha0[:, None, None, None] + self.stats[None]   # (K, R, 2, 10)

    def forecast(self) -> Forecast:
        """Dự báo cho kỳ tới từ mọi kỳ đã cập nhật."""
        weight = np.exp(self.log_weight - self.log_weight.max())
        weight /= weight.sum()
        alpha = self._alpha()
        q = alpha / alpha.sum(axis=-1, keepdims=True)                   # (K, R, 2, 10)
        theta = q[:, :, 1, :, None] * q[:, :, 0, None, :]                # (K, R, 10 chục, 10 đơn vị)
        theta = theta.reshape(theta.shape[0], theta.shape[1], 100)
        appear = -np.expm1(LOTO_DRAWS_PER_DAY * np.log1p(-theta))         # (K, R, 100)
        run = np.exp(self.log_run)                                       # (K, H, R)
        expert_w = weight[1:].reshape(run.shape[0], run.shape[1])        # (K, H)
        mixed_run = expert_w[:, :, None] * run                           # (K, H, R)
        per_k = mixed_run.sum(axis=1)                                    # (K, R)
        loto = weight[0] * np.full(100, LOTO_BASELINE_RATE) + np.einsum("kr,krn->n", per_k, appear)
        special = weight[0] * np.full(100, _SPECIAL_BASE) + np.einsum("kr,krn->n", per_k, theta)
        digits = weight[0] * np.full((len(CAGES), 10), 0.1) + np.einsum("kr,krcd->cd", per_k, q)
        bocpd_total = float(per_k.sum())
        recent = float(per_k[:, :RECENT_RUN].sum() / bocpd_total) if bocpd_total > 0 else 0.0
        return Forecast(loto=loto, special=special, digits=digits, uniform_weight=float(weight[0]),
                        recent_change=recent)

    def update(self, counts: np.ndarray) -> float:
        """Nạp kết quả một kỳ (``(2, 10)`` số đếm); trả ``ln`` tỉ số hợp lý chữ số của hỗn hợp so với đều."""
        counts = np.asarray(counts, dtype=float)
        loglik = dirichlet_multinomial_log(self._alpha(), counts[None, None]).sum(axis=-1)   # (K, R)
        joint = self.log_run + loglik[:, None, :]                                           # (K, H, R)
        evidence = np.logaddexp.reduce(joint, axis=-1)                                      # (K, H)
        uniform = float(counts.sum()) * _UNIFORM_LOG
        expert_log = np.concatenate([[uniform], evidence.ravel()])
        mixture = float(np.logaddexp.reduce(self.log_weight + expert_log))
        # Hậu nghiệm trọng số rồi chia sẻ cố định về tiên nghiệm.
        posterior = self.log_weight + expert_log - mixture
        self.log_weight = np.logaddexp(math.log1p(-self.share) + posterior, math.log(self.share) + self.log_prior)
        self.log_weight -= np.logaddexp.reduce(self.log_weight)
        # BOCPD: đoạn tiếp tục (r → r + 1) hoặc kết thúc sau kỳ này (đoạn mới r = 0 cho kỳ sau).
        grow = joint + self.log_stay[None, :, None]
        restart = evidence + self.log_h[None, :]
        log_run = np.concatenate([restart[:, :, None], grow], axis=-1)
        stats = np.concatenate([np.zeros((1,) + self.stats.shape[1:]), self.stats + counts[None]], axis=0)
        if log_run.shape[-1] > self.max_run + 1:
            # Đoạn dài hơn max_run gộp vào ô max_run, ô ấy dùng max_run kỳ gần nhất (giữ thống kê CHUNG).
            tail = np.logaddexp(log_run[..., self.max_run], log_run[..., self.max_run + 1])
            log_run = np.concatenate([log_run[..., :self.max_run], tail[..., None]], axis=-1)
            stats = stats[: self.max_run + 1]
        self.log_run = log_run - np.logaddexp.reduce(log_run, axis=-1, keepdims=True)
        self.stats = stats
        return mixture - uniform


def fixed_share_bound(draws: int, config: dict = CONFIG) -> float:
    """Cận trên (nat) của phần hỗn hợp kém dự báo đều trên log-loss chữ số sau ``draws`` kỳ, với mọi dãy."""
    return -math.log(float(config["prior_uniform"])) - draws * math.log1p(-float(config["share"]))


# ---------------------------------------------------------------------------- chấm walk-forward
def _bernoulli_total(prob: np.ndarray, outcome: np.ndarray) -> float:
    prob = np.clip(prob, 1e-12, 1 - 1e-12)
    return float(-(outcome * np.log(prob) + (1 - outcome) * np.log1p(-prob)).sum())


_CONSTANT_LOTO = np.full(100, LOTO_BASELINE_RATE)


def walk_forward(counts: np.ndarray, outcome: np.ndarray, special: np.ndarray, *, config: dict = CONFIG,
                 warmup: int = WARMUP) -> tuple[dict[str, np.ndarray], CageBayes]:
    """Mỗi kỳ ``t``: dự báo từ các kỳ trước ``t``, chấm, RỒI mới nạp kỳ ``t``.

    Trả các mảng theo kỳ (kỳ trước ``warmup`` mang ``nan`` ở các cột chấm):
    ``gain_loto`` = log-loss LOTO của hằng số trừ của mô hình (tổng 100 log-loss nhị phân, nat);
    ``gain_de`` = ``ln p(2 số cuối Đặc Biệt) − ln 0,01``; ``log_lr`` = ``ln`` tỉ số hợp lý chữ số so với đều;
    ``uniform_weight``, ``recent_change`` của dự báo trước kỳ ấy. Trả kèm mô hình đã nạp mọi kỳ.
    """
    model = CageBayes(dict(config))
    n = counts.shape[0]
    out = {name: np.full(n, np.nan) for name in ("gain_loto", "gain_de", "uniform_weight", "recent_change")}
    out["log_lr"] = np.zeros(n)
    for t in range(n):
        if t >= warmup:
            fc = model.forecast()
            out["gain_loto"][t] = _bernoulli_total(_CONSTANT_LOTO, outcome[t]) - _bernoulli_total(fc.loto, outcome[t])
            out["gain_de"][t] = math.log(fc.special[int(special[t])]) - math.log(_SPECIAL_BASE)
            out["uniform_weight"][t] = fc.uniform_weight
            out["recent_change"][t] = fc.recent_change
        out["log_lr"][t] = model.update(counts[t])
    return out, model


def _paired(values: np.ndarray) -> dict:
    values = values[np.isfinite(values)]
    if values.size < 2:
        return {"draws": int(values.size), "total": float(values.sum()), "mean": float("nan"), "z": 0.0}
    mean, sd = float(values.mean()), float(values.std(ddof=1))
    z = mean / (sd / math.sqrt(values.size)) if sd > 0 else 0.0
    return {"draws": int(values.size), "total": float(values.sum()), "mean": mean, "z": z}


def _window(scores: dict[str, np.ndarray], mask: np.ndarray, label: str) -> dict:
    scored = mask & np.isfinite(scores["gain_loto"])
    return {
        "label": label,
        "loto": _paired(scores["gain_loto"][scored]),
        "de": _paired(scores["gain_de"][scored]),
        "uniform_weight": float(np.nanmean(scores["uniform_weight"][scored])) if scored.any() else float("nan"),
        "log10_lr": float(scores["log_lr"][scored].sum() / math.log(10)),
    }


# ---------------------------------------------------------------------------- phép kiểm tiến cứu
def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _read_ledger(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _ledger_text(rows: list[dict]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=LEDGER_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def _config_json(config: dict) -> dict:
    return {key: list(value) if isinstance(value, tuple) else value for key, value in config.items()}


def prospective(dates: tuple[date, ...], log_lr: np.ndarray, registry_path: Path, ledger_path: Path, *,
                config: dict = CONFIG, version: int = VERSION) -> dict:
    """Đăng ký (một lần mỗi ``VERSION``) rồi chấm các kỳ SAU ngày đăng ký; sổ chỉ nối thêm.

    ``log_lr[t]`` phải là tỉ số hợp lý của kỳ ``t`` dưới dự báo chỉ đọc các kỳ trước ``t``. Dòng đã ghi của
    sổ không bao giờ bị sửa; nếu tính lại khác dòng đã ghi thì ``ledger_consistent`` là ``False``.
    """
    registry = _read_json(registry_path) or {"schema_version": SCHEMA_VERSION, "retired": []}
    current = registry.get("registration")
    config_json = _config_json(config)
    if current and (current.get("version") != version or current.get("config") != config_json):
        registry.setdefault("retired", []).append(current)
        current = None
    if current is None:
        current = {"version": version, "config": config_json, "alpha": ALPHA, "threshold": 1.0 / ALPHA,
                   "registered_on": dates[-1].isoformat(),
                   "rule": "chấm các kỳ có ngày sau registered_on; e = tích p_hỗn hợp(chữ số) / p_đều(chữ số)"}
        registry["registration"] = current
    registered_on = date.fromisoformat(current["registered_on"])

    existing = _read_ledger(ledger_path)
    rows = [row for row in existing if int(row["version"]) == version]
    others = [row for row in existing if int(row["version"]) != version]
    recorded = {row["date"]: float(row["log_e"]) for row in rows}
    consistent = True
    total = float(rows[-1]["log_e_total"]) if rows else 0.0
    for day, value in zip(dates, log_lr, strict=True):
        if day <= registered_on:
            continue
        key = day.isoformat()
        if key in recorded:
            consistent = consistent and abs(recorded[key] - float(value)) <= 1e-6
            continue
        total += float(value)
        rows.append({"date": key, "version": version, "log_e": f"{float(value):.9f}", "log_e_total": f"{total:.9f}"})
    atomic_write_text(registry_path, json.dumps(registry, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    atomic_write_text(ledger_path, _ledger_text(others + rows))
    log10_e = total / math.log(10)
    return {
        "version": version,
        "registered_on": current["registered_on"],
        "draws": len(rows),
        "log10_e": log10_e,
        "log10_threshold": math.log10(1.0 / ALPHA),
        "evidence": bool(log10_e >= math.log10(1.0 / ALPHA)),
        "ledger_consistent": consistent,
    }


# ---------------------------------------------------------------------------- tóm tắt
def _num(value: float, digits: int) -> str:
    return f"{value:.{digits}f}".replace(".", ",").replace("-", "−")


def _count(value: int) -> str:
    return f"{int(value):,}".replace(",", " ")


def _signed(value: float, digits: int) -> str:
    text = _num(abs(value), digits)
    return ("+" if value >= 0 else "−") + text


def reading(summary: dict) -> str:
    """Câu đọc kết quả cho trang, viết TỪ số đo."""
    whole = summary["windows"]["all"]
    best = max(summary["by_year"], key=lambda row: row["loto"]["total"], default=None)
    pro = summary["prospective"]
    parts = [
        f"Walk-forward {_count(whole['loto']['draws'])} kỳ: so với dự báo đều, LOTO {_signed(whole['loto']['total'], 2)} "
        f"nat (z = {_num(whole['loto']['z'], 2)}), Đặc Biệt {_signed(whole['de']['total'], 2)} nat "
        f"(z = {_num(whole['de']['z'], 2)}).",
    ]
    if best is not None and best["loto"]["total"] > 0:
        parts.append(f"Phần lợi lớn nhất nằm ở năm {best['label']} ({_signed(best['loto']['total'], 2)} nat LOTO).")
    if summary["promotion"]["eligible"]:
        parts.append("Mô hình đủ điều kiện xét đưa vào tổ hợp (walk-forward và phép kiểm tiến cứu đều qua ngưỡng).")
    else:
        parts.append(f"Chưa đủ điều kiện vào tổ hợp: cần walk-forward LOTO z ≥ {_num(PROMOTE_Z, 3)} và phép kiểm "
                     "tiến cứu vượt ngưỡng; mô hình chạy bóng.")
    parts.append(f"Phép kiểm tiến cứu (đăng ký {_day(pro['registered_on'])}): {pro['draws']} kỳ đã chấm, "
                 f"e = 10^{_num(pro['log10_e'], 2)} so với ngưỡng 10^{_num(pro['log10_threshold'], 0)}.")
    state = summary["state"]
    parts.append(f"Trước kỳ tới, trọng số của dự báo đều là {_num(100 * state['uniform_weight'], 1)}%; xác suất LOTO "
                 f"lệch tối đa {_num(100 * state['max_relative_loto'], 2)}% so với mức đều.")
    return " ".join(parts)


def _day(iso: str) -> str:
    year, month, day = iso.split("-")
    return f"{day}-{month}-{year}"


def summarize(draws: Draws, *, config: dict = CONFIG, warmup: int = WARMUP, registry_path: Path | None = None,
              ledger_path: Path | None = None) -> dict:
    counts = cage_counts(draws)
    scores, model = walk_forward(counts, loto_outcome(draws), draws.special, config=config, warmup=warmup)
    years = np.array([day.year for day in draws.dates])
    index = np.arange(draws.n)
    windows = {
        "all": _window(scores, index >= warmup, "toàn bộ"),
        "last": _window(scores, index >= max(warmup, draws.n - LAST_DRAWS), f"{LAST_DRAWS} kỳ cuối"),
    }
    by_year = [_window(scores, years == year, str(year)) for year in sorted(set(years.tolist()))
               if np.isfinite(scores["gain_loto"][years == year]).any()]
    fc = model.forecast()
    state = {
        "uniform_weight": fc.uniform_weight,
        "recent_change": fc.recent_change,
        "max_relative_loto": float(np.abs(fc.loto / LOTO_BASELINE_RATE - 1).max()),
        "max_relative_digit": float(np.abs(fc.digits / 0.1 - 1).max()),
        "digits": np.round(fc.digits, 12).tolist(),
        "next_loto": np.round(fc.loto, 12).tolist(),
        "next_special": np.round(fc.special, 12).tolist(),
    }
    if registry_path is not None and ledger_path is not None:
        pro = prospective(draws.dates, scores["log_lr"], registry_path, ledger_path, config=config)
    else:
        pro = {"version": VERSION, "registered_on": draws.dates[-1].isoformat(), "draws": 0, "log10_e": 0.0,
               "log10_threshold": math.log10(1.0 / ALPHA), "evidence": False, "ledger_consistent": True}
    eligible = bool(windows["all"]["loto"]["z"] >= PROMOTE_Z and pro["evidence"])
    summary = {
        "schema_version": SCHEMA_VERSION,
        "version": VERSION,
        "config": _config_json(config),
        "data_through": draws.dates[-1].isoformat(),
        "draws": draws.n,
        "warmup": warmup,
        "fixed_share_bound_nats": fixed_share_bound(int(np.isfinite(scores["gain_loto"]).sum()), config),
        "windows": windows,
        "by_year": by_year,
        "state": state,
        "prospective": pro,
        "promotion": {"eligible": eligible, "walk_forward_z": windows["all"]["loto"]["z"],
                      "prospective_evidence": pro["evidence"], "deployment": "shadow"},
    }
    summary["reading"] = reading(summary)
    return summary


def _rounded(value: object) -> object:
    if isinstance(value, float):
        return round(value, 10) if math.isfinite(value) else None
    if isinstance(value, dict):
        return {key: _rounded(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_rounded(item) for item in value]
    return value


def run(repo_root: Path = REPO_ROOT) -> Path:
    data = repo_root / "data"
    summary = summarize(load(repo_root), registry_path=data / REGISTRY, ledger_path=data / LEDGER)
    out = data / OUT_DIR / SUMMARY
    out.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(out, json.dumps(_rounded(summary), ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    args = parser.parse_args(argv)
    print(f"đã ghi {run(args.repo_root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
