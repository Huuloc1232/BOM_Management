"""So sánh hai FRS theo ECU part number (D10, FR-27) và theo ticket đã release (D13)."""
from __future__ import annotations

from _func.frs_tree import build_tree
from _func.normalize import split_pn
from _func.parser_change import TICKET_URL

from . import queries

PN_TYPE_ORDER = ["PU", "HW", "SW_BASIC", "SW", "SW_APP", "CAL", "BootLoader"]


def _type_key(pn_type: str):
    return (PN_TYPE_ORDER.index(pn_type) if pn_type in PN_TYPE_ORDER else len(PN_TYPE_ORDER), pn_type)


def _prep(detail: dict) -> list[dict]:
    """Block của một FRS ở dạng gọn: variants là nhãn, parts là {pn_type: [pn...]}, gồm cả PU."""
    names = {v["id"]: v["label"] for v in detail["variants"]}
    out = []
    for b in detail["blocks"]:
        parts: dict[str, list[str]] = {}
        if b["purchase_pn"]:
            parts["PU"] = [b["purchase_pn"]]
        for p in b["parts"]:
            parts.setdefault(p["pn_type"], []).append(p["pn"])
        out.append({"ecu": b["ecu"], "label": b["label"], "variants": [names[v] for v in b["variant_ids"] if v in names], "parts": parts})
    return out


def _score(a: dict, b: dict) -> int:
    """Độ giống nhau của hai block cùng ECU, dùng để ghép cặp block giữa hai FRS."""
    va, vb = set(a["variants"]), set(b["variants"])
    score = 0
    if va and va == vb:
        score += 6
    elif va & vb:
        score += 3
    if a["label"] and a["label"] == b["label"]:
        score += 2
    base = lambda blk, t: {split_pn(x)[0] for x in blk["parts"].get(t, [])}
    if base(a, "HW") & base(b, "HW"):
        score += 2
    if base(a, "PU") & base(b, "PU"):
        score += 1
    return score


def pair_blocks(blocks_a: list[dict], blocks_b: list[dict]) -> list[tuple[dict | None, dict | None]]:
    """Ghép block theo ECU: ưu tiên cùng variant xe, rồi nhãn, rồi HW/PU. Dư thì là chỉ-có-ở-một-bên."""
    pairs: list[tuple[dict | None, dict | None]] = []
    ecus = list(dict.fromkeys([b["ecu"] for b in blocks_a] + [b["ecu"] for b in blocks_b]))
    for ecu in ecus:
        la = [b for b in blocks_a if b["ecu"] == ecu]
        lb = [b for b in blocks_b if b["ecu"] == ecu]
        if len(la) == 1 and len(lb) == 1:
            pairs.append((la[0], lb[0]))
            continue
        scored = sorted(((_score(a, b), -i, -j, i, j) for i, a in enumerate(la) for j, b in enumerate(lb)), reverse=True)
        used_a, used_b, matched = set(), set(), {}
        for score, _, _, i, j in scored:
            if score > 0 and i not in used_a and j not in used_b:
                used_a.add(i), used_b.add(j)
                matched[i] = j
        for i, a in enumerate(la):
            pairs.append((a, lb[matched[i]] if i in matched else None))
        pairs.extend((None, b) for j, b in enumerate(lb) if j not in used_b)
    return pairs


def _status(pa: str, pb: str) -> str:
    if pa == pb:
        return "same"
    if not pa:
        return "added"
    if not pb:
        return "removed"
    return "rev" if split_pn(pa)[0] == split_pn(pb)[0] else "changed"


def compare_blocks(blocks_a: list[dict], blocks_b: list[dict]) -> dict:
    groups = []
    summary = {"same": 0, "rev": 0, "changed": 0, "added": 0, "removed": 0}
    for a, b in pair_blocks(blocks_a, blocks_b):
        ref = a or b
        rows = []
        types = sorted(set((a or {}).get("parts", {})) | set((b or {}).get("parts", {})), key=_type_key)
        for t in types:
            la = (a or {}).get("parts", {}).get(t, [])
            lb = (b or {}).get("parts", {}).get(t, [])
            for i in range(max(len(la), len(lb))):
                pa = la[i] if i < len(la) else ""
                pb = lb[i] if i < len(lb) else ""
                st = _status(pa, pb)
                summary[st] += 1
                rows.append({"pn_type": t, "a": pa, "b": pb, "status": st})
        groups.append({
            "ecu": ref["ecu"],
            "block": "both" if a and b else ("only_a" if a else "only_b"),
            "a": {"variants": a["variants"], "label": a["label"]} if a else None,
            "b": {"variants": b["variants"], "label": b["label"]} if b else None,
            "rows": rows,
            "differs": any(r["status"] != "same" for r in rows),
        })
    return {"groups": groups, "summary": summary}


def frs_tickets(conn, frs_id: int) -> list[dict]:
    """Mọi ticket một FRS đã release, gộp theo key (FR-20)."""
    out: dict[str, dict] = {}
    for r in conn.execute(
        """SELECT t.key, t.prefix, t.line, c.tpv, c.ecu_raw FROM ticket t JOIN change_content c ON c.id=t.change_id
            WHERE t.frs_id=? ORDER BY c.tpv DESC, c.src_row""", (frs_id,)):
        item = out.setdefault(r["key"], {"key": r["key"], "prefix": r["prefix"], "url": TICKET_URL.format(key=r["key"]), "line": r["line"], "tpvs": [], "ecus": []})
        if r["tpv"] is not None and r["tpv"] not in item["tpvs"]:
            item["tpvs"].append(r["tpv"])
        if r["ecu_raw"] not in item["ecus"]:
            item["ecus"].append(r["ecu_raw"])
    for item in out.values():
        item["first_tpv"] = min(item["tpvs"]) if item["tpvs"] else None
    return sorted(out.values(), key=lambda t: (-(t["first_tpv"] or 0), t["prefix"], int(t["key"].rsplit("-", 1)[1])))


def frs_list(conn, meta: dict | None = None) -> list[dict]:
    """Danh sách FRS cho ô chọn so sánh, kèm FRS cha theo cây (mặc định để so sánh)."""
    rows = [dict(r) for r in conn.execute(
        """SELECT f.id, f.project_id, p.name AS project, f.code, f.version, f.side
             FROM frs f JOIN project p ON p.id=f.project_id ORDER BY p.name COLLATE NOCASE, f.family, f.seg, f.major, f.minor""")]
    by_project: dict[int, list[dict]] = {}
    for r in rows:
        by_project.setdefault(r["project_id"], []).append(r)
    for items in by_project.values():
        codes = {r["code"] for r in items}
        manual = {c: p for c, p in (meta or {}).get("projects", {}).get(items[0]["project"], {}).get("frs_parent", {}).items()
                  if c in codes and (p is None or p in codes)}
        tree = build_tree([r["code"] for r in items], manual)
        ids = {r["code"]: r["id"] for r in items}
        for r in items:
            parent = tree["nodes"][r["code"]]["parent"]
            r["parent_id"] = ids.get(parent)
            r["parent_code"] = parent
    return rows


def compare_frs(conn, id_a: int, id_b: int) -> dict | None:
    da, db_ = queries.frs_detail(conn, id_a), queries.frs_detail(conn, id_b)
    if da is None or db_ is None:
        return None
    result = compare_blocks(_prep(da), _prep(db_))
    head = lambda d: {k: d["frs"][k] for k in ("id", "project", "code", "version", "side", "lines")}
    ta = {t["key"]: t for t in frs_tickets(conn, id_a)}
    tb = {t["key"]: t for t in frs_tickets(conn, id_b)}
    result.update({
        "a": head(da), "b": head(db_),
        "variants_a": [v["label"] for v in da["variants"]],
        "variants_b": [v["label"] for v in db_["variants"]],
        "tickets": {
            "common": len(set(ta) & set(tb)),
            "only_a": [ta[k] for k in ta if k not in tb],
            "only_b": [tb[k] for k in tb if k not in ta],
        },
    })
    return result
