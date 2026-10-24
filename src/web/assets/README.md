# Tài nguyên phông

`InterVariable.woff2` — Inter v4.1, bản variable đã cắt gọn (subset) còn Latin +
Latin Extended + khối tiếng Việt + dấu câu thông dụng.

| | |
|---|---|
| Nguồn | https://github.com/rsms/inter/releases/tag/v4.1 |
| Giấy phép | SIL Open Font License 1.1 — xem `Inter-LICENSE.txt` |
| Kích thước gốc | 344 KB |
| Sau khi cắt gọn | 172 KB |
| Trục variable | `wght` 100–900, `opsz` 14–32 (giữ nguyên) |
| Ký tự tiếng Việt | đủ 74/74 đã kiểm |

## Vì sao tự host thay vì Google Fonts

Chính sách bảo mật của trang đặt `font-src 'self'`, nên mọi phông từ tên miền
khác đều bị chặn — im lặng, không báo lỗi. Trước thay đổi này CSS khai báo
`Aptos` mà kho **không có tệp phông nào và không có quy tắc `@font-face` nào**,
nên trang chưa bao giờ thật sự hiển thị bằng Aptos: máy nào không cài sẵn
Microsoft 365 đều rơi về `system-ui`.

Inter còn giải quyết một vấn đề khác: Aptos thuộc Microsoft 365 và **không được
phép phân phối lại**, nên không thể tự host hợp pháp. Inter theo giấy phép SIL
OFL thì được, miễn giữ kèm tệp giấy phép — đó là lý do `Inter-LICENSE.txt` nằm
cạnh tệp phông và được sao chép sang `docs/assets/` cùng nó.

## Cách tái tạo bản cắt gọn

```bash
pip install fonttools brotli
python -m fontTools.subset InterVariable.woff2 \
  --unicodes="U+0000-00FF,U+0100-017F,U+0180-024F,U+0300-036F,U+1EA0-1EF9,\
U+2000-206F,U+20AB,U+2070-209F,U+2122,U+2190-2193,U+2212,U+2248,U+00D7,U+00B7" \
  --layout-features='*' --flavor=woff2 --output-file=InterVariable.woff2
```

Dải `U+1EA0-1EF9` là khối tiếng Việt và `U+0300-036F` là dấu kết hợp — thiếu một
trong hai thì chữ có dấu sẽ hỏng.
