"""Tiện ích đọc worksheet openpyxl: ô merge, tìm hàng header, tìm sheet."""
from __future__ import annotations

from openpyxl.utils import get_column_letter

from .normalize import norm_header, norm_text

EMPTY_STREAK_STOP = 50
HEADER_SCAN_ROWS = 15
HEADER_SCAN_COLS = 40


class Sheet:
    """Bọc worksheet: giá trị ô merge được trả cho mọi ô trong vùng merge."""

    def __init__(self, ws):
        self.ws = ws
        self.title = ws.title
        self._anchor = {}
        for rng in ws.merged_cells.ranges:
            for row in range(rng.min_row, rng.max_row + 1):
                for col in range(rng.min_col, rng.max_col + 1):
                    self._anchor[(row, col)] = (rng.min_row, rng.min_col)

    def raw(self, row: int, col: int):
        """Giá trị của đúng ô đó (ô con trong vùng merge trả None)."""
        return self.ws.cell(row, col).value

    def value(self, row: int, col: int):
        """Giá trị có tính merge."""
        r, c = self._anchor.get((row, col), (row, col))
        return self.ws.cell(r, c).value

    def is_merged(self, row: int, col: int) -> bool:
        return (row, col) in self._anchor

    @staticmethod
    def addr(row: int, col: int) -> str:
        return f"{get_column_letter(col)}{row}"

    def find_header_row(self, required: list[str]) -> int | None:
        """Hàng đầu tiên chứa mọi text trong `required` (so khớp chứa, đã chuẩn hóa)."""
        for row in range(1, HEADER_SCAN_ROWS + 1):
            cells = [norm_header(self.raw(row, col)) for col in range(1, HEADER_SCAN_COLS + 1)]
            if all(any(req in cell for cell in cells) for req in required):
                return row
        return None

    def header_map(self, row: int) -> list[tuple[int, str]]:
        """[(col, header đã chuẩn hóa)] cho các ô có text ở hàng header."""
        out = []
        for col in range(1, HEADER_SCAN_COLS + 1):
            text = norm_header(self.raw(row, col))
            if text:
                out.append((col, text))
        return out

    def data_rows(self, start: int, cols: list[int]):
        """Sinh số hàng có dữ liệu ở các cột `cols`, dừng sau EMPTY_STREAK_STOP hàng trống.

        Sheet BOM khai báo hơn 1 triệu hàng định dạng nên không được duyệt tới max_row.
        """
        empty = 0
        row = start
        while empty < EMPTY_STREAK_STOP:
            if any(norm_text(self.raw(row, col)) for col in cols):
                empty = 0
                yield row
            else:
                empty += 1
            row += 1


def find_sheet_by_name(wb, name: str):
    """Tìm sheet theo tên, bỏ qua hoa thường và khoảng trắng thừa ('Change content ')."""
    target = norm_header(name)
    for ws in wb.worksheets:
        if norm_header(ws.title) == target:
            return ws
    return None


def issue(severity: str, kind: str, sheet: str, cell: str, message: str, raw=None) -> dict:
    return {
        "severity": severity,
        "kind": kind,
        "sheet": sheet,
        "cell": cell,
        "message": message,
        "raw": None if raw is None else str(raw),
    }
