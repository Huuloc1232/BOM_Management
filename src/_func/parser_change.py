"""Parser sheet 'Change content ' và trích ticket (requirements mục 7.3)."""
from __future__ import annotations

import re

from .normalize import find_frs_codes, norm_text, parse_frs_code, parse_version, split_ecu_name
from .xlsx_util import Sheet, find_sheet_by_name, issue

SHEET_NAME = "Change content"
TICKET_URL = "https://tms.vinfast.vn/browse/{key}"

# Danh sách prefix cấu hình được (D14). Không dùng regex chung [A-Z]+-\d+
# vì sẽ khớp nhầm part number như SOW69011004AD-05.
DEFAULT_TICKET_PREFIXES = ("CCB", "IMS", "VF3", "VF3RHD", "VF5", "GTSC", "MINIOGREEN", "MHU3")

CARRY_RE = re.compile(r"carr(?:y|ied)[\s-]*(?:over|across)", re.IGNORECASE)


def build_ticket_regex(prefixes=DEFAULT_TICKET_PREFIXES) -> re.Pattern:
    alternatives = "|".join(re.escape(p) for p in sorted({p.upper() for p in prefixes}, key=len, reverse=True))
    return re.compile(rf"(?<![A-Za-z0-9])({alternatives})-(\d+)(?![A-Za-z0-9])")


def extract_tickets(text: str, prefixes=DEFAULT_TICKET_PREFIXES) -> list[dict]:
    """Ticket duy nhất theo thứ tự xuất hiện, kèm dòng text chứa nó."""
    if not text:
        return []
    pattern = build_ticket_regex(prefixes)
    seen: dict[str, dict] = {}
    for line in str(text).replace("\r", "").split("\n"):
        for m in pattern.finditer(line):
            key = f"{m.group(1)}-{m.group(2)}"
            if key not in seen:
                seen[key] = {"key": key, "prefix": m.group(1), "url": TICKET_URL.format(key=key), "line": norm_text(line)}
    return list(seen.values())


def extract_carry_notes(text: str) -> list[dict]:
    """Dòng 'Carry over from FRS ...' / 'Carry across SW from FRS ...' và các mã FRS trong đó."""
    notes = []
    for line in str(text or "").replace("\r", "").split("\n"):
        if CARRY_RE.search(line):
            notes.append({"line": norm_text(line), "frs_codes": find_frs_codes(line)})
    return notes


def parse_change_content(wb, prefixes=DEFAULT_TICKET_PREFIXES) -> dict:
    ws = find_sheet_by_name(wb, SHEET_NAME)
    if ws is None:
        return {"ok": False, "entries": [], "tpvs": [], "issues": [issue("info", "no_change_sheet", "", "", "File không có sheet Change content")]}
    sheet = Sheet(ws)
    name = sheet.title
    issues: list[dict] = []
    header_row = sheet.find_header_row(["tpv", "ecu", "change content"])
    if header_row is None:
        return {"ok": False, "entries": [], "tpvs": [], "issues": [issue("error", "no_header", name, "", "Không tìm thấy header TPV / ECU / Change content")]}

    cols: dict[str, int] = {}
    for col, text in sheet.header_map(header_row):
        if text == "tpv":
            cols.setdefault("tpv", col)
        elif text == "ecu":
            cols.setdefault("ecu", col)
        elif text.startswith("change content"):
            cols.setdefault("text", col)
        elif text.startswith("remark"):
            cols.setdefault("remarks", col)

    title = ""
    for row in range(1, header_row):
        for col in range(1, 6):
            if parse_frs_code(sheet.raw(row, col)):
                title = norm_text(sheet.raw(row, col))
    frs = parse_frs_code(title)

    entries: list[dict] = []
    last_tpv_raw = None
    for row in sheet.data_rows(header_row + 1, [cols["ecu"], cols["text"]]):
        tpv_raw = sheet.value(row, cols["tpv"])
        if norm_text(tpv_raw):
            last_tpv_raw = tpv_raw
        else:
            tpv_raw = last_tpv_raw
        tpv = parse_version(tpv_raw)
        if tpv is None:
            issues.append(issue("warning", "missing_tpv", name, Sheet.addr(row, cols["tpv"]), "Không xác định được TPV của hàng", tpv_raw))

        ecu_cell = sheet.raw(row, cols["ecu"])
        ecu_raw = norm_text(ecu_cell)
        ecu, qualifier, market = split_ecu_name(ecu_raw)
        if ecu_cell is not None and str(ecu_cell) != str(ecu_cell).strip():
            issues.append(issue("info", "ecu_whitespace", name, Sheet.addr(row, cols["ecu"]), "Tên ECU có khoảng trắng thừa", repr(ecu_cell)))
        if not ecu:
            issues.append(issue("warning", "missing_ecu", name, Sheet.addr(row, cols["ecu"]), "Hàng change content thiếu ECU"))

        # Ô Change content/Remarks có thể merge dọc qua nhiều ECU (dùng chung nội dung).
        text_value = sheet.value(row, cols["text"])
        text = "" if text_value is None else str(text_value).replace("\xa0", " ").strip()
        shared = sheet.is_merged(row, cols["text"]) and sheet.raw(row, cols["text"]) is None
        remarks = norm_text(sheet.value(row, cols["remarks"])) if "remarks" in cols else ""
        if not text:
            issues.append(issue("info", "empty_change", name, Sheet.addr(row, cols["text"]), f"{ecu_raw} (TPV{tpv}) không có nội dung"))

        entries.append({
            "row": row,
            "tpv": tpv,
            "ecu": ecu,
            "ecu_raw": ecu_raw,
            "qualifier": qualifier,
            "market": market,
            "text": text,
            "text_shared_with_row_above": shared,
            "remarks": remarks,
            "tickets": extract_tickets(text + "\n" + remarks, prefixes),
            "carry_notes": extract_carry_notes(text + "\n" + remarks),
        })

    return {
        "ok": True,
        "sheet": name,
        "header_row": header_row,
        "frs": frs,
        "entries": entries,
        "tpvs": sorted({e["tpv"] for e in entries if e["tpv"] is not None}),
        "issues": issues,
    }
