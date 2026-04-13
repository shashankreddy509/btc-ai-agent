const REFRESH_MS = 60_000;
const TZ_KEY     = 'btc_agent_tz';
const DEFAULT_TZ = 'Asia/Kolkata';

// ── Cached data (re-render without re-fetching on tz change) ─────────────────
let _scanData  = null;
let _briefData = null;

// ── Timezone helpers ──────────────────────────────────────────────────────────
function getTz() {
  return localStorage.getItem(TZ_KEY) || DEFAULT_TZ;
}

function setTz(tz) {
  localStorage.setItem(TZ_KEY, tz);
}

function formatTs(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d)) return iso;  // fallback: show raw string if unparseable
  return d.toLocaleString('en-GB', {
    timeZone: getTz(),
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
    hour12: false,
  }).replace(',', '');
}

function tzAbbr() {
  const sel = document.getElementById('tz-select');
  return sel ? sel.options[sel.selectedIndex].text.split(' ')[0] : '';
}

function updateThHeader() {
  const th = document.getElementById('th-baropen');
  if (th) th.textContent = `Bar Open (${tzAbbr()})`;
}

async function fetchJSON(url) {
  const r = await fetch(url, { cache: 'no-store' });
  if (!r.ok) throw new Error(`${url} → ${r.status}`);
  return r.json();
}

function patternClass(name) {
  if (name.includes('Flag'))    return 'pattern-flag';
  if (name.includes('Morning')) return 'pattern-morning';
  if (name.includes('Evening')) return 'pattern-evening';
  return '';
}

// ── Render (uses cached data, no fetch) ───────────────────────────────────────
function renderBriefing() {
  if (!_briefData) return;
  document.getElementById('briefing-text').textContent = _briefData.text || 'No briefing yet.';
  document.getElementById('brief-ts').textContent = formatTs(_briefData.timestamp);
}

function renderScan() {
  if (!_scanData) return;
  document.getElementById('scan-ts').textContent = formatTs(_scanData.timestamp);

  const hits  = _scanData.results || [];
  const tbody = document.getElementById('scan-body');

  if (hits.length === 0) {
    tbody.innerHTML = '<tr class="empty-row"><td colspan="6">No patterns detected yet — trigger a scan to start.</td></tr>';
    return;
  }

  tbody.innerHTML = hits.map(h => {
    const depoHtml = h.depo_line
      ? `<span class="depo-hit">${Number(h.depo_line).toLocaleString()}</span>`
      : `<span class="depo-none">none</span>`;
    const agoHtml = h.bars_ago === 0
      ? `<span style="color:var(--green)">current</span>`
      : `<span style="color:var(--muted)">${h.bars_ago} bars ago</span>`;
    const openTime = formatTs(h.bar_open_time);
    const openPx   = h.bar_open_price
      ? Number(h.bar_open_price).toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 })
      : '—';
    return `<tr>
      <td><span class="tf-badge">${h.tf}</span></td>
      <td class="${patternClass(h.pattern)}">${h.pattern}</td>
      <td style="text-align:right">${agoHtml}</td>
      <td style="color:var(--muted);font-size:12px">${openTime}</td>
      <td style="text-align:right;color:var(--accent)">${openPx}</td>
      <td>${depoHtml}</td>
    </tr>`;
  }).join('');
}

// ── Fetch + render ────────────────────────────────────────────────────────────
async function loadBriefing() {
  try {
    _briefData = await fetchJSON('/api/brief');
    renderBriefing();
  } catch (e) {
    document.getElementById('briefing-text').textContent = 'Failed to load briefing.';
  }
}

async function loadScan() {
  try {
    _scanData = await fetchJSON('/api/scan');
    renderScan();
  } catch (e) {
    document.getElementById('scan-body').innerHTML =
      '<tr class="empty-row"><td colspan="6">Failed to load scan results.</td></tr>';
  }
}

// ── Status / spinner management ───────────────────────────────────────────────
async function pollStatus() {
  try {
    const s = await fetchJSON('/api/status');
    setRunning('scan',  s.scan_running);
    setRunning('brief', s.brief_running);
  } catch (_) {}
}

function setRunning(which, running) {
  const btn = document.getElementById(`${which}-btn`);
  const dot = document.getElementById(`${which}-dot`);
  btn.disabled = running;
  if (running) {
    btn.innerHTML = '<span class="spinner"></span>Running…';
    dot.className = 'status-dot dot-run';
  } else {
    btn.textContent = which === 'scan' ? 'Trigger Scan Now' : 'Trigger Briefing Now';
    dot.className = 'status-dot dot-ok';
  }
}

// ── Trigger buttons ───────────────────────────────────────────────────────────
async function triggerScan() {
  document.getElementById('scan-btn').disabled = true;
  await fetch('/api/scan/trigger', { method: 'POST' });
  const iv = setInterval(async () => {
    await pollStatus();
    await loadScan();
  }, 3000);
  setTimeout(() => clearInterval(iv), 5 * 60 * 1000); // stop polling after 5min
}

async function triggerBrief() {
  document.getElementById('brief-btn').disabled = true;
  await fetch('/api/brief/trigger', { method: 'POST' });
  const iv = setInterval(async () => {
    await pollStatus();
    await loadBriefing();
  }, 3000);
  setTimeout(() => clearInterval(iv), 5 * 60 * 1000);
}

// ── BTC live price ────────────────────────────────────────────────────────────
async function fetchBTCPrice() {
  const endpoints = [
    'https://fapi.binance.com/fapi/v1/ticker/price?symbol=BTCUSDT',
    'https://api.bybit.com/v5/market/tickers?category=linear&symbol=BTCUSDT',
  ];
  for (const url of endpoints) {
    try {
      const r = await fetch(url);
      if (!r.ok) continue;
      const d = await r.json();
      const price = d.price
        ? parseFloat(d.price)
        : parseFloat(d?.result?.list?.[0]?.lastPrice);
      if (!price || isNaN(price)) continue;
      document.getElementById('btc-price').textContent =
        '$' + price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
      return;
    } catch (_) {}
  }
}

// ── Trading scanner ───────────────────────────────────────────────────────────
let _tradingData = null;

function renderTrading() {
  if (!_tradingData) return;
  const { signals = [], positions = [], history = [], running, settings = {} } = _tradingData;

  document.getElementById('trade-mode-label').textContent = (settings.mode || 'paper').toUpperCase();
  const startBtn = document.getElementById('trade-start-btn');
  const stopBtn  = document.getElementById('trade-stop-btn');
  const dot      = document.getElementById('trade-dot');
  if (running) {
    startBtn.style.display = 'none';
    stopBtn.style.display  = '';
    dot.className = 'status-dot dot-run';
  } else {
    startBtn.style.display = '';
    stopBtn.style.display  = 'none';
    dot.className = 'status-dot dot-ok';
  }

  // populate settings inputs (only if not focused)
  const cfgMap = {
    'cfg-mode':     settings.mode,
    'cfg-tf-min':   settings.tf_min,
    'cfg-tf-max':   settings.tf_max,
    'cfg-interval': settings.scan_interval_min,
    'cfg-qty':      settings.qty,
    'cfg-max-sl':   settings.max_sl,
    'cfg-min-tp':   settings.min_tp,
    'cfg-max-conc': settings.max_concurrent,
  };
  for (const [id, val] of Object.entries(cfgMap)) {
    const el = document.getElementById(id);
    if (el && document.activeElement !== el) el.value = val ?? '';
  }

  // signals table
  const sigBody = document.getElementById('trade-signals-body');
  const pendingSigs = signals.filter(s => s.status === 'pending');
  if (!pendingSigs.length) {
    sigBody.innerHTML = '<tr class="empty-row"><td colspan="7">No pending signals</td></tr>';
  } else {
    sigBody.innerHTML = pendingSigs.map(s => {
      const exp = formatTs(s.expires_at);
      const dirClass = s.direction === 'long' ? 'dir-long' : 'dir-short';
      return `<tr>
        <td>${s.pattern}</td>
        <td><span class="tf-badge">${s.tf}m</span></td>
        <td class="${dirClass}">${s.direction.toUpperCase()}</td>
        <td style="text-align:right">${Number(s.entry_trigger).toLocaleString('en-US',{minimumFractionDigits:1,maximumFractionDigits:1})}</td>
        <td style="text-align:right;color:var(--red)">${Number(s.sl_wick).toLocaleString('en-US',{minimumFractionDigits:1,maximumFractionDigits:1})}</td>
        <td style="color:var(--muted);font-size:12px">${exp}</td>
        <td style="color:var(--accent)">${s.status}</td>
      </tr>`;
    }).join('');
  }

  // positions table
  const posBody = document.getElementById('trade-positions-body');
  const openPos = positions.filter(p => p.status === 'open');
  if (!openPos.length) {
    posBody.innerHTML = '<tr class="empty-row"><td colspan="7">No open positions</td></tr>';
  } else {
    posBody.innerHTML = openPos.map(p => {
      const dirClass = p.direction === 'long' ? 'dir-long' : 'dir-short';
      return `<tr>
        <td class="${dirClass}">${p.direction.toUpperCase()}</td>
        <td style="text-align:right">${Number(p.entry_price).toLocaleString('en-US',{minimumFractionDigits:1,maximumFractionDigits:1})}</td>
        <td style="text-align:right;color:var(--red)">${Number(p.sl).toLocaleString('en-US',{minimumFractionDigits:1,maximumFractionDigits:1})}</td>
        <td style="text-align:right;color:var(--green)">${Number(p.tp).toLocaleString('en-US',{minimumFractionDigits:1,maximumFractionDigits:1})}</td>
        <td style="text-align:right">${p.qty}</td>
        <td style="color:var(--muted);font-size:12px">${formatTs(p.opened_at)}</td>
        <td>${p.coinbase_order_id ? `<span style="color:var(--muted);font-size:11px">${p.coinbase_order_id.slice(0,8)}…</span>` : '—'}</td>
      </tr>`;
    }).join('');
  }

  // history table
  const histBody = document.getElementById('trade-history-body');
  if (!history.length) {
    histBody.innerHTML = '<tr class="empty-row"><td colspan="6">No completed trades</td></tr>';
  } else {
    histBody.innerHTML = [...history].reverse().slice(0, 20).map(r => {
      const p = r.position;
      const dirClass = p.direction === 'long' ? 'dir-long' : 'dir-short';
      const pnlClass = (p.pnl ?? 0) >= 0 ? 'pnl-pos' : 'pnl-neg';
      const pnlStr   = p.pnl != null ? (p.pnl >= 0 ? '+' : '') + p.pnl.toFixed(4) : '—';
      return `<tr>
        <td class="${dirClass}">${p.direction.toUpperCase()}</td>
        <td><span class="tf-badge">${p.tf ? p.tf + 'm' : '—'}</span></td>
        <td>${p.pattern || '—'}</td>
        <td style="text-align:right">${Number(p.entry_price).toLocaleString('en-US',{minimumFractionDigits:1,maximumFractionDigits:1})}</td>
        <td style="text-align:right">${Number(r.close_price).toLocaleString('en-US',{minimumFractionDigits:1,maximumFractionDigits:1})}</td>
        <td style="text-align:right" class="${pnlClass}">${pnlStr}</td>
        <td style="color:${r.close_reason==='tp'?'var(--green)':'var(--red)'}">${r.close_reason.toUpperCase()}</td>
        <td style="color:var(--muted);font-size:12px">${formatTs(r.closed_at)}</td>
      </tr>`;
    }).join('');
  }
}

async function loadTrading() {
  try {
    _tradingData = await fetchJSON('/api/trading/state');
    renderTrading();
  } catch (_) {}
}

async function startTrading() {
  await fetch('/api/trading/start', { method: 'POST' });
  await loadTrading();
}

async function stopTrading() {
  await fetch('/api/trading/stop', { method: 'POST' });
  await loadTrading();
}

async function saveTradingSettings() {
  const settings = {
    mode:              document.getElementById('cfg-mode').value,
    tf_min:            parseInt(document.getElementById('cfg-tf-min').value),
    tf_max:            parseInt(document.getElementById('cfg-tf-max').value),
    scan_interval_min: parseInt(document.getElementById('cfg-interval').value),
    qty:               parseFloat(document.getElementById('cfg-qty').value),
    max_sl:            parseFloat(document.getElementById('cfg-max-sl').value),
    min_tp:            parseFloat(document.getElementById('cfg-min-tp').value),
    max_concurrent:    parseInt(document.getElementById('cfg-max-conc').value),
  };
  await fetch('/api/trading/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings),
  });
  const msg = document.getElementById('trade-save-msg');
  msg.style.display = 'inline';
  setTimeout(() => { msg.style.display = 'none'; }, 2000);
  await loadTrading();
}

// ── Boot ──────────────────────────────────────────────────────────────────────
document.getElementById('scan-btn').addEventListener('click', triggerScan);
document.getElementById('brief-btn').addEventListener('click', triggerBrief);
document.getElementById('trade-start-btn').addEventListener('click', startTrading);
document.getElementById('trade-stop-btn').addEventListener('click', stopTrading);
document.getElementById('trade-save-btn').addEventListener('click', saveTradingSettings);

const tzSelect = document.getElementById('tz-select');
tzSelect.value = getTz();
tzSelect.addEventListener('change', () => {
  setTz(tzSelect.value);
  updateThHeader();
  // Re-render instantly from cached data — no network call needed
  renderBriefing();
  renderScan();
});

(async () => {
  updateThHeader();
  await Promise.all([loadBriefing(), loadScan(), loadTrading(), fetchBTCPrice(), pollStatus()]);
  setInterval(() => Promise.all([loadBriefing(), loadScan()]), REFRESH_MS);
  setInterval(loadTrading, 5000);   // refresh trading state every 5s
  setInterval(fetchBTCPrice, 10_000);
  setInterval(pollStatus, 3000);
})();
