"""Đọc một file BOM (template chuẩn) thành dict: BOM + COM_BOM + Change content + kiểm tra."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

import openpyxl

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "_func"

from .compat import check_blocks
from .parser_bom import parse_bom
from .parser_change import DEFAULT_TICKET_PREFIXES, parse_change_content
from .parser_combom import parse_combom
from .xlsx_util import issue


def _load(path: Path):
    """Mở read-only về mặt nghiệp vụ; file đang bị Excel khóa thì copy tạm rồi đọc (NFR-05)."""
    try:
        return openpyxl.load_workbook(path, data_only=True)
    except PermissionError:
        with tempfile.TemporaryDirectory() as tmp:
            copy = Path(tmp) / path.name
            shutil.copy2(path, copy)
            return openpyxl.load_workbook(copy, data_only=True)


def parse_file(path, ticket_prefixes=DEFAULT_TICKET_PREFIXES) -> dict:
    path = Path(path)
    wb = _load(path)
    try:
        bom = parse_bom(wb)
        combom = parse_combom(wb)
        change = parse_change_content(wb, ticket_prefixes)
    finally:
        wb.close()

    issues = list(bom.get("issues", [])) + list(combom.get("issues", [])) + list(change.get("issues", []))
    compat = check_blocks(bom.get("blocks", []), combom.get("rows", [])) if bom.get("ok") else []
    for c in compat:
        if c["warning"]:
            issues.append(issue("warning", "compat_" + c["status"], combom.get("sheet", "COM_BOM"), "", f"{c['ecu']} [{', '.join(c['variants'])}] HW {c['hw_pn']} + SW {c['sw_pn']}: {c['reason']}"))
        elif c["bl_matches"] is False:
            issues.append(issue("info", "compat_bl_mismatch", combom.get("sheet", "COM_BOM"), "", f"{c['ecu']} [{', '.join(c['variants'])}]: BootLoader khác BL Version trong COM_BOM"))

    frs = bom.get("frs")
    change_frs = change.get("frs")
    if frs and change_frs and frs["code"] != change_frs["code"]:
        issues.append(issue("warning", "frs_mismatch", change.get("sheet", ""), "A1", f"Mã FRS ở sheet Change content ({change_frs['code']}) khác sheet BOM ({frs['code']})"))
    version = bom.get("version")
    tpvs = change.get("tpvs", [])
    if version is not None and tpvs and max(tpvs) != version:
        issues.append(issue("warning", "version_mismatch", change.get("sheet", ""), "", f"TPV mới nhất trong Change content (TPV{max(tpvs)}) khác số V của BOM (V{version})"))

    return {
        "file": path.name,
        "ok": bool(bom.get("ok")),
        "frs": frs,
        "version": version,
        "side": bom.get("side", ""),
        "title": bom.get("title", ""),
        "variants": bom.get("variants", []),
        "blocks": bom.get("blocks", []),
        "com_bom": combom.get("rows", []),
        "com_bom_ecus": combom.get("ecus", []),
        "compat": compat,
        "change_content": change.get("entries", []),
        "tpvs": tpvs,
        "issues": issues,
    }


def summary(result: dict) -> str:
    lines = []
    frs = result["frs"]["code"] if result["frs"] else "?"
    lines.append(f"File: {result['file']}")
    lines.append(f"FRS {frs}  V{result['version']}  {result['side']}")
    lines.append("Variant xe: " + ", ".join(f"{v['label']} ({v['market'] or '?'})" for v in result["variants"]))
    blocks = result["blocks"]
    ecus = sorted({b["ecu"] for b in blocks})
    lines.append(f"ECU: {len(ecus)}  Block: {len(blocks)}  Part row: {sum(len(b['parts']) for b in blocks)}")
    for b in blocks:
        parts = "  ".join(f"{p['pn_type']}={p['pn']}" for p in b["parts"])
        label = f"  [{b['label']}]" if b["label"] else ""
        lines.append(f"  {b['ecu']:<6} {'+'.join(b['variants']):<26} PU={b['purchase_pn']:<17} {parts}{label}")
    lines.append(f"COM_BOM: {len(result['com_bom'])} dòng, ECU: {', '.join(result['com_bom_ecus'])}")
    for c in result["compat"]:
        if c["status"] != "not_tracked":
            mark = "CẢNH BÁO" if c["warning"] else "OK"
            lines.append(f"  {mark:<9} {c['ecu']:<6} {'+'.join(c['variants']):<26} {c['reason']}")
    entries = result["change_content"]
    keys = {t["key"] for e in entries for t in e["tickets"]}
    lines.append(f"Change content: {len(entries)} dòng, TPV {result['tpvs']}, {len(keys)} ticket")
    by_sev = {}
    for i in result["issues"]:
        by_sev[i["severity"]] = by_sev.get(i["severity"], 0) + 1
    lines.append("Issues: " + (", ".join(f"{k}={v}" for k, v in sorted(by_sev.items())) or "không có"))
    for i in result["issues"]:
        lines.append(f"  [{i['severity']}] {i['kind']} {i['sheet'].strip()}!{i['cell']}: {i['message']}")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Parse một file HW/SW BOM theo template chuẩn")
    ap.add_argument("path")
    ap.add_argument("--json", action="store_true", help="In toàn bộ kết quả dạng JSON")
    args = ap.parse_args(argv)
    result = parse_file(args.path)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(summary(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
