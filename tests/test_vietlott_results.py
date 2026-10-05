from vietlott_results import parse_detail

def test_parse_mega_preserves_two_digit_numbers():
 html="<h5>Kỳ quay thưởng #01534 ngày 10/07/2026</h5><div>09 17 23 26 42 44</div><p>Các con số dự thưởng phải trùng</p><h5>Giá trị Jackpot</h5><h3>15.125.678.000</h3>"
 d=parse_detail("mega645",html,"https://vietlott.vn/x")
 assert d and d.draw_id=="01534" and d.draw_date=="2026-07-10"
 assert d.result==("09","17","23","26","42","44")

def test_parse_power_bonus():
 html="<h5>Kỳ quay thưởng #01382 ngày 08/08/2026</h5><div>05 29 33 38 40 45 | 37</div><p>Các con số dự thưởng phải trùng</p>"
 d=parse_detail("power655",html)
 assert d and d.result==("05","29","33","38","40","45") and d.bonus=="37"

def test_parse_keno():
 nums=" ".join(f"{i:02d}" for i in range(1,21))
 html=f"<table><tr><td>18/08/2026</td><td>#0292409</td><td>{nums}</td></tr></table><div>C CHẴN 10</div>"
 d=parse_detail("keno",html)
 assert d and len(d.result)==20 and d.result[0]=="01" and d.result[-1]=="20"

def test_parse_bingo18():
 html="<table><tr><td>18/08/2026</td><td>#0182100</td><td>3 5 3</td></tr></table><div>Cửa tổng 11</div><div>Lớn/Hòa/Nhỏ Hòa</div>"
 d=parse_detail("bingo18",html)
 assert d and d.result==("3","5","3")
 assert d.meta_json.find('"sum": 11')>=0

def test_parse_max3d_groups():
 triples=["321","768","784","375","730","099","452","693","901","137","928","093","086","087","039","405","370","657","192","978"]
 html="<h5>Kỳ quay thưởng #01120 ngày 17/08/2026</h5><div>"+" ".join(triples)+"</div><p>Các con số dự thưởng phải trùng</p>"
 d=parse_detail("max3d",html)
 assert d and len(d.result)==20 and d.result[0]=="321" and d.result[-1]=="978"


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
 assert "Chưa có dữ liệu đã đồng bộ" in (tmp_path/"docs"/"vietlott-keno.html").read_text(encoding="utf-8")
