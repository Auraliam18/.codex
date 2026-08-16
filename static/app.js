/* Aura Trade Panel — frontend logic */
"use strict";

const $ = (sel) => document.querySelector(sel);
const fmt = (n, d = 2) =>
  n == null || isNaN(n) ? "—" : Number(n).toLocaleString("en-US", { maximumFractionDigits: d });
const faTime = (ts) =>
  new Date(ts).toLocaleTimeString("fa-IR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });

let state = null;
let strategies = [];
let settings = null;
let candles = [];
let ws = null;

/* ═══════════════ API helpers ═══════════════ */
async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  return res.json();
}

/* ═══════════════ WebSocket ═══════════════ */
function connectWS() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.onopen = () => setConn(true);
  ws.onclose = () => { setConn(false); setTimeout(connectWS, 3000); };
  ws.onmessage = (e) => {
    const msg = JSON.parse(e.data);
    if (msg.event === "state") { state = msg.payload; renderState(); }
    if (msg.event === "signal") prependSignal(msg.payload);
    if (msg.event === "strategies") { strategies = msg.payload; renderStrategies(); }
    if (msg.event === "settings") { settings = msg.payload; renderSettingsBadge(); }
    if (msg.event === "engine") refreshState();
  };
}

function setConn(on) {
  $("#conn-dot").className = `dot ${on ? "dot-on" : "dot-off"}`;
  $("#conn-text").textContent = on ? "متصل" : "قطع — تلاش مجدد…";
}

/* ═══════════════ Rendering ═══════════════ */
function renderState() {
  if (!state) return;
  const isLive = state.mode === "live";
  const equity = isLive
    ? Number(state.live_account?.equity ?? state.live_account?.available ?? 0)
    : state.paper_equity;
  const balance = isLive ? Number(state.live_account?.available ?? 0) : state.paper_balance;

  $("#stat-equity").textContent = `$${fmt(equity)}`;
  $("#stat-balance").textContent = `موجودی آزاد: $${fmt(balance)}`;

  const pnl = state.stats.total_pnl;
  const pnlEl = $("#stat-pnl");
  pnlEl.textContent = `${pnl >= 0 ? "▲" : "▼"} $${fmt(Math.abs(pnl))}`;
  pnlEl.className = `stat-value ${pnl >= 0 ? "pnl-pos" : "pnl-neg"}`;
  $("#stat-trades").textContent = `${state.stats.total_trades} معامله بسته‌شده · ${state.stats.wins} برد`;

  $("#stat-winrate").textContent = state.stats.total_trades ? `${fmt(state.stats.win_rate, 1)}٪` : "—";
  $("#winrate-fill").style.width = `${state.stats.win_rate || 0}%`;

  $("#stat-positions").textContent = state.positions.length;
  $("#stat-engine").textContent = `موتور: ${state.running ? "روشن ✓" : "خاموش"}`;

  const btn = $("#btn-engine");
  btn.textContent = state.running ? "⏸ خاموش کردن موتور" : "▶ روشن کردن موتور";
  btn.className = `btn ${state.running ? "btn-danger" : "btn-primary"}`;

  renderPositions();
  renderTrades();
  renderLogs();
  renderSignals(state.signals);

  const sym = $("#chart-symbol").value;
  if (state.prices[sym] != null) $("#chart-price").textContent = `$${fmt(state.prices[sym])}`;
}

function renderSettingsBadge() {
  if (!settings) return;
  const badge = $("#mode-badge");
  const live = settings.mode === "live";
  badge.textContent = live ? "⚠ حالت واقعی" : "حالت دمو";
  badge.className = `badge ${live ? "badge-live" : "badge-paper"}`;
}

function sideBadge(side) {
  const isLong = side === "LONG";
  return `<span class="side-badge ${isLong ? "long" : "short"}">${isLong ? "▲ لانگ" : "▼ شورت"}</span>`;
}

function renderPositions() {
  const tbody = $("#positions-table tbody");
  if (!state.positions.length) {
    tbody.innerHTML = `<tr><td colspan="10" class="empty-state">پوزیشن بازی وجود ندارد</td></tr>`;
    return;
  }
  tbody.innerHTML = state.positions.map((p) => {
    const pnl = Number(p.pnl ?? p.unrealizedPNL ?? 0);
    const id = p.id ?? p.positionId ?? "";
    return `<tr>
      <td>${p.symbol}</td>
      <td>${sideBadge(p.side === "BUY" ? "LONG" : p.side === "SELL" ? "SHORT" : p.side)}</td>
      <td class="num">${fmt(p.entry ?? p.avgOpenPrice, 4)}</td>
      <td class="num">${fmt(p.mark ?? p.markPrice, 4)}</td>
      <td class="num">${fmt(p.qty, 6)}</td>
      <td class="num">${p.leverage ?? "—"}x</td>
      <td class="num">${fmt(p.sl, 4)}</td>
      <td class="num">${fmt(p.tp, 4)}</td>
      <td class="num ${pnl >= 0 ? "long-ink" : "short-ink"}">${pnl >= 0 ? "+" : ""}${fmt(pnl)}</td>
      <td><button class="btn btn-ghost btn-sm" onclick="closePosition('${id}')">بستن</button></td>
    </tr>`;
  }).join("");
}

function renderTrades() {
  const tbody = $("#trades-table tbody");
  const trades = state.trades || [];
  if (!trades.length) {
    tbody.innerHTML = `<tr><td colspan="7" class="empty-state">معامله‌ای ثبت نشده</td></tr>`;
    return;
  }
  const reasonFa = { SL: "حد ضرر", TP: "حد سود", MANUAL: "دستی" };
  tbody.innerHTML = trades.slice(0, 25).map((t) => `<tr>
      <td>${faTime(t.closed_at || t.opened_at)}</td>
      <td>${t.symbol}</td>
      <td>${sideBadge(t.side)}</td>
      <td class="num">${fmt(t.entry, 4)}</td>
      <td class="num">${fmt(t.exit, 4)}</td>
      <td>${reasonFa[t.close_reason] || t.close_reason || "—"}</td>
      <td class="num ${t.pnl >= 0 ? "long-ink" : "short-ink"}">${t.pnl >= 0 ? "+" : ""}${fmt(t.pnl)}</td>
    </tr>`).join("");
}

function renderLogs() {
  const feed = $("#log-feed");
  feed.innerHTML = (state.logs || []).map((l) =>
    `<div class="log-line ${l.level}">
       <span class="log-time">${faTime(l.ts)}</span>
       <span class="log-text">${l.text}</span>
     </div>`).join("") || `<div class="empty-state">رویدادی ثبت نشده</div>`;
}

function signalHTML(s) {
  const isLong = s.side === "LONG";
  return `<div class="signal-item ${isLong ? "long" : "short"}">
    <div class="signal-top">
      <span class="signal-side ${isLong ? "long-ink" : "short-ink"}">${isLong ? "▲ لانگ" : "▼ شورت"} · ${s.symbol}</span>
      <span class="signal-meta">${faTime(s.ts)}</span>
    </div>
    <div class="signal-reason">${s.reason}</div>
    <div class="signal-meta">${s.strategy} · قیمت ${fmt(s.price, 4)} · اطمینان ${Math.round(s.confidence * 100)}٪</div>
  </div>`;
}

function renderSignals(list) {
  const feed = $("#signals-feed");
  if (!list || !list.length) return;
  feed.innerHTML = list.map(signalHTML).join("");
}

function prependSignal(s) {
  const feed = $("#signals-feed");
  const empty = feed.querySelector(".empty-state");
  if (empty) empty.remove();
  feed.insertAdjacentHTML("afterbegin", signalHTML(s));
}

/* ═══════════════ Strategies ═══════════════ */
const FEATURED = new Set(["aura_liam_max", "liam_trader_9"]);

function renderStrategies() {
  const grid = $("#strategies-grid");
  const sorted = [...strategies].sort((a, b) =>
    (FEATURED.has(b.id) - FEATURED.has(a.id)) || a.name.localeCompare(b.name));
  grid.innerHTML = sorted.map((s) => {
    const c = { symbol: "BTCUSDT", interval: "15m", leverage: 5, risk_pct: 2, ...s.config };
    return `<div class="strategy-card ${s.enabled ? "enabled" : ""}" data-id="${s.id}">
      <div class="strategy-top">
        <span class="strategy-name">${FEATURED.has(s.id) ? '<span class="star">★</span>' : ""}${s.name}</span>
        <label class="switch">
          <input type="checkbox" ${s.enabled ? "checked" : ""} onchange="toggleStrategy('${s.id}', this.checked)">
          <span class="track"></span>
        </label>
      </div>
      <div class="strategy-desc">${s.description}</div>
      <div class="strategy-conf">
        <label>نماد
          <select class="input input-sm" data-cfg="symbol" onchange="saveCfg('${s.id}', this)">
            ${["BTCUSDT","ETHUSDT","SOLUSDT","XRPUSDT","DOGEUSDT","BNBUSDT"].map(
              (x) => `<option ${c.symbol === x ? "selected" : ""}>${x}</option>`).join("")}
          </select>
        </label>
        <label>تایم‌فریم
          <select class="input input-sm" data-cfg="interval" onchange="saveCfg('${s.id}', this)">
            ${[["1m","۱ دقیقه"],["5m","۵ دقیقه"],["15m","۱۵ دقیقه"],["1h","۱ ساعت"],["4h","۴ ساعت"]].map(
              ([v, t]) => `<option value="${v}" ${c.interval === v ? "selected" : ""}>${t}</option>`).join("")}
          </select>
        </label>
        <label>اهرم
          <input class="input input-sm" dir="ltr" type="number" min="1" max="100" value="${c.leverage}"
                 data-cfg="leverage" onchange="saveCfg('${s.id}', this)">
        </label>
        <label>ریسک هر معامله ٪
          <input class="input input-sm" dir="ltr" type="number" min="0.1" max="20" step="0.1" value="${c.risk_pct}"
                 data-cfg="risk_pct" onchange="saveCfg('${s.id}', this)">
        </label>
      </div>
      <div class="strategy-foot">
        <span class="strategy-status ${s.enabled ? "on" : "off"}">${s.enabled ? "● فعال — در حال رصد بازار" : "○ غیرفعال"}</span>
        ${s.builtin ? "" : `<button class="btn btn-ghost btn-sm" onclick="deleteCustom('${s.id}')">حذف</button>`}
      </div>
    </div>`;
  }).join("");
}

window.toggleStrategy = async (id, enabled) => {
  await api(`/api/strategies/${id}/toggle`, { method: "POST", body: { enabled } });
  const s = strategies.find((x) => x.id === id);
  if (s) s.enabled = enabled;
  renderStrategies();
};

window.saveCfg = async (id, el) => {
  const key = el.dataset.cfg;
  const value = el.type === "number" ? Number(el.value) : el.value;
  await api(`/api/strategies/${id}/config`, { method: "POST", body: { config: { [key]: value } } });
  const s = strategies.find((x) => x.id === id);
  if (s) s.config = { ...s.config, [key]: value };
};

window.deleteCustom = async (id) => {
  if (!confirm("این استراتژی سفارشی حذف شود؟")) return;
  await api(`/api/strategies/custom/${id}`, { method: "DELETE" });
  strategies = await api("/api/strategies");
  renderStrategies();
};

window.closePosition = async (id) => {
  if (!confirm("این پوزیشن بسته شود؟")) return;
  await api(`/api/positions/${id}/close`, { method: "POST" });
  refreshState();
};

/* ═══════════════ Candlestick chart ═══════════════ */
const chart = { canvas: null, ctx: null, hover: -1, geom: null };

async function loadChart() {
  const symbol = $("#chart-symbol").value;
  const interval = $("#chart-interval").value;
  try {
    const data = await api(`/api/klines?symbol=${symbol}&interval=${interval}&limit=90`);
    if (Array.isArray(data)) { candles = data; drawChart(); }
  } catch { /* network hiccup — keep last chart */ }
}

function drawChart() {
  const cv = chart.canvas, ctx = chart.ctx;
  if (!cv || !candles.length) return;
  const dpr = window.devicePixelRatio || 1;
  const W = cv.clientWidth, H = cv.clientHeight;
  cv.width = W * dpr; cv.height = H * dpr;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, W, H);

  const padL = 8, padR = 64, padT = 14, padB = 22;
  const plotW = W - padL - padR, plotH = H - padT - padB;
  const lo = Math.min(...candles.map((c) => c.low));
  const hi = Math.max(...candles.map((c) => c.high));
  const range = hi - lo || 1;
  const y = (v) => padT + (1 - (v - lo) / range) * plotH;
  const step = plotW / candles.length;
  const bw = Math.max(2, Math.min(11, step * 0.65));

  // hairline grid + right-side price labels (LTR numbers)
  ctx.strokeStyle = "#232a38"; ctx.lineWidth = 1;
  ctx.fillStyle = "#8a90a0"; ctx.font = "10.5px system-ui, sans-serif"; ctx.textAlign = "left";
  for (let i = 0; i <= 4; i++) {
    const gy = padT + (plotH * i) / 4;
    ctx.beginPath(); ctx.moveTo(padL, gy); ctx.lineTo(W - padR, gy); ctx.stroke();
    const price = hi - (range * i) / 4;
    ctx.fillText(fmt(price, price > 100 ? 1 : 4), W - padR + 6, gy + 3.5);
  }

  const UP = "#0ca30c", DOWN = "#e66767";
  candles.forEach((c, i) => {
    const x = padL + i * step + step / 2;
    const bull = c.close >= c.open;
    ctx.strokeStyle = ctx.fillStyle = bull ? UP : DOWN;
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(x, y(c.high)); ctx.lineTo(x, y(c.low)); ctx.stroke();
    const top = y(Math.max(c.open, c.close));
    const h = Math.max(1.5, Math.abs(y(c.open) - y(c.close)));
    roundRect(ctx, x - bw / 2, top, bw, h, 2); ctx.fill();
  });

  // hover crosshair
  if (chart.hover >= 0 && chart.hover < candles.length) {
    const x = padL + chart.hover * step + step / 2;
    ctx.strokeStyle = "rgba(255,255,255,0.25)"; ctx.setLineDash([4, 4]);
    ctx.beginPath(); ctx.moveTo(x, padT); ctx.lineTo(x, H - padB); ctx.stroke();
    ctx.setLineDash([]);
  }

  chart.geom = { padL, padR, padT, padB, step, W, H };

  const last = candles[candles.length - 1];
  $("#chart-price").textContent = `$${fmt(last.close, last.close > 100 ? 2 : 4)}`;
  $("#chart-price").style.color = last.close >= last.open ? "#4dc44d" : "#e66767";
}

function roundRect(ctx, x, y, w, h, r) {
  r = Math.min(r, w / 2, h / 2);
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

function chartHover(e) {
  if (!chart.geom || !candles.length) return;
  const rect = chart.canvas.getBoundingClientRect();
  const x = e.clientX - rect.left;
  const idx = Math.floor((x - chart.geom.padL) / chart.geom.step);
  const tip = $("#chart-tooltip");
  if (idx < 0 || idx >= candles.length) { tip.hidden = true; chart.hover = -1; drawChart(); return; }
  if (idx !== chart.hover) { chart.hover = idx; drawChart(); }
  const c = candles[idx];
  const d = c.close > 100 ? 2 : 4;
  tip.innerHTML = `<b>${new Date(c.time).toLocaleString("en-GB", { hour12: false })}</b><br>
    O ${fmt(c.open, d)} &nbsp; H ${fmt(c.high, d)}<br>L ${fmt(c.low, d)} &nbsp; C <b>${fmt(c.close, d)}</b>`;
  tip.hidden = false;
  const wrapRect = chart.canvas.parentElement.getBoundingClientRect();
  let tx = e.clientX - wrapRect.left + 14;
  if (tx + 170 > wrapRect.width) tx -= 190;
  tip.style.left = `${tx}px`;
  tip.style.top = `${Math.min(e.clientY - wrapRect.top + 10, wrapRect.height - 80)}px`;
}

/* ═══════════════ Modals ═══════════════ */
function bindModal(id) {
  const backdrop = $(id);
  backdrop.addEventListener("click", (e) => {
    if (e.target === backdrop || e.target.hasAttribute("data-close")) backdrop.hidden = true;
  });
}

async function openSettings() {
  settings = await api("/api/settings");
  $("#set-apikey").value = "";
  $("#set-apikey").placeholder = settings.has_keys ? `ذخیره‌شده: ${settings.api_key_masked}` : "API Key";
  $("#set-secret").value = "";
  $("#set-secret").placeholder = settings.has_keys ? "ذخیره‌شده (برای تغییر وارد کنید)" : "Secret Key";
  $("#set-mode").value = settings.mode;
  $("#set-balance").value = settings.paper_balance;
  $("#live-warning").hidden = settings.mode !== "live";
  $("#settings-msg").textContent = "";
  $("#modal-settings").hidden = false;
}

async function saveSettings() {
  const body = {
    mode: $("#set-mode").value,
    paper_balance: Number($("#set-balance").value) || 10000,
  };
  if ($("#set-apikey").value.trim()) body.api_key = $("#set-apikey").value.trim();
  if ($("#set-secret").value.trim()) body.secret_key = $("#set-secret").value.trim();
  settings = await api("/api/settings", { method: "POST", body });
  renderSettingsBadge();
  const msg = $("#settings-msg");
  msg.textContent = "✓ تنظیمات ذخیره شد";
  msg.className = "settings-msg ok";
  refreshState();
}

async function testConnection() {
  const msg = $("#settings-msg");
  msg.textContent = "در حال بررسی اتصال…";
  msg.className = "settings-msg";
  const res = await api("/api/settings/test", { method: "POST" });
  if (res.ok) {
    const avail = res.account?.available ?? res.account?.equity ?? "?";
    msg.textContent = `✓ اتصال برقرار است — موجودی: ${fmt(Number(avail))} USDT`;
    msg.className = "settings-msg ok";
  } else {
    msg.textContent = `✗ خطا: ${res.error || "اتصال برقرار نشد"}`;
    msg.className = "settings-msg err";
  }
}

/* custom strategy builder */
const INDICATORS = [
  ["rsi", "RSI (14)"], ["macd_hist", "هیستوگرام MACD"], ["macd_line", "خط MACD"],
  ["ema_fast_above_slow", "EMA سریع بالای کند (0/1)"], ["bb_pos", "موقعیت بولینگر (0..1)"],
  ["vol_ratio", "نسبت حجم به میانگین"], ["close", "قیمت پایانی"],
];

function ruleRowHTML() {
  return `<div class="rule-row">
    <select class="input r-ind">${INDICATORS.map(([v, t]) => `<option value="${v}">${t}</option>`).join("")}</select>
    <select class="input r-op"><option><</option><option>></option><option><=</option><option>>=</option><option>==</option></select>
    <input class="input r-val" dir="ltr" type="number" step="any" value="30">
    <button class="rule-del" onclick="this.parentElement.remove()">✕</button>
  </div>`;
}

function collectRules(containerId) {
  return [...document.querySelectorAll(`${containerId} .rule-row`)].map((row) => ({
    indicator: row.querySelector(".r-ind").value,
    op: row.querySelector(".r-op").value,
    value: Number(row.querySelector(".r-val").value),
  }));
}

async function saveCustomStrategy() {
  const name = $("#cs-name").value.trim();
  if (!name) { alert("نام استراتژی را وارد کنید"); return; }
  const body = {
    name,
    long: collectRules("#cs-long-rules"),
    short: collectRules("#cs-short-rules"),
    atr_sl_mult: Number($("#cs-slmult").value) || 1.5,
    rr_ratio: Number($("#cs-rr").value) || 2.0,
  };
  if (!body.long.length && !body.short.length) { alert("حداقل یک شرط تعریف کنید"); return; }
  await api("/api/strategies/custom", { method: "POST", body });
  $("#modal-custom").hidden = true;
  strategies = await api("/api/strategies");
  renderStrategies();
}

/* ═══════════════ Bootstrap ═══════════════ */
async function refreshState() {
  try { state = await api("/api/state"); renderState(); } catch { setConn(false); }
}

async function init() {
  chart.canvas = $("#chart");
  chart.ctx = chart.canvas.getContext("2d");
  chart.canvas.addEventListener("mousemove", chartHover);
  chart.canvas.addEventListener("mouseleave", () => {
    $("#chart-tooltip").hidden = true; chart.hover = -1; drawChart();
  });
  window.addEventListener("resize", drawChart);

  bindModal("#modal-settings");
  bindModal("#modal-custom");
  $("#btn-settings").onclick = openSettings;
  $("#btn-save-settings").onclick = saveSettings;
  $("#btn-test-conn").onclick = testConnection;
  $("#set-mode").onchange = () => { $("#live-warning").hidden = $("#set-mode").value !== "live"; };

  $("#btn-add-strategy").onclick = () => {
    $("#cs-name").value = "";
    $("#cs-long-rules").innerHTML = ruleRowHTML();
    $("#cs-short-rules").innerHTML = "";
    $("#modal-custom").hidden = false;
  };
  document.querySelectorAll("[data-add-rule]").forEach((btn) => {
    btn.onclick = () => {
      const target = btn.dataset.addRule === "long" ? "#cs-long-rules" : "#cs-short-rules";
      $(target).insertAdjacentHTML("beforeend", ruleRowHTML());
    };
  });
  $("#btn-save-custom").onclick = saveCustomStrategy;

  $("#btn-engine").onclick = async () => {
    const running = state?.running;
    if (!running && settings?.mode === "live") {
      if (!confirm("موتور در حالت واقعی روشن می‌شود و سفارش واقعی ثبت خواهد کرد. ادامه می‌دهید؟")) return;
    }
    await api(`/api/engine/${running ? "stop" : "start"}`, { method: "POST" });
    refreshState();
  };

  $("#chart-symbol").onchange = loadChart;
  $("#chart-interval").onchange = loadChart;

  settings = await api("/api/settings");
  renderSettingsBadge();
  strategies = await api("/api/strategies");
  renderStrategies();
  await refreshState();
  await loadChart();
  connectWS();

  setInterval(refreshState, 12000);
  setInterval(loadChart, 20000);
}

init();
