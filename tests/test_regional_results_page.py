from build_regional_results import render


def test_regional_pages_render_without_seed_data():
    for region, label in (("mt", "XSMT"), ("mn", "XSMN")):
        page = render(region, [])
        assert label in page
        assert "Chưa có dữ liệu đã lưu." in page
        assert 'id="rg-data"' in page
        assert "json.dumps" not in page


def test_regional_pages_keep_xsmb_priority_message():
    page = render("mt", [])
    assert "Ưu tiên hệ thống: XSMB" in page


def test_regional_pages_never_name_where_the_data_comes_from():
    """Luật riêng tư của kho: không vẽ danh tính nguồn dữ liệu ra trình duyệt."""
    from sources import REGIONAL_SOURCE_NAMES

    row = {"date": "2026-10-05", "province": "Cà Mau", "prize": "ĐB", "value": "030118"}
    for region in ("mt", "mn"):
        for rows in ([], [row]):
            page = render(region, rows)
            for name in REGIONAL_SOURCE_NAMES:
                assert name not in page
            assert "vla" not in page.lower().replace("vietlott", "")
