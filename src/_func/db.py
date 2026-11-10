"""Chỉ mục SQLite sinh từ các file Excel BOM (docs/plan.md mục 2).

Chỉ mục xóa đi quét lại được: Excel luôn là nguồn sự thật (D9).
"""
from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);

CREATE TABLE IF NOT EXISTS project(
    id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, root_dir TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS line(
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    parent_id INTEGER REFERENCES line(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    path TEXT NOT NULL,                 -- 'Legacy/LHD'
    source TEXT NOT NULL DEFAULT 'auto', -- auto (từ folder) | manual
    UNIQUE(project_id, path));

CREATE TABLE IF NOT EXISTS file(
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    rel_path TEXT NOT NULL,             -- tương đối so với thư mục dự án, dùng '/'
    mtime REAL NOT NULL, size INTEGER NOT NULL, sha1 TEXT NOT NULL,
    status TEXT NOT NULL,               -- ok | not_bom | error
    frs_code TEXT, version INTEGER,
    is_active INTEGER NOT NULL DEFAULT 0,  -- 1 = file được chọn làm TPV cuối của FRS
    note TEXT NOT NULL DEFAULT '',
    parsed_at TEXT NOT NULL,
    UNIQUE(project_id, rel_path));

CREATE TABLE IF NOT EXISTS frs(
    id INTEGER PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES project(id) ON DELETE CASCADE,
    code TEXT NOT NULL, family TEXT NOT NULL, seg INTEGER NOT NULL,
    major INTEGER NOT NULL, minor INTEGER NOT NULL,
    version INTEGER, side TEXT NOT NULL DEFAULT '', title TEXT NOT NULL DEFAULT '',
    file_id INTEGER REFERENCES file(id) ON DELETE SET NULL,
    imported_at TEXT NOT NULL,
    UNIQUE(project_id, code));

CREATE TABLE IF NOT EXISTS frs_line(
    frs_id INTEGER NOT NULL REFERENCES frs(id) ON DELETE CASCADE,
    line_id INTEGER NOT NULL REFERENCES line(id) ON DELETE CASCADE,
    source TEXT NOT NULL DEFAULT 'auto',
    PRIMARY KEY(frs_id, line_id));

CREATE TABLE IF NOT EXISTS variant(
    id INTEGER PRIMARY KEY,
    frs_id INTEGER NOT NULL REFERENCES frs(id) ON DELETE CASCADE,
    idx INTEGER NOT NULL, label TEXT NOT NULL, market TEXT NOT NULL DEFAULT '');

CREATE TABLE IF NOT EXISTS ecu_block(
    id INTEGER PRIMARY KEY,
    frs_id INTEGER NOT NULL REFERENCES frs(id) ON DELETE CASCADE,
    idx INTEGER NOT NULL, ecu TEXT NOT NULL, ecu_raw TEXT NOT NULL,
    label TEXT NOT NULL DEFAULT '',
    purchase_pn TEXT NOT NULL DEFAULT '', purchase_pn_base TEXT NOT NULL DEFAULT '',
    first_row INTEGER, last_row INTEGER,
    compat_status TEXT NOT NULL DEFAULT '', compat_reason TEXT NOT NULL DEFAULT '');

CREATE TABLE IF NOT EXISTS block_variant(
    block_id INTEGER NOT NULL REFERENCES ecu_block(id) ON DELETE CASCADE,
    variant_id INTEGER NOT NULL REFERENCES variant(id) ON DELETE CASCADE,
    applicable INTEGER NOT NULL,
    PRIMARY KEY(block_id, variant_id));

CREATE TABLE IF NOT EXISTS part(
    id INTEGER PRIMARY KEY,
    block_id INTEGER NOT NULL REFERENCES ecu_block(id) ON DELETE CASCADE,
    frs_id INTEGER NOT NULL REFERENCES frs(id) ON DELETE CASCADE,
    pn_type TEXT NOT NULL, pn TEXT NOT NULL, pn_base TEXT NOT NULL, rev TEXT NOT NULL DEFAULT '',
    pn_raw TEXT, did TEXT NOT NULL DEFAULT '', rev_did TEXT NOT NULL DEFAULT '',
    purchase_level TEXT NOT NULL DEFAULT '', component TEXT NOT NULL DEFAULT '', src_row INTEGER);

CREATE TABLE IF NOT EXISTS com_bom(
    id INTEGER PRIMARY KEY,
    frs_id INTEGER NOT NULL REFERENCES frs(id) ON DELETE CASCADE,
    ecu TEXT NOT NULL, ecu_raw TEXT NOT NULL, market TEXT NOT NULL DEFAULT '',
    pu_pn TEXT NOT NULL DEFAULT '', pu_pn_base TEXT NOT NULL DEFAULT '',
    hw_pn TEXT NOT NULL, sw_pn TEXT NOT NULL,
    bl_version TEXT NOT NULL DEFAULT '', remark TEXT NOT NULL DEFAULT '', src_row INTEGER);

CREATE TABLE IF NOT EXISTS change_content(
    id INTEGER PRIMARY KEY,
    frs_id INTEGER NOT NULL REFERENCES frs(id) ON DELETE CASCADE,
    tpv INTEGER, ecu TEXT NOT NULL, ecu_raw TEXT NOT NULL,
    qualifier TEXT NOT NULL DEFAULT '', market TEXT NOT NULL DEFAULT '',
    text TEXT NOT NULL DEFAULT '', remarks TEXT NOT NULL DEFAULT '',
    shared INTEGER NOT NULL DEFAULT 0, src_row INTEGER);

CREATE TABLE IF NOT EXISTS ticket(
    change_id INTEGER NOT NULL REFERENCES change_content(id) ON DELETE CASCADE,
    frs_id INTEGER NOT NULL REFERENCES frs(id) ON DELETE CASCADE,
    key TEXT NOT NULL, prefix TEXT NOT NULL, line TEXT NOT NULL DEFAULT '',
    PRIMARY KEY(change_id, key));

CREATE TABLE IF NOT EXISTS carry_note(
    change_id INTEGER NOT NULL REFERENCES change_content(id) ON DELETE CASCADE,
    frs_id INTEGER NOT NULL REFERENCES frs(id) ON DELETE CASCADE,
    line TEXT NOT NULL, frs_codes TEXT NOT NULL DEFAULT '[]');

CREATE TABLE IF NOT EXISTS quality_issue(
    id INTEGER PRIMARY KEY,
    file_id INTEGER NOT NULL REFERENCES file(id) ON DELETE CASCADE,
    severity TEXT NOT NULL, kind TEXT NOT NULL, sheet TEXT NOT NULL DEFAULT '',
    cell TEXT NOT NULL DEFAULT '', message TEXT NOT NULL, raw TEXT);

CREATE TABLE IF NOT EXISTS import_log(
    id INTEGER PRIMARY KEY, at TEXT NOT NULL, project TEXT NOT NULL, frs_code TEXT NOT NULL,
    action TEXT NOT NULL,               -- new | updated | removed
    old_version INTEGER, new_version INTEGER, old_file TEXT, new_file TEXT,
    diff TEXT NOT NULL DEFAULT '{}');

CREATE INDEX IF NOT EXISTS ix_part_pn ON part(pn);
CREATE INDEX IF NOT EXISTS ix_part_base ON part(pn_base);
CREATE INDEX IF NOT EXISTS ix_part_frs ON part(frs_id);
CREATE INDEX IF NOT EXISTS ix_block_frs ON ecu_block(frs_id, ecu);
CREATE INDEX IF NOT EXISTS ix_block_pu ON ecu_block(purchase_pn_base);
CREATE INDEX IF NOT EXISTS ix_ticket_key ON ticket(key);
CREATE INDEX IF NOT EXISTS ix_ticket_frs ON ticket(frs_id);
CREATE INDEX IF NOT EXISTS ix_combom_frs ON com_bom(frs_id, ecu);
CREATE INDEX IF NOT EXISTS ix_change_frs ON change_content(frs_id, tpv);
CREATE INDEX IF NOT EXISTS ix_issue_file ON quality_issue(file_id);
"""


def default_db_path() -> Path:
    """Chỉ mục nằm ở máy cá nhân, ngoài OneDrive (tránh sync làm hỏng SQLite)."""
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "BOM_management" / "index.db"


def open_db(path=None) -> sqlite3.Connection:
    path = Path(path) if path else default_db_path()
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    row = None
    try:
        row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
    except sqlite3.OperationalError:
        pass
    if row is not None and int(row["value"]) != SCHEMA_VERSION:
        # Schema đổi: chỉ mục dựng lại được từ Excel nên xóa sạch thay vì migrate.
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        conn.execute("PRAGMA foreign_keys = OFF")
        for t in tables:
            conn.execute(f'DROP TABLE IF EXISTS "{t}"')
        conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('schema_version', ?)", (str(SCHEMA_VERSION),))
    conn.commit()
    return conn


# ---------- ghi ----------

def upsert_project(conn, name: str, root_dir: str) -> int:
    conn.execute("INSERT INTO project(name, root_dir) VALUES(?, ?) ON CONFLICT(name) DO UPDATE SET root_dir=excluded.root_dir", (name, root_dir))
    return conn.execute("SELECT id FROM project WHERE name=?", (name,)).fetchone()["id"]


def ensure_line(conn, project_id: int, segments: list[str]) -> int | None:
    """Tạo chuỗi line cha-con theo các segment folder, trả id của line lá."""
    parent_id, path, line_id = None, "", None
    for seg in segments:
        path = f"{path}/{seg}" if path else seg
        row = conn.execute("SELECT id FROM line WHERE project_id=? AND path=?", (project_id, path)).fetchone()
        if row is None:
            cur = conn.execute("INSERT INTO line(project_id, parent_id, name, path, source) VALUES(?,?,?,?, 'auto')", (project_id, parent_id, seg, path))
            line_id = cur.lastrowid
        else:
            line_id = row["id"]
        parent_id = line_id
    return line_id


def part_set(conn, frs_id: int) -> set[tuple]:
    """Tập (ECU, variant áp dụng, PN Type, PN) của một FRS, dùng để diff khi nhập lại."""
    rows = conn.execute(
        """SELECT b.id AS bid, b.ecu, p.pn_type, p.pn,
                  (SELECT group_concat(v.label, '+') FROM block_variant bv JOIN variant v ON v.id=bv.variant_id
                    WHERE bv.block_id=b.id AND bv.applicable=1 ORDER BY v.idx) AS variants
             FROM part p JOIN ecu_block b ON b.id=p.block_id WHERE p.frs_id=?""",
        (frs_id,),
    ).fetchall()
    return {(r["ecu"], r["variants"] or "", r["pn_type"], r["pn"]) for r in rows}


def parsed_part_set(parsed: dict) -> set[tuple]:
    return {(b["ecu"], "+".join(b["variants"]), p["pn_type"], p["pn"]) for b in parsed["blocks"] for p in b["parts"]}


def diff_parts(old: set[tuple], new: set[tuple]) -> dict:
    fmt = lambda s: [dict(zip(("ecu", "variants", "pn_type", "pn"), t)) for t in sorted(s)]
    return {"removed": fmt(old - new), "added": fmt(new - old)}


def delete_frs(conn, frs_id: int) -> None:
    conn.execute("DELETE FROM frs WHERE id=?", (frs_id,))


def store_frs(conn, project_id: int, file_id: int, parsed: dict, now: str) -> int:
    """Ghi (thay thế) toàn bộ dữ liệu của một FRS từ kết quả parse_file."""
    frs = parsed["frs"]
    old = conn.execute("SELECT id FROM frs WHERE project_id=? AND code=?", (project_id, frs["code"])).fetchone()
    manual_lines = []
    if old is not None:
        manual_lines = [r["line_id"] for r in conn.execute("SELECT line_id FROM frs_line WHERE frs_id=? AND source='manual'", (old["id"],))]
        delete_frs(conn, old["id"])
    cur = conn.execute(
        "INSERT INTO frs(project_id, code, family, seg, major, minor, version, side, title, file_id, imported_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (project_id, frs["code"], frs["family"], frs["seg"], frs["major"], frs["minor"], parsed["version"], parsed["side"], parsed["title"], file_id, now),
    )
    frs_id = cur.lastrowid
    for line_id in manual_lines:  # gán tay của người dùng không bị mất khi quét lại
        conn.execute("INSERT OR IGNORE INTO frs_line(frs_id, line_id, source) VALUES(?,?, 'manual')", (frs_id, line_id))

    variant_ids = []
    for v in parsed["variants"]:
        c = conn.execute("INSERT INTO variant(frs_id, idx, label, market) VALUES(?,?,?,?)", (frs_id, v["index"], v["label"], v["market"]))
        variant_ids.append(c.lastrowid)

    compat = {c["block_index"]: c for c in parsed.get("compat", [])}
    for b in parsed["blocks"]:
        cp = compat.get(b["index"], {})
        c = conn.execute(
            "INSERT INTO ecu_block(frs_id, idx, ecu, ecu_raw, label, purchase_pn, purchase_pn_base, first_row, last_row, compat_status, compat_reason) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (frs_id, b["index"], b["ecu"], b["ecu_raw"], b["label"], b["purchase_pn"], b["purchase_pn_base"], b["first_row"], b["last_row"], cp.get("status", ""), cp.get("reason", "")),
        )
        block_id = c.lastrowid
        for i, flag in enumerate(b["applicability"]):
            if i < len(variant_ids):
                conn.execute("INSERT INTO block_variant(block_id, variant_id, applicable) VALUES(?,?,?)", (block_id, variant_ids[i], 1 if flag == "X" else 0))
        conn.executemany(
            "INSERT INTO part(block_id, frs_id, pn_type, pn, pn_base, rev, pn_raw, did, rev_did, purchase_level, component, src_row) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            [(block_id, frs_id, p["pn_type"], p["pn"], p["pn_base"], p["rev"], p["pn_raw"], p["did"], p["rev_did"], p["purchase_level"], p["component"], p["row"]) for p in b["parts"]],
        )

    conn.executemany(
        "INSERT INTO com_bom(frs_id, ecu, ecu_raw, market, pu_pn, pu_pn_base, hw_pn, sw_pn, bl_version, remark, src_row) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        [(frs_id, r["ecu"], r["ecu_raw"], r["market"], r["pu_pn"], r["pu_pn_base"], r["hw_pn"], r["sw_pn"], r["bl_version"], r["remark"], r["row"]) for r in parsed["com_bom"]],
    )

    for e in parsed["change_content"]:
        c = conn.execute(
            "INSERT INTO change_content(frs_id, tpv, ecu, ecu_raw, qualifier, market, text, remarks, shared, src_row) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (frs_id, e["tpv"], e["ecu"], e["ecu_raw"], e["qualifier"], e["market"], e["text"], e["remarks"], 1 if e["text_shared_with_row_above"] else 0, e["row"]),
        )
        change_id = c.lastrowid
        conn.executemany("INSERT OR IGNORE INTO ticket(change_id, frs_id, key, prefix, line) VALUES(?,?,?,?,?)", [(change_id, frs_id, t["key"], t["prefix"], t["line"]) for t in e["tickets"]])
        conn.executemany("INSERT INTO carry_note(change_id, frs_id, line, frs_codes) VALUES(?,?,?,?)", [(change_id, frs_id, n["line"], json.dumps(n["frs_codes"])) for n in e["carry_notes"]])
    return frs_id


def store_issues(conn, file_id: int, issues: list[dict]) -> None:
    conn.execute("DELETE FROM quality_issue WHERE file_id=?", (file_id,))
    conn.executemany(
        "INSERT INTO quality_issue(file_id, severity, kind, sheet, cell, message, raw) VALUES(?,?,?,?,?,?,?)",
        [(file_id, i["severity"], i["kind"], i["sheet"], i["cell"], i["message"], i["raw"]) for i in issues],
    )


# ---------- đọc (dùng cho kiểm thử và Giai đoạn 3) ----------

def counts(conn) -> dict:
    tables = ("project", "line", "file", "frs", "variant", "ecu_block", "part", "com_bom", "change_content", "ticket", "quality_issue")
    return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}


def where_used(conn, pn: str) -> list[dict]:
    """Mỗi block dùng PN là một dòng (D16). Khớp PN đầy đủ, PN bỏ rev, hoặc Purchase PN."""
    from .normalize import norm_pn, split_pn

    q = norm_pn(pn)
    base = split_pn(q)[0]
    rows = conn.execute(
        """SELECT pr.name AS project, f.code AS frs, f.version, b.id AS block_id, b.ecu, b.label, b.purchase_pn,
                  p.pn_type, p.pn,
                  (SELECT group_concat(v.label, ', ') FROM block_variant bv JOIN variant v ON v.id=bv.variant_id
                    WHERE bv.block_id=b.id AND bv.applicable=1) AS variants,
                  (SELECT group_concat(l.path, ', ') FROM frs_line fl JOIN line l ON l.id=fl.line_id WHERE fl.frs_id=f.id) AS lines
             FROM part p JOIN ecu_block b ON b.id=p.block_id JOIN frs f ON f.id=p.frs_id JOIN project pr ON pr.id=f.project_id
            WHERE p.pn=:q OR (:exact=0 AND p.pn_base=:base)
            UNION ALL
           SELECT pr.name, f.code, f.version, b.id, b.ecu, b.label, b.purchase_pn, 'PU', b.purchase_pn,
                  (SELECT group_concat(v.label, ', ') FROM block_variant bv JOIN variant v ON v.id=bv.variant_id
                    WHERE bv.block_id=b.id AND bv.applicable=1),
                  (SELECT group_concat(l.path, ', ') FROM frs_line fl JOIN line l ON l.id=fl.line_id WHERE fl.frs_id=f.id)
             FROM ecu_block b JOIN frs f ON f.id=b.frs_id JOIN project pr ON pr.id=f.project_id
            WHERE b.purchase_pn=:q OR (:exact=0 AND b.purchase_pn_base=:base)
            ORDER BY 1, 2, 4""",
        {"q": q, "base": base, "exact": 1 if "-" in q else 0},
    ).fetchall()
    return [dict(r) for r in rows]


def ticket_lookup(conn, key: str) -> list[dict]:
    rows = conn.execute(
        """SELECT pr.name AS project, f.code AS frs, c.tpv, c.ecu, c.ecu_raw, t.key, t.line
             FROM ticket t JOIN change_content c ON c.id=t.change_id JOIN frs f ON f.id=t.frs_id JOIN project pr ON pr.id=f.project_id
            WHERE t.key=? ORDER BY pr.name, f.code, c.tpv DESC, c.src_row""",
        (key.strip().upper(),),
    ).fetchall()
    return [dict(r) for r in rows]
