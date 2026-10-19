import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


class CliTests(unittest.TestCase):
    def test_csv_strict_chronology_and_labels(self):
        from vlm.multi_agent.cli import read_csv
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'input.csv'
            p.write_text('cycle,outcome\n0,0;2\n1,1;3\n')
            self.assertEqual(read_csv(p, 5, 2), [(0, (0, 2)), (1, (1, 3))])
            for content in ['cycle,outcome\n1,0;2\n', 'cycle,outcome\n0,0;0\n',
                            'cycle,outcome\n0,0;5\n', 'cycle,outcome\n0,1.0;2\n',
                            'cycle,outcome\n0,0;1\n0,1;2\n', 'wrong,header\n0,0;1\n']:
                p.write_text(content)
                with self.assertRaises(ValueError):
                    read_csv(p, 5, 2)

    def test_demo_returns_real_finite_metrics(self):
        from vlm.multi_agent.cli import main
        output = io.StringIO()
        with redirect_stdout(output):
            result = main(['demo', '--n', '5', '--k', '2', '--cycles', '8'])
        self.assertEqual(result, 0)
        report = json.loads(output.getvalue())
        self.assertEqual(report['cycles'], 8)
        self.assertEqual(report['data_kind'], 'synthetic_no_real_world_accuracy_claim')
        self.assertEqual(report['next_forecast']['cycle'], 8)

    def test_bad_csv_does_not_create_database(self):
        from vlm.multi_agent.cli import main
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'input.csv'
            db = Path(d) / 'bad.sqlite'
            p.write_text('cycle,outcome\n0,0;1\n2,1;2\n')
            with redirect_stdout(io.StringIO()):
                code = main(['replay', '--csv', str(p), '--n', '5', '--k', '2', '--database', str(db)])
            self.assertEqual(code, 2)
            self.assertFalse(db.exists())


if __name__ == '__main__':
    unittest.main()
