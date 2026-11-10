# BOM_Management

Web tool local để truy xuất nhanh HW/SW BOM theo FRS. Tài liệu: `docs/requirements.md`, `docs/plan.md`.

Trạng thái: Giai đoạn 1 (parser) xong. Chưa có database, server và giao diện.

## Chạy parser trên một file BOM

Cần Python 3.10+ và `openpyxl`.

```bash
python src/_func/parse_file.py docs/sample.xlsx
```

```bash
python src/_func/parse_file.py docs/sample.xlsx --json
```

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
