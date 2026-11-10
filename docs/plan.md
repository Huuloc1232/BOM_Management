# PLAN: BOM Management Web Tool

Phiên bản: 1.0 (đã chốt yêu cầu, bắt đầu Giai đoạn 1). Đi kèm `docs/requirements.md` (mã FR/NFR/AC/D dùng bên dưới).

Mục tiêu chính: **truy xuất nhanh**. Một người dùng, dưới 100 file BOM, Excel là nguồn sự thật.

## 1. Kiến trúc đề xuất

```
Browser (HTML + JS thuần)
   |  HTTP JSON, 127.0.0.1:8010
Python stdlib http.server (app.py)
   |-- _func/scan.py             quét folder dự án, chọn V cao nhất mỗi FRS
   |-- _func/parser_bom.py       đọc sheet BOM theo header text
   |-- _func/parser_combom.py    đọc COM_BOM, xử lý ô merge dọc
   |-- _func/parser_change.py    đọc Change content, trích ticket
   |-- _func/normalize.py        strip PN, alias ECU, parse mã FRS
   |-- _func/frs_tree.py         suy ra cha-con từ mã FRS + sửa tay
   |-- _func/db.py               SQLite index + metadata
   `-- feature/                  search, compare, compat, tickets, tree
Database nguồn: Excel trên OneDrive (chỉ đọc)
```

Theo convention: `_func/`, `_input/`, `_output/`, `assets/`, `feature/`; khởi chạy bằng `.vbs` -> `.bat` -> `startup_loader.py` (NFR-03).

### Lưu trữ dữ liệu

Vì chỉ có một người dùng, rủi ro nhiều người ghi cùng lúc không còn. Vẫn giữ hai lớp để đơn giản và an toàn với OneDrive:

| Lớp | Nội dung | Vị trí | Ghi |
|---|---|---|---|
| Nguồn sự thật | File Excel BOM | OneDrive (thư mục database, theo folder dự án) | Chỉ đọc |
| Metadata do người dùng nhập | Dự án, line, FRS tạo tay, gán FRS vào line, sửa cha-con, duyệt alias ECU | 1 file JSON trong thư mục tool trên OneDrive, ghi nguyên tử (ghi file tạm rồi đổi tên) | Ít |
| Chỉ mục truy xuất | SQLite sinh từ Excel | Máy cá nhân (`%LOCALAPPDATA%\BOM_management\index.db`) | Xóa đi quét lại được |

Quét gia tăng theo (đường dẫn, thời gian sửa, hash): với dưới 100 file, quét đầy đủ lần đầu mất vài chục giây, các lần sau gần như tức thì. Nếu số file tăng thì kiến trúc này vẫn dùng được (NFR-09).

## 2. Mô hình dữ liệu (SQLite index)

```
project(id, name, root_dir)
line(id, project_id, parent_id, name)
frs(id, project_id, code, family, seg, major, minor, state)       -- state: has_bom | no_bom
frs_line(frs_id, line_id)                                          -- nhiều-nhiều (D4)
frs_bom(frs_id, tpv_n, bom_file, file_mtime, hash)                 -- chỉ TPV cuối (D1)
variant(id, frs_id, label, market, col_index)                      -- cột applicability (D5)
ecu_block(id, frs_id, ecu_name, ecu_raw, block_label, first_row, last_row)   -- block_label = cột R
block_variant(block_id, variant_id, value)                         -- X / O
part(id, block_id, pn_type, did, vf_pn, vf_pn_norm, rev,
     purchase_level, purchase_pn, purchase_pn_base,                 -- K và L (L = K bỏ rev)
     src_row, raw_json)                                             -- cột M, N bỏ qua (D15)
change_content(id, frs_id, tpv_n, ecu_raw, ecu_name, block_id NULL, text, remarks)   -- remarks = cột D
ticket(change_id, key, prefix)                                     -- prefix cấu hình được: CCB, VF3, VF5, GTSC, MINIOGREEN, MHU3, IMS?
com_bom(id, frs_id, ecu_raw, ecu_name, market, pu_pn, pu_pn_base, hw_pn, sw_pn, bl_version, remark)
frs_relation(parent_frs_id, child_frs_id, source)                  -- auto | manual | fota_hint
ecu_alias(alias, ecu_name, status)                                 -- auto | confirmed
quality_issue(id, frs_id, severity, kind, location, raw_value)
```

Mỗi bảng giữ giá trị gốc (`raw`) cạnh giá trị đã chuẩn hóa (FR-40).

## 3. Thuật toán chính

### 3.1 Chọn TPV cuối (D1, FR-06)
Nhóm file theo mã FRS (regex trong tên file/title), lấy số V lớn nhất. Hai file cùng V thì chọn theo thời gian sửa mới nhất và báo cảnh báo. Các V cũ hiển thị ở danh sách "bị bỏ qua".

### 3.2 Cây FRS (D2, FR-35)
Trong cùng `family` + `seg`:
- minor > 0: cha = (major, minor - 1)
- minor = 0: cha = (major - 1, 0)
- Không có cha trong dữ liệu: nút cha "thiếu" (hiển thị mờ) hoặc nối lên tổ tiên gần nhất.

Kiểm tra bằng ví dụ người dùng: `3B.1.7.0 -> 3B.1.8.0 -> 3B.1.9.0 -> 3B.1.9.1 -> 3B.1.9.2`, nhánh `3B.1.8.0 -> 3B.1.8.1 -> 3B.1.8.2 -> 3B.1.8.3`. Sửa tay (`frs_relation.source = manual`) luôn thắng. Sheet FOTA và ghi chú carry-across chỉ dùng để cảnh báo mâu thuẫn.

### 3.3 Tương thích COM_BOM (D7, FR-29, FR-31)
Với (ECU, market, HW, SW): tương thích khi tồn tại hàng khớp (sau chuẩn hóa PN, ô merge dọc đã điền xuống). Không tương thích với lý do: `HW không có trong bảng` hoặc `HW đi với SW khác`. ECU **không có trong COM_BOM** thì trạng thái là "không theo dõi", không cảnh báo. Market của block lấy từ tiền tố nhãn variant (`VN FL` thành VN, `PHL BCO` thành PHL) để nối với tên ECU có hậu tố (`MHU VN`, `2IN1 (PHL)`).

### 3.4 Tra cứu ngược ticket (D13, FR-20)
Trích key từ text change content khi quét theo **danh sách prefix** (không dùng regex chung vì khớp nhầm PN như `SOW69011004AD-05`), chịu được `[KEY]`, `KEY<tab>`, ngoặc lệch `GTSC-7888]`, hai key liền nhau. Lưu vào `ticket`. Hai truy vấn: `key -> (frs, tpv_n, ecu)` và `frs -> các key`.

### 3.5 Tìm kiếm toàn cục (FR-22)
Một ô nhập, phân loại đầu vào (mã FRS, PN, ticket, tên ECU) rồi truy vấn nhiều bảng và trả kết quả phân nhóm. PN khớp theo `vf_pn_norm` và prefix.

## 4. Các giai đoạn

### Giai đoạn 0: Chốt yêu cầu (HOÀN THÀNH)
- Trả lời các câu hỏi còn lại (requirements mục 10). `docs/sample.xlsx` đã được đối chiếu (requirements mục 7).
- Đầu ra: requirements 1.0.

### Giai đoạn 1: Parser và chuẩn hóa (HOÀN THÀNH, 22 test đạt)
- Đọc `frs_parser.py` hiện có và tái sử dụng ý tưởng (`select_bom_sheet`, `EMPTY_STREAK_STOP`, `normalize_text`, `parse_version_sort_key`).
- `parser_bom`: chọn sheet theo header `Common ECU Name`; header hàng 3, dữ liệu từ hàng 4; cột theo text header đã chuẩn hóa (header R có xuống dòng); block bắt đầu ở mỗi hàng `HW`; điền ô merge K/L/M/N/R theo block; variant = các cột giữa `Purchase Remarks` và `Remarks Change Content`; **tính lại** F, G, I, L từ B, C, K (không tin cache công thức); BootLoader ép chuỗi và pad 4 ký tự. Một template duy nhất.
- `parser_combom` (header hàng 2, điền merge dọc B/E/F), `parser_change` (header hàng 2, điền merge dọc cột A, TPV một hàng không merge), sheet `Data` tùy chọn.
- `normalize`: PN, alias ECU, mã FRS. `frs_tree`: thuật toán 3.2.
- Test với 3 file sample.
- Xong khi: AC-01 (15 block, 49 part row), AC-03 (đúng 2 cảnh báo: MHU PHL BCO và SS), AC-04 (ở mức dữ liệu), AC-05, AC-06.

### Giai đoạn 2: Quét thư mục và database (HOÀN THÀNH, 37 test đạt)
- `scan.py` theo folder dự án, suy ra line từ folder và tên file (D12), chọn TPV cuối, quét gia tăng.
- Schema SQLite, báo cáo data quality (FR-41).
- Xong khi: quét thư mục mẫu trong vài giây, danh sách cảnh báo hợp lý.

### Giai đoạn 3: Server, dashboard và tra cứu cốt lõi (HOÀN THÀNH, 45 test đạt; launcher .bat/.vbs chưa thử trên Windows, chưa nối startup_loader)
- `app.py` + REST JSON; dashboard dự án, cây line, trang FRS/ECU/part (FR-01 đến FR-16).
- Ô tìm kiếm toàn cục, where-used theo PN, lọc theo variant xe (FR-22 đến FR-26).
- `.vbs`, `.bat`, cổng 8010.
- Xong khi: AC-02.

### Giai đoạn 4: Change content, ticket, so sánh (HOÀN THÀNH, 55 test đạt)
- Trang change content, link ticket, tra cứu hai chiều CCB/IMS (FR-17 đến FR-21).
- So sánh hai FRS theo ECU part number (FR-27).
- Xong khi: AC-04, AC-07.

### Giai đoạn 5: COM_BOM
- Truy vấn tương thích, ma trận HW x SW, cảnh báo cặp ngoài bảng (FR-28 đến FR-33).
- Xong khi: AC-03 đạt qua giao diện.

### Giai đoạn 6: Sơ đồ cây FRS
- Vẽ cây (SVG hoặc canvas thuần), nhiều nhánh, bật/tắt LHD/RHD, sửa cha-con tay, cảnh báo mâu thuẫn với FOTA (FR-34 đến FR-38).
- Xong khi: AC-05 đạt qua giao diện.

### Giai đoạn 7: Hoàn thiện
- Tạo FRS tay (FR-07), gán FRS vào nhiều line (FR-05).
- Hướng dẫn sử dụng, đăng ký `POWER_TOOLS`, hook cho BOM_autofill_dev (NFR-08).

Ghi chú thứ tự: nếu muốn dùng được sớm, Giai đoạn 1 đến 3 là bản tối thiểu đã đáp ứng mục tiêu "truy xuất nhanh".

## 5. Cấu trúc thư mục repo đề xuất

```
BOM_management/
  docs/            plan.md, requirements.md
  src/
    app.py
    index.html
    _func/         scan.py, parser_*.py, normalize.py, frs_tree.py, db.py
    feature/       search.py, compare.py, compat.py, tickets.py
    assets/        css, js
    _input/        cấu hình, ánh xạ segment, alias
    _output/       file export (tùy chọn)
  tests/           so khớp với file sample
  BOM_MANAGEMENT.vbs
  run_bom_management_web.bat
```

## 6. Rủi ro và cách giảm

| Rủi ro | Cách giảm |
|---|---|
| PN bẩn | Giữ raw + norm, báo cáo quality, tìm theo prefix |
| Quy tắc cha-con có ngoại lệ | Sửa tay thắng quy tắc, cảnh báo khi mâu thuẫn FOTA |
| Alias ECU không đồng nhất | Tự ghép từ cột A/D và COM_BOM, màn hình duyệt các ghép không chắc |
| Sheet có 1 triệu hàng | Dừng theo chuỗi hàng trống |
| pip bị chặn | Chỉ stdlib + openpyxl (đã có) |
| OneDrive sync làm hỏng JSON metadata | Ghi nguyên tử, giữ bản sao lưu gần nhất |
| Số file tăng | Quét gia tăng + SQLite index (NFR-09) |

## 7. Việc tiếp theo

1. Người dùng trả lời các câu hỏi còn lại (requirements mục 10), không chặn Giai đoạn 1.
2. Bắt đầu Giai đoạn 1 (parser) với `docs/sample.xlsx` làm dữ liệu kiểm thử.
