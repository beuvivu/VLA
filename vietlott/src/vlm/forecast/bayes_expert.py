"""Chuyên gia "hỗn hợp Bayes" cho bộ chữ số: luật dự báo hậu nghiệm của ``vietlott_engine.forecast``.

Vì sao bộ ML cần nó (đo 31-10-2026, 1 000 kỳ cuối của seed, chấm trước – học sau):

* Max 3D lệch thật ở hàng đơn vị: chữ số 6 chiếm 10,6–11,3% ở CẢ sáu giai đoạn 2019 → 2026
  (z từ +1,1 đến +2,7 mỗi giai đoạn). Engine cũ thấy nó bằng e-value (10^2,57; Max 3D Pro 10^2,84).
* Các chuyên gia logistic/GRU/RF của bộ ML không học được độ lệch nhỏ và ổn định ấy: tổng log-score
  so với quay công bằng là −0,158 log10 (Max 3D) và −0,161 log10 (Max 3D Pro). Luật ML ghi vào sổ cho
  P(6 ở hàng đơn vị) = 0,1001, nên năm bộ ba công bố đổi mỗi kỳ theo nhiễu.
* Một Dirichlet đầy đủ cũng không phải lời giải: 27 tham số tự do tốn khoảng (d/2)·log n nats để học,
  nhiều hơn lợi ích của một độ lệch 1%. Hỗn hợp Bayes chia sẻ cố định trên các "tilt" thưa (mỗi giả
  thuyết MỘT tham số) cùng Dirichlet co mạnh chỉ trả log(số chuyên gia) — đúng thứ engine cũ làm.

Chuyên gia này chạy đúng ``Component`` của engine cũ trên các kỳ bộ ML được học, theo cùng thứ tự
chấm trước – học sau, và đưa luật ``Σ_j v_j q_j`` của nó vào ensemble ML như một chuyên gia. Trọng số
Bayes của ensemble quyết định có tin nó hay không; trên sản phẩm không có độ lệch, luật ấy gần như
đều và không làm ensemble kém đi.
"""
from __future__ import annotations

import numpy as np

from vietlott_engine.forecast.data import CONFIGS, DigitSpec
from vietlott_engine.forecast.engine import Component, Forecaster, _from_jsonable, _jsonable
from vietlott_engine.core.products import ProductCode

#: Tên chuyên gia trong ensemble ML.
NAME = 'bayes_mixture'


class BayesMixtureExpert:
    """Luật hậu nghiệm của hỗn hợp Bayes (engine cũ) cho MỘT thành phần chữ số."""

    def __init__(self, product: ProductCode, name: str, spec: DigitSpec) -> None:
        if not isinstance(spec, DigitSpec):
            raise ValueError('Chuyên gia hỗn hợp Bayes chỉ dành cho bộ chữ số')
        cfg = CONFIGS[product]
        switch = 1.0 / (Forecaster.SWITCH_YEARS * cfg.draws_per_year)
        self.product, self.name, self.spec = product, name, spec
        self.component = Component(name, spec, cfg.logistic_batch, switch)
        self.state = self.component.init_state()

    def predict(self) -> np.ndarray:
        """Xác suất từng ký hiệu ở từng vị trí cho kỳ kế tiếp, phẳng ``positions·alphabet``."""
        return np.asarray(self.state['v'] @ self.component.predictions(self.state), dtype=float)

    def learn(self, counts: np.ndarray, draw_id: int) -> None:
        """Học MỘT kỳ: ``counts`` là số lần mỗi ký hiệu về ở mỗi vị trí, phẳng hoặc (L, A)."""
        c = np.asarray(counts, dtype=np.float64).reshape(1, self.spec.positions, self.spec.alphabet)
        _, self.state = self.component.process(self.state, {'C': c}, np.array([int(draw_id)]))

    def to_dict(self) -> dict:
        return {'product': self.product.value, 'name': self.name, 'state': _jsonable(self.state)}

    @classmethod
    def from_dict(cls, data: dict, product: ProductCode, name: str, spec: DigitSpec) -> BayesMixtureExpert:
        if data.get('product') != product.value or data.get('name') != name:
            raise ValueError('Chuyên gia hỗn hợp Bayes thuộc sản phẩm/thành phần khác')
        out = cls(product, name, spec)
        state = _from_jsonable(data['state'])
        v = np.asarray(state['v'], dtype=float)
        if v.shape != out.state['v'].shape or (v < 0).any() or not np.isclose(v.sum(), 1) or not np.isfinite(v).all():
            raise ValueError('Trọng số hỗn hợp Bayes không hợp lệ')
        out.state = state
        return out
