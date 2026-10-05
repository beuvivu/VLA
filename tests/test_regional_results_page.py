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
