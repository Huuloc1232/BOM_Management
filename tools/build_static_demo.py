"""Dựng một file HTML độc lập (chỉ đọc) từ một chỉ mục đã quét, để xem thử giao diện không cần server.

    python tools/build_static_demo.py --db <index.db> --root <thư mục database> --out demo.html

Mọi phản hồi API được nhúng sẵn vào file. Tìm kiếm và kiểm tra COM_BOM chạy bằng JS trên dữ liệu nhúng.
Các thao tác ghi (thêm dự án, sửa cha, gán line, quét lại) bị tắt.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from _func import db, metadata  # noqa: E402
from feature import compare, compat_view, queries  # noqa: E402
from feature import tree as tree_view  # noqa: E402

DEMO_JS = r"""
(function () {
  const D = window.__DEMO__;
  const norm = (s) => String(s || "").replace(/\s+/g, "").toUpperCase();
  const frsDetails = Object.keys(D).filter((k) => /^\/api\/frs\/\d+$/.test(k)).map((k) => D[k]);
  function search(params) {
    const q = (params.get("q") || "").trim();
    const out = { q, frs: [], parts: [], ecus: [], tickets: [], truncated: false };
    if (!q) return out;
    const U = q.toUpperCase(), pn = norm(q), code = U.replace(/^FRS\s*/, "").replace(/\s+/g, "");
    const fVariant = params.get("variant"), fType = params.get("pn_type"), fEcu = params.get("ecu"), fProj = params.get("project");
    const isTicket = /^[A-Z][A-Z0-9]*-\d*$/.test(U);
    for (const d of frsDetails) {
      const f = d.frs;
      if (fProj && String(f.project_id) !== fProj) continue;
      if (/\d/.test(code) && code.includes(".") && f.code.includes(code)) out.frs.push({ id: f.id, project: f.project, code: f.code, version: f.version, side: f.side, lines: f.lines });
      const vname = Object.fromEntries(d.variants.map((v) => [v.id, v.label]));
      if (isTicket) {
        for (const c of d.changes) for (const t of c.tickets) if (t.key === U || t.key.startsWith(U))
          out.tickets.push({ key: t.key, url: t.url, project: f.project, frs_id: f.id, frs: f.code, tpv: c.tpv, ecu: c.ecu, ecu_raw: c.ecu_raw, line: (c.text.split("\n").find((l) => l.includes(t.key)) || "").trim() });
        continue;
      }
      for (const b of d.blocks) {
        const variants = b.variant_ids.map((v) => vname[v]).join(", ");
        if (fVariant && !variants.split(", ").includes(fVariant)) continue;
        if (fEcu && b.ecu !== fEcu) continue;
        const base = { project: f.project, frs_id: f.id, frs: f.code, version: f.version, lines: f.lines, block_id: b.id, ecu: b.ecu, label: b.label, purchase_pn: b.purchase_pn, variants };
        if (pn.length >= 3 && /^[0-9A-Z-]+$/.test(pn)) {
          for (const p of b.parts) if (p.pn.startsWith(pn) && (!fType || fType === p.pn_type)) out.parts.push({ ...base, pn_type: p.pn_type, pn: p.pn, did: p.did });
          if (b.purchase_pn.startsWith(pn) && (!fType || fType === "PU")) out.parts.push({ ...base, pn_type: "PU", pn: b.purchase_pn, did: "" });
        }
        if (/^[0-9A-Z_ ]{2,12}$/.test(U) && b.ecu.startsWith(U))
          out.ecus.push({ ...base, compat_status: b.compat_status, parts: b.parts.map((p) => p.pn_type + "=" + p.pn).join("  ") });
      }
    }
    return out;
  }
  function compatCheck(id, params) {
    const cv = D[`/api/frs/${id}/compat`];
    const g = cv && cv.groups.find((x) => x.name === params.get("group"));
    if (!g) throw new Error("ECU này không có trong COM_BOM của FRS");
    const hw = norm(params.get("hw")), sw = norm(params.get("sw"));
    const pairs = Object.keys(g.cells).map((k) => { const [h, s] = k.split("|"); return { hw_pn: h, sw_pn: s, bl_version: g.cells[k], pu_pn: "" }; });
    const matches = pairs.filter((p) => p.hw_pn === hw && p.sw_pn === sw);
    const swForHw = pairs.filter((p) => p.hw_pn === hw), hwForSw = pairs.filter((p) => p.sw_pn === sw);
    const status = matches.length ? "ok" : swForHw.length ? "sw_mismatch" : "hw_not_listed";
    const reason = { ok: "Tương thích: (HW, SW) có trong COM_BOM", sw_mismatch: "HW có trong COM_BOM nhưng đi với SW số khác", hw_not_listed: "HW PN không có trong COM_BOM" }[status];
    return { group: g.name, hw_pn: hw, sw_pn: sw, status, compatible: status === "ok", reason, matches, sw_for_hw: swForHw, hw_for_sw: hwForSw };
  }
  window.__demoApi = async function (path, body) {
    if (body !== undefined) throw new Error("Bản xem thử chỉ đọc: thao tác này chỉ chạy trên tool thật.");
    const [p, query = ""] = path.split("?");
    const params = new URLSearchParams(query);
    if (p === "/api/search") return search(params);
    let m = p.match(/^\/api\/frs\/(\d+)\/compat-check$/);
    if (m) return compatCheck(m[1], params);
    if (p === "/api/compare") {
      const hit = D[`/api/compare?a=${params.get("a")}&b=${params.get("b")}`];
      if (!hit) throw new Error("Không tìm thấy FRS");
      return hit;
    }
    if (!(p in D)) throw new Error("Không có trong bản xem thử: " + p);
    return JSON.parse(JSON.stringify(D[p]));
  };
})();
"""


def build(db_path: Path, root: Path) -> dict:
    conn = db.open_db(db_path)
    meta = metadata.load_metadata(root)
    data: dict[str, object] = {}
    state = queries.state(conn)
    state.update({"root": "(bản xem thử, dữ liệu nhúng sẵn)", "scanning": False, "filters": queries.filter_options(conn)})
    data["/api/state"] = state
    for p in state["projects"]:
        data[f"/api/project/{p['id']}"] = queries.project_detail(conn, p["id"])
        data[f"/api/project/{p['id']}/tree"] = tree_view.project_tree(conn, p["id"], meta)
    frs_ids = [r[0] for r in conn.execute("SELECT id FROM frs ORDER BY id")]
    for fid in frs_ids:
        data[f"/api/frs/{fid}"] = queries.frs_detail(conn, fid)
        data[f"/api/frs/{fid}/tickets"] = {"tickets": compare.frs_tickets(conn, fid)}
        data[f"/api/frs/{fid}/compat"] = compat_view.compat_view(conn, fid)
    listing = compare.frs_list(conn, meta)
    data["/api/frs-list"] = {"frs": listing}
    real = [f["id"] for f in listing]
    for a in real:
        for b in real:
            if a != b:
                data[f"/api/compare?a={a}&b={b}"] = compare.compare_frs(conn, a, b)
    conn.close()
    return data


def render(data: dict) -> str:
    src = ROOT / "src"
    html = (src / "index.html").read_text(encoding="utf-8")
    css = (src / "assets" / "app.css").read_text(encoding="utf-8")
    js = (src / "assets" / "app.js").read_text(encoding="utf-8")
    hook = "async function api(path, body) {"
    assert js.count(hook) == 1
    js = js.replace(hook, hook + "\n  if (window.__demoApi) return window.__demoApi(path, body);")
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    banner = ('<div class="notice" style="margin:12px 20px 0">Bản xem thử chỉ đọc. Dữ liệu là dữ liệu thử dựng từ sample.xlsx. '
              'Thêm dự án, tạo FRS, gán line, đổi FRS cha và quét lại chỉ chạy trên tool thật.</div>')
    html = html.replace('<link rel="stylesheet" href="/assets/app.css">', f"<style>\n{css}\n</style>")
    html = html.replace('<div id="notice" class="notice" hidden></div>', banner + '\n<div id="notice" class="notice" hidden></div>')
    script = f"<script>window.__DEMO__={payload};</script>\n<script>{DEMO_JS}</script>\n<script>\n{js.replace('</script', '<\\/script')}\n</script>"
    assert html.count('<script src="/assets/app.js"></script>') == 1
    html = html.replace('<script src="/assets/app.js"></script>', script)
    return html.replace("<title>BOM Management</title>", "<title>BOM Management (bản xem thử)</title>")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", required=True)
    ap.add_argument("--root", required=True, help="Thư mục database (để đọc metadata.json)")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    data = build(Path(args.db), Path(args.root))
    out = Path(args.out)
    out.write_text(render(data), encoding="utf-8")
    print(f"{out}  {out.stat().st_size / 1e6:.1f} MB, {len(data)} phản hồi API")
    return 0


if __name__ == "__main__":
    sys.exit(main())
