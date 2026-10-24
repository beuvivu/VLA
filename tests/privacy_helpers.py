"""Chuỗi không được lộ ra trang xuất bản, dùng chung cho các nhóm phép kiểm."""

#: Những chuỗi không được xuất hiện trong thứ gửi ra ngoài.
#:
#: `vla` trần, không phải `vla-`. Danh sách trước chỉ chặn dạng có gạch nối
#: nên bỏ lọt hai thứ thật: tên tệp `assets/vla.css` gửi thẳng ra trang trong
#: một thẻ <link>, và các khoá localStorage `vla.picked.` / `vla.defields.`.
#: Chặn theo tiền tố thì không còn khe nào. Từ 24-10-2026 thống kê và cầu theo đường nằm
#: dưới `data/stats/` và `data/soi_cau/`; tiền tố cũ vẫn chặn cho bản sao còn sót.
LEAK_TOKENS = (
    "githubusercontent", "github.io", "github.com", "beuvivu",
    "workers.dev", "deno.dev", "data/xsmb", "data/advanced", "data/stats",
    "data/path", "data/soi_cau", "data/live", "vla", "VLA",
)
