# BOM_Management

Web tool local để truy xuất nhanh HW/SW BOM theo FRS. Tài liệu: `docs/requirements.md`, `docs/plan.md`.

Trạng thái: Giai đoạn 1 (parser) và 2 (quét thư mục, chỉ mục SQLite) xong. Chưa có server và giao diện.

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
