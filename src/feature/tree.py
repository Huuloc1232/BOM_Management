"""Sơ đồ cây FRS của một dự án: quan hệ cha-con, bố cục, gợi ý carry-over, sửa tay (FR-34..FR-38)."""
from __future__ import annotations

import json

from _func.frs_tree import build_tree, sort_key
from _func.metadata import load_metadata, manual_parents, metadata_path, save_metadata  # noqa: F401
from _func.normalize import parse_frs_code

SEG_LABELS = {1: "LHD", 6: "RHD"}  # D3; segment khác hiển thị số thô (D18)


# metadata do người dùng nhập nằm ở _func/metadata.py (dùng chung với scanner)


def set_manual_parent(root, project: str, known_codes: list[str], code: str, parent) -> dict:
    """parent: mã FRS cha, None (ép làm gốc cây) hoặc 'auto' (bỏ sửa tay, quay về quy tắc)."""
    if code not in known_codes:
        raise ValueError(f"Không có FRS {code} trong dự án")
    meta = load_metadata(root)
    proj = meta["projects"].setdefault(project, {})
    if not isinstance(proj.get("frs_parent"), dict):
        proj["frs_parent"] = {}
    table = proj["frs_parent"]
    if parent == "auto":
        table.pop(code, None)
    else:
        if parent is not None:
            if parent not in known_codes:
                raise ValueError(f"Không có FRS {parent} trong dự án")
            if parent == code:
                raise ValueError("FRS không thể là cha của chính nó")
            trial = dict(table)
            trial[code] = parent
            tree = build_tree(known_codes, trial)
            seen, cur = {code}, parent
            while cur in tree["nodes"]:   # đi ngược lên tổ tiên, gặp lại `code` là vòng lặp
                if cur in seen:
                    raise ValueError(f"FRS {parent} đang là con cháu của {code}, không thể làm cha")
                seen.add(cur)
                cur = tree["nodes"][cur]["parent"]
        table[code] = parent
    save_metadata(root, meta)
    return table


# ---------- bố cục ----------

def _main_first(codes: list[str]) -> list[str]:
    """Con thuộc nhánh chính (minor = 0, tức major kế tiếp) đứng đầu để nằm cùng hàng với cha."""
    def key(code):
        frs = parse_frs_code(code)
        return (0 if frs and frs["minor"] == 0 else 1,) + sort_key(code)
    return sorted(codes, key=key)


def layout(tree: dict) -> tuple[dict, list[dict]]:
    """Gán (col, row) cho từng nút: nhánh chính đi ngang, nhánh phụ rẽ xuống hàng dưới."""
    pos: dict[str, tuple[int, int]] = {}
    trees = []
    offset = 0
    for root in tree["roots"]:
        max_row, max_col = offset, 0
        pos[root] = (0, offset)
        # DFS dùng stack (không đệ quy) để cây rất dài không chạm giới hạn đệ quy.
        # Mỗi phần tử: [mã, danh sách con, chỉ số con kế tiếp, hàng lớn nhất đã dùng trong cây con]
        stack = [[root, _main_first(tree["nodes"][root]["children"]), 0, offset]]
        while stack:
            frame = stack[-1]
            code, children, i, used = frame
            if i < len(children):
                frame[2] += 1
                col, row = pos[code][0] + 1, (pos[code][1] if i == 0 else used + 1)
                child = children[i]
                pos[child] = (col, row)
                max_row, max_col = max(max_row, row), max(max_col, col)
                stack.append([child, _main_first(tree["nodes"][child]["children"]), 0, row])
            else:
                stack.pop()
                if stack:
                    stack[-1][3] = max(stack[-1][3], used)
        frs = parse_frs_code(root)
        seg = frs["seg"]
        trees.append({
            "root": root, "family": frs["family"], "seg": seg,
            "key": f"{frs['family']}.{seg}",
            "label": f"{frs['family']}.{seg}" + (f" ({SEG_LABELS[seg]})" if seg in SEG_LABELS else ""),
            "row_start": offset, "rows": max_row - offset + 1, "cols": max_col + 1,
        })
        offset = max_row + 1
    return pos, trees


def _ancestors(tree: dict, code: str) -> list[str]:
    out, seen = [], {code}
    cur = tree["nodes"][code]["parent"]
    while cur in tree["nodes"] and cur not in seen:
        out.append(cur)
        seen.add(cur)
        cur = tree["nodes"][cur]["parent"]
    return out


def project_tree(conn, project_id: int, meta: dict | None = None) -> dict | None:
    project = conn.execute("SELECT id, name FROM project WHERE id=?", (project_id,)).fetchone()
    if project is None:
        return None
    rows = [dict(r) for r in conn.execute(
        """SELECT f.id, f.code, f.family, f.seg, f.major, f.minor, f.version, f.side, f.manual,
                  (SELECT group_concat(path, ', ') FROM (SELECT l.path FROM frs_line fl JOIN line l ON l.id=fl.line_id
                    WHERE fl.frs_id=f.id ORDER BY l.path COLLATE NOCASE)) AS lines,
                  (SELECT COUNT(*) FROM quality_issue q WHERE q.file_id=f.file_id AND q.severity IN ('warning','error')) AS warning_count
             FROM frs f WHERE f.project_id=?""", (project_id,))]
    by_code = {r["code"]: r for r in rows}
    manual = {c: p for c, p in manual_parents(meta or {}, project["name"]).items() if c in by_code}
    # cha gán tay trỏ tới FRS đã bị xóa khỏi chỉ mục: quay về quy tắc tự động
    stale = [c for c, p in manual.items() if p is not None and p not in by_code]
    for c in stale:
        manual.pop(c)
    tree = build_tree(list(by_code), manual)
    pos, trees = layout(tree)

    carry: dict[int, list[str]] = {}
    for r in conn.execute("SELECT frs_id, line, frs_codes FROM carry_note WHERE frs_id IN (SELECT id FROM frs WHERE project_id=?)", (project_id,)):
        for code in json.loads(r["frs_codes"]):
            lst = carry.setdefault(r["frs_id"], [])
            if code not in lst:
                lst.append(code)

    families = {r["family"] for r in rows}
    nodes = []
    for code in sorted(by_code, key=sort_key):
        r, n = by_code[code], tree["nodes"][code]
        ancestors = _ancestors(tree, code)
        hints = []
        for other in carry.get(r["id"], []):
            if other == code:
                continue
            o = parse_frs_code(other)
            if other in ancestors:
                rel = "ancestor"          # khớp với cây
            elif other not in by_code:
                # mã của dòng xe khác (vd 5C... của VF5 trong tiêu đề ticket) hay FRS chưa có file
                rel = "not_indexed" if o["family"] in families else "other_project"
            elif o["family"] != r["family"] or o["seg"] != r["seg"]:
                rel = "other_segment"     # carry-across từ dòng/segment khác
            else:
                rel = "other_branch"      # carry-across từ nhánh khác cùng dòng (bình thường, không phải lỗi)
            hints.append({"code": other, "id": by_code[other]["id"] if other in by_code else None, "relation": rel})
        nodes.append({
            "id": r["id"], "code": code, "version": r["version"], "side": r["side"], "no_bom": bool(r["manual"]),
            "family": r["family"], "seg": r["seg"], "lines": r["lines"] or "", "warning_count": r["warning_count"],
            "parent_code": n["parent"] if n["parent"] in by_code else None,
            "parent_id": by_code[n["parent"]]["id"] if n["parent"] in by_code else None,
            "source": n["source"], "skipped": n["skipped"],
            "col": pos[code][0], "row": pos[code][1],
            "children": n["children"], "carry": hints,
        })
    return {"project": dict(project), "nodes": nodes, "trees": trees,
            "rows": sum(t["rows"] for t in trees), "cols": max((t["cols"] for t in trees), default=0),
            "manual_count": len(manual), "stale_manual": stale}
