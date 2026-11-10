"""Parser sheet BOM của template chuẩn (docs/requirements.md mục 7.1)."""
from __future__ import annotations

from .normalize import (
    DID_BY_PN_TYPE,
    PN_FULL_RE,
    norm_bootloader,
    norm_pn,
    norm_pn_type,
    norm_text,
    parse_frs_code,
    parse_side,
    parse_version,
    split_pn,
    variant_market,
)
from .xlsx_util import Sheet, issue

HEADER_KEY = "common ecu name"


def select_bom_sheet(wb):
    """Sheet BOM = sheet đầu tiên có hàng header chứa 'Common ECU Name'."""
    for ws in wb.worksheets:
        sheet = Sheet(ws)
        row = sheet.find_header_row([HEADER_KEY])
        if row:
            return sheet, row
    return None, None


def _map_columns(headers: list[tuple[int, str]]) -> tuple[dict, list[tuple[int, str]]]:
    """Ánh xạ cột theo text header. Trả (cols, variant_cols)."""
    cols: dict[str, int] = {}

    def put(key, col):
        cols.setdefault(key, col)

    for col, text in headers:
        if text == HEADER_KEY:
            put("ecu", col)
        elif text == "pn type":
            put("pn_type" if "pn_type" not in cols else "pn_type_sys", col)
        elif text.startswith("vf pn with rev"):
            put("vf_pn_rev", col)
        elif text.startswith("component name"):
            put("component", col)
        elif text.startswith("did"):
            put("did", col)
        elif text == "vf pn":
            put("vf_pn", col)
        elif text == "rev did":
            put("rev_did", col)
        elif text == "rev":
            put("rev", col)
        elif text == "purchase level":
            put("purchase_level", col)
        elif text.startswith("purchase part number"):
            put("purchase_pn", col)
        elif text.startswith("purchase partnumber before"):
            put("purchase_base", col)
        elif text.startswith("purchase partnumber after"):
            put("purchase_after", col)
        elif text.startswith("purchase remarks"):
            put("purchase_remarks", col)
        elif text.startswith("remarks"):
            put("remarks", col)

    known = set(cols.values())
    purchase_cols = [c for k, c in cols.items() if k.startswith("purchase")]
    left = max(purchase_cols) if purchase_cols else max(known)
    right = cols.get("remarks", 10**6)
    variant_cols = [(c, t) for c, t in headers if left < c < right and c not in known]
    return cols, variant_cols


def parse_bom(wb) -> dict:
    issues: list[dict] = []
    sheet, header_row = select_bom_sheet(wb)
    if sheet is None:
        return {"ok": False, "issues": [issue("error", "no_bom_sheet", "", "", "Không tìm thấy sheet có header 'Common ECU Name'")]}

    name = sheet.title
    headers = sheet.header_map(header_row)
    cols, variant_cols = _map_columns(headers)
    for key in ("ecu", "pn_type", "vf_pn_rev"):
        if key not in cols:
            issues.append(issue("error", "missing_column", name, f"row {header_row}", f"Thiếu cột bắt buộc: {key}"))
    if any(i["severity"] == "error" for i in issues):
        return {"ok": False, "sheet": name, "issues": issues}

    # Title: A1 (merge A1:C2) là nguồn chính cho mã FRS, số V, LHD/RHD.
    title_raw = ""
    for row in range(1, header_row):
        for col in range(1, 6):
            text = norm_text(sheet.raw(row, col))
            if text and parse_frs_code(text):
                title_raw = text
                break
        if title_raw:
            break
    frs = parse_frs_code(title_raw) or parse_frs_code(name)
    frs_from_name = parse_frs_code(name)
    version = parse_version(title_raw)
    version_from_name = parse_version(name)
    if frs is None:
        issues.append(issue("error", "no_frs_code", name, "A1", "Không đọc được mã FRS từ title hoặc tên sheet", title_raw))
    if frs and frs_from_name and frs["code"] != frs_from_name["code"]:
        issues.append(issue("warning", "frs_mismatch", name, "A1", f"Mã FRS ở title ({frs['code']}) khác tên sheet ({frs_from_name['code']})"))
    if version is None:
        version = version_from_name
    elif version_from_name is not None and version != version_from_name:
        issues.append(issue("warning", "version_mismatch", name, "A1", f"Số V ở title (V{version}) khác tên sheet (V{version_from_name})"))
    if version is None:
        issues.append(issue("warning", "no_version", name, "A1", "Không đọc được số V/TPV", title_raw))

    variants = [
        {"index": i, "label": norm_text(sheet.raw(header_row, col)), "market": variant_market(text), "col": Sheet.addr(header_row, col)[:-len(str(header_row))]}
        for i, (col, text) in enumerate(variant_cols)
    ]
    if not variants:
        issues.append(issue("warning", "no_variants", name, f"row {header_row}", "Không tìm thấy cột variant xe (X/O)"))

    c_ecu, c_type, c_pn = cols["ecu"], cols["pn_type"], cols["vf_pn_rev"]
    blocks: list[dict] = []
    current = None

    def applic(row):
        return [norm_text(sheet.raw(row, col)).upper() for col, _ in variant_cols]

    for row in sheet.data_rows(header_row + 1, [c_ecu, c_type, c_pn]):
        ecu_raw = sheet.raw(row, c_ecu)
        ecu = norm_text(ecu_raw).upper()
        type_raw = sheet.raw(row, c_type)
        pn_type = norm_pn_type(type_raw)
        value_raw = sheet.raw(row, c_pn)

        if not pn_type:
            issues.append(issue("warning", "missing_pn_type", name, Sheet.addr(row, c_type), "Hàng có dữ liệu nhưng thiếu PN Type"))
            continue
        if ecu_raw is not None and str(ecu_raw) != str(ecu_raw).strip():
            issues.append(issue("info", "ecu_whitespace", name, Sheet.addr(row, c_ecu), "Tên ECU có khoảng trắng thừa", repr(ecu_raw)))

        # Block mới ở mỗi hàng HW (khớp vùng merge của cột Purchase PN).
        if pn_type == "HW" or current is None or (ecu and ecu != current["ecu"]):
            if pn_type != "HW":
                issues.append(issue("warning", "block_without_hw", name, Sheet.addr(row, c_type), f"Block của {ecu or '?'} không bắt đầu bằng hàng HW"))
            flags = applic(row)
            purchase_raw = sheet.value(row, cols["purchase_pn"]) if "purchase_pn" in cols else None
            purchase_pn = norm_pn(purchase_raw)
            current = {
                "index": len(blocks),
                "ecu": ecu,
                "ecu_raw": norm_text(ecu_raw),
                "label": norm_text(sheet.value(row, cols["remarks"])) if "remarks" in cols else "",
                "first_row": row,
                "last_row": row,
                "purchase_pn": purchase_pn,
                "purchase_pn_base": split_pn(purchase_pn)[0],
                "applicability": flags,
                "variants": [variants[i]["label"] for i, f in enumerate(flags) if f == "X"],
                "markets": sorted({variants[i]["market"] for i, f in enumerate(flags) if f == "X" and variants[i]["market"]}),
                "parts": [],
            }
            blocks.append(current)
            if purchase_raw is not None and str(purchase_raw) != purchase_pn:
                issues.append(issue("info", "pn_whitespace", name, Sheet.addr(row, cols["purchase_pn"]), "Purchase PN có khoảng trắng/chữ thường", repr(purchase_raw)))
            if purchase_pn and purchase_pn == norm_pn(value_raw):
                issues.append(issue("info", "purchase_equals_hw", name, Sheet.addr(row, cols["purchase_pn"]), f"Purchase PN trùng HW PN ({purchase_pn}), cần kiểm tra"))
            if "purchase_base" in cols:
                cached = norm_pn(sheet.value(row, cols["purchase_base"]))
                if cached and cached != current["purchase_pn_base"]:
                    issues.append(issue("warning", "cache_mismatch", name, Sheet.addr(row, cols["purchase_base"]), f"PU PN bỏ rev trong file ({cached}) khác giá trị tính lại ({current['purchase_pn_base']})"))
            for i, f in enumerate(flags):
                if f not in ("X", "O"):
                    issues.append(issue("warning", "bad_applicability", name, Sheet.addr(row, variant_cols[i][0]), f"Giá trị variant phải là X hoặc O", f))
        else:
            if not ecu:
                issues.append(issue("warning", "missing_ecu", name, Sheet.addr(row, c_ecu), "Thiếu tên ECU, gán theo block phía trên"))
            flags = applic(row)
            if flags != current["applicability"]:
                issues.append(issue("warning", "applicability_inconsistent", name, f"row {row}", f"X/O của hàng khác hàng HW của block ({current['ecu']})"))
            if not current["label"] and "remarks" in cols:
                current["label"] = norm_text(sheet.value(row, cols["remarks"]))
        current["last_row"] = row

        # Giá trị PN: tính lại base/rev/DID, không tin cache công thức.
        if pn_type == "BootLoader":
            value, was_numeric = norm_bootloader(value_raw)
            base, rev = value, ""
            if was_numeric:
                issues.append(issue("info", "bootloader_numeric", name, Sheet.addr(row, c_pn), f"BootLoader lưu dạng số, đã pad thành '{value}'", value_raw))
        else:
            value = norm_pn(value_raw)
            base, rev = split_pn(value)
            if value_raw is not None and str(value_raw) != value:
                issues.append(issue("info", "pn_whitespace", name, Sheet.addr(row, c_pn), "PN có khoảng trắng/chữ thường", repr(value_raw)))
            if value and not PN_FULL_RE.match(value):
                issues.append(issue("warning", "pn_format", name, Sheet.addr(row, c_pn), "PN không đúng dạng AAA00000000AA-00 (gãy, cụt hoặc thiếu rev)", value_raw))
        if not value:
            issues.append(issue("warning", "missing_pn", name, Sheet.addr(row, c_pn), f"Thiếu giá trị PN cho {ecu} {pn_type}"))

        did = DID_BY_PN_TYPE.get(pn_type, "")
        if "did" in cols:
            cached = norm_pn(sheet.raw(row, cols["did"]))
            if cached and did and cached != did:
                issues.append(issue("warning", "cache_mismatch", name, Sheet.addr(row, cols["did"]), f"DID trong file ({cached}) khác DID theo PN Type ({did})"))
            if not did:
                did = cached
        if "vf_pn" in cols and pn_type != "BootLoader":
            cached = norm_pn(sheet.raw(row, cols["vf_pn"]))
            if cached and cached != base:
                issues.append(issue("warning", "cache_mismatch", name, Sheet.addr(row, cols["vf_pn"]), f"VF PN trong file ({cached}) khác giá trị tính lại ({base})"))
        if "rev" in cols and pn_type != "BootLoader":
            cached = norm_pn(sheet.raw(row, cols["rev"]))
            if cached and cached != rev:
                issues.append(issue("warning", "cache_mismatch", name, Sheet.addr(row, cols["rev"]), f"Rev trong file ({cached}) khác giá trị tính lại ({rev})"))
        type_sys = norm_text(sheet.raw(row, cols["pn_type_sys"])) if "pn_type_sys" in cols else ""
        if type_sys and type_sys != norm_text(type_raw):
            if norm_pn_type(type_sys) == pn_type:
                issues.append(issue("info", "pn_type_alias", name, Sheet.addr(row, cols["pn_type_sys"]), f"Cột PN Type thứ hai ghi '{type_sys}', cột B ghi '{norm_text(type_raw)}'"))
            else:
                issues.append(issue("warning", "pn_type_conflict", name, Sheet.addr(row, cols["pn_type_sys"]), f"Hai cột PN Type mâu thuẫn: '{norm_text(type_raw)}' và '{type_sys}'"))

        current["parts"].append({
            "row": row,
            "pn_type": pn_type,
            "pn": value,
            "pn_base": base,
            "rev": rev,
            "pn_raw": None if value_raw is None else str(value_raw),
            "did": did,
            "rev_did": norm_text(sheet.raw(row, cols["rev_did"])) if "rev_did" in cols else "",
            "purchase_level": norm_text(sheet.raw(row, cols["purchase_level"])) if "purchase_level" in cols else "",
            "component": norm_text(sheet.raw(row, cols["component"])) if "component" in cols else "",
        })

    for block in blocks:
        if not block["variants"]:
            issues.append(issue("warning", "block_no_variant", name, f"row {block['first_row']}", f"Block {block['ecu']} không áp dụng cho variant nào"))

    return {
        "ok": True,
        "sheet": name,
        "header_row": header_row,
        "title": title_raw,
        "frs": frs,
        "version": version,
        "side": parse_side(title_raw),
        "variants": variants,
        "blocks": blocks,
        "issues": issues,
    }
