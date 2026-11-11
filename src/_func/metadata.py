"""Metadata do người dùng nhập, lưu cùng thư mục database (không nằm trong chỉ mục SQLite).

File: <thư mục database>/_bom_management/metadata.json
    {"version": 1, "projects": {"VF3": {
        "frs_parent": {"3B.1.11.0": "3B.1.10.2"},        # sửa tay cha-con (FR-36)
        "manual_frs": {"3B.1.12.0": {"created": "..."}},  # FRS tạo tay, chưa có file (FR-07)
        "frs_lines":  {"3B.1.11.0": ["Pin LFP"]}          # gán FRS vào thêm line (FR-05)
    }}}
Chỉ mục xóa đi quét lại được, còn file này là dữ liệu gốc của người dùng nên ghi nguyên tử.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .normalize import parse_frs_code

META_DIR = "_bom_management"   # scanner bỏ qua folder bắt đầu bằng '_'
META_FILE = "metadata.json"
SEG_SIDE = {1: "LHD", 6: "RHD"}  # D3


def metadata_path(root) -> Path:
    return Path(root) / META_DIR / META_FILE


def load_metadata(root) -> dict:
    try:
        data = json.loads(metadata_path(root).read_text(encoding="utf-8"))
        if isinstance(data, dict):
            if not isinstance(data.get("projects"), dict):
                data["projects"] = {}
            return data
    except (OSError, ValueError):
        pass
    return {"version": 1, "projects": {}}


def save_metadata(root, data: dict) -> None:
    path = metadata_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(path)  # ghi nguyên tử để OneDrive không sync file dở dang


def _section(meta: dict, project: str, key: str) -> dict:
    proj = meta["projects"].setdefault(project, {})
    if not isinstance(proj.get(key), dict):
        proj[key] = {}
    return proj[key]


def manual_parents(meta: dict, project: str) -> dict:
    value = meta.get("projects", {}).get(project, {}).get("frs_parent", {})
    return dict(value) if isinstance(value, dict) else {}


def normalize_code(text) -> str:
    """'frs 3b.1.12.0' -> '3B.1.12.0'. Ném ValueError nếu không đúng dạng mã FRS."""
    cleaned = str(text or "").strip().upper()
    if cleaned.startswith("FRS"):
        cleaned = cleaned[3:].strip()
    frs = parse_frs_code(cleaned)
    if frs is None or frs["code"] != cleaned:
        raise ValueError("Mã FRS không hợp lệ. Dạng đúng: 3B.1.12.0 (dòng.segment.major.minor)")
    return frs["code"]


def add_manual_frs(root, project: str, code: str, lines: list[str]) -> str:
    code = normalize_code(code)
    meta = load_metadata(root)
    table = _section(meta, project, "manual_frs")
    if code in table:
        raise ValueError(f"FRS {code} đã được tạo tay trước đó")
    table[code] = {"created": datetime.now().isoformat(timespec="seconds")}
    if lines:
        _section(meta, project, "frs_lines")[code] = list(dict.fromkeys(lines))
    save_metadata(root, meta)
    return code


def remove_manual_frs(root, project: str, code: str) -> None:
    meta = load_metadata(root)
    table = _section(meta, project, "manual_frs")
    if code not in table:
        raise ValueError(f"FRS {code} không phải FRS tạo tay")
    del table[code]
    _section(meta, project, "frs_lines").pop(code, None)
    parents = _section(meta, project, "frs_parent")
    parents.pop(code, None)
    for child in [c for c, p in parents.items() if p == code]:  # con của FRS bị xóa quay về tự động
        parents.pop(child)
    save_metadata(root, meta)


def set_frs_lines(root, project: str, code: str, lines: list[str]) -> None:
    meta = load_metadata(root)
    table = _section(meta, project, "frs_lines")
    lines = list(dict.fromkeys(lines))
    if lines:
        table[code] = lines
    else:
        table.pop(code, None)
    save_metadata(root, meta)


def sync(conn, root) -> dict:
    """Đưa metadata vào chỉ mục: tạo/xóa FRS tạo tay và cập nhật liên kết FRS - line gán tay.

    Gọi sau mỗi lần quét và sau mỗi thay đổi metadata. Không đụng tới liên kết line tự động
    (suy từ folder) và không đụng tới FRS có file.
    """
    meta = load_metadata(root)
    now = datetime.now().isoformat(timespec="seconds")
    stale_lines: list[dict] = []
    for project in conn.execute("SELECT id, name FROM project").fetchall():
        pmeta = meta["projects"].get(project["name"], {})
        wanted = pmeta.get("manual_frs", {}) if isinstance(pmeta.get("manual_frs"), dict) else {}
        existing = {r["code"]: r for r in conn.execute("SELECT id, code, manual FROM frs WHERE project_id=?", (project["id"],))}
        for code in wanted:
            frs = parse_frs_code(code)
            if frs is None or code in existing:   # đã có file thật (hoặc placeholder) cho mã này
                continue
            conn.execute(
                "INSERT INTO frs(project_id, code, family, seg, major, minor, version, side, title, file_id, imported_at, manual) VALUES(?,?,?,?,?,?,NULL,?,'',NULL,?,1)",
                (project["id"], frs["code"], frs["family"], frs["seg"], frs["major"], frs["minor"], SEG_SIDE.get(frs["seg"], ""), now),
            )
        for code, row in existing.items():
            if row["manual"] and code not in wanted:
                conn.execute("DELETE FROM frs WHERE id=?", (row["id"],))

        line_ids = {r["path"]: r["id"] for r in conn.execute("SELECT id, path FROM line WHERE project_id=?", (project["id"],))}
        frs_lines = pmeta.get("frs_lines", {}) if isinstance(pmeta.get("frs_lines"), dict) else {}
        for row in conn.execute("SELECT id, code FROM frs WHERE project_id=?", (project["id"],)).fetchall():
            paths = frs_lines.get(row["code"], [])
            paths = paths if isinstance(paths, list) else []
            want = {line_ids[p] for p in paths if p in line_ids}
            stale_lines += [{"project": project["name"], "frs": row["code"], "line": p} for p in paths if p not in line_ids]
            have = {r["line_id"] for r in conn.execute("SELECT line_id FROM frs_line WHERE frs_id=? AND source='manual'", (row["id"],))}
            for line_id in have - want:
                conn.execute("DELETE FROM frs_line WHERE frs_id=? AND line_id=? AND source='manual'", (row["id"], line_id))
            for line_id in want - have:
                conn.execute("INSERT OR IGNORE INTO frs_line(frs_id, line_id, source) VALUES(?,?, 'manual')", (row["id"], line_id))
    conn.commit()
    return {"stale_lines": stale_lines}
