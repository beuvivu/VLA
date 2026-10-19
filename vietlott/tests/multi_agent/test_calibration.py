import asyncio
import unittest

from vlm.multi_agent.engine import PredictiveEngine


class CalibrationBoundaryTests(unittest.TestCase):
    def test_every_label_enters_exactly_one_probability_bin(self):
        async def run():
            for k in range(1, 6):
                engine = PredictiveEngine(5, k)
                try:
                    await engine.predict(0)
                    await engine.observe(0, list(range(k)))
                    report = (await engine.predict(1))['calibration']
                    self.assertEqual(sum(b['label_observations'] for b in report['calibration_bins']), 5,
                                     f'All marginal labels must be counted at probability {k}/5.')
                finally:
                    engine.close()
        asyncio.run(run())


if __name__ == '__main__':
    unittest.main()
