"use strict";
// BOM Management - giao diện (JS thuần, không thư viện ngoài).

const view = document.getElementById("view");
const notice = document.getElementById("notice");
const searchInput = document.getElementById("search-input");
let appState = { projects: [], root: "", filters: { variants: [], pn_types: [], ecus: [] } };

const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const enc = encodeURIComponent;
const pnLink = (pn) => (pn ? `<a class="mono" href="#/search?q=${enc(pn)}" title="Tìm nơi dùng PN này">${esc(pn)}</a>` : "");
const chips = (text, cls = "") => String(text || "").split(",").map((s) => s.trim()).filter(Boolean).map((s) => `<span class="chip ${cls}">${esc(s)}</span>`).join("");

async function api(path, body) {
  const opt = body === undefined ? {} : { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) };
  const res = await fetch(path, opt);
  let data = {};
  try { data = await res.json(); } catch (e) { /* phản hồi không phải JSON */ }
  if (!res.ok) throw new Error(data.error || `Lỗi ${res.status}`);
  return data;
}

function showNotice(text, kind = "") {
  notice.textContent = text;
  notice.className = "notice " + kind;
  notice.hidden = !text;
}

function scanSummary(report) {
  const parts = [];
  for (const p of report.projects || []) {
    const bits = [`${p.files} file`];
    if (p.imported.length) bits.push(`${p.imported.length} FRS mới/cập nhật`);
    if (p.ignored.length) bits.push(`${p.ignored.length} bỏ qua`);
    if (p.not_bom.length) bits.push(`${p.not_bom.length} không phải BOM`);
    if (p.errors.length) bits.push(`${p.errors.length} lỗi`);
    parts.push(`${p.project}: ${bits.join(", ")}`);
  }
  return `Đã quét trong ${report.seconds} giây. ` + (parts.join(" | ") || "Không có dự án nào.");
}

async function loadState() {
  appState = await api("/api/state");
  return appState;
}

// ---------- định tuyến ----------
function parseHash() {
  const raw = location.hash.replace(/^#/, "") || "/";
  const [path, query = ""] = raw.split("?");
  return { parts: path.split("/").filter(Boolean), params: Object.fromEntries(new URLSearchParams(query)) };
}

async function route() {
  const { parts, params } = parseHash();
  try {
    if (parts[0] === "project" && parts[1]) await renderProject(Number(parts[1]), params);
    else if (parts[0] === "frs" && parts[1]) await renderFrs(Number(parts[1]), params);
    else if (parts[0] === "search") await renderSearch(params);
    else if (parts[0] === "compare") await renderCompare(params);
    else await renderDashboard();
  } catch (e) {
    view.innerHTML = `<div class="empty">Không tải được dữ liệu: ${esc(e.message)}</div>`;
  }
  view.focus({ preventScroll: true });
}

// ---------- dashboard ----------
async function renderDashboard() {
  const s = await loadState();
  searchInput.value = "";
  if (!s.root) {
    view.innerHTML = `<div class="empty"><h1>Chưa chọn thư mục database</h1>
      <p>Chọn thư mục chứa các folder dự án (VF3, ECVan...) để bắt đầu.</p>
      <button type="button" id="pick-root">Chọn thư mục database</button></div>`;
    document.getElementById("pick-root").onclick = openSettings;
    return;
  }
  const cards = s.projects.map((p) => `
    <a class="card" href="#/project/${p.id}">
      <h3>${esc(p.name)}</h3>
      <div class="stats"><span><b>${p.frs_count}</b> FRS</span><span><b>${p.line_count}</b> line</span><span><b>${p.ecu_count}</b> ECU</span></div>
      ${p.warning_count ? `<div style="margin-top:8px"><span class="chip warn">${p.warning_count} cảnh báo</span></div>` : ""}
    </a>`).join("");
  view.innerHTML = `
    <div class="head">
      <div><h1>Dự án</h1><div class="muted">Thư mục: <span class="mono">${esc(s.root)}</span>${s.last_scan ? ` · quét lần cuối ${esc(s.last_scan.replace("T", " "))}` : ""}</div></div>
    </div>
    <div class="cards">${cards}
      <form class="card add" id="add-project">
        <h3>Thêm dự án</h3>
        <input type="text" name="name" placeholder="Tên dự án, vd ECVan" required aria-label="Tên dự án mới">
        <div style="margin-top:8px"><button type="submit">Tạo folder dự án</button></div>
      </form>
    </div>
    ${s.projects.length ? "" : `<p class="muted" style="margin-top:14px">Chưa có dự án nào. Mỗi folder con trong thư mục database là một dự án.</p>`}`;
  document.getElementById("add-project").onsubmit = async (ev) => {
    ev.preventDefault();
    try {
      await api("/api/projects", { name: ev.target.name.value });
      showNotice(`Đã tạo dự án ${ev.target.name.value}.`, "ok");
      renderDashboard();
    } catch (e) { showNotice(e.message, "error"); }
  };
}

// ---------- trang dự án ----------
function lineTree(lines, projectId, selected) {
  const kids = (pid) => lines.filter((l) => l.parent_id === pid);
  const build = (pid) => {
    const items = kids(pid);
    if (!items.length) return "";
    return `<ul>${items.map((l) => `<li><a href="#/project/${projectId}?line=${l.id}" class="${selected === l.id ? "active" : ""}">
      <span>${esc(l.name)}</span><span class="count">${l.total}</span></a>${build(l.id)}</li>`).join("")}</ul>`;
  };
  return build(null).replace(/^<ul>/, '<ul class="tree">');
}

const projectTabs = (id, cur) => `<div class="tabs" role="tablist">
  <button type="button" role="tab" class="${cur === "list" ? "on" : ""}" aria-selected="${cur === "list"}" onclick="location.hash='#/project/${id}'">Danh sách FRS</button>
  <button type="button" role="tab" class="${cur === "tree" ? "on" : ""}" aria-selected="${cur === "tree"}" onclick="location.hash='#/project/${id}?view=tree'">Sơ đồ cây FRS</button></div>`;

async function renderProject(id, params) {
  if (params.view === "tree") return renderProjectTree(id, params);
  const d = await api(`/api/project/${id}`);
  const selected = params.line ? Number(params.line) : null;
  const line = d.lines.find((l) => l.id === selected) || null;
  // line đang chọn gồm cả các line con
  const inLine = new Set();
  if (line) d.lines.filter((l) => l.path === line.path || l.path.startsWith(line.path + "/")).forEach((l) => inLine.add(l.id));
  const frs = line ? d.frs.filter((f) => f.line_ids.some((x) => inLine.has(x))) : d.frs;
  // số FRS của mỗi line tính cả các line con
  for (const l of d.lines) {
    const ids = new Set(d.lines.filter((x) => x.path === l.path || x.path.startsWith(l.path + "/")).map((x) => x.id));
    l.total = d.frs.filter((f) => f.line_ids.some((x) => ids.has(x))).length;
  }
  const rows = frs.map((f) => `<tr>
      <td><a href="#/frs/${f.id}"><b>FRS ${esc(f.code)}</b></a></td>
      <td>${f.version == null ? "" : "V" + f.version}</td>
      <td>${esc(f.side)}</td>
      <td>${chips(f.lines) || '<span class="muted">chưa gán</span>'}</td>
      <td>${f.ecu_count} ECU / ${f.block_count} block</td>
      <td>${f.warning_count ? `<span class="chip warn">${f.warning_count} cảnh báo</span>` : '<span class="chip ok">OK</span>'}</td>
      <td class="mono muted">${esc(f.file)}</td></tr>`).join("");
  const others = d.other_files.map((f) => `<tr><td class="mono">${esc(f.rel_path)}</td>
      <td><span class="chip ${f.status === "error" ? "err" : ""}">${esc({ ok: "bỏ qua", not_bom: "không phải BOM", error: "lỗi" }[f.status] || f.status)}</span></td>
      <td>${esc(f.note)}</td></tr>`).join("");
  view.innerHTML = `
    <div class="crumbs"><a href="#/">Dự án</a> / ${esc(d.project.name)}${line ? " / " + esc(line.path) : ""}</div>
    <div class="head"><h1>${esc(d.project.name)}${line ? ` <span class="muted">· ${esc(line.path)}</span>` : ""}</h1></div>
    ${projectTabs(id, "list")}
    <div class="split">
      <aside class="panel">
        <h2>Line xe</h2>
        <ul class="tree"><li><a href="#/project/${id}" class="${line ? "" : "active"}"><span>Tất cả</span><span class="count">${d.frs.length}</span></a></li></ul>
        ${lineTree(d.lines, id, selected) || '<p class="muted">Chưa có line.</p>'}
        <form id="add-line" style="margin-top:12px">
          <input type="text" name="name" required placeholder="${line ? "Line con của " + esc(line.name) : "Tên line mới"}" aria-label="Tên line mới">
          <div style="margin-top:6px"><button type="submit" class="small">Thêm ${line ? "line con" : "line"}</button></div>
        </form>
      </aside>
      <div>
        <div class="table-wrap"><table>
          <thead><tr><th>FRS</th><th>TPV</th><th>Tay lái</th><th>Line</th><th>ECU</th><th>Dữ liệu</th><th>File</th></tr></thead>
          <tbody>${rows || `<tr><td colspan="7" class="empty">Chưa có FRS${line ? " trong line này" : ""}. Đặt file <span class="mono">FRS&lt;mã&gt;.xlsx</span> vào folder rồi quét lại.</td></tr>`}</tbody>
        </table></div>
        ${others ? `<section><h2>File không được dùng</h2><div class="table-wrap"><table>
          <thead><tr><th>File</th><th>Trạng thái</th><th>Ghi chú</th></tr></thead><tbody>${others}</tbody></table></div></section>` : ""}
      </div>
    </div>`;
  document.getElementById("add-line").onsubmit = async (ev) => {
    ev.preventDefault();
    try {
      await api("/api/lines", { project_id: id, parent_path: line ? line.path : "", name: ev.target.name.value });
      showNotice(`Đã tạo line ${ev.target.name.value}.`, "ok");
      renderProject(id, params);
    } catch (e) { showNotice(e.message, "error"); }
  };
}

// ---------- sơ đồ cây FRS ----------
const TREE = { cw: 196, ch: 74, nw: 164, nh: 50, pad: 16, gap: 30 };
const CARRY_TEXT = { ancestor: "tổ tiên trong cây", other_branch: "nhánh khác", other_segment: "dòng/segment khác", not_indexed: "chưa có file", other_project: "dòng xe khác" };
const treeState = { hidden: new Set(), zoom: 1, carry: false, selected: null };

async function renderProjectTree(id, params) {
  let d = await api(`/api/project/${id}/tree`);
  if (treeState.projectId !== id) Object.assign(treeState, { projectId: id, hidden: new Set(), zoom: 1, carry: false, selected: params.frs || null });
  view.innerHTML = `
    <div class="crumbs"><a href="#/">Dự án</a> / <a href="#/project/${id}">${esc(d.project.name)}</a> / Sơ đồ cây FRS</div>
    <div class="head"><h1>${esc(d.project.name)}</h1></div>
    ${projectTabs(id, "tree")}
    <div id="tree-root"></div>`;
  const root = document.getElementById("tree-root");

  const draw = () => {
    if (!d.nodes.length) { root.innerHTML = '<div class="empty">Dự án chưa có FRS nào.</div>'; return; }
    const keys = [...new Set(d.trees.map((t) => t.key))];
    const labelOf = Object.fromEntries(d.trees.map((t) => [t.key, t.label]));
    const visible = d.trees.filter((t) => !treeState.hidden.has(t.key));
    // dồn các cây đang hiện lên trên, mỗi cây có một dòng tiêu đề
    const yOf = {};
    let y = TREE.pad, cols = 1;
    const titles = [];
    for (const t of visible) {
      titles.push({ y: y + 14, text: `${t.label} · gốc FRS ${t.root}` });
      y += TREE.gap;
      for (let r = 0; r < t.rows; r++) yOf[t.row_start + r] = y + r * TREE.ch;
      y += t.rows * TREE.ch;
      cols = Math.max(cols, t.cols);
    }
    const W = TREE.pad * 2 + cols * TREE.cw - (TREE.cw - TREE.nw), H = y + TREE.pad;
    const shown = d.nodes.filter((n) => n.row in yOf);
    const at = Object.fromEntries(shown.map((n) => [n.code, { x: TREE.pad + n.col * TREE.cw, y: yOf[n.row] }]));
    const edges = shown.filter((n) => n.parent_code && at[n.parent_code]).map((n) => {
      const a = at[n.parent_code], b = at[n.code];
      const x1 = a.x + TREE.nw, y1 = a.y + TREE.nh / 2, x2 = b.x, y2 = b.y + TREE.nh / 2, mx = x1 + (TREE.cw - TREE.nw) / 2;
      const path = y1 === y2 ? `M${x1},${y1}H${x2}` : `M${x1},${y1}H${mx}V${y2}H${x2}`;
      const cls = `edge ${n.skipped.length ? "gap" : ""} ${n.source === "manual" ? "manual" : ""}`;
      return `<path class="${cls}" d="${path}">${n.skipped.length ? `<title>Chưa có file của FRS trung gian: ${esc(n.skipped.join(", "))}</title>` : ""}</path>`;
    }).join("");
    // liên kết carry-over: luôn vẽ cho FRS đang chọn; bật ô đánh dấu thì vẽ cho mọi FRS
    const carry = shown.filter((n) => treeState.carry || n.code === treeState.selected).flatMap((n) => n.carry.filter((h) => h.id && at[h.code] && h.relation !== "ancestor").map((h) => {
      const a = at[h.code], b = at[n.code];
      const x1 = a.x + TREE.nw / 2, y1 = a.y + TREE.nh, x2 = b.x + TREE.nw / 2, y2 = b.y + (b.y > a.y ? 0 : TREE.nh);
      return `<path class="carry" d="M${x1},${y1}C${x1},${y1 + 26} ${x2},${y2 + (b.y > a.y ? -26 : 26)} ${x2},${y2}"><title>Carry-over từ FRS ${esc(h.code)} sang FRS ${esc(n.code)}</title></path>`;
    })).join("");
    const nodes = shown.map((n) => {
      const p = at[n.code];
      const cls = ["node", n.source === "manual" ? "manual" : "", treeState.selected === n.code ? "selected" : ""].join(" ");
      const sub = [n.version == null ? "" : "V" + n.version, n.side, n.lines].filter(Boolean).join(" · ");
      return `<g class="${cls}" data-code="${esc(n.code)}" tabindex="0" role="button" aria-label="FRS ${esc(n.code)}${n.parent_code ? ", cha " + esc(n.parent_code) : ", gốc cây"}" transform="translate(${p.x},${p.y})">
        <rect width="${TREE.nw}" height="${TREE.nh}" rx="7"/>
        <text class="t1" x="10" y="20">FRS ${esc(n.code)}</text><text class="t2" x="10" y="38">${esc(sub.length > 24 ? sub.slice(0, 23) + "…" : sub)}</text>
        ${n.warning_count ? `<circle class="dot" cx="${TREE.nw - 12}" cy="13" r="5"><title>${n.warning_count} cảnh báo dữ liệu</title></circle>` : ""}
        ${n.source === "manual" ? `<text class="t3" x="${TREE.nw - 8}" y="42" text-anchor="end">sửa tay</text>` : ""}</g>`;
    }).join("");
    const sel = d.nodes.find((n) => n.code === treeState.selected);
    root.innerHTML = `
      <div class="toolbar">
        <span class="muted">Nhánh:</span>
        ${keys.map((k) => `<button type="button" class="chip ${treeState.hidden.has(k) ? "" : "on"}" data-key="${esc(k)}" aria-pressed="${!treeState.hidden.has(k)}">${esc(labelOf[k])}</button>`).join("")}
        <label class="check"><input type="checkbox" id="tree-carry" ${treeState.carry ? "checked" : ""}> Hiện mọi liên kết carry-over</label>
        <span style="flex:1"></span>
        <button type="button" class="ghost small" id="zoom-out" aria-label="Thu nhỏ">−</button>
        <span class="muted" id="zoom-label">${Math.round(treeState.zoom * 100)}%</span>
        <button type="button" class="ghost small" id="zoom-in" aria-label="Phóng to">+</button>
        <button type="button" class="ghost small" id="zoom-fit">Vừa khung</button>
      </div>
      <div class="tree-layout">
        <div class="tree-scroll" id="tree-scroll">${visible.length ? `<svg class="frs-tree" viewBox="0 0 ${W} ${H}" width="${Math.round(W * treeState.zoom)}" height="${Math.round(H * treeState.zoom)}" role="group" aria-label="Sơ đồ cây FRS">
          ${titles.map((t) => `<text class="tree-title" x="${TREE.pad}" y="${t.y}">${esc(t.text)}</text>`).join("")}
          ${edges}${carry}${nodes}</svg>` : '<div class="empty">Đã ẩn hết các nhánh.</div>'}</div>
        <aside class="panel" id="tree-panel">${sel ? nodePanel(sel) : '<p class="muted">Bấm vào một FRS để xem chi tiết và sửa FRS cha.</p>'}</aside>
      </div>
      <p class="muted" style="margin-top:10px">Cha được suy từ mã FRS: minor &gt; 0 thì cha là minor − 1, minor = 0 thì cha là major − 1. Đường nét đứt là có FRS trung gian chưa có file.
        Đường chấm cam là ghi chú carry-over từ nhánh khác (hiện khi chọn một FRS). Chấm cam ở góc là FRS có cảnh báo dữ liệu. ${d.manual_count ? d.manual_count + " quan hệ đã sửa tay." : ""}</p>`;

    root.querySelectorAll("[data-key]").forEach((b) => (b.onclick = () => { treeState.hidden.has(b.dataset.key) ? treeState.hidden.delete(b.dataset.key) : treeState.hidden.add(b.dataset.key); draw(); }));
    document.getElementById("tree-carry").onchange = (e) => { treeState.carry = e.target.checked; draw(); };
    const zoom = (z) => { treeState.zoom = Math.min(2, Math.max(0.4, Math.round(z * 100) / 100)); draw(); };
    document.getElementById("zoom-in").onclick = () => zoom(treeState.zoom + 0.2);
    document.getElementById("zoom-out").onclick = () => zoom(treeState.zoom - 0.2);
    document.getElementById("zoom-fit").onclick = () => zoom((document.getElementById("tree-scroll").clientWidth - 4) / W);
    root.querySelectorAll("g.node").forEach((g) => {
      const pick = () => { treeState.selected = g.dataset.code; draw(); const again = root.querySelector(`g.node[data-code="${CSS.escape(treeState.selected)}"]`); if (again) again.focus(); };
      g.onclick = pick;
      g.onkeydown = (ev) => { if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); pick(); } };
    });
    const form = document.getElementById("parent-form");
    if (form) form.onsubmit = async (ev) => {
      ev.preventDefault();
      const v = form.parent.value;
      try {
        d = await api("/api/tree/parent", { project_id: id, code: sel.code, parent: v === "auto" ? "auto" : v === "" ? null : v });
        showNotice(v === "auto" ? `FRS ${sel.code}: cha quay về quy tắc tự động.` : `Đã lưu FRS cha của ${sel.code}.`, "ok");
        draw();
      } catch (e) { showNotice(e.message, "error"); }
    };
  };

  const nodePanel = (n) => {
    const descendants = new Set();
    const walk = (c) => { for (const k of d.nodes.find((x) => x.code === c).children) { descendants.add(k); walk(k); } };
    walk(n.code);
    const cur = n.source === "manual" ? (n.parent_code || "") : "auto";
    const options = d.nodes.filter((x) => x.code !== n.code && !descendants.has(x.code))
      .map((x) => `<option value="${esc(x.code)}" ${cur === x.code ? "selected" : ""}>FRS ${esc(x.code)}</option>`).join("");
    return `<h2>FRS ${esc(n.code)} <span class="muted">${n.version == null ? "" : "V" + n.version} ${esc(n.side)}</span></h2>
      <p>Line: ${chips(n.lines) || '<span class="muted">chưa gán</span>'}</p>
      <p>Cha hiện tại: ${n.parent_code ? `<b>FRS ${esc(n.parent_code)}</b>` : "<b>không có (gốc cây)</b>"} <span class="chip">${n.source === "manual" ? "sửa tay" : "tự động"}</span></p>
      ${n.skipped.length ? `<p class="muted">Chưa có file của FRS trung gian: ${esc(n.skipped.join(", "))}.</p>` : ""}
      ${n.carry.length ? `<p>Ghi chú carry-over nhắc tới:</p><ul class="plain">${n.carry.map((h) => `<li>${h.id ? `<a href="#/frs/${h.id}">FRS ${esc(h.code)}</a>` : "FRS " + esc(h.code)} <span class="chip">${CARRY_TEXT[h.relation]}</span></li>`).join("")}</ul>` : ""}
      <form id="parent-form"><label>Đổi FRS cha
        <select name="parent"><option value="auto" ${cur === "auto" ? "selected" : ""}>Tự động theo mã FRS</option>
          <option value="" ${n.source === "manual" && !n.parent_code ? "selected" : ""}>Không có cha (gốc cây)</option>${options}</select></label>
        <div class="row-end" style="justify-content:flex-start"><button type="submit">Lưu</button></div></form>
      <div class="row-end" style="justify-content:flex-start">
        <a href="#/frs/${n.id}"><button type="button" class="ghost">Mở FRS</button></a>
        ${n.parent_id ? `<a href="#/compare?a=${n.parent_id}&b=${n.id}"><button type="button" class="ghost">So sánh với cha</button></a>` : ""}</div>`;
  };
  draw();
}

// ---------- trang FRS ----------
const COMPAT = {
  ok: ["ok", "Tương thích"], not_tracked: ["", "Không theo dõi"], hw_not_listed: ["warn", "HW không có trong COM_BOM"],
  sw_mismatch: ["warn", "HW đi với SW khác"], no_market_rows: ["warn", "COM_BOM thiếu market"],
};
const compatChip = (status, reason) => {
  const [cls, label] = COMPAT[status] || ["", status || ""];
  return label ? `<span class="chip ${cls}" title="${esc(reason || "")}">${esc(label)}</span>` : "";
};

function linkify(text, tickets) {
  let html = esc(text);
  const keys = [...new Set((tickets || []).map((t) => t.key))].sort((a, b) => b.length - a.length);
  if (!keys.length) return html;
  const urls = Object.fromEntries(tickets.map((t) => [t.key, t.url]));
  const re = new RegExp("(?<![A-Za-z0-9])(" + keys.map((k) => k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|") + ")(?![A-Za-z0-9])", "g");
  return html.replace(re, (m) => `<a href="${esc(urls[m])}" target="_blank" rel="noopener noreferrer">${m}</a>`);
}

async function renderFrs(id, params) {
  const d = await api(`/api/frs/${id}`);
  const f = d.frs;
  const tab = params.tab || "bom";
  const state = { variant: null, ecu: "" };
  const warnCount = d.issues.filter((i) => i.severity !== "info").length;
  const tabs = [["bom", `BOM (${d.blocks.length} block)`], ["combom", `COM_BOM (${d.com_bom.length})`], ["change", `Change content (${d.changes.length})`], ["tickets", "Ticket"], ["issues", `Chất lượng dữ liệu (${warnCount} cảnh báo)`]];
  const projectId = f.project_id;
  view.innerHTML = `
    <div class="crumbs"><a href="#/">Dự án</a> / <a href="#/project/${projectId}">${esc(f.project)}</a> / FRS ${esc(f.code)}</div>
    <div class="head">
      <div><h1>FRS ${esc(f.code)} <span class="muted">${f.version == null ? "" : "V" + f.version} ${esc(f.side)}</span></h1>
        <div class="muted">Line: ${chips(f.lines) || "chưa gán"} · File: <span class="mono">${esc(f.file)}</span></div></div>
      <a href="#/compare?b=${id}"><button type="button" class="ghost">So sánh với FRS khác</button></a>
    </div>
    <div class="tabs" role="tablist">${tabs.map(([k, label]) => `<button type="button" role="tab" data-tab="${k}" class="${k === tab ? "on" : ""}" aria-selected="${k === tab}">${esc(label)}</button>`).join("")}</div>
    <div id="tab-body"></div>`;
  view.querySelectorAll("[data-tab]").forEach((b) => (b.onclick = () => { location.hash = `#/frs/${id}?tab=${b.dataset.tab}`; }));
  const body = document.getElementById("tab-body");

  const drawBom = () => {
    const q = state.ecu.trim().toUpperCase();
    const blocks = d.blocks.filter((b) => (!state.variant || b.variant_ids.includes(state.variant)) &&
      (!q || b.ecu.includes(q) || b.purchase_pn.includes(q) || b.parts.some((p) => p.pn.includes(q))));
    const vname = Object.fromEntries(d.variants.map((v) => [v.id, v.label]));
    const rows = blocks.map((b) => b.parts.map((p, i) => `<tr class="${i === 0 ? "block-start" : ""}">
        ${i === 0 ? `<td class="group" rowspan="${b.parts.length}">${esc(b.ecu)}</td>
          <td class="group" rowspan="${b.parts.length}" style="font-weight:400">${b.variant_ids.map((v) => `<span class="chip">${esc(vname[v])}</span>`).join("")}
            ${b.label ? `<div class="muted">${esc(b.label)}</div>` : ""}</td>
          <td class="group" rowspan="${b.parts.length}" style="font-weight:400">${pnLink(b.purchase_pn)}</td>
          <td class="group" rowspan="${b.parts.length}" style="font-weight:400">${compatChip(b.compat_status, b.compat_reason)}</td>` : ""}
        <td>${esc(p.pn_type)}</td><td>${pnLink(p.pn)}</td><td class="mono">${esc(p.did)}</td><td class="mono">${esc(p.rev_did)}</td></tr>`).join("")).join("");
    body.innerHTML = `
      <div class="toolbar">
        <span class="muted">Variant xe:</span>
        <button type="button" class="chip ${state.variant ? "" : "on"}" data-v="">Tất cả</button>
        ${d.variants.map((v) => `<button type="button" class="chip ${state.variant === v.id ? "on" : ""}" data-v="${v.id}">${esc(v.label)}</button>`).join("")}
        <input type="search" id="bom-filter" placeholder="Lọc theo ECU hoặc PN" value="${esc(state.ecu)}" aria-label="Lọc ECU hoặc PN">
        <span class="muted">${blocks.length}/${d.blocks.length} block</span>
      </div>
      <div class="table-wrap"><table>
        <thead><tr><th>ECU</th><th>Variant / nhãn block</th><th>Purchase PN</th><th>COM_BOM</th><th>PN Type</th><th>Part number</th><th>DID</th><th>Rev DID</th></tr></thead>
        <tbody>${rows || '<tr><td colspan="8" class="empty">Không có block nào khớp bộ lọc.</td></tr>'}</tbody></table></div>`;
    body.querySelectorAll("[data-v]").forEach((b) => (b.onclick = () => { state.variant = b.dataset.v ? Number(b.dataset.v) : null; drawBom(); }));
    const input = document.getElementById("bom-filter");
    input.oninput = () => { state.ecu = input.value; const pos = input.selectionStart; drawBom(); const n = document.getElementById("bom-filter"); n.focus(); n.setSelectionRange(pos, pos); };
  };

  if (tab === "combom") {
    const cv = await api(`/api/frs/${id}/compat`);
    const short = (list) => list.map((h) => `<span class="mono">${esc(h)}</span>`).join(", ");
    const answers = cv.groups.flatMap((g) => g.answers.map((a) => `<div class="answer ${a.incompatible.length ? "warn" : "ok"}">
        <div><b>${esc(g.name)}</b> · SW đang dùng <span class="mono">${esc(a.sw)}</span>${a.listed ? "" : ' <span class="chip warn">SW không có trong COM_BOM</span>'}</div>
        <div>${a.compatible.length ? `Tương thích ${a.compatible.length}/${g.hws.length} HW: ${short(a.compatible)}` : "Không tương thích HW nào trong bảng"}</div>
        ${a.incompatible.length ? `<div>Không tương thích: ${short(a.incompatible)}</div>` : ""}</div>`)).join("");
    const warnings = [
      ...cv.groups.flatMap((g) => g.bom.filter((x) => x.warning).map((x) => ({ ...x, ecu: g.name }))),
      ...cv.orphans,
    ].map((x) => `<li><b>${esc(x.ecu)}</b> [${esc(x.variants.join(", "))}]: HW <span class="mono">${esc(x.hw)}</span> + SW <span class="mono">${esc(x.sw)}</span>. ${esc(x.reason)}.</li>`).join("");
    const matrix = (g) => {
      const extra = g.bom.filter((x) => x.warning);  // cặp của BOM không có trong bảng
      const head = g.sws.map((s) => `<th class="mono ${s.in_bom ? "cur" : ""}">${esc(s.sw_pn)}${s.in_bom ? '<div class="tag">BOM</div>' : ""}</th>`).join("");
      const rows = g.hws.map((h) => `<tr><th scope="row" class="mono ${h.in_bom ? "cur" : ""}">${pnLink(h.hw_pn)}${h.in_bom ? ' <span class="tag">BOM</span>' : ""}
          <div class="muted" style="font-weight:400">PU ${esc(h.pu_pns.join(", ") || "?")}</div></th>
        ${g.sws.map((s) => {
          const key = `${h.hw_pn}|${s.sw_pn}`;
          const ok = key in g.cells;
          const cur = g.bom.some((x) => x.hw === h.hw_pn && x.sw === s.sw_pn);
          return `<td class="cell ${ok ? "yes" : "no"} ${cur ? "current" : ""}" title="${ok ? "Tương thích" : "Không tương thích"}${cur ? " (cặp đang dùng trong BOM)" : ""}">${ok ? `✓${g.cells[key] ? ` <span class="mono">BL ${esc(g.cells[key])}</span>` : ""}` : "–"}</td>`;
        }).join("")}</tr>`).join("");
      return `<section><h2>${esc(g.name)} ${g.warning ? '<span class="chip warn">có cảnh báo</span>' : ""}</h2>
        <div class="table-wrap"><table class="matrix"><thead><tr><th>HW \\ SW</th>${head}</tr></thead><tbody>${rows}</tbody></table></div>
        ${extra.map((x) => `<p class="answer warn" style="margin:8px 0 0">BOM đang dùng HW ${esc(x.hw)} + SW ${esc(x.sw)}: ${esc(x.reason)}</p>`).join("")}</section>`;
    };
    body.innerHTML = cv.groups.length ? `
      ${warnings ? `<div class="notice" style="margin:0 0 14px"><b>${cv.warning_count} cảnh báo:</b><ul style="margin:6px 0 0 18px;padding:0">${warnings}</ul></div>` : ""}
      <section style="margin-top:0"><h2>SW đang dùng có tương thích HW cũ không?</h2><div class="answers">${answers}</div></section>
      <section><h2>Kiểm tra một cặp HW + SW</h2>
        <form class="toolbar" id="check-form">
          <select name="group" aria-label="ECU">${cv.groups.map((g) => `<option>${esc(g.name)}</option>`).join("")}</select>
          <input type="search" name="hw" list="hw-list" placeholder="HW PN" required aria-label="HW PN">
          <input type="search" name="sw" list="sw-list" placeholder="SW PN" required aria-label="SW PN">
          <datalist id="hw-list"></datalist><datalist id="sw-list"></datalist>
          <button type="submit">Kiểm tra</button>
        </form><div id="check-result"></div></section>
      ${cv.groups.map(matrix).join("")}
      <p class="muted" style="margin-top:14px">✓ = tương thích (kèm BL version), – = không tương thích. Ô viền đậm là cặp đang dùng trong BOM.
        ECU không theo dõi trong COM_BOM: ${esc(cv.untracked_ecus.join(", ") || "không có")}.</p>` : '<div class="empty">File không có sheet COM_BOM.</div>';
    const form = document.getElementById("check-form");
    if (form) {
      const fill = () => {
        const g = cv.groups.find((x) => x.name === form.group.value);
        document.getElementById("hw-list").innerHTML = g.hws.map((h) => `<option value="${esc(h.hw_pn)}">`).join("");
        document.getElementById("sw-list").innerHTML = g.sws.map((s) => `<option value="${esc(s.sw_pn)}">`).join("");
      };
      fill();
      form.group.onchange = fill;
      form.onsubmit = async (ev) => {
        ev.preventDefault();
        const out = document.getElementById("check-result");
        try {
          const r = await api(`/api/frs/${id}/compat-check?group=${enc(form.group.value)}&hw=${enc(form.hw.value)}&sw=${enc(form.sw.value)}`);
          const list = (items, key) => items.map((x) => `<span class="mono">${esc(x[key])}</span>`).join(", ") || "không có";
          out.innerHTML = `<div class="answer ${r.compatible ? "ok" : "warn"}">
            <div><b>${r.compatible ? "Tương thích" : "Không tương thích"}</b>: ${esc(r.group)} · HW <span class="mono">${esc(r.hw_pn)}</span> + SW <span class="mono">${esc(r.sw_pn)}</span>${r.compatible && r.matches[0].bl_version ? ` · BL ${esc(r.matches[0].bl_version)}` : ""}</div>
            ${r.compatible ? "" : `<div>${esc(r.reason)}.</div><div>HW này đi với SW: ${list(r.sw_for_hw, "sw_pn")}</div><div>SW này đi với HW: ${list(r.hw_for_sw, "hw_pn")}</div>`}</div>`;
        } catch (e) { out.innerHTML = `<div class="answer warn">${esc(e.message)}</div>`; }
      };
    }
  } else if (tab === "change") {
    const rows = d.changes.map((c, i) => `<tr class="${i === 0 || d.changes[i - 1].tpv !== c.tpv ? "block-start" : ""}">
      <td><b>${c.tpv == null ? "?" : "TPV" + c.tpv}</b></td><td>${esc(c.ecu_raw)}${c.shared ? '<div class="muted">chung nội dung với ECU phía trên</div>' : ""}</td>
      <td class="pre">${linkify(c.text, c.tickets) || '<span class="muted">(trống)</span>'}</td><td class="pre">${linkify(c.remarks, c.tickets)}</td></tr>`).join("");
    body.innerHTML = `<div class="table-wrap"><table><thead><tr><th>TPV</th><th>ECU</th><th>Change content</th><th>Remarks</th></tr></thead>
      <tbody>${rows || '<tr><td colspan="4" class="empty">File không có sheet Change content.</td></tr>'}</tbody></table></div>`;
  } else if (tab === "tickets") {
    const { tickets } = await api(`/api/frs/${id}/tickets`);
    const st = { prefix: "", tpv: "", text: "" };
    const prefixes = [...new Set(tickets.map((t) => t.prefix))].sort();
    const tpvs = [...new Set(tickets.flatMap((t) => t.tpvs))].sort((a, b) => b - a);
    const draw = () => {
      const q = st.text.trim().toLowerCase();
      const list = tickets.filter((t) => (!st.prefix || t.prefix === st.prefix) && (!st.tpv || t.tpvs.includes(Number(st.tpv))) &&
        (!q || t.key.toLowerCase().includes(q) || t.line.toLowerCase().includes(q) || t.ecus.join(" ").toLowerCase().includes(q)));
      document.getElementById("ticket-count").textContent = `${list.length}/${tickets.length} ticket`;
      document.getElementById("ticket-rows").innerHTML = list.map((t) => `<tr>
        <td><a href="${esc(t.url)}" target="_blank" rel="noopener noreferrer"><b>${esc(t.key)}</b></a></td>
        <td>${t.tpvs.map((n) => `<span class="chip">TPV${n}</span>`).join("")}</td><td>${t.ecus.map((e) => `<span class="chip">${esc(e)}</span>`).join("")}</td>
        <td>${esc(t.line)}</td></tr>`).join("") || '<tr><td colspan="4" class="empty">Không có ticket nào khớp bộ lọc.</td></tr>';
    };
    body.innerHTML = `
      <div class="toolbar">
        <select id="t-prefix" aria-label="Loại ticket"><option value="">Mọi loại</option>${prefixes.map((p) => `<option>${esc(p)}</option>`).join("")}</select>
        <select id="t-tpv" aria-label="TPV"><option value="">Mọi TPV</option>${tpvs.map((n) => `<option value="${n}">TPV${n}</option>`).join("")}</select>
        <input type="search" id="t-text" placeholder="Lọc theo mã, nội dung hoặc ECU" aria-label="Lọc ticket">
        <span class="muted" id="ticket-count"></span>
      </div>
      <div class="table-wrap"><table><thead><tr><th>Ticket</th><th>TPV</th><th>ECU</th><th>Nội dung</th></tr></thead><tbody id="ticket-rows"></tbody></table></div>`;
    document.getElementById("t-prefix").onchange = (e) => { st.prefix = e.target.value; draw(); };
    document.getElementById("t-tpv").onchange = (e) => { st.tpv = e.target.value; draw(); };
    document.getElementById("t-text").oninput = (e) => { st.text = e.target.value; draw(); };
    draw();
  } else if (tab === "issues") {
    const label = { error: ["err", "Lỗi"], warning: ["warn", "Cảnh báo"], info: ["", "Ghi chú"] };
    const rows = d.issues.map((i) => `<tr><td><span class="chip ${label[i.severity][0]}">${label[i.severity][1]}</span></td>
      <td class="mono">${esc(i.sheet.trim())}${i.cell ? "!" + esc(i.cell) : ""}</td><td>${esc(i.message)}</td><td class="mono">${esc(i.raw)}</td></tr>`).join("");
    body.innerHTML = `<div class="table-wrap"><table><thead><tr><th>Mức</th><th>Vị trí</th><th>Nội dung</th><th>Giá trị gốc</th></tr></thead>
      <tbody>${rows || '<tr><td colspan="4" class="empty">Không có vấn đề nào.</td></tr>'}</tbody></table></div>`;
  } else drawBom();
}

// ---------- tìm kiếm ----------
async function renderSearch(params) {
  const q = params.q || "";
  searchInput.value = q;
  if (!appState.filters.variants.length) await loadState();
  const qs = new URLSearchParams(Object.entries(params).filter(([, v]) => v)).toString();
  const d = await api(`/api/search?${qs}`);
  const opt = (list, cur, any) => `<option value="">${any}</option>` + list.map((x) => `<option value="${esc(typeof x === "object" ? x.id : x)}" ${String(typeof x === "object" ? x.id : x) === String(cur || "") ? "selected" : ""}>${esc(typeof x === "object" ? x.name : x)}</option>`).join("");
  const total = d.frs.length + d.parts.length + d.ecus.length + d.tickets.length;

  const frsRows = d.frs.map((f) => `<tr><td>${esc(f.project)}</td><td><a href="#/frs/${f.id}"><b>FRS ${esc(f.code)}</b></a></td>
    <td>${f.version == null ? "" : "V" + f.version}</td><td>${esc(f.side)}</td><td>${chips(f.lines)}</td></tr>`).join("");
  const partRows = d.parts.map((p) => `<tr><td>${esc(p.project)}</td><td><a href="#/frs/${p.frs_id}">FRS ${esc(p.frs)}</a> ${p.version == null ? "" : "V" + p.version}</td>
    <td>${chips(p.lines)}</td><td><b>${esc(p.ecu)}</b>${p.label ? `<div class="muted">${esc(p.label)}</div>` : ""}</td><td>${chips(p.variants)}</td>
    <td>${esc(p.pn_type)}</td><td class="mono">${esc(p.pn)}</td><td>${pnLink(p.purchase_pn)}</td></tr>`).join("");
  const ecuRows = d.ecus.map((e) => `<tr><td>${esc(e.project)}</td><td><a href="#/frs/${e.frs_id}">FRS ${esc(e.frs)}</a> ${e.version == null ? "" : "V" + e.version}</td>
    <td><b>${esc(e.ecu)}</b>${e.label ? `<div class="muted">${esc(e.label)}</div>` : ""}</td><td>${chips(e.variants)}</td>
    <td class="mono">${esc(e.parts).replace(/ {2}/g, "<br>")}</td><td>${compatChip(e.compat_status, "")}</td></tr>`).join("");
  const ticketRows = d.tickets.map((t) => `<tr><td><a href="${esc(t.url)}" target="_blank" rel="noopener noreferrer"><b>${esc(t.key)}</b></a></td><td>${esc(t.project)}</td>
    <td><a href="#/frs/${t.frs_id}?tab=change">FRS ${esc(t.frs)}</a></td><td>${t.tpv == null ? "?" : "TPV" + t.tpv}</td><td>${esc(t.ecu_raw)}</td><td>${esc(t.line)}</td></tr>`).join("");
  const section = (title, count, head, rows) => (count ? `<section><h2>${title} (${count})</h2><div class="table-wrap"><table><thead><tr>${head.map((h) => `<th>${h}</th>`).join("")}</tr></thead><tbody>${rows}</tbody></table></div></section>` : "");

  view.innerHTML = `
    <div class="head"><h1>Kết quả cho "${esc(q)}" <span class="muted">· ${total} dòng</span></h1></div>
    <form class="toolbar" id="filters">
      <select name="project" aria-label="Dự án">${opt(appState.projects, params.project, "Mọi dự án")}</select>
      <select name="variant" aria-label="Variant xe">${opt(appState.filters.variants, params.variant, "Mọi variant xe")}</select>
      <select name="pn_type" aria-label="PN Type">${opt(appState.filters.pn_types, params.pn_type, "Mọi PN Type")}</select>
      <select name="ecu" aria-label="ECU">${opt(appState.filters.ecus, params.ecu, "Mọi ECU")}</select>
    </form>
    ${total ? "" : `<div class="empty">Không tìm thấy gì cho "${esc(q)}". Thử gõ ít ký tự hơn (vd bỏ phần revision) hoặc bỏ bộ lọc.</div>`}
    ${section("FRS", d.frs.length, ["Dự án", "FRS", "TPV", "Tay lái", "Line"], frsRows)}
    ${section("Ticket", d.tickets.length, ["Ticket", "Dự án", "FRS", "TPV", "ECU", "Nội dung"], ticketRows)}
    ${section("Part number đang dùng ở", d.parts.length, ["Dự án", "FRS", "Line", "ECU / block", "Variant xe", "PN Type", "Part number", "Purchase PN"], partRows)}
    ${d.truncated ? '<p class="muted">Kết quả part number bị cắt bớt, hãy gõ thêm ký tự hoặc dùng bộ lọc.</p>' : ""}
    ${section("ECU", d.ecus.length, ["Dự án", "FRS", "ECU / block", "Variant xe", "Part number", "COM_BOM"], ecuRows)}`;
  document.getElementById("filters").onchange = (ev) => {
    const p = { ...params, [ev.target.name]: ev.target.value };
    location.hash = "#/search?" + new URLSearchParams(Object.entries(p).filter(([, v]) => v)).toString();
  };
}

// ---------- so sánh hai FRS ----------
const DIFF = { same: ["", "Giống"], rev: ["ok", "Đổi revision"], changed: ["warn", "Đổi PN"], added: ["warn", "Thêm"], removed: ["warn", "Bớt"] };

async function renderCompare(params) {
  searchInput.value = "";
  const { frs } = await api("/api/frs-list");
  let a = params.a ? Number(params.a) : null;
  const b = params.b ? Number(params.b) : null;
  // chỉ chọn FRS mới (b): mặc định so với FRS cha trong cây
  if (!a && b) { const cur = frs.find((f) => f.id === b); if (cur && cur.parent_id) a = cur.parent_id; }
  const groupsOf = {};
  for (const f of frs) (groupsOf[f.project] ||= []).push(f);
  const options = (sel) => `<option value="">Chọn FRS</option>` + Object.entries(groupsOf).map(([proj, items]) =>
    `<optgroup label="${esc(proj)}">${items.map((f) => `<option value="${f.id}" ${f.id === sel ? "selected" : ""}>FRS ${esc(f.code)}${f.version == null ? "" : " V" + f.version} ${esc(f.side)}</option>`).join("")}</optgroup>`).join("");
  view.innerHTML = `
    <div class="crumbs"><a href="#/">Dự án</a> / So sánh FRS</div>
    <div class="head"><h1>So sánh part number giữa hai FRS</h1></div>
    <div class="pickers">
      <label>FRS cũ (A)<select id="cmp-a">${options(a)}</select></label>
      <button type="button" class="ghost" id="cmp-swap" title="Đổi chỗ A và B">⇄</button>
      <label>FRS mới (B)<select id="cmp-b">${options(b)}</select></label>
    </div>
    <div id="cmp-body">${frs.length < 2 ? '<div class="empty">Cần ít nhất hai FRS trong chỉ mục để so sánh.</div>' : ""}</div>`;
  const go = (x, y) => { location.hash = "#/compare?" + new URLSearchParams(Object.entries({ a: x, b: y }).filter(([, v]) => v)).toString(); };
  document.getElementById("cmp-a").onchange = (e) => go(e.target.value, b);
  document.getElementById("cmp-b").onchange = (e) => go(a, e.target.value);
  document.getElementById("cmp-swap").onclick = () => go(b, a);
  const body = document.getElementById("cmp-body");
  if (!a || !b) { if (frs.length >= 2) body.innerHTML = '<div class="empty">Chọn hai FRS để so sánh.</div>'; return; }
  if (a === b) { body.innerHTML = '<div class="empty">Hãy chọn hai FRS khác nhau.</div>'; return; }

  const d = await api(`/api/compare?a=${a}&b=${b}`);
  const st = { onlyDiff: true, text: "" };
  const s = d.summary;
  const blockInfo = (x) => (x ? `${x.variants.map((v) => `<span class="chip">${esc(v)}</span>`).join("")}${x.label ? `<div class="muted">${esc(x.label)}</div>` : ""}` : "");
  const draw = () => {
    const q = st.text.trim().toUpperCase();
    const groups = d.groups.filter((g) => (!st.onlyDiff || g.differs) && (!q || g.ecu.includes(q) || g.rows.some((r) => r.a.includes(q) || r.b.includes(q))));
    const rows = groups.map((g) => {
      const list = st.onlyDiff ? g.rows.filter((r) => r.status !== "same") : g.rows;
      return list.map((r, i) => `<tr class="${i === 0 ? "block-start" : ""} diff-${r.status}">
        ${i === 0 ? `<td class="group" rowspan="${list.length}">${esc(g.ecu)}${g.block === "only_a" ? '<div><span class="chip warn">chỉ có ở A</span></div>' : g.block === "only_b" ? '<div><span class="chip warn">chỉ có ở B</span></div>' : ""}</td>
          <td class="group" rowspan="${list.length}" style="font-weight:400">${blockInfo(g.b || g.a)}${g.a && g.b && g.a.variants.join() !== g.b.variants.join() ? `<div class="muted">A: ${esc(g.a.variants.join(", "))}</div>` : ""}</td>` : ""}
        <td>${esc(r.pn_type)}</td>
        <td class="val mono ${r.a ? "" : "side-missing"}">${r.a ? esc(r.a) : "không có"}</td>
        <td class="val mono ${r.b ? "" : "side-missing"}">${r.b ? esc(r.b) : "không có"}</td>
        <td>${r.status === "same" ? "" : `<span class="chip ${DIFF[r.status][0]}">${DIFF[r.status][1]}</span>`}</td></tr>`).join("");
    }).join("");
    document.getElementById("cmp-rows").innerHTML = rows || `<tr><td colspan="6" class="empty">${st.onlyDiff && !q ? "Hai FRS giống hệt nhau về part number." : "Không có dòng nào khớp bộ lọc."}</td></tr>`;
  };
  const tk = d.tickets;
  const ticketList = (list) => list.map((t) => `<tr><td><a href="${esc(t.url)}" target="_blank" rel="noopener noreferrer"><b>${esc(t.key)}</b></a></td>
    <td>${t.tpvs.map((n) => `<span class="chip">TPV${n}</span>`).join("")}</td><td>${esc(t.ecus.join(", "))}</td><td>${esc(t.line)}</td></tr>`).join("");
  const ticketSection = (title, list) => (list.length ? `<section><h2>${title} (${list.length})</h2><div class="table-wrap"><table>
    <thead><tr><th>Ticket</th><th>TPV</th><th>ECU</th><th>Nội dung</th></tr></thead><tbody>${ticketList(list)}</tbody></table></div></section>` : "");
  body.innerHTML = `
    <div class="summary">
      <span class="chip">${s.same} giống</span><span class="chip ${s.changed ? "warn" : ""}">${s.changed} đổi PN</span>
      <span class="chip ${s.rev ? "ok" : ""}">${s.rev} đổi revision</span><span class="chip ${s.added ? "warn" : ""}">${s.added} thêm</span>
      <span class="chip ${s.removed ? "warn" : ""}">${s.removed} bớt</span>
    </div>
    <div class="toolbar">
      <label class="check"><input type="checkbox" id="cmp-only" checked> Chỉ hiện khác biệt</label>
      <input type="search" id="cmp-text" placeholder="Lọc theo ECU hoặc PN" aria-label="Lọc ECU hoặc PN">
    </div>
    <div class="table-wrap"><table>
      <thead><tr><th>ECU</th><th>Variant / nhãn block</th><th>PN Type</th>
        <th>A: <a href="#/frs/${d.a.id}">FRS ${esc(d.a.code)}</a> ${d.a.version == null ? "" : "V" + d.a.version}</th>
        <th>B: <a href="#/frs/${d.b.id}">FRS ${esc(d.b.code)}</a> ${d.b.version == null ? "" : "V" + d.b.version}</th><th>Khác biệt</th></tr></thead>
      <tbody id="cmp-rows"></tbody></table></div>
    <section><h2>Ticket</h2><p class="muted">${tk.common} ticket có ở cả hai FRS, ${tk.only_b.length} chỉ có ở B, ${tk.only_a.length} chỉ có ở A.</p></section>
    ${ticketSection(`Ticket chỉ có ở B (FRS ${esc(d.b.code)})`, tk.only_b)}
    ${ticketSection(`Ticket chỉ có ở A (FRS ${esc(d.a.code)})`, tk.only_a)}`;
  document.getElementById("cmp-only").onchange = (e) => { st.onlyDiff = e.target.checked; draw(); };
  document.getElementById("cmp-text").oninput = (e) => { st.text = e.target.value; draw(); };
  draw();
}

// ---------- cài đặt ----------
const dialog = document.getElementById("settings-dialog");
const rootInput = document.getElementById("root-input");
const settingsInfo = document.getElementById("settings-info");

function openSettings() {
  rootInput.value = appState.root || "";
  settingsInfo.textContent = appState.last_scan ? `Quét lần cuối: ${appState.last_scan.replace("T", " ")}` : "";
  dialog.showModal();
}

async function runScan(fn, busyText) {
  const buttons = dialog.querySelectorAll("button");
  buttons.forEach((b) => (b.disabled = true));
  settingsInfo.textContent = busyText;
  try {
    const report = await fn();
    dialog.close();
    showNotice(scanSummary(report), "ok");
    await loadState();
    route();
  } catch (e) {
    settingsInfo.textContent = e.message;
  } finally {
    buttons.forEach((b) => (b.disabled = false));
  }
}

document.getElementById("settings-btn").onclick = openSettings;
document.getElementById("close-btn").onclick = () => dialog.close();
document.getElementById("settings-form").onsubmit = (ev) => { ev.preventDefault(); runScan(() => api("/api/settings", { root: rootInput.value }), "Đang quét..."); };
document.getElementById("rescan-btn").onclick = () => runScan(() => api("/api/scan", {}), "Đang quét...");
document.getElementById("force-btn").onclick = () => runScan(() => api("/api/scan", { force: true }), "Đang đọc lại mọi file...");
document.getElementById("search-form").onsubmit = (ev) => {
  ev.preventDefault();
  const q = searchInput.value.trim();
  if (q) location.hash = "#/search?q=" + enc(q);
};
document.addEventListener("keydown", (ev) => {
  if (ev.key === "/" && !/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName)) { ev.preventDefault(); searchInput.focus(); }
});
window.addEventListener("hashchange", () => { showNotice(""); route(); });
loadState().then(route).catch((e) => { view.innerHTML = `<div class="empty">Không kết nối được server: ${esc(e.message)}</div>`; });
