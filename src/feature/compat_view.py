"""COM_BOM: ma trận HW x SW theo từng ECU, câu trả lời nhanh và kiểm tra một cặp (FR-28..FR-33)."""
from __future__ import annotations

from _func.compat import REASONS, SW_TYPES, is_compatible
from _func.normalize import norm_pn

from . import queries

WARN = ("no_market_rows", "hw_not_listed", "sw_mismatch")


def _com_rows(conn, frs_id: int) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT ecu, ecu_raw, market, pu_pn, pu_pn_base, hw_pn, sw_pn, bl_version, remark, src_row FROM com_bom WHERE frs_id=? ORDER BY id", (frs_id,))]


def _bom_blocks(detail: dict) -> list[dict]:
    variants = {v["id"]: v for v in detail["variants"]}
    out = []
    for b in detail["blocks"]:
        vs = [variants[i] for i in b["variant_ids"] if i in variants]
        parts = {}
        for p in b["parts"]:
            parts.setdefault(p["pn_type"], p["pn"])
        out.append({
            "idx": b["idx"], "ecu": b["ecu"], "label": b["label"],
            "variants": [v["label"] for v in vs],
            "markets": sorted({v["market"] for v in vs if v["market"]}),
            "hw": parts.get("HW", ""), "sws": [parts[t] for t in SW_TYPES if parts.get(t)],
            "bl": parts.get("BootLoader", ""), "purchase_pn": b["purchase_pn"],
            "status": b["compat_status"], "reason": b["compat_reason"],
        })
    return out


def compat_view(conn, frs_id: int) -> dict | None:
    detail = queries.frs_detail(conn, frs_id)
    if detail is None:
        return None
    rows = _com_rows(conn, frs_id)
    blocks = _bom_blocks(detail)
    groups = []
    grouped_blocks: set[int] = set()
    for name in dict.fromkeys(r["ecu_raw"] for r in rows):
        grows = [r for r in rows if r["ecu_raw"] == name]
        ecu, market = grows[0]["ecu"], grows[0]["market"]
        hws = list(dict.fromkeys(r["hw_pn"] for r in grows))
        sws = list(dict.fromkeys(r["sw_pn"] for r in grows))
        pu = {}
        for r in grows:
            if r["pu_pn"] and r["pu_pn"] not in pu.setdefault(r["hw_pn"], []):
                pu[r["hw_pn"]].append(r["pu_pn"])
        cells = {f"{r['hw_pn']}|{r['sw_pn']}": r["bl_version"] or "" for r in grows}

        mine = [b for b in blocks if b["ecu"] == ecu and (not market or market in b["markets"])]
        bom = []
        for b in mine:
            grouped_blocks.add(b["idx"])
            sw = next((s for s in b["sws"] if s in sws), b["sws"][0] if b["sws"] else "")
            res = is_compatible(grows, ecu, b["hw"], sw)
            listed_bl = {r["bl_version"] for r in res["matches"] if r["bl_version"]} if res["status"] == "ok" else set()
            bom.append({
                "block_idx": b["idx"], "label": b["label"], "variants": b["variants"], "hw": b["hw"], "sw": sw, "bl": b["bl"],
                "status": res["status"], "reason": res["reason"], "warning": res["status"] in WARN,
                "bl_matches": (not listed_bl or b["bl"] in listed_bl) if res["status"] == "ok" else None,
            })
        # Câu trả lời nhanh (FR-32): SW đang dùng trong BOM tương thích những HW nào
        answers = []
        for sw in dict.fromkeys(x["sw"] for x in bom if x["sw"]):
            ok = [h for h in hws if f"{h}|{sw}" in cells]
            answers.append({
                "sw": sw, "listed": sw in sws,
                "compatible": ok, "incompatible": [h for h in hws if h not in ok],
                "bom_hw": list(dict.fromkeys(x["hw"] for x in bom if x["sw"] == sw)),
            })
        groups.append({
            "name": name, "ecu": ecu, "market": market,
            "hws": [{"hw_pn": h, "pu_pns": pu.get(h, []), "in_bom": any(x["hw"] == h for x in bom)} for h in hws],
            "sws": [{"sw_pn": s, "in_bom": any(x["sw"] == s for x in bom)} for s in sws],
            "cells": cells, "bom": bom, "answers": answers,
            "warning": any(x["warning"] for x in bom),
        })

    tracked = {g["ecu"] for g in groups}
    # Block của ECU có trong COM_BOM nhưng không có nhóm nào cho market của nó
    orphans = [{"block_idx": b["idx"], "ecu": b["ecu"], "label": b["label"], "variants": b["variants"], "hw": b["hw"], "sw": b["sws"][0] if b["sws"] else "",
                "status": "no_market_rows", "reason": REASONS["no_market_rows"], "warning": True}
               for b in blocks if b["ecu"] in tracked and b["idx"] not in grouped_blocks]
    untracked = list(dict.fromkeys(b["ecu"] for b in blocks if b["ecu"] not in tracked))
    head = {k: detail["frs"][k] for k in ("id", "project", "code", "version", "side")}
    return {"frs": head, "groups": groups, "orphans": orphans, "untracked_ecus": untracked,
            "warning_count": sum(1 for g in groups for x in g["bom"] if x["warning"]) + len(orphans)}


def check_pair(conn, frs_id: int, group_name: str, hw_pn: str, sw_pn: str) -> dict | None:
    """Kiểm tra một cặp HW + SW bất kỳ trong một nhóm ECU của COM_BOM (FR-29)."""
    rows = [r for r in _com_rows(conn, frs_id) if r["ecu_raw"] == group_name]
    if not rows:
        return None
    hw, sw = norm_pn(hw_pn), norm_pn(sw_pn)
    res = is_compatible(rows, rows[0]["ecu"], hw, sw)
    pick = lambda r: {"hw_pn": r["hw_pn"], "sw_pn": r["sw_pn"], "bl_version": r["bl_version"], "pu_pn": r["pu_pn"]}
    return {
        "group": group_name, "hw_pn": hw, "sw_pn": sw,
        "status": res["status"], "compatible": res["status"] == "ok", "reason": res["reason"],
        "matches": [pick(r) for r in res["matches"]],
        "sw_for_hw": [pick(r) for r in rows if r["hw_pn"] == hw],   # HW này đi được với những SW nào
        "hw_for_sw": [pick(r) for r in rows if r["sw_pn"] == sw],   # SW này đi được với những HW nào
    }
