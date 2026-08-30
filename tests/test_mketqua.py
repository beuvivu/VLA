from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path as _Path

sys.path.insert(0, str((_Path(__file__).resolve().parents[1] / "src")))

from sources import MketquaSource


class DummyResp:
    def __init__(self, text: str, status_code: int = 200):
        self.text = text
        self.status_code = status_code


class DummyHttp:
    def __init__(self, text: str, status_code: int = 200):
        self._resp = DummyResp(text, status_code=status_code)

    def get(self, url: str, timeout: int = 20):
        return self._resp


class TestMketquaParsing(unittest.TestCase):
    def test_parse_date_section_with_leading_zeroes(self):
        html_text = """
        Thứ ba ngày 11-08-2026
        Ký tự | 3ES
        Đặc biệt | 92191
        Giải nhất | 64720
        Giải nhì | 08936 35676
        Giải ba | 58345 86863 36851 91550 59891 01824
        Giải tư | 1196 9596 6005 0872
        Giải năm | 3220 3169 8526 0486 7849 4836
        Giải sáu | 982 824 787
        Giải bảy | 22 92 40 00

        Thứ hai ngày 10-08-2026
        Đặc biệt | 92957
        """
        src = MketquaSource()
        res = src.fetch(date(2026, 8, 11), DummyHttp(html_text))
        self.assertIsNotNone(res)
        assert res is not None
        self.assertEqual(res.prize2_1, 8936)
        self.assertEqual(res.prize7_4, 0)


if __name__ == "__main__":
    unittest.main()
