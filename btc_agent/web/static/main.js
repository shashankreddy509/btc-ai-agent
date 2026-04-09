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

// ── Boot ──────────────────────────────────────────────────────────────────────
document.getElementById('scan-btn').addEventListener('click', triggerScan);
document.getElementById('brief-btn').addEventListener('click', triggerBrief);

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
  await Promise.all([loadBriefing(), loadScan(), fetchBTCPrice(), pollStatus()]);
  setInterval(() => Promise.all([loadBriefing(), loadScan()]), REFRESH_MS);
  setInterval(fetchBTCPrice, 10_000);
  setInterval(pollStatus, 3000);
})();
