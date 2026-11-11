"""Truy vấn chỉ mục SQLite cho giao diện web (Giai đoạn 3)."""
from __future__ import annotations

import re

from _func.normalize import norm_pn, norm_text, split_pn
from _func.parser_change import TICKET_URL

MAX_ROWS = 300

_VARIANTS = """(SELECT group_concat(v.label, ', ') FROM block_variant bv JOIN variant v ON v.id=bv.variant_id
                 WHERE bv.block_id=b.id AND bv.applicable=1)"""
_LINES = """(SELECT group_concat(path, ', ') FROM (SELECT l.path FROM frs_line fl JOIN line l ON l.id=fl.line_id
               WHERE fl.frs_id=f.id ORDER BY l.path COLLATE NOCASE))"""


def _rows(cur) -> list[dict]:
    return [dict(r) for r in cur.fetchall()]


def _meta(conn, key: str) -> str:
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else ""


def state(conn) -> dict:
    projects = _rows(conn.execute(
        """SELECT p.id, p.name, p.root_dir,
                  (SELECT COUNT(*) FROM frs f WHERE f.project_id=p.id) AS frs_count,
                  (SELECT COUNT(*) FROM line l WHERE l.project_id=p.id) AS line_count,
                  (SELECT COUNT(DISTINCT b.ecu) FROM ecu_block b JOIN frs f ON f.id=b.frs_id WHERE f.project_id=p.id) AS ecu_count,
                  (SELECT COUNT(*) FROM quality_issue q JOIN file fi ON fi.id=q.file_id
                    WHERE fi.project_id=p.id AND fi.is_active=1 AND q.severity IN ('warning','error')) AS warning_count
             FROM project p ORDER BY p.name COLLATE NOCASE"""))
    return {"projects": projects, "last_scan": _meta(conn, "last_scan"), "last_root": _meta(conn, "last_root")}


def project_detail(conn, project_id: int) -> dict | None:
    project = conn.execute("SELECT id, name, root_dir FROM project WHERE id=?", (project_id,)).fetchone()
    if project is None:
        return None
    lines = _rows(conn.execute(
        """SELECT l.id, l.parent_id, l.name, l.path, l.source,
                  (SELECT COUNT(*) FROM frs_line fl WHERE fl.line_id=l.id) AS frs_count
             FROM line l WHERE l.project_id=? ORDER BY l.path COLLATE NOCASE""", (project_id,)))
    frs = _rows(conn.execute(
        f"""SELECT f.id, f.code, f.family, f.seg, f.major, f.minor, f.version, f.side, f.manual, fi.rel_path AS file,
                   {_LINES} AS lines,
                   (SELECT group_concat(fl.line_id) FROM frs_line fl WHERE fl.frs_id=f.id) AS line_ids,
                   (SELECT COUNT(DISTINCT ecu) FROM ecu_block b WHERE b.frs_id=f.id) AS ecu_count,
                   (SELECT COUNT(*) FROM ecu_block b WHERE b.frs_id=f.id) AS block_count,
                   (SELECT COUNT(*) FROM quality_issue q WHERE q.file_id=f.file_id AND q.severity IN ('warning','error')) AS warning_count
              FROM frs f LEFT JOIN file fi ON fi.id=f.file_id
             WHERE f.project_id=? ORDER BY f.family, f.seg, f.major, f.minor""", (project_id,)))
    for f in frs:
        f["line_ids"] = [int(x) for x in f["line_ids"].split(",")] if f["line_ids"] else []
    files = _rows(conn.execute(
        "SELECT rel_path, status, frs_code, version, note FROM file WHERE project_id=? AND is_active=0 ORDER BY rel_path", (project_id,)))
    return {"project": dict(project), "lines": lines, "frs": frs, "other_files": files}


def frs_detail(conn, frs_id: int) -> dict | None:
    frs = conn.execute(
        f"""SELECT f.*, p.name AS project, fi.rel_path AS file, fi.parsed_at, {_LINES} AS lines
              FROM frs f JOIN project p ON p.id=f.project_id LEFT JOIN file fi ON fi.id=f.file_id WHERE f.id=?""", (frs_id,)).fetchone()
    if frs is None:
        return None
    line_links = _rows(conn.execute(
        "SELECT l.id, l.path, fl.source FROM frs_line fl JOIN line l ON l.id=fl.line_id WHERE fl.frs_id=? ORDER BY l.path COLLATE NOCASE", (frs_id,)))
    all_lines = [r[0] for r in conn.execute("SELECT path FROM line WHERE project_id=? ORDER BY path COLLATE NOCASE", (frs["project_id"],))]
    variants = _rows(conn.execute("SELECT id, idx, label, market FROM variant WHERE frs_id=? ORDER BY idx", (frs_id,)))
    blocks = _rows(conn.execute(
        "SELECT id, idx, ecu, ecu_raw, label, purchase_pn, purchase_pn_base, first_row, last_row, compat_status, compat_reason FROM ecu_block WHERE frs_id=? ORDER BY idx", (frs_id,)))
    applic: dict[int, list[int]] = {}
    for r in conn.execute("SELECT bv.block_id, bv.variant_id FROM block_variant bv JOIN ecu_block b ON b.id=bv.block_id WHERE b.frs_id=? AND bv.applicable=1", (frs_id,)):
        applic.setdefault(r["block_id"], []).append(r["variant_id"])
    parts: dict[int, list[dict]] = {}
    for r in conn.execute("SELECT block_id, pn_type, pn, pn_base, rev, did, rev_did, purchase_level, src_row FROM part WHERE frs_id=? ORDER BY id", (frs_id,)):
        parts.setdefault(r["block_id"], []).append({k: r[k] for k in r.keys() if k != "block_id"})
    for b in blocks:
        b["variant_ids"] = applic.get(b["id"], [])
        b["parts"] = parts.get(b["id"], [])
    com_bom = _rows(conn.execute("SELECT ecu, ecu_raw, market, pu_pn, hw_pn, sw_pn, bl_version, remark, src_row FROM com_bom WHERE frs_id=? ORDER BY id", (frs_id,)))
    changes = _rows(conn.execute("SELECT id, tpv, ecu, ecu_raw, text, remarks, shared FROM change_content WHERE frs_id=? ORDER BY tpv DESC, src_row", (frs_id,)))
    tickets: dict[int, list[dict]] = {}
    for r in conn.execute("SELECT change_id, key FROM ticket WHERE frs_id=?", (frs_id,)):
        tickets.setdefault(r["change_id"], []).append({"key": r["key"], "url": TICKET_URL.format(key=r["key"])})
    for c in changes:
        c["tickets"] = tickets.get(c["id"], [])
    issues = _rows(conn.execute("SELECT severity, kind, sheet, cell, message, raw FROM quality_issue WHERE file_id=? ORDER BY CASE severity WHEN 'error' THEN 0 WHEN 'warning' THEN 1 ELSE 2 END, id", (frs["file_id"],))) if frs["file_id"] else []
    return {"frs": dict(frs), "variants": variants, "blocks": blocks, "com_bom": com_bom, "changes": changes, "issues": issues,
            "line_links": line_links, "project_lines": all_lines}


def _filters(args: dict) -> tuple[str, dict]:
    """Bộ lọc chung cho tìm kiếm: dự án, line, variant xe, ECU, PN Type (FR-26)."""
    sql, params = "", {}
    if args.get("project"):
        sql += " AND f.project_id=:project"
        params["project"] = int(args["project"])
    if args.get("line"):
        sql += " AND f.id IN (SELECT fl.frs_id FROM frs_line fl JOIN line l ON l.id=fl.line_id WHERE l.id=:line OR l.path LIKE (SELECT path FROM line WHERE id=:line) || '/%')"
        params["line"] = int(args["line"])
    if args.get("variant"):
        sql += " AND b.id IN (SELECT bv.block_id FROM block_variant bv JOIN variant v ON v.id=bv.variant_id WHERE bv.applicable=1 AND v.label=:variant)"
        params["variant"] = args["variant"]
    if args.get("ecu"):
        sql += " AND b.ecu=:ecu"
        params["ecu"] = args["ecu"].upper()
    return sql, params


def search(conn, q: str, args: dict | None = None) -> dict:
    """Tìm kiếm toàn cục (FR-22): mã FRS, part number, tên ECU, mã ticket."""
    args = args or {}
    text = norm_text(q)
    out = {"q": text, "frs": [], "parts": [], "ecus": [], "tickets": [], "truncated": False}
    if not text:
        return out
    flt, params = _filters(args)
    like = lambda s: s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

    # 1. FRS: 'FRS 3B.1.11.0', '3b.1.11', ...
    code_q = re.sub(r"(?i)^\s*frs\s*", "", text).upper().replace(" ", "")
    if re.search(r"\d", code_q) and "." in code_q or re.fullmatch(r"[0-9A-Z]{1,3}", code_q):
        out["frs"] = _rows(conn.execute(
            f"""SELECT f.id, p.name AS project, f.code, f.version, f.side, {_LINES} AS lines
                  FROM frs f JOIN project p ON p.id=f.project_id
                 WHERE f.code LIKE :c ESCAPE '\\' {" AND f.project_id=:project" if "project" in params else ""}
                 ORDER BY p.name, f.family, f.seg, f.major, f.minor LIMIT {MAX_ROWS}""",
            {"c": f"%{like(code_q)}%", **{k: v for k, v in params.items() if k == "project"}}))

    # 2. Ticket: 'CCB-26107' hoặc tiền tố 'CCB-26'
    tq = text.upper().strip("[] ")
    if re.fullmatch(r"[A-Z][A-Z0-9]*-\d*", tq):
        out["tickets"] = _rows(conn.execute(
            f"""SELECT t.key, p.name AS project, f.id AS frs_id, f.code AS frs, c.tpv, c.ecu, c.ecu_raw, t.line
                  FROM ticket t JOIN change_content c ON c.id=t.change_id JOIN frs f ON f.id=t.frs_id JOIN project p ON p.id=f.project_id
                 WHERE (t.key=:k OR t.key LIKE :kp ESCAPE '\\') {" AND f.project_id=:project" if "project" in params else ""}
                 ORDER BY (t.key=:k) DESC, t.key, p.name, f.code, c.tpv DESC LIMIT {MAX_ROWS}""",
            {"k": tq, "kp": like(tq) + "%", **{k: v for k, v in params.items() if k == "project"}}))
        for t in out["tickets"]:
            t["url"] = TICKET_URL.format(key=t["key"])

    # 3. Part number: mỗi block một dòng (D16). Khớp tiền tố, bỏ khoảng trắng, không cần rev.
    pn = norm_pn(text)
    type_sql = ""
    if args.get("pn_type"):
        type_sql = " AND p.pn_type=:pn_type"
        params["pn_type"] = args["pn_type"]
    if len(pn) >= 3 and re.fullmatch(r"[0-9A-Z-]+", pn) and not out["tickets"]:
        base = split_pn(pn)[0]
        pparams = {"pfx": like(pn) + "%", "exact": pn, "base": base, **params}
        rows = _rows(conn.execute(
            f"""SELECT pr.name AS project, f.id AS frs_id, f.code AS frs, f.version, {_LINES} AS lines,
                       b.id AS block_id, b.idx AS block_idx, b.ecu, b.label, b.purchase_pn, {_VARIANTS} AS variants,
                       p.pn_type, p.pn, p.did, (p.pn=:exact) AS exact
                  FROM part p JOIN ecu_block b ON b.id=p.block_id JOIN frs f ON f.id=p.frs_id JOIN project pr ON pr.id=f.project_id
                 WHERE (p.pn LIKE :pfx ESCAPE '\\') {flt} {type_sql}
                 UNION ALL
                SELECT pr.name, f.id, f.code, f.version, {_LINES}, b.id, b.idx, b.ecu, b.label, b.purchase_pn, {_VARIANTS},
                       'PU', b.purchase_pn, '', (b.purchase_pn=:exact)
                  FROM ecu_block b JOIN frs f ON f.id=b.frs_id JOIN project pr ON pr.id=f.project_id
                 WHERE (b.purchase_pn LIKE :pfx ESCAPE '\\') {flt} {"AND 0" if args.get("pn_type") and args["pn_type"] != "PU" else ""}
                 ORDER BY 15 DESC, 13, 1, 3, 7 LIMIT {MAX_ROWS + 1}""", pparams))
        out["truncated"] = len(rows) > MAX_ROWS
        out["parts"] = rows[:MAX_ROWS]

    # 4. ECU: tên khớp chính xác hoặc tiền tố
    ecu_q = text.upper()
    if re.fullmatch(r"[0-9A-Z_ ]{2,12}", ecu_q):
        eparams = {"e": ecu_q, "ep": like(ecu_q) + "%", **{k: v for k, v in params.items() if k in ("project", "line", "variant")}}
        eflt, _ = _filters({k: v for k, v in args.items() if k in ("project", "line", "variant")})
        out["ecus"] = _rows(conn.execute(
            f"""SELECT pr.name AS project, f.id AS frs_id, f.code AS frs, f.version, {_LINES} AS lines,
                       b.id AS block_id, b.ecu, b.label, b.purchase_pn, {_VARIANTS} AS variants, b.compat_status,
                       (SELECT group_concat(p.pn_type || '=' || p.pn, '  ') FROM part p WHERE p.block_id=b.id) AS parts
                  FROM ecu_block b JOIN frs f ON f.id=b.frs_id JOIN project pr ON pr.id=f.project_id
                 WHERE (b.ecu=:e OR b.ecu LIKE :ep ESCAPE '\\') {eflt}
                 ORDER BY (b.ecu=:e) DESC, b.ecu, pr.name, f.family, f.seg, f.major DESC, f.minor DESC, b.idx LIMIT {MAX_ROWS}""", eparams))
    return out


def filter_options(conn) -> dict:
    return {
        "variants": [r[0] for r in conn.execute("SELECT DISTINCT label FROM variant ORDER BY 1")],
        "pn_types": [r[0] for r in conn.execute("SELECT DISTINCT pn_type FROM part ORDER BY 1")] + ["PU"],
        "ecus": [r[0] for r in conn.execute("SELECT DISTINCT ecu FROM ecu_block ORDER BY 1")],
    }
