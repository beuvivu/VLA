from __future__ import annotations

from datetime import date

from sources import EXPECTED_COUNTS, PRIZE_ORDER, _parse_result_from_prize_map


def _complete_map() -> dict[str, list[str]]:
    widths = {
        "special": 5,
        "prize1": 5,
        "prize2": 5,
        "prize3": 5,
        "prize4": 4,
        "prize5": 4,
        "prize6": 3,
        "prize7": 2,
    }
    return {
        key: [str(i + 1).zfill(widths[key]) for i in range(EXPECTED_COUNTS[key])]
        for key in PRIZE_ORDER
    }


def test_clean_exact_width_tokens_still_parse():
    result = _parse_result_from_prize_map(date(2026, 9, 1), prize_map=_complete_map())
    assert result is not None
    assert result.special == 1


def test_embedded_alpha_is_rejected_not_repaired():
    pmap = _complete_map()
    pmap["special"] = ["12a345"]  # stripping non-digits would incorrectly yield 12345
    assert _parse_result_from_prize_map(date(2026, 9, 1), prize_map=pmap) is None


def test_digit_run_embedded_in_identifier_is_rejected():
    pmap = _complete_map()
    pmap["special"] = ["ABC12345XYZ"]
    assert _parse_result_from_prize_map(date(2026, 9, 1), prize_map=pmap) is None


def test_html_like_token_is_rejected_not_repaired():
    pmap = _complete_map()
    pmap["special"] = ["<b>12345</b>"]
    assert _parse_result_from_prize_map(date(2026, 9, 1), prize_map=pmap) is None


def test_unicode_decimal_digits_are_rejected_at_ascii_boundary():
    pmap = _complete_map()
    pmap["special"] = ["１２３４５"]
    assert _parse_result_from_prize_map(date(2026, 9, 1), prize_map=pmap) is None
