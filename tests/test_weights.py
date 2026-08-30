from __future__ import annotations

import unittest

from ensemble_utils import EnsembleWeights


class TestWeightsFormat(unittest.TestCase):
    def test_five_component_weights_normalize(self):
        w = EnsembleWeights(w_ml=0.25, w_cau=0.30, w_stat=0.20, w_active=0.125, w_stable=0.125).normalized()
        self.assertAlmostEqual(w.w_ml + w.w_cau + w.w_stat + w.w_active + w.w_stable, 1.0, places=9)

    def test_invalid_sum_is_normalized(self):
        w = EnsembleWeights(w_ml=2.0, w_cau=1.0, w_stat=0.5, w_active=-1.0, w_stable=0.0).normalized()
        self.assertAlmostEqual(w.w_ml + w.w_cau + w.w_stat + w.w_active + w.w_stable, 1.0, places=9)
        self.assertGreaterEqual(w.w_active, 0.0)


if __name__ == "__main__":
    unittest.main()
