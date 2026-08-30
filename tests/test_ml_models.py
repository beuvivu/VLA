from __future__ import annotations

import pickle
import sys
import unittest
from pathlib import Path as _Path

sys.path.insert(0, str((_Path(__file__).resolve().parents[1] / "src")))

from ml_models import PlattCalibratedClassifier


class TestMlModelSerialization(unittest.TestCase):
    def test_classifier_is_importable_for_joblib_pickle(self):
        clf = PlattCalibratedClassifier()
        blob = pickle.dumps(clf)
        loaded = pickle.loads(blob)
        self.assertEqual(loaded.__class__.__module__, "ml_models")


if __name__ == "__main__":
    unittest.main()
