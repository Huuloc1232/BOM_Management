# BOM_Management

Web tool local để truy xuất nhanh HW/SW BOM theo FRS. Tài liệu: `docs/requirements.md`, `docs/plan.md`.

Trạng thái: Giai đoạn 1 đến 4 xong (parser, quét thư mục, chỉ mục SQLite, web tool tra cứu, so sánh hai FRS, tra cứu ticket). Chưa có: ma trận COM_BOM, sơ đồ cây FRS.

## Chạy web tool

Trên Windows: bấm đúp `BOM_MANAGEMENT.vbs` (chạy ẩn) hoặc `run_bom_management_web.bat` (có cửa sổ console). Trình duyệt mở `http://127.0.0.1:8010/`.

Hoặc chạy tay:

```bash
python src/app.py --open
```

Lần đầu, bấm "Thư mục database" và dán đường dẫn thư mục chứa các folder dự án. Tool quét gia tăng mỗi lần khởi động; bấm "Quét lại" sau khi thêm hoặc sửa file Excel.

- Ô tìm kiếm nhận mã FRS, part number (không cần gõ revision), tên ECU, mã ticket. Phím `/` để nhảy vào ô tìm.
- "So sánh FRS" so part number của hai FRS theo từng ECU và block, kèm ticket chỉ có ở một bên. Mở từ trang FRS thì mặc định so với FRS cha trong cây.
- Tab "Ticket" ở trang FRS liệt kê mọi CCB/Jira mà FRS đã release, lọc theo loại, TPV, nội dung.
- "Thêm dự án" và "Thêm line" tạo folder tương ứng trong thư mục database. Tool không bao giờ sửa file Excel.
- Server chỉ lắng nghe `127.0.0.1`. Cổng 8010 bận thì dùng cổng kế tiếp.

## Chạy parser trên một file BOM

Cần Python 3.10+ và `openpyxl`.

```bash
python src/_func/parse_file.py docs/sample.xlsx
```

```bash
python src/_func/parse_file.py docs/sample.xlsx --json
```

## Quét thư mục database

Thư mục database tổ chức theo folder dự án, folder con là line xe:

```
database/
  VF3/
    FL/FRS3B.1.11.0.xlsx
    Legacy/LHD/FRS3A.1.11.0.xlsx
  ECVan/FRS....xlsx
```

```bash
python src/_func/scan.py "D:/duong/dan/database"
```

Tra nhanh sau khi quét:

```bash
python src/_func/scan.py "D:/duong/dan/database" --where-used BAT69011016AA-01 --ticket CCB-26107
```

Thư mục phẳng chỉ chứa file của một dự án:

```bash
python src/_func/scan.py "D:/duong/dan/sample" --project VF3
```

Chỉ mục SQLite mặc định nằm ở `%LOCALAPPDATA%\BOM_management\index.db` (đổi bằng `--db`). Xóa file này thì lần quét sau dựng lại từ Excel. Lần quét sau chỉ parse file đã đổi; `--force` để parse lại tất cả.

## Chạy test

```bash
python -m unittest discover -s tests
```

## Cấu trúc

- `src/_func/normalize.py`: chuẩn hóa PN, tên ECU, mã FRS
- `src/_func/parser_bom.py`: sheet BOM (block ECU, variant xe, part row)
- `src/_func/parser_combom.py`: sheet `COM_BOM`
- `src/_func/parser_change.py`: sheet `Change content`, trích ticket
- `src/_func/compat.py`: đối chiếu tương thích HW - SW
- `src/_func/frs_tree.py`: cây cha-con giữa các FRS
- `src/_func/parse_file.py`: gộp kết quả một file, có CLI
- `src/_func/db.py`: schema và truy vấn chỉ mục SQLite
- `src/_func/scan.py`: quét thư mục, chọn TPV cuối, quét gia tăng, có CLI
- `src/feature/queries.py`: truy vấn cho giao diện (dashboard, FRS, tìm kiếm)
- `src/feature/compare.py`: so sánh hai FRS, danh sách ticket của FRS
- `src/app.py`: server web local (stdlib `http.server`)
- `src/index.html`, `src/assets/`: giao diện (HTML, CSS, JS thuần)
