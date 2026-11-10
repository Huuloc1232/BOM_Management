"""Đối chiếu tương thích HW - SW theo COM_BOM (D7, D8, FR-29, FR-31)."""
from __future__ import annotations

from .normalize import norm_pn

SW_TYPES = ("SW", "SW_APP", "SW_BASIC")

REASONS = {
    "ok": "Tương thích: (HW, SW) có trong COM_BOM",
    "not_tracked": "ECU không có trong COM_BOM (không theo dõi)",
    "no_market_rows": "ECU có trong COM_BOM nhưng không có dòng nào cho market của block",
    "hw_not_listed": "HW PN không có trong COM_BOM",
    "sw_mismatch": "HW có trong COM_BOM nhưng đi với SW số khác",
}


def _candidates(com_rows: list[dict], ecu: str, markets: list[str]) -> list[dict]:
    rows = [r for r in com_rows if r["ecu"] == ecu]
    if not rows:
        return []
    # Dòng không ghi market áp dụng cho mọi market; dòng có market phải khớp market của block.
    return [r for r in rows if not r["market"] or not markets or r["market"] in markets]


def is_compatible(com_rows: list[dict], ecu: str, hw_pn: str, sw_pn: str, markets: list[str] | None = None) -> dict:
    """Trả {'status', 'reason', 'matches'} cho bộ (ECU, HW, SW)."""
    ecu = (ecu or "").upper()
    hw, sw = norm_pn(hw_pn), norm_pn(sw_pn)
    if not any(r["ecu"] == ecu for r in com_rows):
        return {"status": "not_tracked", "reason": REASONS["not_tracked"], "matches": []}
    rows = _candidates(com_rows, ecu, markets or [])
    if not rows:
        return {"status": "no_market_rows", "reason": REASONS["no_market_rows"], "matches": []}
    hw_rows = [r for r in rows if r["hw_pn"] == hw]
    if not hw_rows:
        return {"status": "hw_not_listed", "reason": REASONS["hw_not_listed"], "matches": []}
    matches = [r for r in hw_rows if r["sw_pn"] == sw]
    if not matches:
        return {"status": "sw_mismatch", "reason": REASONS["sw_mismatch"], "matches": hw_rows}
    return {"status": "ok", "reason": REASONS["ok"], "matches": matches}


def compatible_hw_for_sw(com_rows: list[dict], ecu: str, sw_pn: str) -> list[dict]:
    sw = norm_pn(sw_pn)
    return [r for r in com_rows if r["ecu"] == (ecu or "").upper() and r["sw_pn"] == sw]


def compatible_sw_for_hw(com_rows: list[dict], ecu: str, hw_pn: str) -> list[dict]:
    hw = norm_pn(hw_pn)
    return [r for r in com_rows if r["ecu"] == (ecu or "").upper() and r["hw_pn"] == hw]


def check_blocks(blocks: list[dict], com_rows: list[dict]) -> list[dict]:
    """Kiểm tra từng block BOM. Chỉ cảnh báo khi ECU có trong COM_BOM mà bộ ba không có."""
    results = []
    for block in blocks:
        parts = {p["pn_type"]: p["pn"] for p in block["parts"]}
        hw = parts.get("HW", "")
        sws = [parts[t] for t in SW_TYPES if parts.get(t)]
        best = None
        for sw in sws or [""]:
            res = is_compatible(com_rows, block["ecu"], hw, sw, block["markets"])
            if best is None or res["status"] == "ok":
                best = dict(res, sw_pn=sw)
            if res["status"] == "ok":
                break
        status = best["status"]
        bl_ok = None
        if status == "ok":
            bl = parts.get("BootLoader", "")
            listed = {r["bl_version"] for r in best["matches"] if r["bl_version"]}
            bl_ok = (not listed) or (bl in listed)
        results.append({
            "block_index": block["index"],
            "ecu": block["ecu"],
            "label": block["label"],
            "variants": block["variants"],
            "hw_pn": hw,
            "sw_pn": best["sw_pn"],
            "status": status,
            "reason": best["reason"],
            "warning": status in ("no_market_rows", "hw_not_listed", "sw_mismatch"),
            "bl_matches": bl_ok,
            "listed": [{"hw_pn": r["hw_pn"], "sw_pn": r["sw_pn"], "bl_version": r["bl_version"], "ecu_raw": r["ecu_raw"]} for r in best["matches"]],
        })
    return results
