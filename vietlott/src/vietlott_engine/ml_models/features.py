from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from vietlott_engine.core.history import DrawHistory

@dataclass(frozen=True)
class Snapshots:
    x: np.ndarray
    a_hat: np.ndarray
    y: np.ndarray
    feature_names: list[str]


class SnapshotBuilder:

    def __init__(self, n: int, k: int, half_lives: tuple[int, ...] = (10, 30, 100), graph_decay: float = 0.995, markov_smoothing: float = 10.0) -> None:
        self.n, self.k = n, k
        self.base = k / n
        self.half_lives = half_lives
        self.graph_decay = graph_decay
        self.markov_smoothing = markov_smoothing
        self.lams = np.array([0.5 ** (1.0 / hl) for hl in half_lives])
        self.ew = np.zeros((len(half_lives), n))
        self.ew_norm = np.zeros(len(half_lives))
        self.gap = np.zeros(n)
        self.joint = np.zeros((n, n))
        self.row = np.zeros(n)
        self.cooc = np.zeros((n, n))
        self.last: np.ndarray | None = None
        self._eye = np.eye(n)
        self._gap_scale = np.log1p(1 / self.base)
        self._xs: list[np.ndarray] = []
        self._as: list[np.ndarray] = []
        self._ys: list[np.ndarray] = []
        self._emit()

    @property
    def feature_names(self) -> list[str]:
        return [f"rate_hl{hl}" for hl in self.half_lives] + ["log_gap", "in_last_draw", "markov_score"]

    @property
    def draws_seen(self) -> int:
        return len(self._ys)

    def _emit(self) -> None:
        base, hl = self.base, len(self.half_lives)
        x = np.zeros((self.n, hl + 3))
        rates = np.where(self.ew_norm[:, None] > 0, self.ew / np.maximum(self.ew_norm[:, None], 1e-12), base)
        x[:, :hl] = ((rates - base) / np.sqrt(base * (1 - base))).T
        x[:, hl] = (np.log1p(self.gap) - self._gap_scale) / self._gap_scale
        if self.last is not None:
            x[:, hl + 1] = self.last
            trans = (self.joint + self.markov_smoothing * base) / (self.row[:, None] + self.markov_smoothing)
            x[:, hl + 2] = (trans[self.last.astype(bool)].mean(axis=0) - base) / base
        tot = self.cooc.sum()
        if tot > 0:
            deg = self.cooc.sum(axis=1)
            observed = self.cooc > 0
            pmi = np.zeros_like(self.cooc)
            rows, cols = np.nonzero(observed)
            pmi[observed] = np.log(self.cooc[observed]) + np.log(tot) - (np.log(deg[rows]) + np.log(deg[cols]))
            adj = np.maximum(pmi, 0.0) * (1 - self._eye)
        else:
            adj = np.zeros((self.n, self.n))
        adj = adj + self._eye
        dinv = 1.0 / np.sqrt(adj.sum(axis=1))
        self._xs.append(x.astype(np.float32))
        self._as.append((adj * (dinv[:, None] * dinv[None, :])).astype(np.float32))

    def update(self, row: np.ndarray) -> None:
        xt = np.asarray(row, dtype=np.float64)
        self.ew = self.lams[:, None] * self.ew + xt[None, :]
        self.ew_norm = self.lams * self.ew_norm + 1.0
        self.gap = np.where(xt > 0, 0.0, self.gap + 1.0)
        if self.last is not None:
            self.joint += np.outer(self.last, xt)
            self.row += self.last
        self.cooc = self.graph_decay * self.cooc + np.outer(xt, xt)
        self.last = xt
        self._ys.append(xt.astype(np.float32))
        self._emit()

    def snapshots(self) -> Snapshots:
        y = np.stack(self._ys) if self._ys else np.zeros((0, self.n), dtype=np.float32)
        return Snapshots(x=np.stack(self._xs), a_hat=np.stack(self._as), y=y, feature_names=self.feature_names)


def build_snapshots(h: DrawHistory, half_lives: tuple[int, ...] = (10, 30, 100), graph_decay: float = 0.995, markov_smoothing: float = 10.0) -> Snapshots:
    builder = SnapshotBuilder(h.n, h.k, half_lives, graph_decay, markov_smoothing)
    for row in h.incidence:
        builder.update(row)
    return builder.snapshots()


def spectral_embedding(a_hat: np.ndarray, dims: int = 4) -> np.ndarray:
    vals, vecs = np.linalg.eigh(a_hat.astype(np.float64))
    return vecs[:, np.argsort(-vals)[1 : dims + 1]]
