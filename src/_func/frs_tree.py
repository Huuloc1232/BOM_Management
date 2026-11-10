"""Suy ra cây cha-con giữa các FRS từ mã FRS (D2, D18, FR-35, FR-36)."""
from __future__ import annotations

from .normalize import parse_frs_code


def rule_parent(code: str) -> str | None:
    """Cha theo quy tắc: minor > 0 -> minor - 1; minor = 0 -> (major - 1).0; hết thì là gốc."""
    frs = parse_frs_code(code)
    if frs is None:
        return None
    family, seg, major, minor = frs["family"], frs["seg"], frs["major"], frs["minor"]
    if minor > 0:
        return f"{family}.{seg}.{major}.{minor - 1}"
    if major > 0:
        return f"{family}.{seg}.{major - 1}.0"
    return None


def sort_key(code: str):
    frs = parse_frs_code(code)
    if frs is None:
        return ("", 0, 0, 0, code)
    return (frs["family"], frs["seg"], frs["major"], frs["minor"], "")


def build_tree(codes: list[str], manual: dict[str, str | None] | None = None) -> dict:
    """Dựng cây cho tập mã FRS có sẵn.

    manual: {child: parent hoặc None (ép làm gốc)}; luôn thắng quy tắc tự động.
    FRS cha theo quy tắc không có trong dữ liệu thì nối lên tổ tiên gần nhất có sẵn;
    không còn tổ tiên nào thì là gốc cây.
    """
    manual = manual or {}
    known = {parse_frs_code(c)["code"] for c in codes if parse_frs_code(c)}
    nodes = {}
    for code in sorted(known, key=sort_key):
        if code in manual:
            parent = manual[code]
            nodes[code] = {"code": code, "parent": parent, "source": "manual", "skipped": [], "children": []}
            continue
        skipped = []
        parent = rule_parent(code)
        while parent is not None and parent not in known:
            skipped.append(parent)
            parent = rule_parent(parent)
        if parent is None:
            skipped = []  # không có tổ tiên nào: gốc cây, không coi là thiếu
        nodes[code] = {"code": code, "parent": parent, "source": "auto", "skipped": skipped, "children": []}
    for code, node in nodes.items():
        parent = node["parent"]
        if parent in nodes:
            nodes[parent]["children"].append(code)
    for node in nodes.values():
        node["children"].sort(key=sort_key)
    roots = sorted([c for c, n in nodes.items() if n["parent"] not in nodes], key=sort_key)
    return {"nodes": nodes, "roots": roots}


def path_to_root(tree: dict, code: str) -> list[str]:
    path, seen = [], set()
    while code in tree["nodes"] and code not in seen:
        seen.add(code)
        path.append(code)
        code = tree["nodes"][code]["parent"]
    return list(reversed(path))
