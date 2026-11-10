"""Quét thư mục database (theo folder dự án) và dựng chỉ mục SQLite, có quét gia tăng.

Cấu trúc thư mục (D12):
    <root>/<Dự án>/<Line>/<Line con>/FRS3B.1.11.0.xlsx
Mỗi FRS chỉ giữ file có số V cao nhất (D1); số V đọc từ trong file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    __package__ = "_func"

from . import db
from .normalize import FRS_CODE_RE, norm_text
from .parse_file import parse_file
from .xlsx_util import issue

EXTENSIONS = (".xlsx", ".xlsm")
SKIP_DIR_PREFIXES = (".", "_", "~")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _sha1(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def list_projects(root: Path) -> list[Path]:
    return sorted(p for p in root.iterdir() if p.is_dir() and not p.name.startswith(SKIP_DIR_PREFIXES))


def list_bom_files(project_dir: Path) -> list[Path]:
    out = []
    for path in sorted(project_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in EXTENSIONS:
            continue
        if path.name.startswith("~$"):  # file tạm của Excel khi đang mở
            continue
        rel = path.relative_to(project_dir)
        if any(part.startswith(SKIP_DIR_PREFIXES) for part in rel.parts[:-1]):
            continue
        out.append(path)
    return out


def _key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def filename_line_hint(stem: str, project: str) -> str:
    """Phần tên file đứng trước mã FRS, bỏ tên dự án: 'VF3_FACELIFT_VN_FRS3B...' -> 'FACELIFT VN'."""
    m = FRS_CODE_RE.search(stem)
    head = stem[: m.start()] if m else stem
    head = re.sub(r"FRS\s*$", "", head, flags=re.IGNORECASE)
    tokens = [t for t in re.split(r"[_\s]+", head) if t and _key(t) != _key(project)]
    return " ".join(tokens)


def infer_line(rel_path: Path, project: str) -> tuple[list[str], str]:
    """Line từ folder và từ tên file. Trả (segments, ghi chú mâu thuẫn nếu có)."""
    segments = list(rel_path.parts[:-1])
    hint = filename_line_hint(rel_path.stem, project)
    if not segments:
        return ([hint] if hint else []), ""
    if hint and _key(hint) not in _key("".join(segments)) and _key(segments[-1]) not in _key(hint):
        return segments, f"Line theo folder ('{'/'.join(segments)}') khác gợi ý từ tên file ('{hint}'); đang dùng folder"
    return segments, ""


def _link_lines(conn, project_id: int, frs_id: int, group: list, winner, project: str) -> None:
    """Gán FRS vào line theo folder. Cùng một FRS (cùng số V) đặt ở nhiều folder line
    thì thuộc tất cả các line đó (D4). Liên kết gán tay không bị đụng tới."""
    conn.execute("DELETE FROM frs_line WHERE frs_id=? AND source='auto'", (frs_id,))
    for f in group:
        if f["version"] != winner["version"]:
            continue
        segments, _ = infer_line(Path(f["rel_path"]), project)
        line_id = db.ensure_line(conn, project_id, segments)
        if line_id is not None:
            conn.execute("INSERT OR IGNORE INTO frs_line(frs_id, line_id, source) VALUES(?,?, 'auto')", (frs_id, line_id))


def scan_project(conn, project_dir: Path, name: str | None = None, force: bool = False, progress=None) -> dict:
    project_dir = Path(project_dir)
    name = name or project_dir.name
    now = _now()
    report = {"project": name, "files": 0, "parsed": 0, "unchanged": 0, "not_bom": [], "errors": [], "ignored": [], "imported": [], "removed": [], "line_conflicts": []}
    project_id = db.upsert_project(conn, name, str(project_dir))
    existing = {r["rel_path"]: r for r in conn.execute("SELECT * FROM file WHERE project_id=?", (project_id,))}
    parsed_cache: dict[int, dict] = {}
    seen: set[str] = set()

    paths = list_bom_files(project_dir)
    for n, path in enumerate(paths, 1):
        rel = path.relative_to(project_dir).as_posix()
        seen.add(rel)
        report["files"] += 1
        if progress:
            progress(name, n, len(paths), rel)
        st = path.stat()
        row = existing.get(rel)
        if row is not None and not force and row["mtime"] == st.st_mtime and row["size"] == st.st_size:
            report["unchanged"] += 1
            continue
        sha1 = _sha1(path)
        if row is not None and not force and row["sha1"] == sha1:
            # OneDrive đổi mtime nhưng nội dung không đổi: không parse lại
            conn.execute("UPDATE file SET mtime=?, size=? WHERE id=?", (st.st_mtime, st.st_size, row["id"]))
            report["unchanged"] += 1
            continue

        status, note, frs_code, version, parsed, issues = "ok", "", None, None, None, []
        try:
            parsed = parse_file(path)
            issues = parsed["issues"]
            if not parsed["ok"] or not parsed["frs"]:
                status = "not_bom"
                note = "; ".join(i["message"] for i in issues if i["severity"] == "error") or "Không phải file BOM theo template"
                parsed = None
            else:
                frs_code, version = parsed["frs"]["code"], parsed["version"]
        except Exception as exc:  # file hỏng, bị khóa, sai định dạng
            status, note = "error", f"{type(exc).__name__}: {exc}"
            issues = [issue("error", "read_error", "", "", note)]
        report["parsed"] += 1
        if status == "not_bom":
            report["not_bom"].append({"file": rel, "note": note})
        elif status == "error":
            report["errors"].append({"file": rel, "note": note})

        conn.execute(
            """INSERT INTO file(project_id, rel_path, mtime, size, sha1, status, frs_code, version, is_active, note, parsed_at)
               VALUES(?,?,?,?,?,?,?,?,0,?,?)
               ON CONFLICT(project_id, rel_path) DO UPDATE SET mtime=excluded.mtime, size=excluded.size, sha1=excluded.sha1,
                   status=excluded.status, frs_code=excluded.frs_code, version=excluded.version, note=excluded.note, parsed_at=excluded.parsed_at""",
            (project_id, rel, st.st_mtime, st.st_size, sha1, status, frs_code, version, note, now),
        )
        file_id = conn.execute("SELECT id FROM file WHERE project_id=? AND rel_path=?", (project_id, rel)).fetchone()["id"]
        if status == "ok":
            segments, conflict = infer_line(Path(rel), name)
            if conflict:
                issues = issues + [issue("info", "line_conflict", "", "", conflict)]
                report["line_conflicts"].append({"file": rel, "note": conflict})
            parsed_cache[file_id] = parsed
        db.store_issues(conn, file_id, issues)

    # File đã bị xóa khỏi thư mục
    for rel, row in existing.items():
        if rel not in seen:
            conn.execute("DELETE FROM file WHERE id=?", (row["id"],))

    # Chọn TPV cuối cho mỗi FRS: V lớn nhất, bằng nhau thì file sửa gần nhất (D1)
    files = conn.execute("SELECT * FROM file WHERE project_id=? AND status='ok'", (project_id,)).fetchall()
    groups: dict[str, list] = {}
    for f in files:
        groups.setdefault(f["frs_code"], []).append(f)

    for code, group in sorted(groups.items()):
        group.sort(key=lambda f: (f["version"] if f["version"] is not None else -1, f["mtime"]), reverse=True)
        winner = group[0]
        for loser in group[1:]:
            same = loser["version"] == winner["version"]
            note = (f"Bỏ qua: cùng V{winner['version']} nhưng cũ hơn {winner['rel_path']}" if same
                    else f"Bỏ qua: V{loser['version']} thấp hơn V{winner['version']} của {winner['rel_path']}")
            conn.execute("UPDATE file SET is_active=0, note=? WHERE id=?", (note, loser["id"]))
            report["ignored"].append({"file": loser["rel_path"], "frs": code, "version": loser["version"], "note": note, "same_version": same})
        conn.execute("UPDATE file SET is_active=1, note='' WHERE id=?", (winner["id"],))

        current = conn.execute("SELECT * FROM frs WHERE project_id=? AND code=?", (project_id, code)).fetchone()
        if current is not None and current["file_id"] == winner["id"] and winner["id"] not in parsed_cache:
            _link_lines(conn, project_id, current["id"], group, winner, name)
            continue  # không đổi
        parsed = parsed_cache.get(winner["id"]) or parse_file(project_dir / winner["rel_path"])
        old_parts = db.part_set(conn, current["id"]) if current is not None else None
        old_file = None
        if current is not None and current["file_id"] is not None:
            r = conn.execute("SELECT rel_path FROM file WHERE id=?", (current["file_id"],)).fetchone()
            old_file = r["rel_path"] if r else None
        frs_id = db.store_frs(conn, project_id, winner["id"], parsed, now)
        segments, _ = infer_line(Path(winner["rel_path"]), name)
        _link_lines(conn, project_id, frs_id, group, winner, name)
        diff = db.diff_parts(old_parts, db.parsed_part_set(parsed)) if old_parts is not None else {}
        action = "new" if current is None else "updated"
        conn.execute(
            "INSERT INTO import_log(at, project, frs_code, action, old_version, new_version, old_file, new_file, diff) VALUES(?,?,?,?,?,?,?,?,?)",
            (now, name, code, action, current["version"] if current is not None else None, parsed["version"], old_file, winner["rel_path"], json.dumps(diff, ensure_ascii=False)),
        )
        report["imported"].append({"frs": code, "version": parsed["version"], "file": winner["rel_path"], "action": action, "line": "/".join(segments), "diff": diff})

    # FRS không còn file nào
    for row in conn.execute("SELECT id, code, version FROM frs WHERE project_id=?", (project_id,)).fetchall():
        if row["code"] not in groups:
            db.delete_frs(conn, row["id"])
            conn.execute("INSERT INTO import_log(at, project, frs_code, action, old_version) VALUES(?,?,?, 'removed', ?)", (now, name, row["code"], row["version"]))
            report["removed"].append({"frs": row["code"], "version": row["version"]})

    # Mỗi folder con là một line, kể cả folder chưa có file (line vừa tạo, FR-03)
    folders = set()
    for d in sorted(project_dir.rglob("*")):
        if d.is_dir():
            rel_parts = d.relative_to(project_dir).parts
            if not any(part.startswith(SKIP_DIR_PREFIXES) for part in rel_parts):
                folders.add("/".join(rel_parts))
                db.ensure_line(conn, project_id, list(rel_parts))
    # Dọn line tự tạo: không còn folder, không còn FRS và không còn line con
    while True:
        stale = [r["id"] for r in conn.execute(
            """SELECT id, path FROM line WHERE project_id=? AND source='auto'
                  AND id NOT IN (SELECT line_id FROM frs_line)
                  AND id NOT IN (SELECT parent_id FROM line WHERE parent_id IS NOT NULL)""",
            (project_id,),
        ) if r["path"] not in folders]
        if not stale:
            break
        conn.executemany("DELETE FROM line WHERE id=?", [(i,) for i in stale])
    conn.commit()
    return report


def scan_database(conn, root, force: bool = False, progress=None, single_project: str | None = None) -> dict:
    """Quét cả thư mục database. single_project: coi `root` là một dự án (thư mục phẳng)."""
    root = Path(root)
    started = time.time()
    if single_project:
        reports = [scan_project(conn, root, single_project, force, progress)]
    else:
        reports = [scan_project(conn, p, None, force, progress) for p in list_projects(root)]
        names = {r["project"] for r in reports}
        for row in conn.execute("SELECT id, name FROM project").fetchall():
            if row["name"] not in names:  # folder dự án đã bị xóa
                conn.execute("DELETE FROM project WHERE id=?", (row["id"],))
        conn.commit()
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('last_scan', ?)", (_now(),))
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES('last_root', ?)", (str(root),))
    conn.commit()
    return {"root": str(root), "seconds": round(time.time() - started, 2), "projects": reports, "counts": db.counts(conn)}


def format_report(report: dict) -> str:
    lines = [f"Thư mục: {report['root']}  ({report['seconds']} giây)"]
    for p in report["projects"]:
        lines.append(f"Dự án {p['project']}: {p['files']} file, parse {p['parsed']}, không đổi {p['unchanged']}")
        for i in p["imported"]:
            tag = "MỚI" if i["action"] == "new" else "CẬP NHẬT"
            lines.append(f"  {tag:<9} FRS {i['frs']} V{i['version']}  line: {i['line'] or '(chưa có)'}  <- {i['file']}")
            d = i["diff"]
            if d and (d["added"] or d["removed"]):
                for x in d["removed"]:
                    lines.append(f"      - {x['ecu']} [{x['variants']}] {x['pn_type']} {x['pn']}")
                for x in d["added"]:
                    lines.append(f"      + {x['ecu']} [{x['variants']}] {x['pn_type']} {x['pn']}")
        for i in p["ignored"]:
            lines.append(f"  BỎ QUA    {i['file']}: {i['note']}")
        for i in p["removed"]:
            lines.append(f"  ĐÃ XÓA    FRS {i['frs']} (không còn file)")
        for i in p["not_bom"]:
            lines.append(f"  KHÔNG PHẢI BOM  {i['file']}: {i['note']}")
        for i in p["errors"]:
            lines.append(f"  LỖI       {i['file']}: {i['note']}")
        for i in p["line_conflicts"]:
            lines.append(f"  LINE?     {i['file']}: {i['note']}")
    lines.append("Chỉ mục: " + ", ".join(f"{k}={v}" for k, v in report["counts"].items()))
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Quét thư mục database BOM và dựng chỉ mục SQLite")
    ap.add_argument("root", help="Thư mục database (mỗi folder con là một dự án)")
    ap.add_argument("--db", help=f"File chỉ mục SQLite (mặc định {db.default_db_path()})")
    ap.add_argument("--project", help="Coi thư mục này là MỘT dự án với tên đã cho")
    ap.add_argument("--force", action="store_true", help="Parse lại mọi file")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--where-used", metavar="PN", help="Sau khi quét, tra PN đang dùng ở đâu")
    ap.add_argument("--ticket", metavar="KEY", help="Sau khi quét, tra ticket thuộc FRS/ECU nào")
    args = ap.parse_args(argv)

    conn = db.open_db(args.db)
    progress = None if args.json else (lambda proj, n, total, rel: print(f"  [{proj}] {n}/{total} {rel}", file=sys.stderr))
    report = scan_database(conn, args.root, force=args.force, progress=progress, single_project=args.project)
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else format_report(report))
    if args.where_used:
        print(f"\nPN {args.where_used} đang dùng ở:")
        for r in db.where_used(conn, args.where_used):
            print(f"  {r['project']} | FRS {r['frs']} V{r['version']} | {r['ecu']} [{r['variants']}] | {r['pn_type']} {r['pn']} | {r['label']}")
    if args.ticket:
        print(f"\nTicket {args.ticket}:")
        for r in db.ticket_lookup(conn, args.ticket):
            print(f"  {r['project']} | FRS {r['frs']} TPV{r['tpv']} | {r['ecu_raw']} | {r['line'][:90]}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
