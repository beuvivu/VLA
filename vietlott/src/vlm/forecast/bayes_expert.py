from __future__ import annotations

import numpy as np

from vietlott_engine.forecast.data import CONFIGS, DigitSpec
from vietlott_engine.forecast.engine import Component, Forecaster, _from_jsonable, _jsonable
from vietlott_engine.core.products import ProductCode

NAME = 'bayes_mixture'


class BayesMixtureExpert:

    def __init__(self, product: ProductCode, name: str, spec: DigitSpec) -> None:
        if not isinstance(spec, DigitSpec):
            raise ValueError('Chuyên gia hỗn hợp Bayes chỉ dành cho bộ chữ số')
        cfg = CONFIGS[product]
        switch = 1.0 / (Forecaster.SWITCH_YEARS * cfg.draws_per_year)
        self.product, self.name, self.spec = product, name, spec
        self.component = Component(name, spec, cfg.logistic_batch, switch)
        self.state = self.component.init_state()

    def predict(self) -> np.ndarray:
        return np.asarray(self.state['v'] @ self.component.predictions(self.state), dtype=float)

    def learn(self, counts: np.ndarray, draw_id: int) -> None:
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
