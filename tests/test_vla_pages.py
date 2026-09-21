from __future__ import annotations

"""Bất biến cấp TRANG cho cả hai mươi chín trang đã xuất bản.

Ba nhóm, và nhóm cuối là nhóm dễ bỏ quên nhất:

* **Cấu trúc** — mỗi trang đúng một ``<h1>``, có CSP, có ``lang="vi"``, mọi
  bảng có ``<caption>``, mọi trang trong sidebar có đúng một mục đang mở.
* **Thuật ngữ** — mục IX đòi chữ hiển thị là "Đặc Biệt", còn định danh kỹ
  thuật (tên tệp, ``mode="de"``) giữ nguyên. Hai luật này NGƯỢC nhau nên phải
  kiểm riêng từng luật.
* **Trung thực** — mọi trang mang tính dự đoán phải có cảnh báo, và mọi bảng
  xác suất phải có cột đường cơ sở. Đây là bất biến về NỘI DUNG chứ không
  phải về hình thức, và nó là thứ giữ cho trang không biến một xác suất
  23,9% trên nền 23,77% thành một phát hiện.
"""

import re
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from vla_design.navigation import NAV, all_items

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"

#: Trang QA của khung, không phải trang sản phẩm.
PREVIEW = "_shell-preview.html"

PAGES = sorted(p for p in DOCS.glob("*.html") if p.name != PREVIEW)
IDS = [p.name for p in PAGES]

#: Trang có bảng xác suất và BẮT BUỘC phải kèm cột đường cơ sở.
PROBABILITY_PAGES = {
    "dashboard.html",
    "giai-db-ngay-mai.html",
    "ml_top10_loto.html",
    "ml_top10_de.html",
    "soi-path-loto-stable.html",
    "soi-path-loto-active.html",
    "soi-path-de-stable.html",
    "soi-path-de-active.html",
}

#: Hai biến thể trang chủ KHÔNG nằm trong sidebar — ba mục dẫn tới cùng nội
#: dung thì không mục nào nhận ra được là đang mở.
UNLISTED = {"landing.html", "landing_desktop.html"}


def _soup(path: Path) -> BeautifulSoup:
    return BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")


def test_every_page_in_the_navigation_model_was_actually_built() -> None:
    """Mô hình điều hướng và thư mục xuất bản phải KHỚP hai chiều.

    Thiếu một chiều là một liên kết chết; thừa một chiều là một trang không ai
    tới được. Giao diện cũ có đúng lỗi này: bốn trang soi-path nằm lệch khỏi
    phần còn lại vì không trình dựng nào chạy lại chúng.
    """
    wanted = {item.href for item in all_items()}
    built = {p.name for p in PAGES}
    assert not wanted - built, f"khai trong điều hướng mà chưa dựng: {sorted(wanted - built)}"
    assert not built - wanted, f"đã dựng mà không có trong điều hướng: {sorted(built - wanted)}"
    assert len(wanted) == 29, f"phải có đúng 29 trang, đang có {len(wanted)}"


@pytest.mark.parametrize("path", PAGES, ids=IDS)
def test_each_page_has_exactly_one_heading_and_declares_its_language(path: Path) -> None:
    """Một ``<h1>``, ngôn ngữ ``vi``, và một chính sách CSP.

    Hai ``<h1>`` làm trình đọc màn hình báo hai tiêu đề trang; không có
    ``lang`` thì bộ đọc phát âm tiếng Việt bằng quy tắc tiếng Anh.
    """
    soup = _soup(path)
    assert len(soup.find_all("h1")) == 1, f"{path.name}: số <h1> phải là 1"
    assert soup.html.get("lang") == "vi", f"{path.name}: thiếu lang=\"vi\""
    csp = soup.find("meta", attrs={"http-equiv": "Content-Security-Policy"})
    assert csp is not None, f"{path.name}: thiếu Content-Security-Policy"
    assert "default-src 'none'" in csp.get("content", ""), f"{path.name}: CSP không mặc-định-đóng"


@pytest.mark.parametrize("path", PAGES, ids=IDS)
def test_every_table_on_every_page_has_a_caption(path: Path) -> None:
    """Bảng không có ``<caption>`` là bảng trình đọc màn hình không giới thiệu được.

    Với những trang mang bốn bảng cạnh nhau, người dùng trình đọc màn hình
    không có cách nào biết mình đang ở bảng nào.
    """
    missing = [
        str(t.get("class")) for t in _soup(path).find_all("table") if not t.find("caption")
    ]
    assert not missing, f"{path.name}: {len(missing)} bảng thiếu caption"


@pytest.mark.parametrize("path", PAGES, ids=IDS)
def test_the_navigation_marks_exactly_one_current_page(path: Path) -> None:
    """Đúng một mục mang ``aria-current="page"`` — hoặc không mục nào, ở hai
    biến thể trang chủ vốn cố ý nằm ngoài sidebar."""
    marked = _soup(path).select('.vla-nav-link[aria-current="page"]')
    expected = 0 if path.name in UNLISTED else 1
    assert len(marked) == expected, (
        f"{path.name}: có {len(marked)} mục đang mở, cần {expected}"
    )
    # Và phải trỏ ĐÚNG trang này. Đếm số mục là chưa đủ: một trang khai nhầm
    # `nav_key` vẫn đánh dấu đúng MỘT mục — chỉ là mục của trang khác, nên
    # người đọc thấy mình đang ở chỗ mình không ở.
    if marked:
        assert marked[0].get("href") == path.name, (
            f"{path.name}: mục đang mở trỏ tới {marked[0].get('href')!r}"
        )


@pytest.mark.parametrize("path", PAGES, ids=IDS)
def test_no_visible_text_says_de_where_it_means_dac_biet(path: Path) -> None:
    """Chữ hiển thị phải là "Đặc Biệt", theo mục IX.

    Chỉ soi CHỮ NGƯỜI ĐỌC THẤY, không soi thuộc tính hay đường dẫn: tên tệp
    ``ml_top10_de.html`` và khoá ``mode="de"`` phải giữ nguyên, vì tên tệp là
    URL và đổi nó làm chết mọi liên kết đã lưu.
    """
    soup = _soup(path)
    for tag in soup(["script", "style", "code"]):
        tag.decompose()
    text = soup.get_text(" ", strip=True)
    # Từ "đề" đứng riêng như một danh từ chỉ loại xổ số. Không bắt "đề" trong
    # "vấn đề", "chủ đề", "đề bạt" — nên đòi nó đứng sau một từ khoá ngữ cảnh.
    offenders = re.findall(r"\b(?:Thống kê|Dự đoán|Bảng|Giải|Cầu|Chu kỳ|Top 10)\s+đề\b", text, re.IGNORECASE)
    assert not offenders, f"{path.name}: còn dùng 'đề' thay vì 'Đặc Biệt': {offenders[:3]}"


@pytest.mark.parametrize("path", PAGES, ids=IDS)
def test_the_technical_identifiers_were_not_renamed(path: Path) -> None:
    """Định danh kỹ thuật KHÔNG được đổi theo quy tắc hiển thị.

    Luật ngược với phép kiểm trên, và cần cả hai: một phép thay chuỗi vô tội
    vạ sẽ đổi ``ml_top10_de.html`` thành ``ml_top10_dac_biet.html`` và làm
    chết mọi liên kết đã lưu của người đọc.
    """
    html = path.read_text(encoding="utf-8")
    for dead in ("ml_top10_dac_biet", "soi-path-dac-biet", "weights_dac_biet"):
        assert dead not in html, f"{path.name}: định danh kỹ thuật bị đổi tên: {dead}"


@pytest.mark.parametrize("path", PAGES, ids=IDS)
def test_a_predictive_page_always_carries_its_warning(path: Path) -> None:
    """Trang mang tính dự đoán phải nói rõ bản chất số liệu.

    Không phải lời rào đón lấy lệ: kho đã quét 824 328 giả thuyết và KHÔNG
    cái nào sống sót sau hiệu chỉnh đa giả thuyết. Câu cảnh báo là kết luận
    ấy nói thành lời.
    """
    # Mọi trang phân tích, không chỉ trang xác suất. Đo bằng đột biến: bản đầu
    # chỉ soi tám trang trong PROBABILITY_PAGES, nên bỏ cảnh báo khỏi `lo-gan`
    # vẫn xanh — mà chính lô gan là trang dễ bị đọc thành "con này đến hạn"
    # nhất. Chỉ hai biến thể trang chủ được miễn, vì chúng không mang bảng nào.
    if path.name in UNLISTED:
        return
    soup = _soup(path)
    # CHỈ soi phần nội dung. Chân sidebar cũng mang câu "THỐNG KÊ MÔ TẢ" và nó
    # có mặt trên MỌI trang, nên soi cả tài liệu thì phép kiểm luôn xanh —
    # đo bằng đột biến: bỏ hẳn cảnh báo khỏi trang lô gan vẫn không đỏ.
    main = soup.select_one("#vla-content")
    assert main is not None, f"{path.name}: không tìm thấy vùng nội dung"

    # Đòi KHỐI cảnh báo, không đòi một câu chữ cụ thể. Khớp chữ sẽ buộc mọi
    # trang dùng chung một câu, trong khi `research-lab` và `live` có cảnh báo
    # riêng đúng với nội dung của chúng — và một câu chung chung lặp lại ở hai
    # mươi chín trang thì người đọc ngừng đọc nó.
    blocks = main.select(".vla-disclaimer")
    assert blocks, f"{path.name}: nội dung trang không mang khối cảnh báo nào"
    assert any(len(b.get_text(" ", strip=True)) > 40 for b in blocks), (
        f"{path.name}: khối cảnh báo rỗng hoặc quá ngắn để nói được điều gì"
    )


@pytest.mark.parametrize(
    "path", [p for p in PAGES if p.name in PROBABILITY_PAGES], ids=sorted(PROBABILITY_PAGES)
)
def test_a_probability_table_always_shows_the_baseline(path: Path) -> None:
    """Bảng xác suất phải có cột ĐƯỜNG CƠ SỞ đứng cạnh.

    Đây là bất biến quan trọng nhất của cả sản phẩm. Với lô tô, đường cơ sở là
    23,766%; một con "top 10" ở 23,887% hơn nó đúng 0,12 điểm phần trăm. Bỏ
    cột ấy đi thì con số 23,887% trông như một phát hiện, trong khi nó gần như
    không phân biệt được với việc chọn bừa.
    """
    soup = _soup(path)
    tables = soup.select("table")
    if not tables:
        # Không có bảng thì PHẢI là trạng thái rỗng hoặc lỗi có thật, không
        # phải một trang đã lặng lẽ đánh rơi bảng của nó. Đo được: dữ liệu
        # `paths_de_active.csv` hiện chỉ có dòng tiêu đề, nên trang ấy ở
        # trạng thái rỗng một cách chính đáng — và bản đầu của phép kiểm này
        # báo đỏ nhầm cho nó.
        assert soup.select(".vla-state"), (
            f"{path.name}: không có bảng xác suất mà cũng không có trạng thái rỗng/lỗi"
        )
        return
    cells = soup.select('td[data-col="coso"]')
    assert cells, f"{path.name}: bảng xác suất thiếu cột đường cơ sở"

    # Và giá trị phải ĐÚNG, không chỉ tồn tại. Đường cơ sở bằng 0 làm mọi xác
    # suất trông như lợi thế vô hạn — một cột có mặt nhưng sai giá trị còn tệ
    # hơn không có cột, vì nó trông như đã được kiểm.
    # So bằng SỐ, không bằng chuỗi. So chuỗi buộc mọi trang phải trùng khít
    # cách định dạng, nên một thay đổi độ chính xác vô hại sẽ báo đỏ nhầm —
    # đúng lỗi bản đầu của phép kiểm này mắc với ba trang soi path.
    numbers = set()
    for cell in cells:
        text = cell.get_text(strip=True).removesuffix("%").replace(",", ".")
        try:
            numbers.add(round(float(text), 2))
        except ValueError:
            continue
    # Lô tô: 100 × (1 − (99/100)^27) = 23,7657% — 27 ô giải trên 100 con.
    # Đặc Biệt: một ô giải, 100 con, nên đúng 1%.
    assert numbers & {23.77, 1.0}, (
        f"{path.name}: đường cơ sở {sorted(numbers)[:3]} không khớp tỉ lệ nền thật "
        "(lô tô 23,766%; Đặc Biệt 1,000%)"
    )

    # Và phải đủ ba chữ số thập phân. Ở Đặc Biệt, 1,00% so với 1,01% là không
    # phân biệt được ở hai chữ số — tức cột này mất đúng công dụng của nó.
    assert any(len(c.get_text(strip=True).split(",")[-1]) >= 4 for c in cells), (
        f"{path.name}: đường cơ sở làm tròn quá thô để so sánh được"
    )


@pytest.mark.parametrize("path", PAGES, ids=IDS)
def test_every_page_says_where_its_numbers_came_from(path: Path) -> None:
    """Mỗi trang phải truy được về tệp dữ liệu sinh ra số của nó.

    Không có dòng này thì người đọc không phân biệt được số đo thật với số
    minh hoạ — và một trang phân tích mất khả năng ấy thì mất luôn lý do tồn
    tại.
    """
    soup = _soup(path)
    has_source = bool(soup.select(".vla-source-note"))
    has_state = bool(soup.select(".vla-state"))
    assert has_source or has_state, (
        f"{path.name}: không ghi nguồn dữ liệu và cũng không ở trạng thái rỗng/lỗi"
    )


def test_the_navigation_covers_every_group_on_every_page() -> None:
    """Sidebar phải giống nhau ở MỌI trang.

    Giao diện cũ để bốn trang soi-path lệch khỏi phần còn lại; ở đây sidebar
    dựng từ một mô hình duy nhất, và phép kiểm này ghim điều đó.
    """
    expected_links = sum(len(group.items) for group in NAV)
    for path in PAGES:
        links = _soup(path).select(".vla-nav-link")
        assert len(links) == expected_links, (
            f"{path.name}: sidebar có {len(links)} liên kết, các trang khác có {expected_links}"
        )
