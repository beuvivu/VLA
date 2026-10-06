"""Bộ thu thập Vietlott: đọc đúng bảng của nguồn đăng lại, mỗi kỳ mang ngày và số kỳ
riêng, và trang theo ngày KHÔNG nhận kết quả cùng ngày của năm khác.

HTML mẫu chép nguyên từ trang thật, đọc qua runner Actions ngày 06-10-2026
(``inspect-reference-pages.yml`` với ``html_selector=table``).
"""

from datetime import date

import vietlott_results as v

MEGA = (
    '<table class="result"><tr><td class="kmt" colspan="2"><span>Kỳ mở thưởng:</span> '
    '<a href="/xsmega645/ngay-4-10-2026"><b>#01571</b></a></td></tr><tr><td class="ketquatxt">Kết quả</td>'
    '<td class="megaresult"><em>15 20 29 37 40 45</em></td></tr></table>'
    '<table class="trunggiai"><tr><td colspan="4">Thống kê trúng giải</td></tr><tr><th>Giải</th>'
    "<th>Trùng khớp</th><th>Số người trúng</th><th>Trị giá giải (VNĐ)</th></tr>"
    "<tr><td>J.pot</td><td></td><td><em>1</em></td><td><em>199,576,277,000</em></td></tr>"
    "<tr><td>G.1</td><td></td><td><b>153</b></td><td>10,000,000</td></tr></table>"
)
#: Ngày 05-10 không quay Mega: trang theo ngày hiện kỳ cùng ngày của năm 2025 và 2022.
MEGA_OTHER_YEARS = (
    '<table class="result"><tr><td class="kmt" colspan="2"><a href="/xsmega645/ngay-5-10-2025">'
    '<b>#01415</b></a></td></tr><tr><td class="megaresult"><em>05 14 22 28 32 39</em></td></tr></table>'
    '<table class="result"><tr><td class="kmt" colspan="2"><a href="/xsmega645/ngay-5-10-2022">'
    '<b>#00949</b></a></td></tr><tr><td class="megaresult"><em>09 18 23 24 29 34</em></td></tr></table>'
)
LOTTO = (
    '<table class="result"><tr><td class="kmt" colspan="2"><span>Kỳ mở thưởng:</span> '
    '<a href="/xslotto-21h/ngay-5-10-2026"><b>#00928 (21h)</b></a></td></tr><tr><td class="ketquatxt">'
    'Kết quả</td><td class="megaresult"><em>01 13 16 20 26 <span>11</span></em></td></tr></table>'
    '<table class="trunggiai"><tr><td colspan="4">Thống kê trúng giải</td></tr>'
    "<tr><td>J.pot</td><td></td><td><b>0</b></td><td>10,323,886,500</td></tr></table>"
)
POWER = (
    '<table class="result"><tr><td class="kmt" colspan="2"><a href="/xspower/ngay-3-10-2026"><b>#01406</b>'
    '</a></td></tr><tr><td class="ketquatxt">Kết quả</td><td class="megaresult"><em>07 11 13 16 18 54</em>'
    "</td></tr><tr><td>Số JP2</td><td><em>41</em></td></tr></table>"
    '<table class="trunggiai"><tr><td>J.pot</td><td></td><td>0</td><td>112,784,140,200</td></tr>'
    "<tr><td>Jpot2</td><td></td><td>0</td><td>3,695,872,550</td></tr></table>"
)
MAX3D = (
    '<table class="max3d"><tr><th><b>Max 3D</b></th><th class="kmt">Kỳ MT: <a href="/xsmax3d/ngay-5-10-2026">'
    '<b>#01141</b></a></th><th><b>MAX 3D+</b></th></tr><tr><th class="th2">Trúng giải</th><th class="th2">'
    'Kết quả</th><th class="th2">Trúng giải</th></tr><tr><td class="name"><span>Giải nhất</span><br/>'
    '<span>1tr:</span> <em>80</em></td><td><b class="red">546 085</b></td><td class="name"><span>Đặc biệt'
    '</span><br/><span>1tỷ:</span> <em>0</em></td></tr><tr><td class="name"><span>Giải nhì</span><br/>'
    "<span>350K:</span> <em>201</em></td><td><b>472 486</b><br/><b>159 586</b></td><td></td></tr><tr>"
    '<td class="name"><span>Giải ba</span><br/><span>210K:</span> <em>326</em></td><td><b>525 877</b><br/>'
    "<b>261 110</b><br/><b>123 238</b></td><td></td></tr><tr><td class=\"name\"><span>Giải tư (KK)</span>"
    "<br/><span>100K:</span> <em>277</em></td><td><b>399 183</b><br/><b>166 713</b><br/><b>699 490</b><br/>"
    '<b>993 152</b></td><td></td></tr><tr><td colspan="2"><p><em>Max 3D+:</em> Trùng khớp <strong>2 bộ số'
    "</strong></p></td><td></td></tr></table>"
)
MAX3DPRO = (
    '<table><tr><th>Giải</th><th class="kmt">Kỳ MT: <a href="/xsmax3dpro/ngay-3-10-2026"><b>#00787</b></a>'
    "</th><th>Trúng giải</th></tr><tr><td>Giải ĐB 2 tỷ</td><td><b>509 954</b></td><td>0</td></tr>"
    "<tr><td>G. phụ ĐB 400tr</td><td><b>954 509</b></td><td>0</td></tr>"
    "<tr><td>Giải nhất 30tr</td><td><b>467 123</b><br/><b>573 811</b></td><td>2</td></tr>"
    "<tr><td>Giải nhì 10tr</td><td>101 202<br/>303 404<br/>505 606</td><td>1</td></tr>"
    "<tr><td>Giải ba 4tr</td><td>111 222<br/>333 444<br/>555 666<br/>777 888</td><td>3</td></tr></table>"
)


def test_mega_reads_numbers_draw_id_date_and_jackpot():
    (d,) = v.parse_page("mega645", MEGA, "u")
    assert (d.draw_id, d.draw_date, d.result) == ("01571", "2026-10-04", ("15", "20", "29", "37", "40", "45"))
    assert d.jackpot_1 == 199_576_277_000 and d.bonus == ""


def test_lotto_keeps_the_special_number_and_the_session():
    (d,) = v.parse_page("lotto535", LOTTO)
    assert d.result == ("01", "13", "16", "20", "26") and d.bonus == "11"
    assert '"21h"' in d.meta_json and d.jackpot_1 == 10_323_886_500


def test_power_reads_the_jackpot_2_number_and_both_jackpots():
    (d,) = v.parse_page("power655", POWER)
    assert d.result == ("07", "11", "13", "16", "18", "54") and d.bonus == "41"
    assert (d.jackpot_1, d.jackpot_2) == (112_784_140_200, 3_695_872_550)


def test_max3d_keeps_twenty_triples_in_prize_order():
    (d,) = v.parse_page("max3d", MAX3D)
    assert (d.draw_id, d.draw_date, len(d.result)) == ("01141", "2026-10-05", 20)
    assert d.result[:2] == ("546", "085") and d.result[-1] == "152"
    assert '"fourth"' in d.meta_json


def test_max3d_pro_skips_the_derived_reverse_row():
    (d,) = v.parse_page("max3dpro", MAX3DPRO)
    assert d.result[:2] == ("509", "954") and d.result[2] == "467" and len(d.result) == 20
    assert "954" not in d.result[2:6]


class _Http:
    def __init__(self, pages):
        self.pages, self.asked = pages, []

    def get(self, url, **_):
        self.asked.append(url)
        body = self.pages.get(url)
        return type("R", (), {"status_code": 200 if body else 404, "text": body or ""})()


def test_a_no_draw_day_does_not_borrow_results_from_other_years():
    """Ngày không quay, trang theo ngày hiện kỳ CÙNG NGÀY của năm khác."""
    url = v.day_urls("mega645", date(2026, 10, 5))[0]
    assert v.fetch_day(_Http({url: MEGA_OTHER_YEARS}), "mega645", date(2026, 10, 5)) == []
    url = v.day_urls("mega645", date(2026, 10, 4))[0]
    assert [d.draw_id for d in v.fetch_day(_Http({url: MEGA}), "mega645", date(2026, 10, 4))] == ["01571"]


def test_lotto_reads_both_daily_sessions():
    urls = v.day_urls("lotto535", date(2026, 10, 5))
    assert [u.rsplit("/", 2)[1] for u in urls] == ["xslotto-13h", "xslotto-21h"]


def test_backfill_walks_only_the_product_draw_days():
    days = list(v.backfill_days(date(2026, 10, 4), v.PRODUCTS["mega645"][5], 7))
    # Mega quay thứ Tư, thứ Sáu, Chủ Nhật: 02-10, 30-09, 27-09.
    assert [d.isoformat() for d in days] == ["2026-10-02", "2026-09-30", "2026-09-27"]


def test_products_without_a_source_are_left_empty_not_faked(tmp_path):
    db = v.init_db(tmp_path / "x.sqlite3")
    assert v.crawl_product(db, _Http({}), "keno") == (0, 0)
    assert "keno" not in v.available_products() and "bingo18" not in v.available_products()


def test_pages_are_built_through_the_shell_even_before_the_first_sync(tmp_path):
 """Thiếu cơ sở dữ liệu thì trước đây bỏ qua, để lại bản giữ chỗ viết tay không có
 khung, bằng chứng hay điều hướng. Nay luôn dựng đủ 8 trang, trạng thái trống."""
 import build_vietlott_results as b
 out=b.build(tmp_path)
 assert sorted(p.name for p in out)==sorted(["vietlott.html",*(f for _,f,_ in b.PRODUCTS.values())])
 for path in out:
  page=path.read_text(encoding="utf-8")
  assert 'id="app-rail"' in page and 'id="app-evidence-data"' in page, path.name
  assert "vietlott.vn" not in page and "VLA" not in page, path.name
 assert "Chưa có dữ liệu đã đồng bộ" in (tmp_path/"docs"/"vietlott-mega-645.html").read_text(encoding="utf-8")
 assert "chưa đăng kết quả sản phẩm này" in (tmp_path/"docs"/"vietlott-keno.html").read_text(encoding="utf-8")


def test_gap_days_cover_only_the_draw_days_between_a_broken_id_run():
    known = [("00922", "2026-10-02"), ("00925", "2026-10-04"), ("00926", "2026-10-04")]
    assert v.gap_days(known, None) == [date(2026, 10, 4), date(2026, 10, 3), date(2026, 10, 2)]
    # Mega: kỳ 1570 (02-10) và 1571 (04-10) liền nhau — không có gì phải vá.
    assert v.gap_days([("01570", "2026-10-02"), ("01571", "2026-10-04")], (2, 4, 6)) == []


def test_a_transient_server_error_is_retried_but_a_missing_page_is_not():
    class Flaky:
        def __init__(self, codes):
            self.codes, self.calls = list(codes), 0

        def get(self, url, **_):
            self.calls += 1
            code = self.codes.pop(0)
            return type("R", (), {"status_code": code, "text": "ok"})()

    flaky = Flaky([503, 200])
    assert v._get(flaky, "u", pause=0) == "ok" and flaky.calls == 2
    missing = Flaky([404, 200])
    assert v._get(missing, "u", pause=0) is None and missing.calls == 1
