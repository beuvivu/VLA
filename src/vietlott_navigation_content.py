"""Các đích điều hướng Vietlott, tính từ bản dữ liệu đã xác thực của engine."""
from collections import Counter
from html import escape
from itertools import combinations


def statistics(draws: list[dict], maximum: int) -> dict:
    """Đếm số chính theo kỳ; không trộn số đặc biệt hoặc các sản phẩm."""
    counts: Counter = Counter()
    pairs: Counter = Counter()
    for draw in draws:
        numbers = sorted({int(n) for n in draw.get("numbers", []) if 1 <= int(n) <= maximum})
        counts.update(numbers)
        pairs.update(combinations(numbers, 2))
    ordered = sorted(range(1, maximum + 1), key=lambda n: (-counts[n], n))
    cold = sorted(range(1, maximum + 1), key=lambda n: (counts[n], n))
    return {"count": len(draws), "counts": counts, "hot": ordered[:5], "cold": cold[:5],
            "pairs": sorted(pairs.items(), key=lambda p: (-p[1], p[0]))[:10]}


def overview_sections(dashboard: dict) -> str:
    """Tổng hợp thống kê, dự báo, đối soát và trạng thái; không gọi mạng."""
    import build_vietlott_results as b

    def section(key, title, body, note=""):
        return (f'<section class="vl-section" aria-labelledby="{key}"><h2 id="{key}">{title}</h2>'
                + (f'<p class="vl-muted">{note}</p>' if note else "") + body + '</section>')

    def table(headers, rows):
        if not rows:
            return '<p class="vl-empty">Chưa có dữ liệu đã xác thực trong bản cập nhật này.</p>'
        return ('<div class="vl-table-wrap"><table class="vl-table"><thead><tr>'
                + ''.join(f'<th scope="col">{escape(h)}</th>' for h in headers) + '</tr></thead><tbody>'
                + ''.join('<tr>' + ''.join(f'<td>{v}</td>' for v in row) + '</tr>' for row in rows)
                + '</tbody></table></div>')

    by_code = {p['product']: p for p in dashboard.get('products', [])}
    analysis = dashboard.get('analysis') or {}
    frequencies, pair_rows, temperatures = [], [], []
    for code, maximum in [('lotto535', 35), ('mega645', 45), ('power655', 55), ('keno', 80)]:
        data = by_code.get(code, {})
        draws = data.get('draws') or []
        if not draws:
            continue
        stats = statistics(draws, maximum)
        name = b.PRODUCTS[code][0]
        frequencies.append('<details class="app-vietlott-detail"><summary>' + escape(name)
                           + f' · {stats["count"]} kỳ có trong bản dữ liệu</summary>'
                           + table(['Số chính', 'Số kỳ xuất hiện', 'Tỷ lệ theo kỳ'], [
                               [f'{n:02d}', str(stats['counts'][n]), f'{stats["counts"][n] / stats["count"]:.1%}']
                               for n in range(1, maximum + 1)]) + '</details>')
        pair_rows.extend([[escape(name), f'{a:02d}–{c:02d}', str(count), str(stats['count'])]
                          for (a, c), count in stats['pairs']])
        label = lambda nums: ' · '.join(f'{n:02d} ({stats["counts"][n]})' for n in nums)
        temperatures.append([escape(name), label(stats['hot']), label(stats['cold']), str(stats['count'])])

    rendered = [section('vl-frequency', 'Tần suất số chính', ''.join(frequencies) or table([], []),
                        'Đếm trên các kỳ gần nhất đang được công bố; mỗi số tính tối đa một lần mỗi kỳ. Không gồm số đặc biệt. Max 3D và Bingo18 có cấu trúc khác nên không gộp vào bảng này.'),
                section('vl-pairs', 'Cặp số cùng xuất hiện', table(['Sản phẩm', 'Cặp số', 'Cùng kỳ', 'Số kỳ khảo sát'], pair_rows),
                        '10 cặp phổ biến nhất mỗi sản phẩm; hòa tần suất được sắp theo giá trị số.'),
                section('vl-hot-cold', 'Hot / Cold', table(['Sản phẩm', '5 số xuất hiện nhiều', '5 số xuất hiện ít', 'Số kỳ'], temperatures),
                        'Số trong ngoặc là số kỳ xuất hiện. Đây là mô tả lịch sử, không phải xác suất kỳ sau; khi hòa, thứ tự theo giá trị số.')]
    prediction_cards, confidence_cards, comparison_cards = [], [], []
    boards, status, parameters, models = [], [], [], []
    for code, (name, file, _desc) in b.PRODUCTS.items():
        data = by_code.get(code, {})
        model = analysis.get(code) or {}
        evidence = model.get('evidence') or {}
        forecast = data.get('next_forecast')
        heading = f'<h3><a href="{file}">{escape(name)}</a></h3>'
        prediction_cards.append('<article class="app-vietlott-card">' + heading + b.forecast_markup(code, forecast) + '</article>')
        confidence_cards.append('<article class="app-vietlott-card">' + heading
                                + (b.analysis_markup(model) if model else '<p>Chưa có phân tích mô hình.</p>') + '</article>')
        comparisons = data.get('comparisons') or []
        comparison_cards.append('<article class="app-vietlott-card">' + heading + b.comparisons_markup(code, comparisons) + '</article>')
        board = model.get('board') or {}
        boards.append([escape(name), b.esc(board.get('recorded', '—')), b.esc(board.get('scored', '—')),
                       b.esc(board.get('hits', '—')), b.esc(board.get('expected', '—'))])
        latest = data.get('latest') or {}
        status.append([escape(name), b.esc(latest.get('draw_id', '—')), b.day_label(latest.get('draw_date')),
                       escape(data.get('schedule') or 'Chưa có lịch'), 'Có dữ liệu xác thực' if latest else 'Chưa có dữ liệu'])
        parameters.append([escape(name), b.esc(model.get('draws', '—')), b.esc(evidence.get('threshold_log10', '—')),
                           'Toàn bộ lịch sử hợp lệ' if evidence.get('valid') else 'Chưa xác nhận cửa sổ kiểm định'])
        engine = {'ml': 'ML', 'legacy': 'Tự học trực tuyến'}.get((forecast or {}).get('engine'), 'Chưa có dự báo')
        models.append([escape(name), engine, b.esc((forecast or {}).get('target_id', '—')),
                       ('Đã ghi trước kỳ' if forecast.get('registered') else 'Tham khảo') if forecast else 'Chưa có dự báo',
                       b.esc((forecast or {}).get('based_on_id', '—'))])
    rendered.extend([
        section('vl-predictions', 'AI & ML · Phỏng đoán bộ số', '<div class="vl-cols">' + ''.join(prediction_cards) + '</div>',
                'Phân biệt dự báo đã ghi trước kỳ và bộ số tham khảo của mô hình.'),
        section('vl-confidence', 'Độ tin cậy mô hình', '<div class="vl-cols">' + ''.join(confidence_cards) + '</div>',
                'Bằng chứng e-value của mô hình tự học trực tuyến, không phải điểm tin cậy của engine ML. Không quy đổi thành phần trăm chắc chắn trúng.'),
        section('vl-comparisons', 'Thực tế vs Dự đoán', ''.join(comparison_cards)),
        section('vl-backtesting', 'Kiểm định dự báo đã công bố', table(['Sản phẩm', 'Đã ghi', 'Đã chấm', 'Số trùng', 'Kỳ vọng ngẫu nhiên'], boards),
                'Sổ kiểm định tiến cứu của mô hình tự học trực tuyến, không gộp sổ ML: chỉ chấm dự báo đã ghi trước kỳ quay. Dấu — nghĩa là chưa có số liệu, không phải bằng 0.'),
        section('vl-crawler', 'Trạng thái dữ liệu Vietlott', table(['Sản phẩm', 'Kỳ mới nhất', 'Ngày quay', 'Lịch quay', 'Trạng thái'], status),
                'Bản dữ liệu được dựng lúc ' + b.stamp_label(dashboard.get('generated_at'))
                + ' (giờ Việt Nam). Đây là bản chụp tại lần dựng trang, không phải heartbeat trực tiếp hoặc lịch sử chạy crawler theo giờ.'),
        section('vl-tuning', 'Tham số kiểm định · chỉ đọc', table(['Sản phẩm', 'Số kỳ học', 'Ngưỡng log10 e-value', 'Phạm vi'], parameters),
                'Giá trị đọc từ trạng thái mô hình. Thay đổi tham số được thực hiện trong quy trình chạy engine; trang công bố không ghi cấu hình.'),
        section('vl-models', 'Danh mục mô hình · chỉ đọc', table(['Sản phẩm', 'Engine dự báo', 'Kỳ đích', 'Đăng ký', 'Học tới kỳ'], models),
                'Trạng thái mô hình đang cung cấp dự báo. Việc huấn luyện, kích hoạt và thay thế mô hình được quản lý bởi pipeline riêng.'),
    ])
    return ''.join(rendered)
