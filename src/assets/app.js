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

async function renderProject(id, params) {
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
    const rows = d.com_bom.map((r, i) => `<tr class="${i === 0 || d.com_bom[i - 1].ecu_raw !== r.ecu_raw ? "block-start" : ""}">
      <td><b>${esc(r.ecu_raw)}</b></td><td>${esc(r.market)}</td><td>${pnLink(r.pu_pn)}</td><td>${pnLink(r.hw_pn)}</td><td>${pnLink(r.sw_pn)}</td>
      <td class="mono">${esc(r.bl_version)}</td><td>${esc(r.remark)}</td></tr>`).join("");
    body.innerHTML = `<p class="muted">Một dòng = HW và SW tương thích với nhau. ECU không có trong bảng là "không theo dõi".</p>
      <div class="table-wrap"><table><thead><tr><th>ECU</th><th>Market</th><th>PU PN</th><th>HW PN</th><th>SW PN</th><th>BL version</th><th>Remark</th></tr></thead>
      <tbody>${rows || '<tr><td colspan="7" class="empty">File không có sheet COM_BOM.</td></tr>'}</tbody></table></div>`;
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
