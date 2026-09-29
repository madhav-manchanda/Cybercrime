(function () {
"use strict";

const API = (function () {
  const BASE = (
    localStorage.getItem("cci.api") ||
    "http://" + (globalThis.location ? globalThis.location.hostname : "localhost") + ":8000/api/v1"
  ).replace(/\/+$/, "");
  let token = localStorage.getItem("cci.token") || null;
  function headers(bodyDefined) {
    const h = {};
    if (token) h["Authorization"] = "Bearer " + token;
    if (bodyDefined) h["Content-Type"] = "application/json";
    return h;
  }
  async function req(method, path, body) {
    const res = await fetch(BASE + path, {
      method,
      headers: headers(body !== undefined),
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    let data = null;
    try { data = await res.json(); } catch (e) { /* noop */ }
    if (!res.ok) {
      const msg = data && data.error && data.error.message ? data.error.message : res.status + " " + res.statusText;
      const err = new Error(msg);
      err.status = res.status;
      err.code = data && data.error ? data.error.code : null;
      err.detail = data && data.error ? data.error.details : null;
      throw err;
    }
    return data;
  }
  return {
    BASE,
    get token() { return token; },
    async login(email, password) {
      const d = await req("POST", "/auth/login", { email, password, client_platform: "command-center-ui" });
      token = d.access_token;
      localStorage.setItem("cci.token", d.access_token);
      return d;
    },
    me: () => req("GET", "/auth/me"),
    logout() {
      token = null;
      localStorage.removeItem("cci.token");
    },
    get: (p) => req("GET", p),
    post: (p, b) => req("POST", p, b === undefined ? {} : b),
    patch: (p, b) => req("PATCH", p, b === undefined ? {} : b),
  };
})();

const S = {
  user: null,
  view: "dashboard",
  case: null,
  cases: null,
  overview: null,
  hotspots: null,
  geojson: null,
  alerts: null,
  audit: null,
  simCaseId: null,
  forecast: [],
  _fAt: 0,
  poller: null,
  clockId: null,
  mapFilter: { hotspots: true, cases: true, atms: true },
};

const esc = (s) =>
  String(s === undefined || s === null ? "" : s).replace(/[&<>"']/g, (c) =>
    ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[c]));

const $ = (sel, root) => (root || document).querySelector(sel);
const $$ = (sel, root) => Array.from((root || document).querySelectorAll(sel));

const inr = (n) => {
  if (n === null || n === undefined || isNaN(n)) return "—";
  return "₹" + Number(n).toLocaleString("en-IN", { maximumFractionDigits: 0 });
};
const pct = (n) => (n === null || n === undefined || isNaN(n) ? "—" : Math.round(n * 100) + "%");
const nf = (n) => (n === null || n === undefined || isNaN(n) ? "—" : Number(n).toLocaleString("en-IN"));
const fmtBar = (n) => (n === null || n === undefined || isNaN(n) ? 0 : Math.max(0, Math.min(100, Math.round(n * 100))));

function fmtDT(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d)) return iso;
  return d.toLocaleString("en-GB", {
    day: "2-digit", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
  }).replace(",", "");
}
function fmtClock(iso) {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleTimeString("en-IN", { hour12: false, hour: "2-digit", minute: "2-digit", second: "2-digit" });
}
function timeAgo(iso) {
  if (!iso) return "—";
  const s = (Date.now() - new Date(iso).getTime()) / 1000;
  if (s < 0) return "NOW";
  if (s < 60) return Math.round(s) + "s ago";
  if (s < 3600) return Math.round(s / 60) + "m ago";
  if (s < 86400) return (s / 3600).toFixed(1) + "h ago";
  return Math.round(s / 86400) + "d ago";
}
function countdown(iso) {
  if (!iso) return "NO WINDOW";
  const ms = new Date(iso).getTime() - Date.now();
  if (ms <= 0) return "WINDOW EXPIRED";
  const s = Math.floor(ms / 1000);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return h + "h " + String(m).padStart(2, "0") + "m " + String(sec).padStart(2, "0") + "s REM";
}

function riskColor(r) {
  if (r === null || r === undefined || isNaN(r)) return "#849396";
  r = Math.max(0, Math.min(1, r));
  if (r < 0.35) return "#4cd6fb";
  if (r < 0.65) return "#ffb95f";
  return "#ffb4ab";
}
function riskLabel(r) {
  if (r === null || r === undefined || isNaN(r)) return "UNKNOWN";
  r = Math.max(0, Math.min(1, r));
  if (r < 0.35) return "LOW";
  if (r < 0.65) return "MEDIUM";
  return "HIGH";
}
function humanize(s) {
  return String(s || "").replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function toast(msg, kind) {
  const root = $("#toast-root");
  const el = document.createElement("div");
  el.className =
    "toast flex items-start gap-2 rounded-lg border px-4 py-3 font-mono-data-sm shadow-lg bg-surface-container-high " +
    (kind === "error" ? "border-error/50 text-error" : "border-primary-container/40 text-on-surface");
  el.innerHTML =
    '<span class="material-symbols-outlined text-lg mt-px">' +
    (kind === "error" ? "error" : "check_circle") + "</span><span>" + esc(msg) + "</span>";
  root.appendChild(el);
  setTimeout(() => el.remove(), 5200);
}

function pageTitle(title, sub) {
  $("#page-title").textContent = title;
  $("#page-sub").textContent = sub || "";
  document.title = "I4C // " + title;
}
function navActive(name) {
  $$("#main-nav .nav-pill").forEach((b) => b.classList.toggle("active", b.dataset.nav === name));
}

function setApiStatus(ok) {
  const el = $("#api-status");
  el.classList.remove("hidden");
  el.classList.add("flex");
  const dot = $("span", el);
  dot.className = "w-1.5 h-1.5 rounded-full " + (ok ? "bg-secondary animate-pulse" : "bg-error");
  $("span:nth-child(2)", el).textContent = ok ? "API LIVE" : "API DOWN";
}

/* ------------------------------ modal ------------------------------ */
function openModal(html, wide) {
  const wrap = document.createElement("div");
  wrap.className =
    "fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm";
  wrap.innerHTML =
    '<div class="card w-full ' + (wide ? "max-w-3xl" : "max-w-lg") +
    ' p-5 max-h-[86vh] overflow-y-auto"><div class="dropdown-panel">' +
    '<div class="flex items-center justify-between mb-4">' +
    '<div id="_mh" class="font-headline-sm"></div>' +
    '<button class="_mc text-on-surface-variant hover:text-on-surface"><span class="material-symbols-outlined">close</span></button></div>' +
    '<div id="_mb"></div><div id="_mf" class="mt-4 flex justify-end gap-2"></div></div></div>';
  wrap.addEventListener("click", (e) => { if (e.target === wrap) wrap.remove(); });
  $("._mc", wrap).addEventListener("click", () => wrap.remove());
  document.body.appendChild(wrap);
  return {
    el: wrap,
    title(t) { $("#_mh", wrap).textContent = t; },
    body(b) { $("#_mb", wrap).innerHTML = b; },
    foot(b) { $("#_mf", wrap).innerHTML = b; },
    close() { wrap.remove(); },
  };
}

/* ------------------------------ router ------------------------------ */
function go(name) {
  S.view = name;
  navActive(name);
  const fab = $("#fab-sim");
  fab.classList.add("hidden");
  fab.classList.remove("flex");
  if (name === "dashboard") renderDashboard();
  else if (name === "cases") renderCasesList();
  else if (name === "case") renderCaseWorkspace();
  else if (name === "sim") renderSimulator();
  else if (name === "audit") renderAudit();
  window.scrollTo(0, 0);
}

/* ============================ LOGIN ============================ */
function showLogin() {
  $("#bootscreen").classList.add("hidden");
  $("#app").classList.add("hidden");
  $("#view-login").classList.remove("hidden");
  $("#view-login").classList.add("flex");
  $("#login-api").textContent = "API: " + API.BASE;
}
$("#login-submit").addEventListener("click", doLogin);
$("#login-password").addEventListener("keydown", (e) => { if (e.key === "Enter") doLogin(); });

async function doLogin() {
  const email = $("#login-email").value.trim();
  const password = $("#login-password").value;
  const errEl = $("#login-error");
  errEl.classList.add("hidden");
  if (!email || !password) { errEl.textContent = "Enter analyst email and password."; errEl.classList.remove("hidden"); return; }
  const btn = $("#login-submit");
  btn.disabled = true;
  btn.textContent = "AUTHENTICATING…";
  try {
    await API.login(email, password);
    const user = await API.me();
    enterApp(user);
  } catch (e) {
    if (e.status === 401) {
      errEl.textContent = "Authentication failed. Use the analyst credentials seeded in the backend, or register via the device-flow CLI in README.";
    } else {
      errEl.textContent = (e && e.message) || "Cannot reach API at " + API.BASE;
    }
    errEl.classList.remove("hidden");
    setApiStatus(false);
  } finally {
    btn.disabled = false;
    btn.textContent = "AUTHENTICATE →";
  }
}

/* ============================ APP ENTRY ============================ */
function enterApp(user) {
  S.user = user;
  $("#bootscreen").classList.add("hidden");
  $("#view-login").classList.add("hidden");
  $("#view-login").classList.remove("flex");
  $("#app").classList.remove("hidden");
  $("#rail-user").innerHTML =
    '<span class="material-symbols-outlined text-base">account_circle</span><span class="truncate">' +
    esc(user.full_name) + ' · ' + esc(user.role && user.role.name) + "</span>";
  $("#session-chip").innerHTML =
    '<span class="material-symbols-outlined text-sm">fingerprint</span>' + esc(user.email);
  $("#rail-mode").textContent =
    "DATA: " + (cachedDataSource() || "—").toUpperCase();
  startTimers();
  go("dashboard");
}
function cachedDataSource() {
  if (S.cases && S.cases[0]) return S.cases[0].data_source || "SYNTHETIC";
  if (S.overview && S.overview.risk_distribution) return "SYNTHETIC";
  return "SYNTHETIC";
}

$("#logout-btn").addEventListener("click", () => {
  API.logout();
  stopTimers();
  location.reload();
  showLogin();
});
$$("#main-nav .nav-pill").forEach((b) =>
  b.addEventListener("click", () => {
    if (b.dataset.nav === "cases") S.case = null;
    go(b.dataset.nav);
  }));
$("#fab-sim").addEventListener("click", () => { go("sim"); });

/* ------------------------------ timers ------------------------------ */
function startTimers() {
  stopTimers();
  S.clockId = setInterval(() => {
    const el = $("#live-clock");
    if (el) el.textContent = new Date().toLocaleTimeString("en-IN", { hour12: false });
  }, 1000);
  S.poller = setInterval(async () => {
    if (S.view === "dashboard") await refreshDashboard();
    else if (S.view === "audit") await refreshAudit();
    else if (S.view === "case" && S.case) await refreshCaseData(true);
  }, 12000);
}
function stopTimers() {
  if (S.clockId) clearInterval(S.clockId);
  if (S.poller) clearInterval(S.poller);
  S.clockId = null;
  S.poller = null;
}

/* ============================ DASHBOARD ============================ */
function renderDashboard() {
  pageTitle("COMMAND CENTER", "GLOBAL THREAT OVERVIEW");
  navActive("dashboard");
  $("#view-root").innerHTML = `
    <div class="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-5 gap-4" id="telemetry"></div>
    <div class="grid grid-cols-1 xl:grid-cols-3 gap-4">
      <div class="xl:col-span-2 card card-glow p-4">
        <div class="flex items-center justify-between flex-wrap gap-3 mb-3">
          <div>
            <div class="font-label-caps text-primary/80">TACTICAL MAP</div>
            <div class="font-headline-sm mt-1">TARGET GEOSPATIAL LAYER</div>
          </div>
          <div class="flex items-center gap-3 flex-wrap">
            <label class="map-toggle flex items-center gap-1.5 font-mono-data-sm text-on-surface-variant cursor-pointer"><input type="checkbox" data-layer="hotspots" checked class="accent-cyan-400">HOTSPOTS</label>
            <label class="flex items-center gap-1.5 font-mono-data-sm text-on-surface-variant cursor-pointer"><input type="checkbox" data-layer="cases" checked class="accent-cyan-400">CASES</label>
            <label class="flex items-center gap-1.5 font-mono-data-sm text-on-surface-variant cursor-pointer"><input type="checkbox" data-layer="atms" checked class="accent-cyan-400">FORECAST</label>
            <span class="hidden md:inline font-mono-data-sm text-primary/60">LAYERS:</span>
          </div>
        </div>
        <div class="map-canvas h-[420px] bg-surface-dim border border-outline-variant rounded-lg">
          <div class="grid-layer"></div>
          <div class="scanner"></div>
          <svg id="map-svg" class="relative w-full h-full"></svg>
        </div>
        <div class="flex items-center gap-4 mt-3 flex-wrap font-mono-data-sm text-on-surface-variant">
          <span class="flex items-center gap-1.5"><span class="w-3 h-3 rounded-full border-2 border-dashed" style="border-color:#9cf0ff"></span>FORECAST NODE</span>
          <span class="flex items-center gap-1.5"><span class="w-2.5 h-2.5 rounded-full" style="background:#00e5ff"></span>FORECAST HOTSPOT</span>
          <span class="flex items-center gap-1.5"><span class="w-2.5 h-2.5 rotate-45 border-2" style="border-color:#4cd6fb"></span>ACTIVE CASE</span>
          <span class="flex items-center gap-1.5"><span class="w-2.5 h-2.5 rounded-full" style="background:#ffb4ab"></span>HIGH RISK (&gt;0.65)</span>
          <span class="ml-auto" id="map-meta"></span>
        </div>
      </div>
      <div class="space-y-4">
        <div class="card p-4">
          <div class="flex items-center justify-between mb-3">
            <div><div class="font-label-caps text-secondary">INCIDENT STREAM</div><div class="font-headline-sm mt-1">LIVE CASES</div></div>
            <button class="font-mono-data-sm text-primary hover:underline" data-action="view-all-cases">VIEW ALL →</button>
          </div>
          <div id="incident-stream" class="space-y-2"></div>
        </div>
        <div class="card p-4">
          <div class="flex items-center justify-between mb-3">
            <div><div class="font-label-caps text-error">SIGNAL STREAM</div><div class="font-headline-sm mt-1">ALERT ENGINE</div></div>
            <span class="flex items-center gap-1.5 font-mono-data-sm text-secondary"><span class="w-1.5 h-1.5 rounded-full bg-secondary animate-pulse"></span>ACTIVE</span>
          </div>
          <div id="signal-stream" class="space-y-2"></div>
        </div>
      </div>
    </div>
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-4">
      <div class="card p-4">
        <div class="font-label-caps text-on-surface-variant mb-3">RISK DISTRIBUTION</div>
        <div id="risk-dist" class="space-y-2.5"></div>
      </div>
      <div class="card p-4">
        <div class="font-label-caps text-on-surface-variant mb-3">CASE FLOW OVER TIME</div>
        <svg id="flow-chart" class="w-full h-36" viewBox="0 0 320 144"></svg>
      </div>
      <div class="card p-4">
        <div class="flex items-center justify-between mb-3">
          <div class="font-label-caps text-on-surface-variant">ALERT CENTER</div>
          <button class="font-mono-data-sm text-primary" data-action="ack-all">ACK ALL</button>
        </div>
        <div id="alert-center" class="space-y-2 max-h-56 overflow-y-auto"></div>
      </div>
    </div>`;
  $("#view-root").querySelector('[data-action="view-all-cases"]').addEventListener("click", () => go("cases"));
  $$(".map-toggle input").forEach((cb) =>
    cb.addEventListener("change", () => {
      S.mapFilter[cb.dataset.layer] = cb.checked;
      paintMap();
    }));
  $("#view-root").querySelector('[data-action="ack-all"]').addEventListener("click", ackAllAlerts);
  refreshDashboard();
}

async function refreshDashboard() {
  const root = $("#view-root");
  if (!root || S.view !== "dashboard") return;
  try {
    const [overview, hotspots, geojson, cases, alerts] = await Promise.all([
      API.get("/analytics/overview"),
      API.get("/analytics/hotspots"),
      API.get("/analytics/geojson"),
      API.get("/cases?page=1&page_size=100"),
      API.get("/alerts?page=1&page_size=100"),
    ]);
    S.overview = overview;
    S.hotspots = hotspots || [];
    S.geojson = geojson;
    S.cases = (cases && cases.items) || [];
    S.alerts = (alerts && alerts.items) || [];
    if (S.cases[0]) $("#rail-mode").textContent = "DATA: " + (S.cases[0].data_source || "SYNTHETIC").toUpperCase();
    if (!S._fAt || Date.now() - S._fAt > 60000) {
      const openList = S.cases.filter((c) => c.is_open).slice(0, 6);
      const per = await Promise.all(openList.map(async (c) => {
        try {
          const ll = await API.get("/cases/" + c.id + "/predictions/latest-locations");
          return (Array.isArray(ll) ? ll.sort((a, b) => a.rank - b.rank) : []);
        } catch (e) { return []; }
      }));
      S.forecast = openList.flatMap((c, i) => per[i].map((l) => Object.assign({}, l, { case_number: c.case_number, case_risk: c.current_risk_score })));
      S._fAt = Date.now();
    }
    setApiStatus(true);
    renderTelemetry();
    paintMap();
    renderIncidentStream();
    renderSignalStream();
    renderRiskDist();
    renderFlowChart();
    renderAlertCenter();
  } catch (e) {
    setApiStatus(false);
    if (!root.innerHTML.trim() || !$("#telemetry", root)) {
      root.innerHTML =
        '<div class="card p-8 text-center font-mono-data-md text-error"><div class="material-symbols-outlined text-4xl mb-3">link_off</div>' +
        esc(e && e.message) + "</div>";
      return;
    }
    toast("API: " + ((e && e.message) || "unreachable"), "error");
  }
}

function renderTelemetry() {
  const o = S.overview || {};
  const crit = S.alerts.filter((a) => a.severity === "CRITICAL").length;
  const hi = S.alerts.filter((a) => a.severity === "HIGH").length;
  const cards = [
    {
      k: "01", t: "ACTIVE CASES", v: nf(o.active_cases),
      s: "OPEN " + nf(o.open_cases) + " · " + nf(o.resolved_cases) + " RESOLVED",
      b: [Math.min(100, (o.open_cases / (o.active_cases || 1)) * 100)], c: "#00e5ff",
    },
    {
      k: "02", t: "HIGH RISK ESCALATION", v: nf(o.high_risk_cases),
      s: nf(crit) + " CRIT ALRT", b: [Math.min(100, (o.high_risk_cases / (o.active_cases || 1)) * 100)], c: "#ffb4ab",
    },
    {
      k: "03", t: "ACTIVE ALERTS", v: nf(o.active_alerts),
      s: hi + " HI · " + crit + " CRIT",
      b: [crit / (o.active_alerts || 1), hi / (o.active_alerts || 1)], c: "#ffb4ab",
    },
    {
      k: "04", t: "TARGET CLUSTERS", v: nf(o.predicted_locations),
      s: (S.hotspots ? S.hotspots.length : 0) + " FORECAST ZONES",
      b: [S.hotspots && S.hotspots.length ? 1 : 0], c: "#00daf3",
    },
    {
      k: "05", t: "HIT PRECISION (TOP-3)", v: pct(o.prediction_accuracy),
      s: "SAMPLE " + nf(o.prediction_count),
      b: [o.prediction_accuracy || 0], c: "#9cf0ff", dim: o.prediction_accuracy === null || o.prediction_accuracy === undefined,
    },
  ];
  $("#telemetry").innerHTML = cards.map((c) => `
    <div class="card p-4">
      <div class="flex items-center justify-between mb-4">
        <span class="font-mono-data-sm text-on-surface-variant">${c.k} / ${c.t}</span>
        <span class="material-symbols-outlined text-lg" style="color:${c.c}">${c.k === "05" ? "track_changes" : c.k === "03" ? "notification_important" : c.k === "02" ? "warning" : c.k === "04" ? "radar" : "assignment_turned_in"}</span>
      </div>
      <div class="font-headline-xl countdown ${c.dim ? "text-on-surface-variant" : ""}">${c.v}${c.dim ? " <span class='text-mono-data-sm'>AWAITING DATA</span>" : ""}</div>
      <div class="font-mono-data-sm text-on-surface-variant mt-2 mb-3">${esc(c.s)}</div>
      <div class="ring-bar"><div style="width:0;background:${c.c};transition:width .6s ease" data-bars="${c.b.map((x) => Math.round(Math.min(1, x) * 100)).join(",")}"></div></div>
    </div>`).join("");
  setTimeout(() => {
    $$("#telemetry .ring-bar > div").forEach((d) => {
      const parts = d.dataset.bars.split(",").filter((x) => x > 0);
      if (!parts.length) return;
      d.style.width = parts.reduce((a, x) => a + Number(x), 0) + "%";
      d.style.background = parts.map((x, i) => x + "% " + (i === 0 ? (d.style.background || "#00e5ff") : "#31353a")).join(",");
    });
  }, 50);
}

function computeBounds(points) {
  const pts = points.filter((p) => p.latitude !== null && p.latitude !== undefined && p.longitude !== null && p.longitude !== undefined);
  if (!pts.length) return null;
  const lats = pts.map((p) => p.latitude);
  const lons = pts.map((p) => p.longitude);
  const ml = Math.min(...lats), MH = Math.max(...lats);
  const mlon = Math.min(...lons), MLon = Math.max(...lons);
  const padLat = Math.max((MH - ml) * 0.12, 0.05);
  const padLon = Math.max((MLon - mlon) * 0.12, 0.05);
  return { minLat: ml - padLat, maxLat: MH + padLat, minLon: mlon - padLon, maxLon: MLon + padLon };
}

function paintMap() {
  const svg = $("#map-svg");
  if (!svg) return;
  const hotspots = (S.hotspots || []).map((h) => ({ latitude: h.latitude, longitude: h.longitude }));
  const casesPts = (S.cases || []).filter((c) => c.latitude !== null && c.latitude !== undefined);
  const forecast = (S.forecast || []).filter((f) => f.latitude !== null && f.latitude !== undefined);
  const points = hotspots.concat(casesPts.map((c) => ({ latitude: c.latitude, longitude: c.longitude, c })), forecast.map((f) => ({ latitude: f.latitude, longitude: f.longitude, f })));
  const bounds = computeBounds(points);
  if (!bounds) {
    svg.innerHTML =
      '<text x="500" y="230" text-anchor="middle" fill="#849396" font-family="JetBrains Mono" font-size="14">' +
      "NO GEOSPATIAL FORECAST — RUN PREDICTIONS TO POPULATE TACTICAL GRID</text>";
    $("#map-meta").textContent = "GRID: IND-NORTH-04 · " + (points.length) + " NODES";
    return;
  }
  const W = 1000, H = 540;
  let html = '<defs><filter id="glow"><feGaussianBlur stdDeviation="5" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>';
  html += `<g font-family="JetBrains Mono">`;
  hotspots.forEach((h) => {
    const [x, y] = projectPoint(h.latitude, h.longitude, bounds);
    const r = Math.max(6, Math.round(h.risk_score * 16));
    html += `<circle cx="${x}" cy="${y}" r="${r + 3}" fill="${riskColor(h.risk_score)}" opacity="0.18" class="pulse-ring" style="transform-origin:${x}px ${y}px"/>`;
    html += `<circle class="hs-core" cx="${x}" cy="${y}" r="${r}" fill="${riskColor(h.risk_score)}" opacity="0.85" filter="url(#glow)"/>`;
    html += `<circle class="hs-core" cx="${x}" cy="${y}" r="2.5" fill="#0b0f13"/>`;
    html += `<text x="${x + 8}" y="${y - 6}" fill="#9cf0ff" font-size="12" opacity="0.95">${esc(h.label)}</text>`;
    html += `<text x="${x + 8}" y="${y + 8}" fill="${riskColor(h.risk_score)}" font-size="10">${pct(h.risk_score)} · ${nf(h.case_count)} cases · ${inr(h.predicted_amount)}</text>`;
  });
  const seenCase = {};
  forecast.forEach((f) => {
    const [x, y] = projectPoint(f.latitude, f.longitude, bounds);
    const col = riskColor(f.risk_score);
    if (!seenCase[f.atm_code]) seenCase[f.atm_code] = true;
    html += `<circle class="f-ring" cx="${x}" cy="${y}" r="11" fill="none" stroke="${col}" stroke-width="2" stroke-dasharray="4 3" filter="url(#glow)"/>`;
    html += `<circle class="f-core" cx="${x}" cy="${y}" r="4" fill="${col}"/>`;
    html += `<text x="${x + 14}" y="${y - 4}" fill="${col}" font-size="11">${esc(f.atm_code || "ATM")} · CASE ${esc(f.case_number)}</text>`;
    html += `<text x="${x + 14}" y="${y + 9}" fill="#849396" font-size="10">RISK ${pct(f.risk_score)} · ${f.rank === 1 ? "TOP NODE" : "NODE " + f.rank}</text>`;
  });
  casesPts.forEach((c) => {
    const [x, y] = projectPoint(c.latitude, c.longitude, bounds);
    const col = riskColor(c.current_risk_score);
    html += `<rect class="case-node" x="${x - 6}" y="${y - 6}" width="12" height="12" transform="rotate(45 ${x} ${y})" fill="none" stroke="${col}" stroke-width="2" filter="url(#glow)"/>`;
    html += `<text x="${x + 10}" y="${y - 4}" fill="${col}" font-size="11">CASE ${esc(c.case_number)}</text>`;
  });
  html += "</g>";
  svg.innerHTML = html;
  svg.querySelectorAll("circle.pulse-ring").forEach((n) => { n.style.display = S.mapFilter.hotspots ? "block" : "none"; });
  svg.querySelectorAll("circle.hs-core").forEach((n) => { n.style.display = S.mapFilter.hotspots ? "" : "none"; });
  svg.querySelectorAll("rect.case-node").forEach((n) => { n.style.display = S.mapFilter.cases ? "" : "none"; });
  svg.querySelectorAll("circle.f-ring, circle.f-core").forEach((n) => { n.style.display = S.mapFilter.atms ? "" : "none"; });
  $("#map-meta").textContent = "GRID: IND-NORTH-04 · " + points.length + " NODES · " + hotspots.length + " HOTSPOTS";
}

function renderIncidentStream() {
  const el = $("#incident-stream");
  const list = (S.cases || []).slice().sort((a, b) => new Date(b.reported_at || b.opened_at) - new Date(a.reported_at || a.opened_at)).slice(0, 6);
  el.innerHTML = list.length
    ? list.map((c) => `
      <button data-case="${c.id}" class="w-full flex items-center gap-3 rounded border border-outline-variant/40 bg-surface/40 hover:border-primary-container/50 hover:bg-surface-container px-3 py-2.5 text-left transition">
        <span class="w-2 h-2 rounded-full shrink-0" style="background:${riskColor(c.current_risk_score)}"></span>
        <span class="min-w-0 flex-1">
          <span class="block font-mono-data-sm text-on-surface truncate">${esc(c.case_number)} · ${esc(c.fraud_type)}</span>
          <span class="block text-[11px] text-on-surface-variant truncate">${esc(c.title)}</span>
        </span>
        <span class="font-mono-data-sm shrink-0" style="color:${riskColor(c.current_risk_score)}">${pct(c.current_risk_score)}</span>
        <span class="font-mono-data-sm text-on-surface-variant shrink-0 hidden sm:block">${timeAgo(c.reported_at || c.opened_at)}</span>
      </button>`).join("")
    : '<div class="font-mono-data-sm text-on-surface-variant py-4 text-center">NO CASES ON FILE</div>';
  $$("[data-case]", el).forEach((b) => b.addEventListener("click", () => { openCase(b.dataset.case); }));
}

function renderSignalStream() {
  const el = $("#signal-stream");
  const alerts = (S.alerts || []).slice().sort((a, b) => new Date(b.acknowledged_at || 0) - new Date(a.acknowledged_at || 0)).slice(0, 6);
  if (!alerts.length) {
    el.innerHTML = '<div class="font-mono-data-sm text-on-surface-variant py-4 text-center">NO ALERTS — ENGINE QUIET</div>';
    return;
  }
  el.innerHTML = alerts.map((a) => `
    <button data-alert="${a.id}" class="w-full text-left rounded border px-3 py-2.5 font-mono-data-sm border-outline-variant/40 bg-surface/40 hover:bg-surface-container transition">
      <span class="flex items-center gap-2">
        <span class="w-1.5 h-1.5 rounded-full shrink-0" style="background:${a.severity === "CRITICAL" ? "#ffb4ab" : a.severity === "HIGH" ? "#ffb95f" : "#4cd6fb"}"></span>
        <span class="text-on-surface truncate flex-1">${esc(a.title)}</span>
        <span class="text-on-surface-variant shrink-0">${a.acknowledged_at ? timeAgo(a.acknowledged_at) : "OPEN"}</span>
      </span>
      <span class="flex items-center gap-2 mt-1 pl-3.5">
        <span class="text-primary">${(a.risk_score === null || a.risk_score === undefined) ? "RISK —" : pct(a.risk_score)}</span>
        <span class="text-on-surface-variant truncate">${esc(a.alert_type || "")}</span>
        <span class="text-on-surface-variant">${esc(a.status)}</span>
      </span>
    </button>`).join("");
  $$("[data-alert]", el).forEach((b) => b.addEventListener("click", () => {
    const alert = S.alerts.find((a) => a.id === b.dataset.alert);
    if (alert && alert.case_id) openCase(alert.case_id);
  }));
}

async function renderRiskDist() {
  const el = $("#risk-dist");
  let data;
  try {
    data = await API.get("/analytics/risk-distribution");
    const buckets = data.buckets || [];
    const total = buckets.reduce((a, b) => a + (b.count || 0), 0);
    el.innerHTML = buckets.map((b) => {
      const w = Math.min(100, (b.count / (total || 1)) * 100);
      return `<div><div class="flex justify-between font-mono-data-sm text-on-surface-variant mb-1"><span>${esc(b.bucket)}</span><span>${nf(b.count)}</span></div>
      <div class="ring-bar"><div style="width:${w}%;background:#00e5ff"></div></div></div>`;
    }).join("") || '<div class="text-on-surface-variant font-mono-data-sm">NO DISTRIBUTION DATA</div>';
  } catch (e) {
    el.innerHTML = '<div class="text-on-surface-variant font-mono-data-sm">' + esc(e.message) + "</div>";
  }
}

async function renderFlowChart() {
  const svg = $("#flow-chart");
  try {
    const series = (await API.get("/analytics/cases-over-time")) || [];
    if (!series.length) { svg.innerHTML = '<text x="160" y="75" text-anchor="middle" fill="#849396" font-size="12" font-family="JetBrains Mono">NO CASE FLOW DATA</text>'; return; }
    const W = 320, H = 144, pad = 26;
    const maxV = Math.max(1, ...series.map((p) => Math.max(p.opened || 0, p.resolved || 0)));
    const step = (W - pad * 2) / Math.max(1, series.length - 1);
    const pts = (key) => series.map((p, i) => {
      const x = pad + i * step;
      const y = H - 14 - ((p[key] || 0) / maxV) * (H - 34);
      return x + "," + y;
    }).join(" ");
    const line = (key, col) => `<polyline points="${pts(key)}" fill="none" stroke="${col}" stroke-width="2" opacity="0.9"/>`;
    let html = `<line x1="${pad}" y1="2" x2="${pad}" y2="${H - 14}" stroke="#3b494c"/><line x1="${pad}" y1="${H - 14}" x2="${W - 8}" y2="${H - 14}" stroke="#3b494c"/>`;
    html += line("opened", "#00e5ff");
    html += line("resolved", "#ffb95f");
    series.forEach((p, i) => {
      const x = pad + i * step;
      html += `<text x="${x}" y="${H - 2}" text-anchor="middle" fill="#849396" font-size="8" font-family="JetBrains Mono">${esc(p.period)}</text>`;
    });
    html += `<text x="6" y="12" fill="#9cf0ff" font-size="9" font-family="JetBrains Mono">OPENED</text><text x="${W - 8}" y="${H - 2}" text-anchor="end" fill="#ffb95f" font-size="9" font-family="JetBrains Mono">RESOLVED</text>`;
    svg.innerHTML = html;
  } catch (e) {
    svg.innerHTML = '<text x="160" y="75" text-anchor="middle" fill="#849396" font-size="12" font-family="JetBrains Mono">' + esc(e.message) + "</text>";
  }
}

function renderAlertCenter() {
  const el = $("#alert-center");
  const open = (S.alerts || []).filter((a) => a.status === "OPEN" || a.status === "ACKNOWLEDGED").slice(0, 8);
  if (!open.length) {
    el.innerHTML = '<div class="font-mono-data-sm text-on-surface-variant py-4 text-center">ALERT CENTER CLEAR</div>';
    return;
  }
  el.innerHTML = open.map((a) => `
    <div class="flex items-start gap-2.5 rounded border border-outline-variant/40 bg-surface/40 px-3 py-2.5">
      <span class="w-1.5 h-1.5 rounded-full mt-1.5 shrink-0" style="background:${a.severity === "CRITICAL" ? "#ffb4ab" : a.severity === "HIGH" ? "#ffb95f" : "#4cd6fb"}"></span>
      <div class="min-w-0 flex-1">
        <div class="font-mono-data-sm text-on-surface truncate">${esc(a.title)}</div>
        <div class="font-mono-data-xs text-on-surface-variant mt-0.5">${esc(a.alert_type)} · ${esc(a.status)}${a.risk_score !== null && a.risk_score !== undefined ? " · " + pct(a.risk_score) : ""}</div>
      </div>
      ${a.status !== "ACKNOWLEDGED" ? '<button data-ack="' + a.id + '" class="font-label-caps text-primary hover:underline shrink-0">ACK</button>' : ""}
    </div>`).join("");
  $$("[data-ack]", el).forEach((b) =>
    b.addEventListener("click", () => ackAlert(b.dataset.ack)));
}

async function ackAlert(id) {
  try {
    await API.post("/alerts/" + id + "/acknowledge", { note: "Acknowledged from Command Center" });
    toast("Alert acknowledged");
    await refreshDashboard();
  } catch (e) { toast(e.message || "Ack failed", "error"); }
}
async function ackAllAlerts() {
  const open = (S.alerts || []).filter((a) => a.status === "OPEN");
  if (!open.length) { toast("No open alerts"); return; }
  let ok = 0;
  for (const a of open) {
    try { await API.post("/alerts/" + a.id + "/acknowledge", { note: "Bulk ACK from Command Center" }); ok++; }
    catch (e) { /* skip */ }
  }
  toast(ok + " of " + open.length + " alerts acknowledged");
  await refreshDashboard();
}

/* ============================ CASES LIST ============================ */
async function renderCasesList() {
  pageTitle("INVESTIGATIONS", "LIVE CASE FILE INDEX");
  navActive("cases");
  const root = $("#view-root");
  root.innerHTML = `
    <div class="card p-4">
      <div class="flex items-center justify-between flex-wrap gap-3 mb-4">
        <div class="flex items-center gap-2 flex-wrap">
          <input id="case-search" placeholder="SEARCH CASE / ID / VICTIM…" class="w-56 bg-surface-dim border border-outline-variant rounded px-3 py-2 font-mono-data-sm text-on-surface placeholder:text-on-surface-variant/50 focus:outline-none focus:border-primary-container"/>
          <select id="case-status-filter" class="bg-surface-dim border border-outline-variant rounded px-2 py-2 font-mono-data-sm text-on-surface focus:outline-none"><option value="">ALL STATUS</option></select>
          <select id="case-fraud-filter" class="bg-surface-dim border border-outline-variant rounded px-2 py-2 font-mono-data-sm text-on-surface focus:outline-none"><option value="">ALL FRAUD TYPE</option></select>
        </div>
        <button id="new-case-btn" class="flex items-center gap-2 bg-primary-container text-on-primary-container font-label-caps rounded px-4 py-2.5 hover:brightness-110 transition">
          <span class="material-symbols-outlined text-base">add</span>NEW CASE
        </button>
      </div>
      <div class="overflow-x-auto"><table class="cdata" id="cases-table">
        <thead><tr>
          <th>CASE NO</th><th>FRAUD TYPE</th><th>STATUS</th><th>PRIORITY</th><th>AMOUNT</th>
          <th>RISK</th><th class="text-center">COMPL</th><th class="text-center">TX</th><th class="text-center">PRED</th><th class="text-center">ALRT</th>
          <th>REPORTED</th><th>INVESTIGATOR</th><th></th>
        </tr></thead><tbody id="cases-tbody"></tbody></table></div>
      <div id="cases-foot" class="mt-3 font-mono-data-sm text-on-surface-variant text-center py-2"></div>
    </div>`;
  $("#new-case-btn").addEventListener("click", openNewCaseModal);
  $("#case-search").addEventListener("input", applyCaseFilters);
  const frag = {};
  try {
    S.cases = (await API.get("/cases?page=1&page_size=200")).items || [];
    const stats = await API.get("/cases/stats");
    frag.statuses = Object.keys(stats.by_status || {});
    frag.frauds = Object.keys(stats.by_fraud_type || {});
  } catch (e) { toast(e.message || "Cannot load cases", "error"); S.cases = []; }
  const statusSel = $("#case-status-filter");
  const fraudSel = $("#case-fraud-filter");
  (frag.statuses || []).forEach((s) => { const o = document.createElement("option"); o.value = s; o.textContent = humanize(s); statusSel.appendChild(o); });
  (frag.frauds || []).forEach((s) => { const o = document.createElement("option"); o.value = s; o.textContent = humanize(s); fraudSel.appendChild(o); });
  statusSel.addEventListener("change", applyCaseFilters);
  fraudSel.addEventListener("change", applyCaseFilters);
  applyCaseFilters();
}
function applyCaseFilters() {
  const q = ($("#case-search").value || "").toLowerCase();
  const st = $("#case-status-filter").value;
  const fr = $("#case-fraud-filter").value;
  const list = caseModel() || [];
  const filtered = list.filter((c) =>
    (!st || c.status === st) && (!fr || c.fraud_type === fr) &&
    (!q || (c.case_number + " " + (c.title || "") + " " + (c.victim_name || "") + " " + (c.victim_masked_phone || "")).toLowerCase().includes(q)));
  const tbody = $("#cases-tbody");
  if (!tbody) return;
  tbody.innerHTML = filtered.length
    ? filtered.map((c) => `
      <tr class="row-click" data-case="${c.id}">
        <td class="text-primary font-semibold">${esc(c.case_number)}</td>
        <td>${esc(humanize(c.fraud_type))}</td>
        <td><span class="status-chip px-2 py-0.5 rounded border border-outline-variant text-on-surface-variant" data-status="${esc(c.status)}">${esc(humanize(c.status))}</span></td>
        <td style="color:${c.priority === "CRITICAL" ? "#ffb4ab" : c.priority === "HIGH" ? "#ffb95f" : c.priority === "MEDIUM" ? "#9cf0ff" : "#4cd6fb"}">${esc(c.priority)}</td>
        <td>${inr(c.amount)}</td>
        <td style="color:${riskColor(c.current_risk_score)}">${c.current_risk_score === null ? "—" : pct(c.current_risk_score)}</td>
        <td class="text-center">${nf(c.complaint_count)}</td>
        <td class="text-center">${nf(c.transaction_count)}</td>
        <td class="text-center">${nf(c.prediction_count)}</td>
        <td class="text-center">${nf(c.alert_count)}</td>
        <td class="text-on-surface-variant">${c.reported_at ? fmtDT(c.reported_at).replace(/\d{2}:\d{2}:\d{2}/, "") : "—"}</td>
        <td class="text-on-surface-variant truncate max-w-[120px]">${esc(c.investigation_officer || c.assigned_investigator || "—")}</td>
        <td class="text-right whitespace-nowrap"><button class="font-label-caps text-primary hover:underline">OPEN</button></td>
      </tr>`).join("")
    : '<tr><td colspan="13" class="text-center text-on-surface-variant py-8">NO CASES MATCH — CLEAR FILTERS OR REGISTER A COMPLAINT</td></tr>';
  $("#cases-foot").textContent = filtered.length + " of " + list.length + " case files";
  $$("#cases-tbody tr").forEach((tr) => tr.addEventListener("click", () => openCase(tr.dataset.case)));
}
function caseModel() {
  return S.cases || [];
}
function openCase(id) {
  S.caseId = id;
  S.view = "case";
  go("case");
}

/* ------------------------------ NEW CASE ------------------------------ */
function openNewCaseModal() {
  const modal = openModal(null, false);
  modal.title("REGISTER CASE / COMPLAINT");
  modal.body(`
    <div class="grid grid-cols-2 gap-3">
      <label class="col-span-2 block"><span class="font-label-caps text-on-surface-variant">CASE TITLE *</span><input id="nc-title" class="mt-1.5 w-full bg-surface-dim border border-outline-variant rounded px-3 py-2 font-mono-data-sm text-on-surface"/></label>
      <label class="col-span-2 block"><span class="font-label-caps text-on-surface-variant">DESCRIPTION</span><textarea id="nc-desc" rows="2" class="mt-1.5 w-full bg-surface-dim border border-outline-variant rounded px-3 py-2 font-mono-data-sm text-on-surface"></textarea></label>
      <label class="block"><span class="font-label-caps text-on-surface-variant">FRAUD TYPE</span><select id="nc-fraud" class="mt-1.5 w-full bg-surface-dim border border-outline-variant rounded px-2 py-2 font-mono-data-sm text-on-surface"><option>UPI_FRAUD</option><option>PHISHING</option><option>OTP_FRAUD</option><option>SIM_SWAP</option><option>ACCOUNT_TAKEOVER</option><option>SOCIAL_ENGINEERING</option><option>INVESTMENT_FRAUD</option><option>TASK_FRAUD</option><option>SEXTORTION</option><option>LOTTERY_PRIZE_FRAUD</option><option>FAKE_CUSTOMER_SERVICE</option><option>OTHER</option></select></label>
      <label class="block"><span class="font-label-caps text-on-surface-variant">PRIORITY</span><select id="nc-priority" class="mt-1.5 w-full bg-surface-dim border border-outline-variant rounded px-2 py-2 font-mono-data-sm text-on-surface"><option>MEDIUM</option><option>LOW</option><option>HIGH</option><option>CRITICAL</option></select></label>
      <label class="block"><span class="font-label-caps text-on-surface-variant">AMOUNT ₹</span><input id="nc-amount" type="number" min="0" value="0" class="mt-1.5 w-full bg-surface-dim border border-outline-variant rounded px-3 py-2 font-mono-data-sm text-on-surface"/></label>
      <label class="block"><span class="font-label-caps text-on-surface-variant">SOURCE</span><select id="nc-source" class="mt-1.5 w-full bg-surface-dim border border-outline-variant rounded px-2 py-2 font-mono-data-sm text-on-surface"><option>PORTAL</option><option>HELPLINE</option><option>BANK_REPORT</option><option>POLICE_STATION</option><option>I4C_REFERRAL</option><option>API_PARTNER</option></select></label>
      <label class="block"><span class="font-label-caps text-on-surface-variant">VICTIM NAME</span><input id="nc-vname" class="mt-1.5 w-full bg-surface-dim border border-outline-variant rounded px-3 py-2 font-mono-data-sm text-on-surface"/></label>
      <label class="block"><span class="font-label-caps text-on-surface-variant">VICTIM PHONE</span><input id="nc-vphone" class="mt-1.5 w-full bg-surface-dim border border-outline-variant rounded px-3 py-2 font-mono-data-sm text-on-surface"/></label>
      <label class="block"><span class="font-label-caps text-on-surface-variant">VICTIM EMAIL</span><input id="nc-vemail" class="mt-1.5 w-full bg-surface-dim border border-outline-variant rounded px-3 py-2 font-mono-data-sm text-on-surface"/></label>
      <label class="block"><span class="font-label-caps text-on-surface-variant">VICTIM A/C NO</span><input id="nc-vacct" class="mt-1.5 w-full bg-surface-dim border border-outline-variant rounded px-3 py-2 font-mono-data-sm text-on-surface"/></label>
      <label class="block"><span class="font-label-caps text-on-surface-variant">STATE</span><input id="nc-state" class="mt-1.5 w-full bg-surface-dim border border-outline-variant rounded px-3 py-2 font-mono-data-sm text-on-surface"/></label>
      <label class="block"><span class="font-label-caps text-on-surface-variant">DISTRICT</span><input id="nc-district" class="mt-1.5 w-full bg-surface-dim border border-outline-variant rounded px-3 py-2 font-mono-data-sm text-on-surface"/></label>
    </div>`);
  modal.foot('<button class="px-4 py-2 border border-outline-variant rounded font-label-caps text-on-surface-variant hover:text-on-surface" data-c="cancel">CANCEL</button><button class="px-4 py-2 bg-primary-container text-on-primary-container rounded font-label-caps" data-c="save">REGISTER CASE</button>');
  $('[data-c="cancel"]', modal.el).addEventListener("click", () => modal.close());
  $('[data-c="save"]', modal.el).addEventListener("click", async () => {
    const body = {
      title: $("#nc-title").value.trim(),
      description: $("#nc-desc").value.trim() || null,
      fraud_type: $("#nc-fraud").value,
      priority: $("#nc-priority").value,
      amount: Number($("#nc-amount").value) || 0,
      complaint_source: $("#nc-source").value,
    };
    const victim = {
      name: $("#nc-vname").value.trim() || null,
      phone: $("#nc-vphone").value.trim() || null,
      email: $("#nc-vemail").value.trim() || null,
      account_number: $("#nc-vacct").value.trim() || null,
    };
    if ($("#nc-state").value) body.state = $("#nc-state").value.trim();
    if ($("#nc-district").value) body.district = $("#nc-district").value.trim();
    if (victim.name || victim.phone || victim.email || victim.account_number) body.victim = victim;
    if (!body.title || body.title.length < 3) { toast("Case title is required (min 3 chars)", "error"); return; }
    try {
      const created = await API.post("/cases", body);
      toast("Case " + created.case_number + " registered");
      modal.close();
      openCase(created.id);
    } catch (e) { toast(e.message || "Registration failed", "error"); }
  });
}

/* ============================ CASE WORKSPACE ============================ */
async function renderCaseWorkspace() {
  navActive("cases");
  const root = $("#view-root");
  root.innerHTML = '<div class="text-center py-24"><span class="material-symbols-outlined text-4xl text-primary animate-spin spin">progress_activity</span></div>';
  try {
    await loadCaseBundle();
  } catch (e) {
    root.innerHTML = '<div class="card p-8 text-center font-mono-data-md text-error">' + esc(e.message || "Cannot load case") + "</div>";
    return;
  }
  const c = S.case;
  const out = c.out;
  const loc = (c.locations && c.locations[0]) || null;
  pageTitle("CASE INVESTIGATION // " + out.case_number, humanize(out.status) + " · " + out.fraud_type);
  $("#fab-sim").classList.remove("hidden");
  $("#fab-sim").classList.add("flex");
  $("#fab-sim").textContent = "RUN INTERVENTION SIM";
  root.innerHTML = `
    <div class="card p-4">
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div class="min-w-0">
          <div class="flex items-center gap-3 flex-wrap">
            <span class="font-headline-lg text-primary">${esc(out.case_number)}</span>
            <span class="font-mono-data-sm border border-outline-variant rounded-full px-2.5 py-0.5 text-on-surface-variant">${esc(humanize(out.fraud_type))}</span>
            <span class="font-mono-data-sm rounded-full px-2.5 py-0.5" style="background:${riskColor(out.current_risk_score)}22;color:${riskColor(out.current_risk_score)};border:1px solid ${riskColor(out.current_risk_score)}55">RISK ${pct(out.current_risk_score)}</span>
          </div>
          <div class="text-lg mt-2">${esc(out.title)}</div>
          <div class="font-mono-data-sm text-on-surface-variant mt-1 flex flex-wrap gap-x-4 gap-y-1" id="case-meta-line">
            <span>STATUS: ${esc(humanize(out.status))}</span><span>PRIORITY: ${esc(out.priority)}</span>
            <span>EXPOSURE: ${inr(out.amount)}</span><span>SRC: ${esc(out.complaint_source)}</span>
            <span>INV: ${esc(out.investigation_officer || out.assigned_investigator || "—")}</span>
          </div>
        </div>
        <div class="flex items-center gap-2 flex-wrap">
          <select id="case-status-select" class="bg-surface-dim border border-outline-variant rounded px-2 py-2 font-mono-data-sm text-on-surface"></select>
          <button data-case-action="predict" class="flex items-center gap-1.5 bg-primary-container text-on-primary-container font-label-caps rounded px-3.5 py-2.5 hover:brightness-110 transition">
            <span class="material-symbols-outlined text-base">auto_awesome</span>RUN PREDICTION
          </button>
          <button data-case-action="sim" class="flex items-center gap-1.5 border border-primary-container/60 text-primary font-label-caps rounded px-3.5 py-2.5 hover:bg-primary-container/10 transition">
            <span class="material-symbols-outlined text-base">model_training</span>SIMULATE
          </button>
          <button data-case-action="event" class="flex items-center gap-1.5 border border-outline-variant text-on-surface-variant font-label-caps rounded px-3.5 py-2.5 hover:text-on-surface transition">
            <span class="material-symbols-outlined text-base">note_add</span>ADD EVENT
          </button>
          <button data-case-action="export" class="flex items-center gap-1.5 border border-outline-variant text-on-surface-variant font-label-caps rounded px-3.5 py-2.5 hover:text-on-surface transition">
            <span class="material-symbols-outlined text-base">print</span>EXPORT
          </button>
        </div>
      </div>
    </div>

    <div class="grid grid-cols-1 xl:grid-cols-3 gap-4">
      <div class="xl:col-span-2 space-y-4">
        <div class="grid grid-cols-1 md:grid-cols-3 gap-4" id="golden-hour"></div>

        <div class="card p-4">
          <div class="flex items-center justify-between mb-3">
            <div><div class="font-label-caps text-primary/80">TACTICAL FORECAST</div><div class="font-headline-sm mt-1">TOP PREDICTED CASH-OUT NODES</div></div>
            <span class="font-mono-data-sm text-on-surface-variant" id="forecast-meta"></span>
          </div>
          <div class="map-canvas h-72 bg-surface-dim border border-outline-variant rounded-lg">
            <div class="grid-layer"></div>
            <svg id="case-map" class="relative w-full h-full"></svg>
          </div>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div class="card p-4">
            <div class="font-label-caps text-on-surface-variant mb-3">WHY THIS LOCATION — SIGNAL CONTRIBUTORS</div>
            <div id="why-location" class="space-y-3"></div>
          </div>
          <div class="card p-4">
            <div class="font-label-caps text-on-surface-variant mb-3">TOP PREDICTED ATMs</div>
            <div id="top-atms" class="space-y-3"></div>
          </div>
        </div>

        <div class="card p-4">
          <div class="flex items-center justify-between mb-3">
            <div><div class="font-label-caps text-on-surface-variant">FRAUD NETWORK GRAPH</div><div class="font-headline-sm mt-1">ENTITY/LINK TOPOLOGY</div></div>
            <div class="flex items-center gap-3 font-mono-data-sm text-on-surface-variant" id="net-metrics"></div>
          </div>
          <div class="map-canvas h-80 bg-surface-dim border border-outline-variant rounded-lg">
            <div id="net-canvas" class="relative w-full h-full"></div>
          </div>
        </div>
      </div>

      <div class="space-y-4">
        <div class="card p-4">
          <div class="font-label-caps text-on-surface-variant mb-2">METADATA LEDGER</div>
          <dl id="case-ledger"></dl>
        </div>
        <div class="card p-4">
          <div class="font-label-caps text-on-surface-variant mb-2">RISK SIGNALS</div>
          <div id="risk-signals"></div>
        </div>
        <div class="card p-4">
          <div class="font-label-caps text-on-surface-variant mb-2">AUDIT TRAIL — RECENT EVENTS</div>
          <div class="flex items-center justify-between mb-2">
            <button data-case-action="event" class="font-mono-data-sm text-primary hover:underline">+ ADD EVENT</button>
          </div>
          <div id="case-timeline" class="relative pl-5 space-y-3"></div>
        </div>
      </div>
    </div>

    <div class="card p-4">
      <div class="font-label-caps text-on-surface-variant mb-3">TRANSACTION LEDGER</div>
      <div class="overflow-x-auto"><table class="cdata">
        <thead><tr><th>REF</th><th>AMOUNT</th><th>DIR</th><th>TYPE</th><th>CHANNEL</th><th>TIMESTAMP</th><th>FROM</th><th>TO</th><th>MERCHANT</th></tr></thead>
        <tbody id="tx-tbody"></tbody></table></div>
    </div>`;
  bindCaseActions();
  renderGoldenHour();
  paintCaseMap();
  renderWhyLocation();
  renderTopAtms();
  renderNetwork();
  renderLedger();
  renderRiskSignals();
  renderTimeline();
  renderTransactions();
}

async function loadCaseBundle() {
  const id = S.caseId;
  if (!id) { S.caseId = S.cases && S.cases[0] ? S.cases[0].id : null; return renderCaseWorkspace(); }
  const [out, locations, predictions, timeline, network, tx, feature] = await Promise.all([
    API.get("/cases/" + id),
    API.get("/cases/" + id + "/predictions/latest-locations"),
    API.get("/cases/" + id + "/predictions"),
    API.get("/cases/" + id + "/timeline"),
    API.get("/entities/cases/" + id + "/network"),
    API.get("/transactions/cases/" + id + "?page=1&page_size=50"),
    API.get("/transactions/cases/" + id + "/feature-vector"),
  ]);
  S.case = {
    out,
    locations: Array.isArray(locations) ? locations : [],
    predictions: Array.isArray(predictions) ? predictions : [],
    timeline: Array.isArray(timeline) ? timeline : [],
    network: (network.nodes || (network.graph && network.graph.nodes)) ? network : (network.graph || network),
    tx: (tx && tx.items) || [],
    feature,
  };
  setApiStatus(true);
}

async function refreshCaseData(silent) {
  if (!S.case) return;
  try {
    await loadCaseBundle();
    if (!silent) return;
    renderGoldenHour();
    paintCaseMap();
    renderWhyLocation();
    renderTopAtms();
    renderLedger();
    renderRiskSignals();
    renderTimeline();
    renderTransactions();
  } catch (e) { /* keep stale */ }
}

function bindCaseActions() {
  const statusSel = $("#case-status-select");
  const opts = ["NEW", "UNDER_ANALYSIS", "PREDICTION_ACTIVE", "ALERTED", "INVESTIGATION_ACTIVE", "RESOLVED", "CLOSED"];
  statusSel.innerHTML = opts.map((s) => '<option' + (s === S.case.out.status ? " selected" : "") + ">" + s + "</option>").join("");
  statusSel.addEventListener("change", async () => {
    try {
      const updated = await API.post("/cases/" + S.caseId + "/status", { status: statusSel.value });
      S.case.out.status = updated.status;
      toast("Status → " + updated.status);
      await refreshCaseData();
    } catch (e) { toast(e.message || "Status update failed", "error"); }
  });
  $$("[data-case-action]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const a = btn.dataset.caseAction;
      if (a === "predict") runPrediction();
      else if (a === "sim") { S.simCaseId = S.caseId; go("sim"); }
      else if (a === "event") openEventModal();
      else if (a === "export") window.print();
    });
  });
}

async function runPrediction() {
  toast("Queueing prediction run…");
  try {
    const res = await API.post("/cases/" + S.caseId + "/predict", { horizon: "H24", top_k: 5 });
    toast((res.queued ? "Prediction queued" : "Prediction completed") + " · " + (res.prediction_id || ""));
    setTimeout(async () => {
      await loadCaseBundle();
      renderGoldenHour();
      paintCaseMap();
      renderWhyLocation();
      renderTopAtms();
      renderLedger();
      renderRiskSignals();
      renderTimeline();
    }, 1600);
  } catch (e) { toast(e.message || "Prediction failed", "error"); }
}

function openEventModal() {
  const modal = openModal(null, false);
  const types = ["NOTE_ADDED", "COMPLAINT_RECEIVED", "TRANSACTION_DETECTED", "ENTITY_IDENTIFIED", "NETWORK_ANALYZED", "PREDICTION_GENERATED", "ALERT_CREATED", "INTERVENTION_SIMULATED", "INTERVENTION_EXECUTED", "OUTCOME_RECORDED", "CASE_STATUS_CHANGED"];
  modal.title("RECORD TIMELINE EVENT");
  modal.body(`
    <label class="block mb-4"><span class="font-label-caps text-on-surface-variant">EVENT TYPE</span>
      <select id="ev-type" class="mt-1.5 w-full bg-surface-dim border border-outline-variant rounded px-2 py-2 font-mono-data-sm text-on-surface">${types.map((t) => '<option>' + t + "</option>").join("")}</select></label>
    <label class="block"><span class="font-label-caps text-on-surface-variant">DESCRIPTION *</span>
      <textarea id="ev-desc" rows="3" class="mt-1.5 w-full bg-surface-dim border border-outline-variant rounded px-3 py-2 font-mono-data-sm text-on-surface"></textarea></label>`);
  modal.foot('<button class="px-4 py-2 border border-outline-variant rounded font-label-caps text-on-surface-variant hover:text-on-surface" data-c="cancel">CANCEL</button><button class="px-4 py-2 bg-primary-container text-on-primary-container rounded font-label-caps" data-c="save">SAVE EVENT</button>');
  $('[data-c="cancel"]', modal.el).addEventListener("click", () => modal.close());
  $('[data-c="save"]', modal.el).addEventListener("click", async () => {
    const desc = $("#ev-desc").value.trim();
    if (!desc) { toast("Description is required", "error"); return; }
    try {
      await API.post("/cases/" + S.caseId + "/events", { event_type: $("#ev-type").value, description: desc, metadata: {} });
      toast("Event recorded on chain");
      modal.close();
      await loadCaseBundle();
      renderTimeline();
    } catch (e) { toast(e.message || "Event failed", "error"); }
  });
}

function renderGoldenHour() {
  const el = $("#golden-hour");
  const c = S.case;
  const loc = c.locations[0] || null;
  const pred = (c.predictions && c.predictions[0]) || null;
  const win = loc && loc.time_window;
  const cards = [];
  cards.push({
    label: "CASH-OUT WINDOW COUNTDOWN",
    big: countdown(win && win.end),
    sub: (win && win.start ? "WINDOW " + fmtClock(win.start) : "NO ACTIVE FORECAST WINDOW"),
    bar: win ? Math.min(1, (new Date(win.start).getTime() - Date.now()) / (86400000)) : 0,
    barc: "#00e5ff",
  });
  cards.push({
    label: "RISK VELOCITY",
    big: pct(c.out.current_risk_score),
    sub: riskLabel(c.out.current_risk_score) + " PRIORITY · " + c.out.priority,
    bar: c.out.current_risk_score || 0,
    barc: riskColor(c.out.current_risk_score),
  });
  cards.push({
    label: "FORECAST CONFIDENCE",
    big: pct(loc ? loc.confidence : null),
    sub: loc ? "TOP NODE " + (loc.atm_code || "-") : "RUN PREDICTION TO POPULATE",
    bar: loc ? loc.confidence : 0,
    barc: "#ffb95f",
  });
  el.innerHTML = cards.map((k, i) => `
    <div class="card p-4 ${i === 0 ? "md:col-span-1" : ""}">
      <div class="font-label-caps text-on-surface-variant mb-3">${k.label}</div>
      <div class="font-headline-lg countdown ${i === 0 ? "text-primary" : ""}">${k.big}</div>
      <div class="font-mono-data-sm text-on-surface-variant mt-2 mb-3 truncate">${esc(k.sub)}</div>
      <div class="ring-bar"><div style="width:${fmtBar(k.bar)}%;background:${k.barc};transition:width .5s ease"></div></div>
    </div>`).join("");
  if (!loc && pred) el.classList.add("opacity-90");
}

function paintCaseMap() {
  const svg = $("#case-map");
  if (!svg) return;
  const locs = S.case.locations;
  const bounds = computeBounds(locs.map((l) => ({ latitude: l.latitude, longitude: l.longitude })));
  if (!bounds || !locs.length) {
    svg.innerHTML = '<text x="500" y="140" text-anchor="middle" fill="#849396" font-family="JetBrains Mono" font-size="13">NO PREDICTED NODES — RUN PREDICTION</text>';
    $("#forecast-meta").textContent = "0 NODES";
    return;
  }
  const W = 1000, H = 280;
  let html = '<defs><filter id="cglow"><feGaussianBlur stdDeviation="6" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter></defs>';
  const sorted = locs.slice().sort((a, b) => a.rank - b.rank);
  const ranked = sorted.map((l, i) => {
    const [x, y] = projectPoint(l.latitude, l.longitude, bounds, H);
    return { l, x, y, i };
  });
  html += '<path d="' + ranked.map((p, i) => (i === 0 ? "M" : "L") + p.x + "," + p.y).join(" ") + '" fill="none" stroke="#00e5ff55" stroke-width="1.5" stroke-dasharray="6 6"/>';
  ranked.forEach((p) => {
    const r = Math.max(8, Math.round(p.l.risk_score * 22));
    const col = riskColor(p.l.risk_score);
    html += `<circle cx="${p.x}" cy="${p.y}" r="${r + 4}" fill="${col}" opacity="0.15" class="pulse-ring" style="transform-origin:${p.x}px ${p.y}px"/>`;
    html += `<circle cx="${p.x}" cy="${p.y}" r="${r}" fill="${col}" opacity="0.8" filter="url(#cglow)"/>`;
    html += `<text x="${p.x + r + 6}" y="${p.y - 4}" fill="#e0e2e9" font-size="12" font-family="JetBrains Mono">${p.i + 1}. ${esc(p.l.atm_code || "-")} — ${esc(p.l.atm_name || "ATM")}</text>`;
    html += `<text x="${p.x + r + 6}" y="${p.y + 12}" fill="${col}" font-size="11" font-family="JetBrains Mono">RISK ${pct(p.l.risk_score)} · CONF ${pct(p.l.confidence)}</text>`;
    if (p.l.time_window && p.l.time_window.start) {
      html += `<text x="${p.x + r + 6}" y="${p.y + 26}" fill="#849396" font-size="10" font-family="JetBrains Mono">${fmtClock(p.l.time_window.start)}→${fmtClock(p.l.time_window.end)}</text>`;
    }
  });
  svg.innerHTML = html;
  $("#forecast-meta").textContent = locs.length + " NODES · " + (S.case.out.model_name ? "MODEL " + esc(S.case.predictions.length ? (S.case.predictions[0].model_name || "-") : "-") : "");
}
function projectPoint(lat, lon, bounds, H) {
  const x = ((lon - bounds.minLon) / ((bounds.maxLon - bounds.minLon) || 1)) * 960 + 20;
  const h = H || 520;
  const y = h - 14 - ((lat - bounds.minLat) / ((bounds.maxLat - bounds.minLat) || 1)) * (h - 28);
  return [x, y];
}

function renderWhyLocation() {
  const el = $("#why-location");
  const loc = S.case.locations[0];
  const factors = (loc && loc.contributing_factors) || [];
  if (!factors.length) {
    el.innerHTML = '<div class="font-mono-data-sm text-on-surface-variant py-4 text-center">NO SIGNAL CONTRIBUTORS — RUN PREDICTION</div>';
    return;
  }
  const maxAbs = Math.max(1, ...factors.map((f) => Math.abs(f.impact || 0)));
  el.innerHTML = factors.map((f) => {
    const w = Math.abs(f.impact || 0) / maxAbs * 100;
    const pos = (f.impact || 0) >= 0;
    return `
      <div>
        <div class="flex justify-between mb-1 font-mono-data-sm">
          <span class="text-on-surface truncate pr-2">${esc(f.factor || humanize(f.name || ""))}</span>
          <span class="${pos ? "val-pos" : "val-neg"}">${pos ? "+" : ""}${Math.round(f.impact * 100)}</span>
        </div>
        <div class="ring-bar"><div style="width:${w}%;background:${pos ? "#00e5ff" : "#ffb4ab"}"></div></div>
        ${f.details ? '<div class="font-body-sm text-on-surface-variant mt-1">' + esc(f.details) + "</div>" : ""}
      </div>`;
  }).join("");
}

function renderTopAtms() {
  const el = $("#top-atms");
  const locs = S.case.locations.slice().sort((a, b) => a.rank - b.rank);
  if (!locs.length) {
    el.innerHTML = '<div class="font-mono-data-sm text-on-surface-variant py-4 text-center">NO PREDICTED NODES YET</div>';
    return;
  }
  el.innerHTML = locs.slice(0, 4).map((l) => `
    <div class="flex items-center gap-3 rounded border border-outline-variant/40 bg-surface/40 px-3 py-2.5">
      <span class="font-headline-lg shrink-0" style="color:${riskColor(l.risk_score)}">${l.rank}</span>
      <div class="min-w-0 flex-1">
        <div class="font-mono-data-md text-on-surface truncate">${esc(l.atm_code || "—")} <span class="text-on-surface-variant">·</span> ${esc(l.atm_name || "ATM")}</div>
        <div class="font-mono-data-sm text-on-surface-variant truncate">${l.time_window ? fmtClock(l.time_window.start) + " → " + fmtClock(l.time_window.end) : "—"}</div>
      </div>
      <div class="text-right shrink-0 font-mono-data-sm">
        <div style="color:${riskColor(l.risk_score)}">${pct(l.risk_score)}</div>
        <div class="text-on-surface-variant">${pct(l.confidence)} CONF</div>
      </div>
    </div>`).join("");
}

function renderNetwork() {
  const el = $("#net-canvas");
  const m = $("#net-metrics");
  const net = S.case.network;
  const nodes = (net && net.nodes) || [];
  const edges = (net && net.edges) || [];
  if (!nodes.length) {
    el.innerHTML = '<div class="h-full flex items-center justify-center font-mono-data-sm text-on-surface-variant">NO ENTITY GRAPH — LINK ENTITIES VIA DEVICE FLOW OR SEED</div>';
    m.textContent = "0 NODES · 0 LINKS";
    return;
  }
  const W = 900, H = 360;
  const cx = W / 2, cy = H / 2;
  const typeColor = {
    VICTIM: "#9cf0ff", SUSPECT: "#ffb4ab", ACCOUNT: "#4cd6fb", MULE_ACCOUNT: "#ffb95f",
    PHONE: "#c3f5ff", UPI: "#00e5ff", DEVICE: "#b3ebff", ATM: "#ff9aa8", CSP: "#ffc681",
    LOCATION: "#ffb95f", COMPLAINT: "#849396", TRANSACTION: "#849396", IP: "#ffddb8",
    EMAIL: "#b3ebff", BANK: "#ffddb8", POLICE_STATION: "#4cd6fb", PERSON: "#e0e2e9",
  };
  const ring = (t) => ([VICTIM, SUSPECT, ACCOUNT, MULE_ACCOUNT, PHONE, UPI, DEVICE, ATM, CSP, LOCATION].includes(t) ? 0 : 1);
  const types = Array.from(new Set(nodes.map((n) => n.type || "PERSON")));
  const positions = {};
  let idx = 0;
  nodes.forEach((n) => {
    const t = n.type || "PERSON";
    const r = t === "VICTIM" || t === "SUSPECT" ? 150 : t === "ATM" ? 220 : 250;
    const angle = (idx / Math.max(1, nodes.length)) * Math.PI * 2;
    positions[n.id] = { x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle) * 0.8 };
    idx++;
  });
  let html = '<defs><marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 Z" fill="#3b494c"/></marker></defs>';
  edges.forEach((e) => {
    const s = positions[e.source] || { x: cx, y: cy };
    const t = positions[e.target] || { x: cx, y: cy };
    const hot = e.confidence >= 0.7;
    html += `<line x1="${s.x}" y1="${s.y}" x2="${t.x}" y2="${t.y}" class="edge ${hot ? "hot" : ""}"/>`;
  });
  nodes.forEach((n) => {
    const p = positions[n.id];
    const col = typeColor[n.type] || "#e0e2e9";
    const core = ["VICTIM", "SUSPECT", "ATM"].includes(n.type);
    const r = core ? 16 : 10;
    html += `<g transform="translate(${p.x},${p.y})"><circle r="${r}" fill="${col}" opacity="0.16" class="pulse-ring" style="transform-origin:${p.x}px ${p.y}px"/>`;
    html += `<circle r="${r}" fill="${col}" opacity="${core ? 0.95 : 0.8}" filter="url(#glow)"/>`;
    html += `<text x="0" y="${r + 12}" text-anchor="middle" fill="#e0e2e9" font-size="10" font-family="JetBrains Mono">${esc(n.label || n.id)}</text></g>`;
  });
  html += `<g fill="#849396" font-family="JetBrains Mono" font-size="9"><text x="${cx}" y="14" text-anchor="middle">CANVAS: ENTITY TOPOLOGY — ${types.join(" / ")}</text></g>`;
  el.innerHTML = '<svg class="w-full h-full" viewBox="0 0 900 360">' + html + "</svg>";
  const metrics = net.metrics || {};
  const parts = [];
  if (metrics.nodes !== undefined) parts.push(metrics.nodes + " NODES");
  if (metrics.edges !== undefined) parts.push(metrics.edges + " LINKS");
  if (metrics.connected_components !== undefined) parts.push(metrics.connected_components + " COMP");
  if (metrics.density !== undefined) parts.push("DENSITY " + Number(metrics.density).toFixed(3));
  m.textContent = parts.join(" · ") || (nodes.length + " NODES · " + edges.length + " LINKS");
}

function renderLedger() {
  const el = $("#case-ledger");
  const out = S.case.out;
  const rows = [
    ["COMPLAINT NO", out.complaint_number || "—"],
    ["VICTIM (MASKED)", out.victim_name ? esc(out.victim_name) + (out.victim_masked_phone ? " · " + esc(out.victim_masked_phone) : "") : "—"],
    ["VICTIM EMAIL", out.victim_masked_email || "—"],
    ["VICTIM A/C", out.victim_masked_account || "—"],
    ["STATE", out.state || "—"],
    ["DISTRICT", out.district || "—"],
    ["LOCALITY", out.locality_note || "—"],
    ["EXPOSURE", inr(out.amount)],
    ["SOURCE", out.complaint_source || "—"],
    ["REPORTED", out.reported_at ? fmtDT(out.reported_at) : "—"],
    ["OPENED", fmtDT(out.opened_at)],
    ["DATA SOURCE", out.data_source || "—"],
    ["INVESTIGATOR", out.investigation_officer || out.assigned_investigator || "—"],
    ["ASSIGNED ID", out.assigned_user_id ? String(out.assigned_user_id).slice(0, 8) : "—"],
    ["OPEN CYCLE", String(out.is_open)],
  ];
  el.innerHTML = rows.map(([k, v]) => '<div class="data-row"><dt>' + k + '</dt><dd>' + v + "</dd></div>").join("");
}

function renderRiskSignals() {
  const el = $("#risk-signals");
  const out = S.case.out;
  const loc = S.case.locations[0];
  const rows = [];
  rows.push(["RISK SCORE", pct(out.current_risk_score), riskColor(out.current_risk_score)]);
  rows.push(["PREDICTIONS", nf(out.prediction_count), "#00e5ff"]);
  rows.push(["ALERTS", nf(out.alert_count), out.alert_count > 0 ? "#ffb4ab" : "#849396"]);
  rows.push(["COMPLAINTS", nf(out.complaint_count), "#4cd6fb"]);
  rows.push(["TRANSACTIONS", nf(out.transaction_count), "#4cd6fb"]);
  if (loc) {
    rows.push(["TOP NODE", loc.atm_code || "—", "#ffb95f"]);
    rows.push(["TOP RISK", pct(loc.risk_score), riskColor(loc.risk_score)]);
  }
  el.innerHTML = rows.map(([k, v, c]) =>
    '<div class="flex items-center justify-between py-1.5 border-b border-dashed border-outline-variant/40 last:border-0"><span class="font-mono-data-sm text-on-surface-variant">' + k + '</span><span class="font-mono-data-md" style="color:' + c + '">' + v + "</span></div>").join("");
}

function renderTimeline() {
  const el = $("#case-timeline");
  const events = (S.case.timeline || []).slice().sort((a, b) => new Date(b.occurred_at) - new Date(a.occurred_at));
  if (!events.length) {
    el.innerHTML = '<div class="font-mono-data-sm text-on-surface-variant py-2">NO TIMELINE EVENTS — ADD EVENT TO START CHAIN</div>';
    return;
  }
  const icon = (t) => ({
    NOTE_ADDED: "sticky_note_2", COMPLAINT_RECEIVED: "add_alert", TRANSACTION_DETECTED: "currency_exchange",
    ENTITY_IDENTIFIED: "fingerprint", NETWORK_ANALYZED: "hub", PREDICTION_GENERATED: "auto_awesome",
    ALERT_CREATED: "notifications", ALERT_ACKNOWLEDGED: "fact_check", INTERVENTION_SIMULATED: "model_training",
    INTERVENTION_EXECUTED: "cyclone", OUTCOME_RECORDED: "assignment_turned_in", CASE_STATUS_CHANGED: "swap_horiz",
    ENTITY_LINKED: "link", EVIDENCE_ATTACHED: "attachment",
  }[t] || "schedule");
  el.innerHTML = events.map((ev, i) => `
    <div class="relative">
      ${i < events.length - 1 ? '<span class="absolute left-0 top-5 bottom-0 w-px -ml-[21px] bg-outline-variant/60"></span>' : ""}
      <div class="flex items-start gap-2">
        <span class="w-2 h-2 rounded-full mt-1.5 shrink-0" style="background:${ev.event_type.includes("ALERT") || ev.event_type.includes("INTERVENTION_EXECUTED") ? "#ffb4ab" : ev.event_type.includes("PREDICTION") ? "#ffb95f" : "#00e5ff"}"></span>
        <div class="min-w-0">
          <div class="font-mono-data-sm text-on-surface"><span class="material-symbols-outlined text-sm align-text-bottom text-on-surface-variant">${icon(ev.event_type)}</span> ${esc(humanize(ev.event_type))}</div>
          <div class="font-body-sm text-on-surface-variant mt-0.5">${esc(ev.description || "")}</div>
          <div class="font-mono-data-sm text-on-surface-variant/70 mt-0.5">${fmtClock(ev.occurred_at)} IST · ${ev.actor_id ? String(ev.actor_id).slice(0, 8) : "SYSTEM"}</div>
        </div>
      </div>
    </div>`).join("");
}

async function renderTransactions() {
  const el = $("#tx-tbody");
  const tx = S.case.tx || [];
  if (!tx.length) {
    el.innerHTML = '<tr><td colspan="9" class="text-center text-on-surface-variant py-6">NO TRANSACTIONS ON FILE FOR THIS CASE</td></tr>';
    return;
  }
  el.innerHTML = tx.map((t) => `
    <tr>
      <td class="text-on-surface-variant">${esc(t.transaction_ref || "—")}</td>
      <td>${inr(t.amount)}</td>
      <td style="color:${t.direction === "DEBIT" ? "#ffb4ab" : "#9cf0ff"}">${esc(t.direction)}</td>
      <td>${esc(t.type)}</td>
      <td class="text-on-surface-variant">${esc(t.channel)}</td>
      <td class="text-on-surface-variant">${t.timestamp ? fmtDT(t.timestamp) : "—"}</td>
      <td class="text-on-surface-variant">${esc(t.source_account || "—")}</td>
      <td class="text-on-surface-variant">${esc(t.destination_account || "—")}</td>
      <td class="text-on-surface-variant">${esc(t.merchant || "—")}</td>
    </tr>`).join("");
}

/* ============================ SIMULATOR ============================ */
async function renderSimulator() {
  pageTitle("INTERVENTION SIMULATOR", "PRE-RELEASE CASH-OUT DEGRADATION MODELLING");
  navActive("sim");
  const root = $("#view-root");
  root.innerHTML = `
    <div class="grid grid-cols-1 xl:grid-cols-4 gap-4">
      <div class="space-y-4">
        <div class="card p-4">
          <div class="font-label-caps text-on-surface-variant mb-3">CASE TARGET</div>
          <select id="sim-case" class="w-full bg-surface-dim border border-outline-variant rounded px-2 py-2.5 font-mono-data-sm text-on-surface"></select>
        </div>
        <div class="card p-4" id="sim-target">
          <div class="font-label-caps text-on-surface-variant mb-3">PREDICTED CASH-OUT TARGET</div>
          <div class="text-center py-6 font-mono-data-sm text-on-surface-variant">SELECT CASE</div>
        </div>
        <div class="card p-4" id="sim-model">
          <div class="font-label-caps text-on-surface-variant mb-3">MODEL BENCHMARK</div>
          <div class="text-center py-6 font-mono-data-sm text-on-surface-variant">LOADING MODEL REGISTRY…</div>
        </div>
      </div>

      <div class="xl:col-span-2 space-y-4">
        <div class="card p-4">
          <div class="font-label-caps text-on-surface-variant mb-3">SELECT INTERVENTION TACTIC</div>
          <div id="sim-tactics" class="grid grid-cols-1 sm:grid-cols-2 gap-3"></div>
          <button id="sim-run" class="w-full mt-3 bg-primary-container text-on-primary-container font-label-caps tracking-wider rounded px-4 py-3.5 hover:brightness-110 transition">SIMULATE DEPLOYMENT ↗</button>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div class="card p-4"><div class="font-label-caps text-on-surface-variant mb-2">BASELINE TRANCHE</div><div id="sim-baseline"></div></div>
          <div class="card p-4"><div class="font-label-caps text-on-surface-variant mb-2">SIMULATED EXPOSURE</div><div id="sim-result"></div></div>
        </div>
        <div class="card p-4">
          <div class="font-label-caps text-on-surface-variant mb-3">CASH-OUT DEGRADATION CURVE ACROSS TIME STEPS</div>
          <div id="sim-chart"></div>
          <div id="sim-assumptions" class="mt-3"></div>
        </div>
      </div>

      <div class="space-y-4">
        <div class="card p-4">
          <div class="font-label-caps text-on-surface-variant mb-3">DISPATCH DIRECTIVE</div>
          <div id="sim-directive">
            <div class="font-mono-data-sm text-on-surface-variant py-4 text-center">RUN A SIMULATION TO GENERATE DIRECTIVE</div>
          </div>
          <button id="sim-dispatch" class="hidden w-full mt-3 bg-error-container text-on-error-container font-label-caps rounded px-4 py-3 hover:brightness-110 transition">EXECUTE INTERVENTION ↑</button>
        </div>
        <div class="card p-4">
          <div class="font-label-caps text-on-surface-variant mb-3">HEAD-TO-HEAD OUTCOME TELEMETRY</div>
          <div id="sim-telemetry"></div>
        </div>
      </div>
    </div>`;
  try {
    S.cases = (await API.get("/cases?page=1&page_size=200")).items || [];
    const sel = $("#sim-case");
    sel.innerHTML = S.cases.map((c) => '<option value="' + c.id + '"' + (c.id === S.simCaseId ? " selected" : "") + ">" + c.case_number + " — " + c.fraud_type + "</option>").join("");
    if (!S.cases.length) sel.innerHTML = '<option value="">NO CASES ON FILE</option>';
    else if (!S.simCaseId) { S.simCaseId = S.cases[0].id; sel.value = S.simCaseId; }
    sel.addEventListener("change", () => { S.simCaseId = sel.value; wireSimCase(); });
    $("#sim-dispatch").addEventListener("click", executeIntervention);
    wireSimCase();
    loadModels();
    loadTelemetry();
  } catch (e) { toast(e.message || "Cannot load simulator", "error"); }
}

async function wireSimCase() {
  const id = S.simCaseId;
  S.simPrediction = null;
  S.simLocations = [];
  if (!id) return;
  try {
    const [locations, predictions] = await Promise.all([
      API.get("/cases/" + id + "/predictions/latest-locations"),
      API.get("/cases/" + id + "/predictions"),
    ]);
    S.simLocations = (Array.isArray(locations) ? locations : []).sort((a, b) => a.rank - b.rank);
    S.simPrediction = (Array.isArray(predictions) ? predictions : [null])[0] || null;
  } catch (e) { toast(e.message || "Cannot load prediction target", "error"); }
  renderSimTarget();
  renderTactics();
  resetSimResult();
}

function renderSimTarget() {
  const el = $("#sim-target");
  const loc = (S.simLocations || [])[0];
  const pred = S.simPrediction;
  if (!loc) {
    el.innerHTML = '<div class="text-center py-6 font-mono-data-sm text-on-surface-variant">NO PREDICTION FOR THIS CASE — RUN PREDICTION IN WORKSPACE</div>';
    return;
  }
  el.innerHTML = `
    <div class="text-center mb-4">
      <div class="font-headline-lg text-primary">${esc(loc.atm_code || "—")}</div>
      <div class="font-mono-data-sm text-on-surface-variant mt-1">${esc(loc.atm_name || "—")}</div>
    </div>
    <div class="data-row"><dt>RISK</dt><dd style="color:${riskColor(loc.risk_score)}">${pct(loc.risk_score)}</dd></div>
    <div class="data-row"><dt>CONFIDENCE</dt><dd>${pct(loc.confidence)}</dd></div>
    <div class="data-row"><dt>WINDOW</dt><dd>${loc.time_window ? fmtClock(loc.time_window.start) + " → " + fmtClock(loc.time_window.end) : "—"}</dd></div>
    ${pred && pred.headline_risk !== null && pred.headline_risk !== undefined ? '<div class="data-row"><dt>HEADLINE RISK</dt><dd>' + pct(pred.headline_risk) + "</dd></div>" : ""}
    ${pred && pred.predicted_amount !== null && pred.predicted_amount !== undefined ? '<div class="data-row"><dt>PREDICTED AMOUNT</dt><dd>' + inr(pred.predicted_amount) + "</dd></div>" : ""}
    <div class="data-row"><dt>MODEL</dt><dd>${pred ? esc(pred.model_name + " " + pred.model_version) : "—"}</dd></div>
    <div class="data-row"><dt>FEATURE SET</dt><dd>${pred ? esc(pred.feature_version) : "—"}</dd></div>
    <div class="data-row"><dt>GENERATED</dt><dd>${pred ? timeAgo(pred.generated_at) : "—"}</dd></div>`;
}

function renderTactics() {
  const el = $("#sim-tactics");
  const tactics = [
    { t: "MONITOR_ATM", label: "ATM SURVEILLANCE", desc: "Increase ATM surveillance & CCTV geo-lock on target node" },
    { t: "ALERT_BANK", label: "ALERT PARTNER BANK", desc: "Notify partner FI to hold/flag the predicted tranche" },
    { t: "DISPATCH_UNIT", label: "DISPATCH PATROL UNIT", desc: "Auto-broadcast to district field vector for physical intercept" },
    { t: "INCREASE_MONITORING", label: "RAMP MONITORING", desc: "Generate additional CAFTA-style alerts across cluster" },
    { t: "FREEZE_SIMULATION", label: "LAYER-2 FREEZE", desc: "Auto-freeze mule A/C & card tokens (simulate)" },
    { t: "NO_INTERVENTION", label: "NO INTERVENTION", desc: "Baseline — allow flow, observe degradation without action" },
  ];
  el.innerHTML = tactics.map((x, i) => `
    <label class="block cursor-pointer rounded border px-3 py-3 transition border-outline-variant/40 hover:border-primary-container/60" data-t="${x.t}">
      <input type="radio" name="tactic" value="${x.t}" class="hidden" ${i === 0 ? "checked" : ""}/>
      <div class="flex items-center justify-between">
        <span class="font-mono-data-md text-on-surface">${x.label}</span>
        <span class="w-4 h-4 rounded-full border border-outline-variant flex items-center justify-center"><span class="w-2 h-2 rounded-full bg-primary-container scale-0 transition" data-dot></span></span>
      </div>
      <div class="font-body-sm text-on-surface-variant mt-1.5">${x.desc}</div>
    </label>`).join("");
  $$("label[data-t]", el).forEach((lb) => {
    const input = $("input", lb);
    lb.addEventListener("change", () => {
      $$("label[data-t]", el).forEach((o) => $("[data-dot]", o).classList.toggle("scale-0", true));
      $("[data-dot]", lb).classList.remove("scale-0");
      resetSimResult();
    });
    input.addEventListener("change", () => { $("[data-dot]", lb).classList.remove("scale-0"); resetSimResult(); });
  });
}

async function runSimulation() {
  const id = S.simCaseId;
  if (!id) { toast("Select a case first", "error"); return; }
  const tactic = ($('input[name="tactic"]:checked') || {}).value || "MONITOR_ATM";
  const btn = $("#sim-run");
  if (btn) { btn.disabled = true; btn.textContent = "ENGINE: MONTE-CARLO RUNNING…"; }
  try {
    const body = { case_id: id, intervention_type: tactic, notes: "Simulated from Command Center UI" };
    if (S.simPrediction && S.simPrediction.id) body.prediction_id = S.simPrediction.id;
    const result = await API.post("/cases/" + id + "/simulate", body);
    S.simResult = result;
    renderSimResult();
  } catch (e) {
    toast(e.message || "Simulation failed", "error");
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = "SIMULATE DEPLOYMENT ↗"; }
  }
}

async function executeIntervention() {
  const id = S.simCaseId;
  if (!id || !S.simResult) { toast("Run a simulation first", "error"); return; }
  const btn = $("#sim-dispatch");
  const label = btn.textContent;
  btn.disabled = true;
  btn.textContent = "RECORDING ON CHAIN…";
  try {
    await API.post("/cases/" + id + "/events", {
      event_type: "INTERVENTION_EXECUTED",
      description: "Intervention executed during live analysis: " + S.simResult.intervention_type + " — " + (S.simResult.description || ""),
      metadata: { intervention_type: S.simResult.intervention_type, status: S.simResult.status },
    });
    toast("INTERVENTION_EXECUTED recorded on case timeline & audit chain");
    btn.disabled = false;
    btn.textContent = "✓ LOGGED ON CHAIN";
  } catch (e) {
    toast(e.message || "Dispatch record failed", "error");
    btn.disabled = false;
    btn.textContent = label;
  }
}

function resetSimResult() {
  S.simResult = null;
  const b = $("#sim-baseline"); if (b) b.innerHTML = placeholderPair("RUN SIMULATION");
  const r = $("#sim-result"); if (r) r.innerHTML = placeholderPair("AWAITING MODEL OUTPUT");
  const c = $("#sim-chart"); if (c) c.innerHTML = "";
  const a = $("#sim-assumptions"); if (a) a.innerHTML = "";
  $("#sim-directive").innerHTML = '<div class="font-mono-data-sm text-on-surface-variant py-4 text-center">RUN A SIMULATION TO GENERATE DIRECTIVE</div>';
  $("#sim-dispatch").classList.add("hidden");
}
function placeholderPair(txt) {
  return '<div class="text-center py-10 font-mono-data-sm text-on-surface-variant"><div class="material-symbols-outlined text-3xl mb-2 opacity-40">gavel</div>' + txt + "</div>";
}

async function renderSimResult() {
  const res = S.simResult;
  if (!res) return;
  const b = $("#sim-baseline");
  const r = $("#sim-result");
  b.innerHTML = `
    <div class="font-headline-lg countdown">${inr(res.baseline_exposure)}${res.baseline_exposure === null || res.baseline_exposure === undefined ? "" : ""}</div>
    <div class="font-mono-data-sm text-on-surface-variant mt-1">EST. EXPOSURE WITHOUT ACTION</div>
    <div class="ring-bar mt-3"><div style="width:100%;background:#ffb4ab"></div></div>
    <div class="font-mono-data-sm text-on-surface-variant mt-2">100% of illicit tranche disbursed</div>`;
  const rej = res.risk_reduction;
  r.innerHTML = `
    <div class="font-headline-lg countdown" style="color:${rej !== null && rej !== undefined && rej > 0 ? "#9cf0ff" : "#e0e2e9"}">${inr(res.simulated_exposure)}</div>
    <div class="font-mono-data-sm text-on-surface-variant mt-1">PROJECTED EXPOSURE AFTER INTERVENTION</div>
    <div class="ring-bar mt-3"><div style="width:${rej !== null && rej !== undefined ? fmtBar(rej) : 0}%;background:#00e5ff"></div></div>
    <div class="font-mono-data-md mt-2 ${rej !== null && rej !== undefined && rej > 0 ? "val-pos" : "val-neutral"}">RISK REDUCTION ${pct(rej)}</div>
    <div class="font-mono-data-sm text-on-surface-variant mt-1">STATUS: ${esc(res.status)} · ${esc(humanize(res.intervention_type))}</div>`;
  drawDegradationCurve(res);
  $("#sim-assumptions").innerHTML = (res.assumptions || []).map((x) =>
    '<div class="flex items-start gap-2 font-mono-data-sm text-on-surface-variant"><span class="material-symbols-outlined text-sm mt-px text-primary">fact_check</span>' + esc(x) + "</div>").join("");
  $("#sim-directive").innerHTML = directiveBody(res);
  $("#sim-dispatch").classList.remove("hidden");
}

function drawDegradationCurve(res) {
  const el = $("#sim-chart");
  const steps = ["T+0", "T+15", "T+30", "T+45", "T+60"];
  const baseline = res.baseline_exposure || 0;
  const simulated = res.simulated_exposure || 0;
  const red = (res.risk_reduction || 0);
  const values = steps.map((_, i) => Math.max(0, baseline - (baseline - simulated) * (i / (steps.length - 1))));
  const maxV = Math.max(baseline, 1);
  el.innerHTML = `
    <div class="flex items-end gap-2 h-48 pt-4" style="border-bottom:1px solid #3b494c">
      ${values.map((v, i) => {
        const h = Math.max(4, (v / maxV) * 170);
        return `<div class="flex-1 flex flex-col items-center gap-1.5">
          <span class="font-mono-data-sm ${i === steps.length - 1 ? "val-pos" : "val-neutral"}">${inr(v)}</span>
          <div class="w-full rounded-t" style="height:${h}px;background:${i === steps.length - 1 ? "#00e5ff" : "#00e5ff55"};box-shadow:${i === steps.length - 1 ? "0 0 14px #00e5ff44" : "none"}"></div>
          <span class="font-mono-data-sm text-on-surface-variant">${steps[i]}</span>
        </div>`;
      }).join("")}
    </div>
    <div class="flex justify-between font-mono-data-sm text-on-surface-variant mt-2">
      <span>BASELINE <span class="val-neg">${inr(baseline)}</span></span>
      <span>SIMULATED <span class="val-pos">${inr(simulated)}</span></span>
      <span>Δ REDUCTION ${pct(red)}</span>
    </div>`;
}

function directiveBody(res) {
  const target = (S.simLocations || [])[0];
  const isDispatch = res.intervention_type === "DISPATCH_UNIT";
  if (isDispatch) {
    return `
      <div class="font-mono-data-sm text-primary mb-2">AUTO BROADCAST → DISTRICT FIELD VECTOR</div>
      <div class="data-row"><dt>UNIT</dt><dd>${target ? esc(target.atm_name || "TARGET NODE") : "TARGET NODE"}</dd></div>
      <div class="data-row"><dt>ETA</dt><dd>${res.metadata && res.metadata.eta ? res.metadata.eta : "—"}</dd></div>
      <div class="data-row"><dt>DIRECTIVE REF</dt><dd>${String(res.case_id).slice(0, 8).toUpperCase()}</dd></div>
      <div class="font-body-sm text-on-surface-variant mt-2">Intervention sim approved. Execute to log INTERVENTION_EXECUTED on the case timeline & audit chain.</div>`;
  }
  if (res.intervention_type === "FREEZE_SIMULATION") {
    return `<div class="font-mono-data-sm text-primary mb-2">LAYER-2 FREEZE DIRECTIVE</div>
      <div class="font-body-sm text-on-surface-variant">${(res.assumptions || []).length ? esc(res.assumptions[0]) : "Auto-freeze mule A/C & card tokens. Execute to record on chain."}</div>`;
  }
  if (res.intervention_type === "ALERT_BANK") {
    return '<div class="font-mono-data-sm text-primary mb-2">PARTNER BANK NOTIFICATION</div><div class="font-body-sm text-on-surface-variant">Alert raised to partner FI to hold/flag tranche. Execute to record dispatch.</div>';
  }
  return '<div class="font-mono-data-sm text-primary mb-2">MONITORING DIRECTIVE ACTIVE</div><div class="font-body-sm text-on-surface-variant">Subject node placed under surveillance. Execute to record on chain.</div>';
}

async function loadModels() {
  const el = $("#sim-model");
  try {
    const models = (await API.get("/models")) || [];
    if (!models.length) { el.innerText = "MODEL REGISTRY EMPTY"; return; }
    const active = models.find((m) => m.active) || models[0];
    const met = active.metrics || {};
    el.innerHTML = `
      <div class="font-mono-data-md text-primary mb-2">${esc(active.model_name)} v${esc(active.model_version)}</div>
      <div class="font-mono-data-sm text-on-surface-variant">${esc(active.artifact_path || "")}${" · " + (active.status || "")}</div>
      <div class="mt-2">${Object.keys(met).slice(0, 6).map((k) => '<div class="data-row"><dt colspan="2">' + esc(k) + '</dt><dd>' + esc(met[k]) + "</dd></div>").join("") || '<div class="font-mono-data-sm text-on-surface-variant">NO METRICS REGISTERED</div>'}</div>
      <div class="flex items-center gap-2 mt-3 font-mono-data-sm text-secondary"><span class="w-1.5 h-1.5 rounded-full bg-secondary animate-pulse"></span>ML ENGINE (ONLINE)</div>`;
  } catch (e) { el.innerHTML = '<div class="font-mono-data-sm text-error">' + esc(e.message) + "</div>"; }
}

async function loadTelemetry() {
  const el = $("#sim-telemetry");
  try {
    const [outcomes, overview] = await Promise.all([
      API.get("/analytics/outcomes-summary"),
      API.get("/analytics/overview"),
    ]);
    const entries = (outcomes && typeof outcomes === "object" ? Object.entries(outcomes) : []).filter(([, v]) => typeof v !== "object");
    el.innerHTML = `
      <div class="data-row"><dt>HIT PRECISION</dt><dd>${pct(overview.prediction_accuracy)}</dd></div>
      <div class="data-row"><dt>PREDICTION SAMPLE</dt><dd>${nf(overview.prediction_count)}</dd></div>
      ${entries.slice(0, 6).map(([k, v]) => '<div class="data-row"><dt>' + esc(k.replace(/_/g, " ")) + '</dt><dd>' + esc(v) + "</dd></div>").join("")}
      <div class="font-mono-data-sm text-on-surface-variant mt-2">Benchmark readout derived from operational outcomes ledger.</div>`;
    if (!entries.length) el.innerHTML = '<div class="font-mono-data-sm text-on-surface-variant py-3">NO OUTCOME RECORDS — RUN DISPATCHES TO BUILD TELEMETRY</div>';
  } catch (e) { el.innerHTML = '<div class="font-mono-data-sm text-error">' + esc(e.message) + "</div>"; }
}

$("#view-root").addEventListener("click", (e) => {
  const btn = e.target.closest("#sim-run");
  if (btn) { e.preventDefault(); runSimulation(); }
});

/* ============================ AUDIT ============================ */
async function renderAudit() {
  pageTitle("AUDIT LOG", "CHAINED IMMUTABLE EVENT LEDGER");
  navActive("audit");
  const root = $("#view-root");
  root.innerHTML = `
    <div class="card p-4">
      <div class="flex items-center justify-between flex-wrap gap-3 mb-4">
        <div>
          <div class="font-headline-sm">CHAIN INTEGRITY</div>
          <div class="font-mono-data-sm text-on-surface-variant mt-1" id="audit-chain"></div>
        </div>
        <button class="font-label-caps text-primary hover:underline" data-action="refresh-audit">REFRESH</button>
      </div>
      <div class="overflow-x-auto"><table class="cdata">
        <thead><tr><th>TIME</th><th>ACTOR</th><th>ROLE</th><th>ACTION</th><th>RESOURCE</th><th>RESULT</th><th>REQUEST</th><th>HASH</th></tr></thead>
        <tbody id="audit-tbody"></tbody></table></div>
    </div>
    <div class="card p-4"><div class="font-label-caps text-on-surface-variant mb-3">CHAIN LINK PREVIEW</div><div id="audit-link" class="overflow-x-auto font-mono-data-sm text-on-surface-variant"></div></div>`;
  $('[data-action="refresh-audit"]').addEventListener("click", refreshAudit);
  await refreshAudit();
}

async function refreshAudit() {
  const tbody = $("#audit-tbody");
  if (!tbody || S.view !== "audit") return;
  try {
    const [page, chain] = await Promise.all([API.get("/audit?page=1&page_size=60"), API.get("/audit/verify")]);
    S.audit = page;
    const items = (page && page.items) || [];
    const ok = chain && chain.verified;
    $("#audit-chain").innerHTML =
      '<span class="inline-flex items-center gap-2 mr-3">' +
      '<span class="w-2 h-2 rounded-full ' + (ok ? "bg-secondary animate-pulse" : "bg-error") + '"></span>' +
      (ok ? "CHAIN VERIFIED — " : "CHAIN INCONSISTENT — ") + nf(chain.total) + " EVENTS</span>" +
      '<span class="hidden lg:inline font-mono-data-sm">FIRST ' + truncHash(chain.first_hash) + " · LAST " + truncHash(chain.last_hash) + "</span>";
    tbody.innerHTML = items.map((a) => `
      <tr>
        <td class="text-on-surface-variant whitespace-nowrap">${fmtDT(a.created_at)}</td>
        <td class="text-on-surface">${esc(a.actor_email || "SYSTEM")}</td>
        <td class="text-on-surface-variant">${esc(a.actor_role || "—")}</td>
        <td class="text-primary">${esc(a.action)}</td>
        <td class="text-on-surface-variant">${esc(a.resource || "—")}${a.resource_id ? " · " + esc(String(a.resource_id).slice(0, 8)) : ""}</td>
        <td>${a.result === "SUCCESS" ? '<span class="text-secondary">' + esc(a.result) + "</span>" : '<span class="text-error">' + esc(a.result) + "</span>"}</td>
        <td class="text-on-surface-variant">${esc(a.request_id || "—")}</td>
        <td class="text-on-surface-variant mono">${truncHash(a.hash)}</td>
      </tr>`).join("") ||
      '<tr><td colspan="8" class="text-center text-on-surface-variant py-8">NO AUDIT EVENTS YET — PERFORM ACTIONS TO SEED THE CHAIN</td></tr>';
    $("#audit-link").innerHTML = items.slice(0, 6).map((a) => {
      const raw = { id: a.id, action: a.action, actor: a.actor_email, result: a.result, prev_hash: a.prev_hash, hash: a.hash, payload: a.event_payload };
      try { JSON.stringify(raw); } catch (e) { /* noop */ }
      return '<div class="py-1.5 border-b border-dashed border-outline-variant/40 last:border-0"><span class="material-symbols-outlined text-sm align-text-bottom text-primary mr-2">link</span><span class="mono text-on-surface-variant">' + esc(JSON.stringify(raw)) + "</span></div>";
    }).join("");
  } catch (e) {
    tbody.innerHTML = '<tr><td colspan="8" class="text-center text-error py-8">' + esc(e.message || "Cannot reach audit chain") + "</td></tr>";
  }
}
function truncHash(h) {
  if (!h) return "—";
  return String(h).length > 20 ? String(h).slice(0, 20) + "…" : String(h);
}

/* ============================ BOOT ============================ */
function boot() {
  $("#login-api").textContent = "API: " + API.BASE;
  if (API.token) {
    API.me().then((user) => {
      enterApp(user);
    }).catch(() => showLogin());
  } else {
    showLogin();
  }
}
document.addEventListener("DOMContentLoaded", boot);
})();