# PLAN: BOM Management Web Tool

Phiên bản: 0.1 (draft). Đi kèm `docs/requirements.md` (mã FR/NFR/AC dùng bên dưới).

## 1. Kiến trúc đề xuất

```
Browser (HTML + JS thuần)
   |  HTTP JSON, 127.0.0.1:8010
Python stdlib http.server (app.py)
   |-- _func/parser_bom.py        đọc sheet BOM theo header text
   |-- _func/parser_combom.py     đọc COM_BOM, xử lý ô merge dọc
   |-- _func/parser_change.py     đọc Change content, trích ticket
   |-- _func/normalize.py         strip PN, alias ECU, parse mã FRS
   |-- _func/db.py                SQLite (index) + metadata
   `-- feature/                   search, compare, tree, report
Database nguồn: Excel trên OneDrive (chỉ đọc)
```

Theo convention: `_func/`, `_input/`, `_output/`, `assets/`, `feature/`; khởi chạy bằng `.vbs` -> `.bat` -> `startup_loader.py` (xem NFR-03). Tool desktop không dùng PyQt, đây là web tool kiểu Abbreviation-Dict.

### Quyết định then chốt: dữ liệu lưu ở đâu

Rủi ro: SQLite trên thư mục OneDrive dễ hỏng khi nhiều người mở hoặc sync conflict. Đề xuất hai lớp:

| Lớp | Nội dung | Vị trí | Ghi |
|---|---|---|---|
| Nguồn sự thật | File Excel BOM | OneDrive share (thư mục database) | Chỉ đọc |
| Metadata do người dùng nhập | Dự án, line, quan hệ cha-con FRS, alias ECU | 1 file JSON hoặc một file nhỏ trong OneDrive, ghi nguyên tử (ghi file tạm rồi đổi tên), kèm số phiên bản để phát hiện xung đột | Ghi ít |
| Chỉ mục truy xuất | SQLite sinh ra từ Excel | Máy cá nhân (`%LOCALAPPDATA%\BOM_management\index.db`) | Dựng lại được bất cứ lúc nào |

Nhờ vậy: mỗi máy tự dựng chỉ mục từ Excel (không xung đột), chỉ metadata nhỏ là dữ liệu chung. Nếu câu hỏi 10 trả lời "Excel luôn là nguồn sự thật" thì metadata cũng có thể là một file Excel/JSON nhỏ.

## 2. Mô hình dữ liệu (SQLite index)

```
project(id, name, root_dir)
line(id, project_id, parent_id, name)
frs(id, line_id, code, family, seg, major, minor)
tpv(id, frs_id, n, bom_file, file_mtime, hash)
ecu_block(id, tpv_id, ecu_name, ecu_raw, variant, remarks)
block_applicability(block_id, column_label, market, value)   -- X / O
part(id, block_id, pn_type, did, vf_pn, vf_pn_norm, rev,
     purchase_level, purchase_pn, purchase_before, purchase_after,
     purchase_remarks, raw_json)
change_content(id, tpv_id, ecu_name, text, remarks)
ticket(change_id, key, kind)                                 -- CCB, VF3, GTSC...
com_bom(id, tpv_id, ecu_name, pu_pn, hw_pn, sw_pn, bl_version, remark)
frs_relation(parent_frs_id, child_frs_id, kind, source)      -- base_fota, carry_across, manual
ecu_alias(alias, ecu_name)
quality_issue(id, tpv_id, severity, kind, location, raw_value)
```

Mỗi bảng giữ giá trị gốc (`raw`) cạnh giá trị đã chuẩn hóa (FR-33).

## 3. Các giai đoạn

### Giai đoạn 0: Chốt yêu cầu (trước khi code)
- Người dùng trả lời 16 câu hỏi mở ở `requirements.md` mục 9.
- Đối chiếu trực tiếp 3 file sample với bảng quy tắc parser (mục 6 của requirements), chốt lại cột/hàng.
- Đầu ra: requirements bản 1.0, danh sách alias ECU ban đầu.

### Giai đoạn 1: Parser và chuẩn hóa (nền tảng)
- Đọc `frs_parser.py` hiện có và tái sử dụng ý tưởng (`select_bom_sheet`, `EMPTY_STREAK_STOP`, `normalize_text`, `parse_version_sort_key`).
- `parser_bom`: detect sheet, header row, cột theo text, block ECU, ô merge, cột applicability, 2 template (VF3, EBUS).
- `parser_combom`, `parser_change`, đọc sheet `Data`.
- `normalize`: strip PN, alias ECU, tách mã FRS bằng regex.
- Bộ kiểm thử với 3 file sample (script so khớp số ECU/block/part đếm tay).
- Hoàn thành khi: AC-01, AC-03, AC-04 đạt ở mức dữ liệu (chưa có UI).

### Giai đoạn 2: Database và import
- Dựng schema SQLite, import một file, import cả thư mục (preview, tiến trình, báo lỗi).
- Re-import và diff với lần trước (FR-10).
- Báo cáo data quality (FR-34).
- Hoàn thành khi: import 3 file trong vài giây, báo cáo cảnh báo hợp lý.

### Giai đoạn 3: Server và giao diện cốt lõi
- `app.py` (http.server) + REST JSON cho project, line, FRS, ECU.
- Dashboard dự án, cây line, trang chi tiết FRS/TPV/ECU (FR-01 đến FR-14).
- `.vbs`, `.bat`, đăng ký `startup_loader`, cổng 8010.
- Hoàn thành khi: dùng được từ trình duyệt, thêm dự án/line, import qua giao diện.

### Giai đoạn 4: Truy xuất và change content
- Tìm theo FRS, theo PN (where-used), lọc, gần đúng (FR-20 đến FR-23).
- Trang change content, link ticket, xuất Excel/CSV (FR-15 đến FR-19).
- Hoàn thành khi: AC-02, AC-04 đạt qua giao diện.

### Giai đoạn 5: COM_BOM và so sánh
- Ma trận HW x SW, truy vấn hai chiều, cảnh báo cặp ngoài COM_BOM (FR-25 đến FR-28).
- So sánh hai FRS/TPV (FR-24).
- Hoàn thành khi: AC-03 đạt qua giao diện.

### Giai đoạn 6: Sơ đồ cây FRS
- Dựng cây Project > Line > FRS > TPV, quan hệ FRS (FR-29 đến FR-31).
- Nhập/sửa quan hệ thủ công, gợi ý tự động từ sheet FOTA và ghi chú carry-across.
- Hoàn thành khi: AC-05 đạt.

### Giai đoạn 7: Chịu tải OneDrive và đóng gói
- Thử hai người mở cùng lúc, ghi nguyên tử metadata, phát hiện xung đột (AC-06).
- Hướng dẫn sử dụng, đăng ký vào `POWER_TOOLS`, chỗ tích hợp cho BOM_autofill_dev (NFR-08).

## 4. Cấu trúc thư mục repo đề xuất

```
BOM_management/
  docs/            plan.md, requirements.md
  src/
    app.py
    index.html
    _func/         parser_*.py, normalize.py, db.py
    feature/       search.py, compare.py, tree.py, report.py
    assets/        css, js
    _input/        database mẫu / cấu hình
    _output/       file export
  tests/           so khớp với file sample
  BOM_MANAGEMENT.vbs
  run_bom_management_web.bat
```

## 5. Rủi ro và cách giảm

| Rủi ro | Cách giảm |
|---|---|
| Template mới (ECVan) | Parser detect cột theo text, cấu hình ánh xạ cột theo template |
| PN bẩn | Giữ raw + norm, báo cáo quality, tìm gần đúng |
| OneDrive conflict | Excel chỉ đọc, chỉ mục local, metadata ghi nguyên tử |
| Cây FRS thiếu nguồn | Gợi ý tự động + nhập tay, đánh dấu nguồn quan hệ |
| Sheet có 1 triệu hàng | Dừng theo chuỗi hàng trống |
| pip bị chặn | Chỉ stdlib + openpyxl (đã có) |

## 6. Việc tiếp theo

1. Người dùng trả lời các câu hỏi mở (`requirements.md` mục 9).
2. Cung cấp 3 file sample (hoặc dump) vào phiên làm việc để đối chiếu parser, vì phiên này chưa đọc được file trên máy người dùng.
3. Sau đó bắt đầu Giai đoạn 1.
