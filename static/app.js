/* Aura Trade Panel — frontend logic */
"use strict";

const $ = (sel) => document.querySelector(sel);
const fmt = (n, d = 2) =>
  n == null || isNaN(n) ? "—" : Number(n).toLocaleString("en-US", { maximumFractionDigits: d });
const faTime = (ts) =>
  new Date(ts).toLocaleTimeString("fa-IR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const QUICK_COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "BNBUSDT", "DOGEUSDT",
  "ADAUSDT", "LINKUSDT", "AVAXUSDT", "TONUSDT", "TRXUSDT", "DOTUSDT", "LTCUSDT",
  "NEARUSDT", "SUIUSDT", "PEPEUSDT"];
const VIEW_TITLES = { overview: "نمای کلی", strategies: "استراتژی‌ها", risk: "مدیریت ریسک و سرمایه" };

let state = null;
let strategies = [];
let settings = null;
let indicators = [];
let candles = [];
let ws = null;
const openTabs = {}; // strategy_id -> active tab name

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

/* ═══════════════ Views ═══════════════ */
function switchView(name) {
  document.querySelectorAll(".view").forEach((v) => (v.hidden = true));
  $(`#view-${name}`).hidden = false;
  document.querySelectorAll(".nav-item").forEach((b) =>
    b.classList.toggle("active", b.dataset.view === name));
  $("#view-title").textContent = VIEW_TITLES[name] || "";
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
  const daily = state.daily_pnl || 0;
  $("#stat-daily").textContent = `امروز: ${daily >= 0 ? "+" : "−"}$${fmt(Math.abs(daily))}`;

  $("#stat-winrate").textContent = state.stats.total_trades ? `${fmt(state.stats.win_rate, 1)}٪` : "—";
  $("#winrate-fill").style.width = `${state.stats.win_rate || 0}%`;

  $("#stat-positions").textContent = state.positions.length;
  $("#stat-strategies").textContent =
    `استراتژی فعال: ${strategies.filter((s) => s.enabled).length}`;

  const btn = $("#btn-engine");
  btn.textContent = state.running ? "⏸ خاموش کردن موتور" : "▶ روشن کردن موتور";
  btn.className = `btn btn-block ${state.running ? "btn-danger" : "btn-primary"}`;
  $("#engine-dot").className = `dot ${state.running ? "dot-on" : "dot-off"}`;
  $("#engine-label").textContent = state.running ? "موتور روشن" : "موتور خاموش";

  renderPositions();
  renderTrades();
  renderLogs();
  renderSignals(state.signals);
  renderRiskStatus(equity);

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

function renderRiskStatus(equity) {
  if (!state) return;
  const risk = state.risk || {};
  const daily = state.daily_pnl || 0;
  const cap = equity > 0 ? equity * (risk.max_daily_loss_pct || 5) / 100 : 0;
  const el = $("#risk-daily-now");
  el.textContent = `${daily >= 0 ? "+" : "−"}$${fmt(Math.abs(daily))}`;
  el.className = `stat-value ${daily >= 0 ? "pnl-pos" : "pnl-neg"}`;
  $("#risk-daily-cap").textContent = cap ? `سقف ضرر مجاز امروز: $${fmt(cap)}` : "سقف مجاز: —";
  $("#risk-daily-fill").style.width =
    cap && daily < 0 ? `${Math.min(100, Math.abs(daily) / cap * 100)}%` : "0";
  $("#risk-pos-now").textContent = state.positions.length;
  $("#risk-pos-cap").textContent = `از سقف ${risk.max_open_positions ?? "—"}`;
}

function sideBadge(side) {
  const isLong = side === "LONG" || side === "BUY";
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
      <td>${esc(p.symbol)}</td>
      <td>${sideBadge(p.side)}</td>
      <td class="num">${fmt(p.entry ?? p.avgOpenPrice, 4)}</td>
      <td class="num">${fmt(p.mark ?? p.markPrice, 4)}</td>
      <td class="num">${fmt(p.qty, 6)}</td>
      <td class="num">${p.leverage ?? "—"}x</td>
      <td class="num">${fmt(p.sl, 4)}</td>
      <td class="num">${fmt(p.tp, 4)}</td>
      <td class="num ${pnl >= 0 ? "long-ink" : "short-ink"}">${pnl >= 0 ? "+" : ""}${fmt(pnl)}</td>
      <td><button class="btn btn-ghost btn-sm" onclick="closePosition('${esc(id)}')">بستن</button></td>
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
  const reasonFa = { SL: "حد ضرر", TP: "حد سود", MANUAL: "دستی", END: "پایان" };
  tbody.innerHTML = trades.slice(0, 25).map((t) => `<tr>
      <td>${faTime(t.closed_at || t.opened_at)}</td>
      <td>${esc(t.symbol)}</td>
      <td>${sideBadge(t.side)}</td>
      <td class="num">${fmt(t.entry, 4)}</td>
      <td class="num">${fmt(t.exit, 4)}</td>
      <td>${reasonFa[t.close_reason] || esc(t.close_reason) || "—"}</td>
      <td class="num ${t.pnl >= 0 ? "long-ink" : "short-ink"}">${t.pnl >= 0 ? "+" : ""}${fmt(t.pnl)}</td>
    </tr>`).join("");
}

function renderLogs() {
  const feed = $("#log-feed");
  feed.innerHTML = (state.logs || []).map((l) =>
    `<div class="log-line ${esc(l.level)}">
       <span class="log-time">${faTime(l.ts)}</span>
       <span class="log-text">${esc(l.text)}</span>
     </div>`).join("") || `<div class="empty-state">رویدادی ثبت نشده</div>`;
}

function signalHTML(s) {
  const isLong = s.side === "LONG";
  return `<div class="signal-item ${isLong ? "long" : "short"}">
    <div class="signal-top">
      <span class="signal-side ${isLong ? "long-ink" : "short-ink"}">${isLong ? "▲ لانگ" : "▼ شورت"} · ${esc(s.symbol)}</span>
      <span class="signal-meta">${faTime(s.ts)}</span>
    </div>
    <div class="signal-reason">${esc(s.reason)}</div>
    <div class="signal-meta">${esc(s.strategy)} · قیمت ${fmt(s.price, 4)} · اطمینان ${Math.round(s.confidence * 100)}٪</div>
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
const SOURCE_TAGS = { user: "کد شما", custom: "سازنده", builtin: "داخلی" };

function renderStrategies() {
  const grid = $("#strategies-grid");
  if (!strategies.length) {
    grid.innerHTML = `<div class="empty-state card">هنوز استراتژی‌ای اضافه نکرده‌اید — از بالا شروع کنید</div>`;
    refreshChartSymbols();
    return;
  }
  grid.innerHTML = strategies.map((s) => strategyCardHTML(s)).join("");
  refreshChartSymbols();
}

function strategyCardHTML(s) {
  const c = s.config || {};
  const tab = openTabs[s.id] || "config";
  const symbols = c.symbols || ["BTCUSDT"];
  return `<div class="strategy-card ${s.enabled ? "enabled" : ""}" data-id="${esc(s.id)}">
    <div class="strategy-top">
      <span class="strategy-name">${esc(s.name)}
        <span class="source-tag">${SOURCE_TAGS[s.source] || ""}</span>
      </span>
      <label class="switch">
        <input type="checkbox" ${s.enabled ? "checked" : ""} onchange="toggleStrategy('${esc(s.id)}', this.checked)">
        <span class="track"></span>
      </label>
    </div>
    <div class="strategy-desc">${esc(s.description)}</div>

    <div class="tabs">
      ${[["config", "تنظیمات"], ["coins", "ارزها"], ["backtest", "بک‌تست"]].map(([t, label]) =>
        `<button class="tab ${tab === t ? "active" : ""}" onclick="setTab('${esc(s.id)}','${t}')">${label}</button>`).join("")}
    </div>

    <div class="tab-panel" ${tab !== "config" ? "hidden" : ""}>
      <div class="strategy-conf">
        <label>تایم‌فریم
          <select class="input input-sm" data-cfg="interval" onchange="saveCfg('${esc(s.id)}', this)">
            ${[["1m","۱ دقیقه"],["5m","۵ دقیقه"],["15m","۱۵ دقیقه"],["1h","۱ ساعت"],["4h","۴ ساعت"],["1d","روزانه"]].map(
              ([v, t]) => `<option value="${v}" ${c.interval === v ? "selected" : ""}>${t}</option>`).join("")}
          </select>
        </label>
        <label>اهرم
          <input class="input input-sm" dir="ltr" type="number" min="1" max="125" value="${c.leverage ?? 5}"
                 data-cfg="leverage" onchange="saveCfg('${esc(s.id)}', this)">
        </label>
        <label>ریسک هر معامله ٪
          <input class="input input-sm" dir="ltr" type="number" min="0.1" max="20" step="0.1" value="${c.risk_pct ?? 2}"
                 data-cfg="risk_pct" onchange="saveCfg('${esc(s.id)}', this)">
        </label>
        <label>سقف پوزیشن این استراتژی
          <input class="input input-sm" dir="ltr" type="number" min="1" max="20" value="${c.max_positions ?? 1}"
                 data-cfg="max_positions" onchange="saveCfg('${esc(s.id)}', this)">
        </label>
      </div>
    </div>

    <div class="tab-panel" ${tab !== "coins" ? "hidden" : ""}>
      <div class="chips">
        ${symbols.map((sym) => `<span class="chip">${esc(sym)}
          <button title="حذف" onclick="removeSymbol('${esc(s.id)}','${esc(sym)}')">✕</button></span>`).join("")}
      </div>
      <div class="chip-add">
        <input class="input input-sm" dir="ltr" placeholder="مثلاً OPUSDT" style="flex:1"
               onkeydown="if(event.key==='Enter')addSymbol('${esc(s.id)}', this)">
        <button class="btn btn-ghost btn-sm" onclick="addSymbol('${esc(s.id)}', this.previousElementSibling)">افزودن</button>
      </div>
      <div class="quick-coins">
        ${QUICK_COINS.filter((q) => !symbols.includes(q)).slice(0, 10).map((q) =>
          `<button class="quick-coin" onclick="addSymbolDirect('${esc(s.id)}','${q}')">＋ ${q}</button>`).join("")}
      </div>
    </div>

    <div class="tab-panel" ${tab !== "backtest" ? "hidden" : ""}>
      <div class="bt-controls">
        <select class="input input-sm bt-symbol">
          ${symbols.map((sym) => `<option>${esc(sym)}</option>`).join("")}
        </select>
        <select class="input input-sm bt-interval">
          ${["15m", "5m", "1m", "1h", "4h", "1d"].map((v) =>
            `<option ${v === (c.interval || "15m") ? "selected" : ""}>${v}</option>`).join("")}
        </select>
        <select class="input input-sm bt-bars">
          <option value="300">۳۰۰ کندل</option><option value="500" selected>۵۰۰ کندل</option>
          <option value="1000">۱۰۰۰ کندل</option>
        </select>
        <button class="btn btn-primary btn-sm" onclick="runBacktest('${esc(s.id)}', this)">اجرای بک‌تست</button>
      </div>
      <div class="bt-result"></div>
    </div>

    <div class="strategy-foot">
      <span class="strategy-status ${s.enabled ? "on" : "off"}">
        ${s.enabled ? "● فعال — در حال رصد " + symbols.length + " ارز" : "○ غیرفعال"}</span>
      <button class="btn btn-ghost btn-sm" onclick="deleteStrategy('${esc(s.id)}')">حذف</button>
    </div>
  </div>`;
}

window.setTab = (id, tab) => {
  openTabs[id] = tab;
  renderStrategies();
};

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

async function saveSymbols(id, symbols) {
  await api(`/api/strategies/${id}/config`, { method: "POST", body: { config: { symbols } } });
  const s = strategies.find((x) => x.id === id);
  if (s) s.config = { ...s.config, symbols };
  renderStrategies();
}

window.addSymbol = (id, input) => {
  const sym = (input.value || "").trim().toUpperCase();
  if (!sym) return;
  const s = strategies.find((x) => x.id === id);
  const symbols = [...new Set([...(s.config.symbols || []), sym])];
  saveSymbols(id, symbols);
};

window.addSymbolDirect = (id, sym) => {
  const s = strategies.find((x) => x.id === id);
  const symbols = [...new Set([...(s.config.symbols || []), sym])];
  saveSymbols(id, symbols);
};

window.removeSymbol = (id, sym) => {
  const s = strategies.find((x) => x.id === id);
  const symbols = (s.config.symbols || []).filter((x) => x !== sym);
  if (!symbols.length) { alert("حداقل یک ارز باید در واچ‌لیست بماند"); return; }
  saveSymbols(id, symbols);
};

window.deleteStrategy = async (id) => {
  if (!confirm("این استراتژی حذف شود؟")) return;
  await api(`/api/strategies/${id}`, { method: "DELETE" });
  strategies = await api("/api/strategies");
  renderStrategies();
};

window.closePosition = async (id) => {
  if (!confirm("این پوزیشن بسته شود؟")) return;
  await api(`/api/positions/${id}/close`, { method: "POST" });
  refreshState();
};

/* ═══════════════ Backtest ═══════════════ */
window.runBacktest = async (id, btn) => {
  const card = btn.closest(".strategy-card");
  const out = card.querySelector(".bt-result");
  out.innerHTML = `<div class="muted small">در حال اجرای بک‌تست…</div>`;
  btn.disabled = true;
  try {
    const res = await api("/api/backtest", { method: "POST", body: {
      strategy_id: id,
      symbol: card.querySelector(".bt-symbol").value,
      interval: card.querySelector(".bt-interval").value,
      bars: Number(card.querySelector(".bt-bars").value),
    }});
    if (!res.ok) { out.innerHTML = `<div class="settings-msg err">✗ ${esc(res.error)}</div>`; return; }
    const r = res.result;
    const pf = r.profit_factor == null ? "—" : r.profit_factor;
    out.innerHTML = `
      <div class="bt-stats">
        <div class="bt-stat"><b class="${r.return_pct >= 0 ? "long-ink" : "short-ink"}">${r.return_pct >= 0 ? "+" : ""}${fmt(r.return_pct, 1)}%</b><span>بازده کل</span></div>
        <div class="bt-stat"><b>${fmt(r.win_rate, 1)}%</b><span>نرخ برد (${r.wins}/${r.total_trades})</span></div>
        <div class="bt-stat"><b>${pf}</b><span>فاکتور سود</span></div>
        <div class="bt-stat"><b class="short-ink">−${fmt(r.max_drawdown_pct, 1)}%</b><span>حداکثر افت سرمایه</span></div>
        <div class="bt-stat"><b>${r.total_trades}</b><span>تعداد معامله</span></div>
        <div class="bt-stat"><b>$${fmt(r.final_balance)}</b><span>سرمایه نهایی</span></div>
      </div>
      <canvas class="bt-curve"></canvas>
      <div class="muted small">${res.bars} کندل ${esc(res.interval)} روی ${esc(res.symbol)} — نتایج گذشته تضمین آینده نیست.</div>`;
    drawEquityCurve(out.querySelector(".bt-curve"), r.equity_curve, r.initial_balance);
  } catch (e) {
    out.innerHTML = `<div class="settings-msg err">✗ خطا در بک‌تست</div>`;
  } finally {
    btn.disabled = false;
  }
};

function drawEquityCurve(canvas, curve, base) {
  if (!canvas || !curve || curve.length < 2) return;
  const dpr = window.devicePixelRatio || 1;
  const W = canvas.clientWidth || 300, H = canvas.clientHeight || 70;
  canvas.width = W * dpr; canvas.height = H * dpr;
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const lo = Math.min(...curve), hi = Math.max(...curve);
  const range = hi - lo || 1;
  const x = (i) => (i / (curve.length - 1)) * (W - 8) + 4;
  const y = (v) => 6 + (1 - (v - lo) / range) * (H - 12);
  // baseline
  ctx.strokeStyle = "#232a38"; ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(4, y(base)); ctx.lineTo(W - 4, y(base)); ctx.stroke();
  const up = curve[curve.length - 1] >= base;
  ctx.strokeStyle = up ? "#0ca30c" : "#e66767";
  ctx.lineWidth = 2; ctx.lineJoin = "round";
  ctx.beginPath();
  curve.forEach((v, i) => (i ? ctx.lineTo(x(i), y(v)) : ctx.moveTo(x(i), y(v))));
  ctx.stroke();
}

/* ═══════════════ Candlestick chart ═══════════════ */
const chart = { canvas: null, ctx: null, hover: -1, geom: null };

function refreshChartSymbols() {
  const sel = $("#chart-symbol");
  const current = sel.value;
  const all = new Set(QUICK_COINS.slice(0, 6));
  strategies.forEach((s) => (s.config.symbols || []).forEach((sym) => all.add(sym)));
  sel.innerHTML = [...all].map((sym) => `<option>${esc(sym)}</option>`).join("");
  if (current && all.has(current)) sel.value = current;
}

async function loadChart() {
  const symbol = $("#chart-symbol").value || "BTCUSDT";
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

/* risk settings */
function fillRiskForm() {
  const r = settings?.risk || {};
  $("#risk-per-trade").value = r.default_risk_pct ?? 2;
  $("#risk-daily").value = r.max_daily_loss_pct ?? 5;
  $("#risk-maxpos").value = r.max_open_positions ?? 5;
  $("#risk-maxlev").value = r.max_leverage ?? 20;
}

async function saveRisk() {
  const res = await api("/api/settings/risk", { method: "POST", body: {
    default_risk_pct: Number($("#risk-per-trade").value),
    max_daily_loss_pct: Number($("#risk-daily").value),
    max_open_positions: Number($("#risk-maxpos").value),
    max_leverage: Number($("#risk-maxlev").value),
  }});
  const msg = $("#risk-msg");
  if (res.ok) {
    if (settings) settings.risk = res.risk;
    msg.textContent = "✓ قوانین ریسک ذخیره شد";
    msg.className = "settings-msg ok";
    refreshState();
  } else {
    msg.textContent = "✗ ذخیره نشد";
    msg.className = "settings-msg err";
  }
}

/* custom strategy builder */
function ruleRowHTML() {
  return `<div class="rule-row">
    <select class="input r-ind" onchange="showHint(this)">
      ${indicators.map((it) => `<option value="${esc(it.id)}">${esc(it.label)}</option>`).join("")}
    </select>
    <select class="input r-op"><option><</option><option>></option><option><=</option><option>>=</option><option>==</option></select>
    <input class="input r-val" dir="ltr" type="number" step="any" value="30">
    <button class="rule-del" onclick="this.closest('.rule-row').nextElementSibling?.remove(); this.closest('.rule-row').remove()">✕</button>
  </div><div class="rule-hint">${esc(indicators[0]?.hint || "")}</div>`;
}

window.showHint = (sel) => {
  const it = indicators.find((x) => x.id === sel.value);
  const hint = sel.closest(".rule-row").nextElementSibling;
  if (hint && hint.classList.contains("rule-hint")) hint.textContent = it?.hint || "";
};

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

/* user python strategy upload */
async function saveUpload() {
  const msg = $("#upload-msg");
  const name = $("#up-name").value.trim() || "my_strategy.py";
  const code = $("#up-code").value;
  if (!code.trim()) { msg.textContent = "✗ کد استراتژی خالی است"; msg.className = "settings-msg err"; return; }
  msg.textContent = "در حال بارگذاری…"; msg.className = "settings-msg";
  const res = await api("/api/strategies/upload", { method: "POST", body: { filename: name, code } });
  if (res.ok) {
    msg.textContent = "✓ استراتژی بارگذاری شد"; msg.className = "settings-msg ok";
    strategies = await api("/api/strategies");
    renderStrategies();
    setTimeout(() => { $("#modal-upload").hidden = true; }, 700);
  } else {
    msg.textContent = `✗ ${res.error}`; msg.className = "settings-msg err";
  }
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

  document.querySelectorAll(".nav-item").forEach((b) =>
    b.addEventListener("click", () => switchView(b.dataset.view)));

  bindModal("#modal-settings");
  bindModal("#modal-custom");
  bindModal("#modal-upload");
  $("#btn-settings").onclick = openSettings;
  $("#btn-save-settings").onclick = saveSettings;
  $("#btn-test-conn").onclick = testConnection;
  $("#set-mode").onchange = () => { $("#live-warning").hidden = $("#set-mode").value !== "live"; };
  $("#btn-save-risk").onclick = saveRisk;

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

  $("#btn-upload-strategy").onclick = () => {
    $("#upload-msg").textContent = "";
    $("#modal-upload").hidden = false;
  };
  $("#up-file").onchange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    $("#up-name").value = file.name;
    $("#up-code").value = await file.text();
  };
  $("#btn-save-upload").onclick = saveUpload;

  $("#btn-engine").onclick = async () => {
    const running = state?.running;
    if (!running && settings?.mode === "live") {
      if (!confirm("موتور در حالت واقعی روشن می‌شود و سفارش واقعی ثبت خواهد کرد. ادامه می‌دهید؟")) return;
    }
    const res = await api(`/api/engine/${running ? "stop" : "start"}`, { method: "POST" });
    if (!running && !res.running) {
      alert("موتور روشن نشد — در حالت واقعی ابتدا کلید API را در تنظیمات وارد کنید.");
    }
    refreshState();
  };

  $("#chart-symbol").onchange = loadChart;
  $("#chart-interval").onchange = loadChart;

  [settings, strategies, indicators] = await Promise.all([
    api("/api/settings"), api("/api/strategies"), api("/api/indicators"),
  ]);
  renderSettingsBadge();
  renderStrategies();
  fillRiskForm();
  await refreshState();
  await loadChart();
  connectWS();

  setInterval(refreshState, 12000);
  setInterval(loadChart, 20000);
}

init();
