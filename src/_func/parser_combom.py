"""Parser sheet COM_BOM: Compatibility Matrix HW - SW (requirements mục 7.2)."""
from __future__ import annotations

from .normalize import norm_bootloader, norm_pn, norm_text, split_ecu_name, split_pn
from .xlsx_util import Sheet, find_sheet_by_name, issue

SHEET_NAME = "COM_BOM"


def parse_combom(wb) -> dict:
    ws = find_sheet_by_name(wb, SHEET_NAME)
    if ws is None:
        return {"ok": False, "rows": [], "ecus": [], "issues": [issue("info", "no_combom_sheet", "", "", "File không có sheet COM_BOM")]}
    sheet = Sheet(ws)
    name = sheet.title
    issues: list[dict] = []
    header_row = sheet.find_header_row(["ecu name", "hw pn", "sw pn"])
    if header_row is None:
        return {"ok": False, "rows": [], "ecus": [], "issues": [issue("error", "no_header", name, "", "Không tìm thấy header ECU NAME / HW PN / SW PN")]}

    cols: dict[str, int] = {}
    for col, text in sheet.header_map(header_row):
        if text.startswith("ecu"):
            cols.setdefault("ecu", col)
        elif text.startswith("pu pn"):
            cols.setdefault("pu", col)
        elif text.startswith("hw pn"):
            cols.setdefault("hw", col)
        elif text.startswith("sw pn"):
            cols.setdefault("sw", col)
        elif text.startswith("bl"):
            cols.setdefault("bl", col)
        elif text.startswith("remark"):
            cols.setdefault("remark", col)

    rows: list[dict] = []
    last_ecu = None
    for row in sheet.data_rows(header_row + 1, [cols["hw"], cols["sw"]] + ([cols["pu"]] if "pu" in cols else [])):
        ecu_raw = sheet.value(row, cols["ecu"])
        if norm_text(ecu_raw):
            last_ecu = ecu_raw
        else:
            ecu_raw = last_ecu  # tên ECU trống ngoài vùng merge: lấy theo hàng trên
        ecu, qualifier, market = split_ecu_name(ecu_raw)
        hw_raw = sheet.value(row, cols["hw"])
        sw_raw = sheet.value(row, cols["sw"])
        pu_raw = sheet.value(row, cols["pu"]) if "pu" in cols else None
        bl_raw = sheet.value(row, cols["bl"]) if "bl" in cols else None
        hw, sw, pu = norm_pn(hw_raw), norm_pn(sw_raw), norm_pn(pu_raw)
        bl = norm_bootloader(bl_raw)[0] if bl_raw is not None else ""

        for label, raw, norm, col_key in (("PU PN", pu_raw, pu, "pu"), ("HW PN", hw_raw, hw, "hw"), ("SW PN", sw_raw, sw, "sw")):
            if raw is not None and str(raw) != norm:
                issues.append(issue("info", "pn_whitespace", name, Sheet.addr(row, cols[col_key]), f"{label} có khoảng trắng/chữ thường", repr(raw)))
        if not ecu:
            issues.append(issue("warning", "missing_ecu", name, f"row {row}", "Hàng COM_BOM không xác định được ECU"))
        if not hw or not sw:
            issues.append(issue("warning", "incomplete_row", name, f"row {row}", "Hàng COM_BOM thiếu HW PN hoặc SW PN"))
            continue

        rows.append({
            "row": row,
            "ecu": ecu,
            "ecu_raw": norm_text(ecu_raw),
            "qualifier": qualifier,
            "market": market,
            "pu_pn": pu,
            "pu_pn_base": split_pn(pu)[0],
            "hw_pn": hw,
            "sw_pn": sw,
            "bl_version": bl,
            "remark": norm_text(sheet.value(row, cols["remark"])) if "remark" in cols else "",
        })

    return {
        "ok": True,
        "sheet": name,
        "header_row": header_row,
        "rows": rows,
        "ecus": sorted({r["ecu"] for r in rows}),
        "issues": issues,
    }
