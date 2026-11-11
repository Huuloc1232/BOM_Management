# Hướng dẫn sử dụng BOM Management

## 1. Chuẩn bị thư mục database

```
database/
  VF3/                         <- mỗi folder con là một dự án
    FL/                        <- folder bên trong là line xe
      FRS3B.1.11.0.xlsx
    Legacy/
      LHD/                     <- line con
        FRS3A.1.11.0.xlsx
  ECVan/
  _bom_management/             <- tool tự tạo, chứa metadata.json (đừng xóa)
```

- File BOM theo template chuẩn (`docs/sample.xlsx`): 3 sheet là BOM, `COM_BOM`, `Change content`.
- Mã FRS, số V và LHD/RHD đọc từ ô A1 của sheet BOM (`FRS 3B.1.11.0 V8 LHD`), không phụ thuộc tên file.
- Cùng một mã FRS có nhiều file thì tool dùng file có số V lớn nhất, các file còn lại hiện ở "File không được dùng".
- Folder bắt đầu bằng `.`, `_`, `~` bị bỏ qua.

## 2. Khởi chạy

Bấm đúp `BOM_MANAGEMENT.vbs` (chạy ẩn) hoặc `run_bom_management_web.bat`. Trình duyệt mở `http://127.0.0.1:8010/`.
Lần đầu: bấm "Thư mục database", dán đường dẫn, bấm "Lưu và quét".

Sau khi thêm hoặc sửa file Excel: "Thư mục database" > "Quét lại" (chỉ đọc lại file đã đổi).

## 3. Tra cứu

| Muốn biết | Cách làm |
|---|---|
| FRS dùng những ECU và PN nào | Gõ mã FRS vào ô tìm kiếm, hoặc mở từ trang dự án |
| Một PN đang dùng ở đâu | Gõ PN (không cần revision). Mỗi block ra một dòng |
| ECU có những PN nào qua các FRS | Gõ tên ECU, vd `MHU` |
| CCB / Jira được release ở FRS nào | Gõ mã ticket, vd `CCB-26107` |
| FRS đã release những ticket nào | Trang FRS > tab "Ticket" |
| Hai FRS khác nhau gì | "So sánh FRS", hoặc nút "So sánh với FRS khác" ở trang FRS |
| SW có tương thích HW cũ không | Trang FRS > tab "COM_BOM" |
| Các nhánh FRS | Trang dự án > tab "Sơ đồ cây FRS" |

Phím `/` nhảy vào ô tìm kiếm.

## 4. Thêm và sửa

| Việc | Cách làm | Lưu ở đâu |
|---|---|---|
| Thêm dự án | Dashboard > "Thêm dự án" | Tạo folder trong thư mục database |
| Thêm line, line con | Trang dự án > chọn line cha > "Thêm line" | Tạo folder |
| Tạo FRS chưa có file | Trang dự án > "Tạo FRS chưa có file" | `metadata.json` |
| Gán FRS vào thêm line | Trang FRS > "+ gán thêm line" | `metadata.json` |
| Đổi FRS cha trong cây | Sơ đồ cây > bấm FRS > "Đổi FRS cha" | `metadata.json` |

- Line suy từ folder chứa file là cố định. Muốn đổi thì di chuyển file sang folder khác.
- FRS tạo tay hiện "chưa có BOM". Khi đặt file `FRS<mã>.xlsx` vào và quét lại, dữ liệu thật thay thế, các line đã gán tay được giữ.
- Tool không bao giờ sửa file Excel. Sửa PN thì sửa trong Excel rồi quét lại.

## 5. Dữ liệu nằm ở đâu

| Thứ | Vị trí | Mất thì sao |
|---|---|---|
| File Excel BOM | Thư mục database | Mất dữ liệu gốc |
| `metadata.json` | `<database>/_bom_management/` | Mất FRS tạo tay, line gán tay, quan hệ cha-con sửa tay |
| Chỉ mục `index.db` | `%LOCALAPPDATA%\BOM_management\` | Không sao, quét lại là có |
| `settings.json` | `%LOCALAPPDATA%\BOM_management\` | Chọn lại thư mục database |

## 6. Cảnh báo thường gặp (tab "Chất lượng dữ liệu")

| Cảnh báo | Ý nghĩa |
|---|---|
| HW PN không có trong COM_BOM | BOM dùng HW mà sheet COM_BOM của ECU đó không liệt kê |
| HW đi với SW khác | HW có trong COM_BOM nhưng với SW số khác |
| COM_BOM thiếu market | ECU có trong COM_BOM nhưng không có nhóm cho market của block |
| PN không đúng dạng | PN gãy, cụt hoặc thiếu revision |
| BootLoader lưu dạng số | Excel có thể cắt số 0 đầu, nên định dạng ô là Text |
| Purchase PN trùng HW PN | Thường là nhập nhầm |
