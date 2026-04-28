const REFRESH_MS    = 60_000;
const TZ_KEY        = 'btc_agent_tz';
const DEFAULT_TZ    = 'Asia/Kolkata';
const THEME_KEY     = 'btc_agent_theme';
const DEFAULT_THEME = 'dark';

// ── Firebase Auth ──────────────────────────────────────────────────────────────
const _auth     = firebase.auth();
const _provider = new firebase.auth.GoogleAuthProvider();
let   _currentUser = null;   // null = not signed in

async function _getToken() {
  if (!_currentUser) return null;
  return _currentUser.getIdToken();   // auto-refreshes before expiry
}

function signOut() {
  _auth.signOut();
}

async function signInWithGoogle() {
  try {
    await _auth.signInWithPopup(_provider);
  } catch (e) {
    console.error('Sign-in failed:', e.message);
  }
}

// Watch auth state — update UI and re-render relevant pages on change
_auth.onAuthStateChanged(user => {
  _currentUser = user;
  _updateAuthUI();
  // Re-render trading page if it's currently visible
  if (document.getElementById('page-trading')?.classList.contains('active')) {
    _showTradingContent();
  }
  // Re-render settings account card if visible
  if (document.getElementById('page-settings')?.classList.contains('active')) {
    _renderAccountCard();
  }
});

function _updateAuthUI() {
  const signedIn  = !!_currentUser;
  const photo     = _currentUser?.photoURL || '';
  const name      = _currentUser?.displayName || _currentUser?.email || '';
  const email     = _currentUser?.email || '';

  // Sidebar
  _show('sidebar-user-signed-in',  signedIn);
  _show('sidebar-user-signed-out', !signedIn);
  if (signedIn) {
    const av = document.getElementById('sidebar-avatar');
    if (av) { av.src = photo; av.style.display = photo ? 'inline-block' : 'none'; }
    _setText('sidebar-display-name', name);
  }

  // Mobile topbar
  _show('mob-user-signed-in',  signedIn);
  _show('mob-user-signed-out', !signedIn);
  if (signedIn && photo) {
    const mav = document.getElementById('mob-avatar');
    if (mav) mav.src = photo;
  }
}

const ADMIN_EMAIL = 'shashankreddy509@gmail.com';
function _isAdmin() { return _currentUser?.email === ADMIN_EMAIL; }

function _renderAccountCard() {
  const signedIn = !!_currentUser;
  const admin    = _isAdmin();
  _show('settings-signed-in',  signedIn);
  _show('settings-signed-out', !signedIn);
  _show('settings-auth-note',  !signedIn);

  // Only broker selector card is always visible to signed-in users
  // All credential cards are controlled by onBrokerChange
  const brokerCard = document.getElementById('s-card-broker');
  if (brokerCard) brokerCard.style.display = signedIn ? '' : 'none';
  if (!signedIn) onBrokerChange('');
  // Re-gate Vishal page when auth state changes
  if (document.getElementById('page-vishal')?.classList.contains('active')) _showVishalContent();

  // Admin-only cards
  ['s-card-general','s-card-notifications','s-card-scanner'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.style.display = admin ? '' : 'none';
  });

  // Admin-only section inside Notifications card
  const adminNotif = document.getElementById('s-notif-admin');
  if (adminNotif) adminNotif.style.display = admin ? '' : 'none';

  if (signedIn) {
    const av = document.getElementById('settings-avatar');
    if (av) av.src = _currentUser.photoURL || '';
    _setText('settings-display-name', _currentUser.displayName || '');
    _setText('settings-email', _currentUser.email || '');
  }
}

// ── Settings load ─────────────────────────────────────────────────────────────

async function loadAppSettings() {
  if (!_currentUser) return;
  try {
    const d = await fetchJSON('/api/settings/app');
    const sp = (id, v) => { const el = document.getElementById(id); if (el && v) el.placeholder = v; };
    const sv = (id, v) => { const el = document.getElementById(id); if (el && v != null) el.value = v; };
    sp('s-anthropic-key',    d.anthropic_api_key);
    sv('s-anthropic-model',  d.anthropic_model);
    sv('s-cb-product',       d.coinbase_product_id);
    sv('s-cb-contract',      d.coinbase_contract_size);
    sp('s-tg-token',         d.telegram_bot_token);
    sv('s-tg-chat',          d.telegram_chat_id);
    sv('s-email-host',       d.email_smtp_host);
    sv('s-email-port',       d.email_smtp_port);
    sv('s-email-user',       d.email_user);
    sp('s-email-pass',       d.email_pass);
    sv('s-email-to',         d.email_to);
    sv('s-briefing-time',    d.briefing_time);
    sv('s-scanner-time',     d.scanner_time);
    sv('s-scanner-interval', d.scanner_interval_min);
    sv('s-scanner-tf-min',   d.scanner_tf_min);
    sv('s-scanner-tf-max',   d.scanner_tf_max);
    const channels = d.delivery_channels || [];
    ['terminal','telegram','email'].forEach(c => {
      const el = document.getElementById(`s-ch-${c}`);
      if (el) el.checked = channels.includes(c);
    });
    const patterns = d.scanner_patterns || [];
    const pm = {'s-pat-4flag':'4-Flag','s-pat-morning':'Morning Star','s-pat-evening':'Evening Star'};
    Object.entries(pm).forEach(([id, name]) => {
      const el = document.getElementById(id);
      if (el) el.checked = patterns.includes(name);
    });
  } catch (_) {}
}

async function loadUserSettings() {
  if (!_currentUser) return;
  try {
    const d = await fetchJSON('/api/settings/user');
    const sp = (id, v) => { const el = document.getElementById(id); if (el && v) el.placeholder = v; };
    sp('s-cb-key',    d.coinbase_api_key);
    sp('s-cb-secret', d.coinbase_api_secret);
    const broker = d.broker || '';
    const sel = document.getElementById('s-broker-select');
    if (sel) sel.value = broker;
    onBrokerChange(broker);
  } catch (_) {}
}

const _BROKER_CRED_CARDS = ['binance','bybit','delta','coindcx'];

function onBrokerChange(broker) {
  // Non-Coinbase credential panels
  _BROKER_CRED_CARDS.forEach(b => {
    const el = document.getElementById(`s-card-broker-${b}`);
    if (el) el.style.display = (b === broker && _currentUser) ? '' : 'none';
  });
  // Coinbase-specific cards
  const isCoinbase = broker === 'coinbase' && !!_currentUser;
  const el_exchange = document.getElementById('s-card-coinbase-exchange');
  if (el_exchange) el_exchange.style.display = (isCoinbase && _isAdmin()) ? '' : 'none';
  const el_creds = document.getElementById('s-card-coinbase-creds');
  if (el_creds) el_creds.style.display = isCoinbase ? '' : 'none';
}

async function saveBrokerChoice() {
  if (!_currentUser) return;
  const broker = _gv('s-broker-select');
  if (!broker) return;
  await fetchJSON('/api/trading/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ broker }),
  });
  onBrokerChange(broker);
}

async function saveBrokerCreds(broker) {
  if (!_currentUser) return;
  const keyEl    = document.getElementById(`s-${broker}-key`);
  const secretEl = document.getElementById(`s-${broker}-secret`);
  const key    = keyEl    ? keyEl.value.trim()    : '';
  const secret = secretEl ? secretEl.value.trim() : '';
  if (!key || !secret) {
    const errEl = document.getElementById(`s-err-broker-${broker}`);
    if (errEl) { errEl.textContent = 'Both fields are required.'; errEl.style.display = 'inline'; }
    return;
  }
  const contractEl = document.getElementById(`s-${broker}-contract`);
  const contractSize = contractEl ? _gn(`s-${broker}-contract`) : null;
  const payload = { [`${broker}_api_key`]: key, [`${broker}_api_secret`]: secret };
  if (contractSize) payload[`${broker}_contract_size`] = contractSize;
  await _saveSettings('/api/settings/user', payload, `broker-${broker}`);
  if (keyEl)    keyEl.value    = '';
  if (secretEl) secretEl.value = '';
  if (contractEl) contractEl.value = '';
}

// ── Settings save ─────────────────────────────────────────────────────────────

async function _saveSettings(endpoint, data, section) {
  const okEl  = document.getElementById(`s-ok-${section}`);
  const errEl = document.getElementById(`s-err-${section}`);
  const clean = Object.fromEntries(
    Object.entries(data).filter(([_, v]) => v !== null && v !== undefined && v !== '' && !String(v).includes('****'))
  );
  try {
    await fetchJSON(endpoint, { method: 'PUT', headers: {'Content-Type':'application/json'}, body: JSON.stringify(clean) });
    if (errEl) errEl.style.display = 'none';
    if (okEl)  { okEl.style.display = 'inline'; setTimeout(() => okEl.style.display = 'none', 2500); }
  } catch (e) {
    if (errEl) { errEl.textContent = 'Save failed.'; errEl.style.display = 'inline'; }
  }
}

function _gv(id) { const el = document.getElementById(id); return el ? el.value.trim() : null; }
function _gn(id) { const v = _gv(id); return v ? Number(v) : null; }
function _gc(id) { const el = document.getElementById(id); return el ? el.checked : false; }

async function saveAppSection(section) {
  if (!_currentUser || !_isAdmin()) return;
  let data = {};
  if (section === 'general') {
    data = { anthropic_api_key: _gv('s-anthropic-key'), anthropic_model: _gv('s-anthropic-model') };
  } else if (section === 'coinbase-exchange') {
    data = { coinbase_product_id: _gv('s-cb-product'), coinbase_contract_size: _gn('s-cb-contract') };
  } else if (section === 'notifications') {
    const channels = ['terminal','telegram','email'].filter(c => _gc(`s-ch-${c}`));
    data = { delivery_channels: channels };
    if (_isAdmin()) {
      Object.assign(data, {
        telegram_bot_token: _gv('s-tg-token'), telegram_chat_id: _gv('s-tg-chat'),
        email_smtp_host: _gv('s-email-host'), email_smtp_port: _gn('s-email-port'),
        email_user: _gv('s-email-user'), email_pass: _gv('s-email-pass'), email_to: _gv('s-email-to'),
      });
    }
  } else if (section === 'scanner') {
    const patterns = [
      ...(_gc('s-pat-4flag')   ? ['4-Flag']       : []),
      ...(_gc('s-pat-morning') ? ['Morning Star']  : []),
      ...(_gc('s-pat-evening') ? ['Evening Star']  : []),
    ];
    data = {
      briefing_time: _gv('s-briefing-time'), scanner_time: _gv('s-scanner-time'),
      scanner_interval_min: _gn('s-scanner-interval'),
      scanner_tf_min: _gn('s-scanner-tf-min'), scanner_tf_max: _gn('s-scanner-tf-max'),
      scanner_patterns: patterns.length ? patterns : null,
    };
  }
  await _saveSettings('/api/settings/app', data, section);
}

async function saveUserSection(section) {
  if (!_currentUser) return;
  let data = {};
  if (section === 'coinbase-creds') {
    data = { coinbase_api_key: _gv('s-cb-key'), coinbase_api_secret: _gv('s-cb-secret') };
    if (!data.coinbase_api_key || !data.coinbase_api_secret) {
      const errEl = document.getElementById('s-err-coinbase-creds');
      if (errEl) { errEl.textContent = 'Both fields are required.'; errEl.style.display = 'inline'; }
      return;
    }
    // Clear inputs after save
    ['s-cb-key','s-cb-secret'].forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
  }
  await _saveSettings('/api/settings/user', data, section);
  if (section === 'coinbase-creds') await loadUserSettings();
}

function _showTradingContent() {
  const gate    = document.getElementById('trading-auth-gate');
  const content = document.getElementById('trading-content');
  if (_currentUser) {
    if (gate)    gate.style.display    = 'none';
    if (content) content.style.display = '';
    loadTrading();
  } else {
    if (gate)    gate.style.display    = '';
    if (content) content.style.display = 'none';
  }
}

function _showVishalContent() {
  const gate    = document.getElementById('vishal-auth-gate');
  const content = document.getElementById('vishal-content');
  if (_currentUser) {
    if (gate)    gate.style.display    = 'none';
    if (content) content.style.display = '';
    loadVishalSettings();
  } else {
    if (gate)    gate.style.display    = '';
    if (content) content.style.display = 'none';
  }
}

// ── Vishal Sir Strategy settings ──────────────────────────────────────────────
async function loadVishalSettings() {
  if (!_currentUser) return;
  try {
    const d = await fetchJSON('/api/trading/settings');
    const vs = d.vishal || {};
    const sv = (id, v) => { const el = document.getElementById(id); if (el && v != null) el.value = v; };
    const sc = (id, v) => { const el = document.getElementById(id); if (el) el.checked = !!v; };
    sc('v-pp-enabled',    vs.pingpong_enabled);
    sv('v-pp-tf',         vs.pingpong_tf   ?? '4h');
    sv('v-pp-tp',         vs.pingpong_tp   ?? 1000);
    sv('v-pp-sl',         vs.pingpong_sl   ?? 500);
    sc('v-esc-enabled',   vs.escalator_enabled);
    sv('v-esc-trigger',   vs.escalator_trigger ?? 200);
    sv('v-esc-max-sl',    vs.escalator_max_sl  ?? 3);
    sc('v-hwt-enabled',   vs.hwt_enabled);
    sv('v-hwt-target',    vs.hwt_target ?? 450);
    sv('v-hwt-sl',        vs.hwt_sl     ?? 100);
    sv('v-hwt-sz',        vs.hwt_sz     || '');
    sv('v-hwt-dz',        vs.hwt_dz     || '');
    sc('v-cpc-enabled',   vs.cpc_enabled);
    sv('v-cpc-target',    vs.cpc_target ?? 1950);
    sv('v-cpc-sz',        vs.cpc_sz || '');
    sv('v-cpc-dz',        vs.cpc_dz || '');
    sc('v-rain-enabled',  vs.rain_enabled);
    sv('v-rain-tp',       vs.rain_tp ?? 500);
    sv('v-rain-sz',       vs.rain_sz || '');
    sv('v-rain-dz',       vs.rain_dz || '');
    sc('v-dp-enabled',    vs.dp_enabled);
    sv('v-dp-t1-pct',     vs.dp_t1_pct ?? 50);
    sv('v-dp-sz',         vs.dp_sz || '');
    sv('v-dp-dz',         vs.dp_dz || '');
  } catch (e) { console.error('loadVishalSettings', e); }
}

async function saveVishalStrategy(id) {
  if (!_currentUser) return;
  const gn = elId => { const el = document.getElementById(elId); return el ? Number(el.value) || 0 : 0; };
  const gb = elId => { const el = document.getElementById(elId); return el ? el.checked : false; };
  const existing = await fetchJSON('/api/trading/settings').catch(() => ({}));
  const vs = Object.assign({}, existing.vishal || {});
  if (id === 'pingpong') {
    const ppTf = document.getElementById('v-pp-tf')?.value || '4h';
    Object.assign(vs, { pingpong_enabled: gb('v-pp-enabled'), pingpong_tf: ppTf, pingpong_tp: gn('v-pp-tp'), pingpong_sl: gn('v-pp-sl') });
  } else if (id === 'escalator') {
    Object.assign(vs, { escalator_enabled: gb('v-esc-enabled'), escalator_trigger: gn('v-esc-trigger'), escalator_max_sl: gn('v-esc-max-sl') });
  } else if (id === 'hwt') {
    Object.assign(vs, { hwt_enabled: gb('v-hwt-enabled'), hwt_target: gn('v-hwt-target'), hwt_sl: gn('v-hwt-sl'), hwt_sz: gn('v-hwt-sz'), hwt_dz: gn('v-hwt-dz') });
  } else if (id === 'cpc') {
    Object.assign(vs, { cpc_enabled: gb('v-cpc-enabled'), cpc_target: gn('v-cpc-target'), cpc_sz: gn('v-cpc-sz'), cpc_dz: gn('v-cpc-dz') });
  } else if (id === 'rain') {
    Object.assign(vs, { rain_enabled: gb('v-rain-enabled'), rain_tp: gn('v-rain-tp'), rain_sz: gn('v-rain-sz'), rain_dz: gn('v-rain-dz') });
  } else if (id === 'dp') {
    Object.assign(vs, { dp_enabled: gb('v-dp-enabled'), dp_t1_pct: gn('v-dp-t1-pct'), dp_sz: gn('v-dp-sz'), dp_dz: gn('v-dp-dz') });
  }
  try {
    await fetchJSON('/api/trading/settings', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ vishal: vs }) });
    const btn = document.querySelector(`#v-card-${id === 'pingpong' ? 'pingpong' : id === 'escalator' ? 'escalator' : id === 'hwt' ? 'hwt' : id === 'cpc' ? 'cpc' : id === 'rain' ? 'rain' : 'dp'} .btn`);
    if (btn) { const orig = btn.textContent; btn.textContent = 'Saved ✓'; setTimeout(() => { btn.textContent = orig; }, 1500); }
  } catch (e) { console.error('saveVishalStrategy', e); }
}

// ── Utility helpers ────────────────────────────────────────────────────────────
function _show(id, visible) {
  const el = document.getElementById(id);
  if (el) el.style.display = visible ? '' : 'none';
}

function _setText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

// ── Navigation ─────────────────────────────────────────────────────────────────
let _currentSection = 'home';
let _currentSubTab  = 'briefing';

const SECTION_TITLES = { briefing: 'Morning Briefing', scanner: 'Pattern Scanner', trading: 'Live Trading', settings: 'Settings' };

function navTo(section) {
  _currentSection = section;
  const subTabsEl = document.getElementById('sub-tabs');

  if (section === 'vishal') {
    _showPage('vishal');
    subTabsEl.style.display = 'none';
    _setTopbarTitle('Vishal Sir Strategy');
    _setSidebarActive('nav-vishal');
    _showVishalContent();
  } else if (section === 'trading') {
    _showPage('trading');
    subTabsEl.style.display = 'none';
    _setTopbarTitle('Live Trading');
    _setSidebarActive('nav-trading');
    _setMobTabActive('mob-tab-trading');
    _showTradingContent();
  } else if (section === 'settings') {
    _showPage('settings');
    subTabsEl.style.display = 'none';
    _setTopbarTitle('Settings');
    _setSidebarActive('nav-settings');
    _setMobTabActive('mob-tab-settings');
    _renderSettingsPage();
  } else if (section === 'scanner') {
    _currentSubTab = 'scanner';
    _showPage('scanner');
    subTabsEl.style.display = '';
    _activateSubTab('scanner');
    _setTopbarTitle('Pattern Scanner');
    _setSidebarActive('nav-home');
    _setMobTabActive('mob-tab-scanner');
  } else {
    _currentSubTab = 'briefing';
    _showPage('briefing');
    subTabsEl.style.display = '';
    _activateSubTab('briefing');
    _setTopbarTitle(SECTION_TITLES['briefing']);
    _setSidebarActive('nav-home');
    _setMobTabActive('mob-tab-home');
  }
}

const _PP_PRESETS = { '1h': {tp:400,sl:200}, '4h': {tp:1000,sl:500}, '6h': {tp:1200,sl:600}, '12h': {tp:2000,sl:200} };
function onPingPongTfChange() {
  const tf = document.getElementById('v-pp-tf')?.value;
  const p  = _PP_PRESETS[tf];
  if (!p) return;
  const tp = document.getElementById('v-pp-tp');
  const sl = document.getElementById('v-pp-sl');
  if (tp) tp.value = p.tp;
  if (sl) sl.value = p.sl;
}

function toggleVishal(id) {
  const body    = document.getElementById('v-body-' + id);
  const chevron = document.getElementById('v-chevron-' + id);
  if (!body) return;
  const open = body.style.display === 'none';
  body.style.display = open ? 'block' : 'none';
  if (chevron) chevron.style.transform = open ? 'rotate(0deg)' : 'rotate(-90deg)';
}

function toggleCfg() {
  const body = document.getElementById('cfg-body');
  const chevron = document.getElementById('cfg-chevron');
  const open = body.style.display === 'none';
  body.style.display = open ? 'block' : 'none';
  chevron.style.transform = open ? 'rotate(0deg)' : 'rotate(-90deg)';
}

function switchSubTab(tab) {
  _currentSubTab = tab;
  _currentSection = tab === 'scanner' ? 'scanner' : 'home';
  _showPage(tab);
  _activateSubTab(tab);
  _setTopbarTitle(SECTION_TITLES[tab]);
  _setMobTabActive(tab === 'scanner' ? 'mob-tab-scanner' : 'mob-tab-home');
}

function _showPage(id) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  const el = document.getElementById('page-' + id);
  if (el) el.classList.add('active');
}

function _activateSubTab(tab) {
  document.querySelectorAll('.sub-tab').forEach(b => b.classList.remove('active'));
  const el = document.getElementById('subtab-' + tab);
  if (el) el.classList.add('active');
}

function _setSidebarActive(id) {
  document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
  const el = document.getElementById(id);
  if (el) el.classList.add('active');
}

function _setMobTabActive(id) {
  document.querySelectorAll('.tab-item').forEach(b => b.classList.remove('active'));
  const el = document.getElementById(id);
  if (el) el.classList.add('active');
}

function _setTopbarTitle(title) {
  const el = document.getElementById('topbar-title');
  if (el) el.textContent = title;
}

// ── Cached data ────────────────────────────────────────────────────────────────
let _scanData    = null;
let _briefData   = null;
let _scanFilter  = 'all';

// ── Timezone helpers ───────────────────────────────────────────────────────────
function getTz() { return localStorage.getItem(TZ_KEY) || DEFAULT_TZ; }
function setTz(tz) { localStorage.setItem(TZ_KEY, tz); }

function formatTs(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d)) return iso;
  return d.toLocaleString('en-GB', {
    timeZone: getTz(),
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit', hour12: false,
  }).replace(',', '');
}

function tzAbbr() {
  const sel = document.getElementById('tz-select');
  return sel ? sel.options[sel.selectedIndex].text.split('(')[0].trim() : '';
}

function updateThHeader() {
  const th = document.getElementById('th-baropen');
  if (th) th.textContent = `Bar Open (${tzAbbr()})`;
}

// ── Theme ──────────────────────────────────────────────────────────────────────
function getTheme() { return localStorage.getItem(THEME_KEY) || DEFAULT_THEME; }

function applyTheme(t) {
  document.documentElement.setAttribute('data-theme', t);
  localStorage.setItem(THEME_KEY, t);
  // Keep all theme selectors in sync
  ['theme-select', 'settings-theme-select'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.value = t;
  });
}

// ── HTTP helpers ───────────────────────────────────────────────────────────────
async function fetchJSON(url, opts = {}) {
  const token = await _getToken();
  const headers = { ...(opts.headers || {}) };
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const r = await fetch(url, { ...opts, headers, cache: 'no-store' });
  if (r.status === 401) throw Object.assign(new Error('Unauthenticated'), { status: 401 });
  if (!r.ok) throw new Error(`${url} → ${r.status}`);
  return r.json();
}

// ── Pattern helpers ────────────────────────────────────────────────────────────
function inferDirection(patternName) {
  const n = (patternName || '').toLowerCase();
  if (n.includes('morning') || n.includes('bullish') || n.includes('bottom')) return 'long';
  if (n.includes('evening') || n.includes('bearish') || n.includes('top'))    return 'short';
  return null;
}

function directionBadge(dir) {
  if (dir === 'long')  return '<span class="badge badge-bull">▲ Long</span>';
  if (dir === 'short') return '<span class="badge badge-bear">▼ Short</span>';
  return '<span class="badge badge-neutral">—</span>';
}

function patternMatchesFilter(h) {
  if (_scanFilter === 'all')     return true;
  if (_scanFilter === 'depo')    return !!h.depo_line;
  const dir = inferDirection(h.pattern);
  if (_scanFilter === 'bullish') return dir === 'long';
  if (_scanFilter === 'bearish') return dir === 'short';
  return true;
}

// ── Markdown renderer ──────────────────────────────────────────────────────────
function renderMarkdown(text) {
  if (!text) return '<p style="color:var(--text-3)">No briefing yet.</p>';
  const esc    = s => s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  const inline = s => esc(s)
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g,     '<em>$1</em>');

  const lines = text.split('\n');
  let html = '', inList = false;

  for (const raw of lines) {
    const t = raw.trim();
    if      (t.startsWith('### ')) { if (inList) { html += '</ul>'; inList = false; } html += `<h3>${inline(t.slice(4))}</h3>`; }
    else if (t.startsWith('## '))  { if (inList) { html += '</ul>'; inList = false; } html += `<h2>${inline(t.slice(3))}</h2>`; }
    else if (t.startsWith('# '))   { if (inList) { html += '</ul>'; inList = false; } html += `<h1>${inline(t.slice(2))}</h1>`; }
    else if (t === '---')           { if (inList) { html += '</ul>'; inList = false; } html += '<hr>'; }
    else if (t.startsWith('- ') || t.startsWith('* ')) {
      if (!inList) { html += '<ul>'; inList = true; }
      html += `<li>${inline(t.slice(2))}</li>`;
    } else if (t === '') {
      if (inList) { html += '</ul>'; inList = false; }
    } else {
      if (inList) { html += '</ul>'; inList = false; }
      html += `<p>${inline(t)}</p>`;
    }
  }
  if (inList) html += '</ul>';
  return html;
}

// ── Briefing ───────────────────────────────────────────────────────────────────
function renderBriefing() {
  if (!_briefData) return;
  document.getElementById('briefing-text').innerHTML = renderMarkdown(_briefData.text);
  _setText('brief-ts', formatTs(_briefData.timestamp));
}

async function loadBriefing() {
  try {
    _briefData = await fetchJSON('/api/brief');
    renderBriefing();
  } catch (_) {
    document.getElementById('briefing-text').innerHTML = '<p style="color:var(--red)">Failed to load briefing.</p>';
  }
}

// ── Scanner ────────────────────────────────────────────────────────────────────
function renderScan() {
  if (!_scanData) return;
  _setText('scan-ts', formatTs(_scanData.timestamp));
  const hits  = (_scanData.results || []).filter(patternMatchesFilter);
  const tbody = document.getElementById('scan-body');

  if (!hits.length) {
    tbody.innerHTML = '<tr class="empty-row"><td colspan="7">No patterns detected yet — trigger a scan to start.</td></tr>';
    return;
  }

  tbody.innerHTML = hits.map(h => {
    const dir      = inferDirection(h.pattern);
    const depoHtml = h.depo_line
      ? `<span class="depo-val">⚡${Number(h.depo_line).toLocaleString()}</span>`
      : `<span class="depo-none">—</span>`;
    const agoHtml  = h.bars_ago === 0
      ? `<span style="color:var(--green)">current</span>`
      : `<span style="color:var(--text-3)">${h.bars_ago}b</span>`;
    const openPx   = h.bar_open_price
      ? Number(h.bar_open_price).toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 })
      : '—';
    return `<tr>
      <td><span class="badge badge-neutral">${h.tf}m</span></td>
      <td style="color:var(--text)">${h.pattern}</td>
      <td>${directionBadge(dir)}</td>
      <td style="text-align:right">${agoHtml}</td>
      <td style="color:var(--text-3);font-size:12px">${formatTs(h.bar_open_time)}</td>
      <td style="text-align:right;color:var(--text);font-variant-numeric:tabular-nums">${openPx}</td>
      <td>${depoHtml}</td>
    </tr>`;
  }).join('');
}

async function loadScan() {
  try {
    _scanData = await fetchJSON('/api/scan');
    renderScan();
  } catch (_) {
    document.getElementById('scan-body').innerHTML =
      '<tr class="empty-row"><td colspan="7">Failed to load scan results.</td></tr>';
  }
}

// ── Status dots ────────────────────────────────────────────────────────────────
async function pollStatus() {
  try {
    const s = await fetchJSON('/api/status');
    _setDot('scan-dot',  s.scan_running);
    _setDot('brief-dot', s.brief_running);
    _setRunningBtn(s.scan_running, s.brief_running);
    const navVishal  = document.getElementById('nav-vishal');
    const pageVishal = document.getElementById('page-vishal');
    if (navVishal)  navVishal.style.display  = s.vishal_enabled ? '' : 'none';
    if (pageVishal) pageVishal.style.display = s.vishal_enabled ? '' : 'none';
  } catch (_) {}
}

function _setDot(id, running) {
  const el = document.getElementById(id);
  if (el) el.className = running ? 'status-dot dot-run' : 'status-dot dot-ok';
}

function _setRunningBtn(scanRunning, briefRunning) {
  const scanBtn  = document.getElementById('scan-btn');
  const briefBtn = document.getElementById('brief-btn');
  const adminOnly = _isAdmin();
  if (scanBtn)  scanBtn.style.display  = adminOnly ? '' : 'none';
  if (briefBtn) briefBtn.style.display = adminOnly ? '' : 'none';
  if (scanBtn) {
    scanBtn.disabled = scanRunning;
    scanBtn.innerHTML = scanRunning
      ? '<span class="spinner"></span> Scanning…'
      : `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:13px;height:13px"><polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/></svg> Refresh`;
  }
  if (briefBtn) {
    briefBtn.disabled = briefRunning;
    briefBtn.innerHTML = briefRunning
      ? '<span class="spinner"></span> Generating…'
      : `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="width:13px;height:13px"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/></svg> Briefing`;
  }
}

// ── Trigger buttons ────────────────────────────────────────────────────────────
async function triggerScan() {
  document.getElementById('scan-btn').disabled = true;
  await fetchJSON('/api/scan/trigger', { method: 'POST' });
  const iv = setInterval(async () => { await pollStatus(); await loadScan(); }, 3000);
  setTimeout(() => clearInterval(iv), 5 * 60 * 1000);
}

async function triggerBrief() {
  document.getElementById('brief-btn').disabled = true;
  await fetchJSON('/api/brief/trigger', { method: 'POST' });
  const iv = setInterval(async () => { await pollStatus(); await loadBriefing(); }, 3000);
  setTimeout(() => clearInterval(iv), 5 * 60 * 1000);
}

// ── BTC price ──────────────────────────────────────────────────────────────────
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
      const fmt = '$' + price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
      ['btc-price', 'btc-price-mobile'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.textContent = fmt;
      });
      return;
    } catch (_) {}
  }
}

// ── Trading scanner ────────────────────────────────────────────────────────────
let _tradingData = null;

function fmtPrice(v) {
  return v != null
    ? Number(v).toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 })
    : '—';
}

function renderLevels(levels, running) {
  const el = document.getElementById('levels-row');
  if (!el) return;
  if (!running) { el.style.display = 'none'; return; }
  el.style.display = '';
  const mrpStr  = levels.mrp       ? `<span style="color:var(--accent)">$${fmtPrice(levels.mrp)}</span>`      : '<span style="color:var(--text-3)">—</span>';
  const dpocStr = levels.daily_poc  ? `<span style="color:var(--green)">$${fmtPrice(levels.daily_poc)}</span>` : '<span style="color:var(--text-3)">—</span>';
  const wpocStr = levels.weekly_poc ? `<span style="color:#c084fc">$${fmtPrice(levels.weekly_poc)}</span>`     : '<span style="color:var(--text-3)">—</span>';

  const price = _tradingData?.current_price;
  let bias = '—', biasColor = 'var(--text-3)';
  if (price) {
    const vals  = [levels.mrp, levels.daily_poc, levels.weekly_poc].filter(v => v != null);
    const above = vals.filter(v => price > v).length;
    if (vals.length) {
      if      (above === vals.length)       { bias = 'strongly bullish'; biasColor = 'var(--green)'; }
      else if (above > vals.length / 2)     { bias = 'bullish';          biasColor = 'var(--green)'; }
      else if (above === 0)                 { bias = 'strongly bearish'; biasColor = 'var(--red)';   }
      else                                  { bias = 'bearish';          biasColor = 'var(--red)';   }
    }
  }
  el.innerHTML = `
    <span class="level-item">MRP: ${mrpStr}</span><span class="level-sep">·</span>
    <span class="level-item">D-POC: ${dpocStr}</span><span class="level-sep">·</span>
    <span class="level-item">W-POC: ${wpocStr}</span><span class="level-sep">·</span>
    <span class="level-item">Bias: <span style="color:${biasColor}">${bias}</span></span>`;
}

function renderTrading() {
  if (!_tradingData) return;
  const { signals = [], positions = [], history = [], running, settings = {}, levels = {}, current_price = 0 } = _tradingData;

  _setText('trade-mode-label', (settings.mode || 'paper').toUpperCase());
  const liveEl = document.getElementById('trade-live-price');
  if (liveEl) liveEl.textContent = current_price ? `$${fmtPrice(current_price)}` : '—';
  if (current_price && running) {
    const fmt = '$' + current_price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    ['btc-price', 'btc-price-mobile'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.textContent = fmt;
    });
  }

  const startBtn = document.getElementById('trade-start-btn');
  const stopBtn  = document.getElementById('trade-stop-btn');
  const dot      = document.getElementById('trade-dot');
  if (running) {
    if (startBtn) startBtn.style.display = 'none';
    if (stopBtn)  stopBtn.style.display  = '';
    if (dot)      dot.className = 'status-dot dot-run';
  } else {
    if (startBtn) startBtn.style.display = '';
    if (stopBtn)  stopBtn.style.display  = 'none';
    if (dot)      dot.className = 'status-dot dot-ok';
  }

  renderLevels(levels, running);

  // sync settings inputs only when config panel is collapsed (not being edited)
  if (document.getElementById('cfg-body')?.style.display === 'none') {
    _syncSettingsInputs(settings);
  }

  // signals table
  const sigBody = document.getElementById('trade-signals-body');
  const pendingSigs = signals.filter(s => s.status === 'pending');
  if (!pendingSigs.length) {
    sigBody.innerHTML = '<tr class="empty-row"><td colspan="7">No pending signals</td></tr>';
  } else {
    sigBody.innerHTML = pendingSigs.map(s => {
      const dirBadge = s.direction === 'long'
        ? '<span class="badge badge-bull">▲ Long</span>'
        : '<span class="badge badge-bear">▼ Short</span>';
      return `<tr>
        <td>${s.pattern}</td>
        <td><span class="badge badge-neutral">${s.tf}m</span></td>
        <td>${dirBadge}</td>
        <td style="text-align:right;font-variant-numeric:tabular-nums">${Number(s.entry_trigger).toLocaleString('en-US',{minimumFractionDigits:1,maximumFractionDigits:1})}</td>
        <td style="text-align:right;color:var(--red);font-variant-numeric:tabular-nums">${Number(s.sl_wick).toLocaleString('en-US',{minimumFractionDigits:1,maximumFractionDigits:1})}</td>
        <td style="color:var(--text-3);font-size:12px">${formatTs(s.expires_at)}</td>
        <td style="color:var(--accent)">${s.status}</td>
      </tr>`;
    }).join('');
  }

  // positions table
  const posBody = document.getElementById('trade-positions-body');
  const openPos = positions.filter(p => p.status === 'open');
  if (!openPos.length) {
    posBody.innerHTML = '<tr class="empty-row"><td colspan="11">No open positions</td></tr>';
  } else {
    posBody.innerHTML = openPos.map(p => {
      const dirBadge  = p.direction === 'long'
        ? '<span class="badge badge-bull">▲ Long</span>'
        : '<span class="badge badge-bear">▼ Short</span>';
      const slColor   = p.partial_closed ? 'var(--accent)' : 'var(--red)';
      const phaseHtml = p.partial_closed
        ? `<span class="phase-trail">TRAILING <span style="color:var(--text-3);font-size:10px">@${fmtPrice(p.trail_anchor)}</span></span>`
        : `<span class="phase-watch">WATCHING</span>`;
      const remQty    = p.remaining_qty ?? p.qty;
      const tp1Str    = p.partial_closed
        ? `<span style="color:var(--text-3)">${fmtPrice(p.tp)} ✓</span>`
        : `<span style="color:var(--green)">${fmtPrice(p.tp)}</span>`;
      const pts       = current_price
        ? (p.direction === 'long' ? current_price - p.entry_price : p.entry_price - current_price)
        : null;
      const ptsStr    = pts !== null
        ? `<span style="color:${pts >= 0 ? 'var(--green)' : 'var(--red)'}">${pts >= 0 ? '+' : ''}${pts.toFixed(1)}</span>`
        : '—';
      return `<tr>
        <td>${dirBadge}</td>
        <td><span class="badge badge-neutral">${p.tf ? p.tf + 'm' : '—'}</span></td>
        <td>${p.pattern || '—'}</td>
        <td style="text-align:right;font-variant-numeric:tabular-nums">$${fmtPrice(p.entry_price)}</td>
        <td style="text-align:right;color:${slColor};font-variant-numeric:tabular-nums">$${fmtPrice(p.sl)}</td>
        <td style="text-align:right">${tp1Str}</td>
        <td style="text-align:right">${ptsStr}</td>
        <td style="text-align:right;color:var(--text-3)">${remQty}</td>
        <td>${phaseHtml}</td>
        <td style="color:var(--text-3);font-size:12px">${formatTs(p.opened_at)}</td>
        <td><button class="btn btn-danger" style="font-size:11px;padding:3px 10px" onclick="cancelPosition('${p.signal_id}')">Cancel</button></td>
      </tr>`;
    }).join('');
  }

  // history table
  const histBody = document.getElementById('trade-history-body');
  if (!history.length) {
    histBody.innerHTML = '<tr class="empty-row"><td colspan="9">No completed trades</td></tr>';
  } else {
    histBody.innerHTML = [...history].reverse().slice(0, 40).map(r => {
      const p          = r.position;
      const isPartial  = r.close_reason === 'tp_partial';
      const isStopped  = r.close_reason === 'stopped_by_user';
      const dirBadge   = p.direction === 'long'
        ? '<span class="badge badge-bull">▲ Long</span>'
        : '<span class="badge badge-bear">▼ Short</span>';
      const pnl        = r.pnl_closed ?? 0;
      const pnlClass   = pnl >= 0 ? 'pnl-pos' : 'pnl-neg';
      const pnlStr     = isStopped ? '—' : (pnl >= 0 ? '+' : '') + pnl.toFixed(4);
      const reasonColor = isStopped ? 'var(--text-3)' : r.close_reason === 'sl' ? 'var(--red)' : 'var(--green)';
      const reasonLabel = isPartial ? 'TP 50%' : isStopped ? 'Stopped by user' : r.close_reason.toUpperCase();
      return `<tr style="${isPartial || isStopped ? 'opacity:0.75' : ''}">
        <td>${dirBadge}</td>
        <td><span class="badge badge-neutral">${p.tf ? p.tf + 'm' : '—'}</span></td>
        <td>${p.pattern || '—'}</td>
        <td style="text-align:right;font-variant-numeric:tabular-nums">$${fmtPrice(p.entry_price)}</td>
        <td style="text-align:right;font-variant-numeric:tabular-nums">${isStopped ? '—' : '$' + fmtPrice(r.close_price)}</td>
        <td style="text-align:right;color:var(--text-3)">${r.qty_closed ?? p.qty}</td>
        <td style="text-align:right" class="${isStopped ? '' : pnlClass}">${pnlStr}</td>
        <td style="color:${reasonColor}">${reasonLabel}</td>
        <td style="color:var(--text-3);font-size:12px">${formatTs(p.opened_at)}</td>
        <td style="color:var(--text-3);font-size:12px">${formatTs(r.closed_at)}</td>
      </tr>`;
    }).join('');
  }
}

async function loadTrading() {
  try {
    _tradingData = await fetchJSON('/api/trading/state');
    renderTrading();
  } catch (e) {
    if (e.status === 401) _showTradingContent();  // re-show gate if token expired
  }
}

async function startTrading() {
  await fetchJSON('/api/trading/start', { method: 'POST' });
  await loadTrading();
}

async function stopTrading() {
  await fetchJSON('/api/trading/stop', { method: 'POST' });
  await loadTrading();
}

async function cancelPosition(signalId) {
  if (!confirm('Cancel this position? This will close it at market price.')) return;
  await fetchJSON(`/api/trading/position/${signalId}/cancel`, { method: 'POST' });
  await loadTrading();
}

// ── Settings page ──────────────────────────────────────────────────────────────
function _syncSettingsInputs(settings) {
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
  const activePatterns = settings.patterns || ['4-Flag', 'Engulfing'];
  document.getElementById('cfg-pattern-4flag').checked    = activePatterns.includes('4-Flag');
  document.getElementById('cfg-pattern-engulfing').checked = activePatterns.includes('Engulfing');
  document.getElementById('cfg-bias-filter').checked = !!settings.bias_filter;
}

async function _renderSettingsPage() {
  _renderAccountCard();
  const st = document.getElementById('settings-theme-select');
  const sz = document.getElementById('settings-tz-select');
  if (st) st.value = getTheme();
  if (sz) sz.value = getTz();
  await Promise.all([loadAppSettings(), loadUserSettings()]);
}

async function saveTradingSettings() {
  if (!_currentUser) return;
  const qtyVal = parseFloat(document.getElementById('cfg-qty').value);
  if (!Number.isInteger(qtyVal) || qtyVal % 2 !== 0) {
    alert('Qty (Contracts) must be a multiple of 2 (e.g. 2, 4, 6, …)');
    return;
  }
  const settings = {
    mode:              document.getElementById('cfg-mode').value,
    tf_min:            parseInt(document.getElementById('cfg-tf-min').value),
    tf_max:            parseInt(document.getElementById('cfg-tf-max').value),
    scan_interval_min: parseInt(document.getElementById('cfg-interval').value),
    qty:               parseFloat(document.getElementById('cfg-qty').value),
    max_sl:            parseFloat(document.getElementById('cfg-max-sl').value),
    min_tp:            parseFloat(document.getElementById('cfg-min-tp').value),
    max_concurrent:    parseInt(document.getElementById('cfg-max-conc').value),
    patterns: [
      ...(document.getElementById('cfg-pattern-4flag').checked    ? ['4-Flag']    : []),
      ...(document.getElementById('cfg-pattern-engulfing').checked ? ['Engulfing'] : []),
    ],
    bias_filter: document.getElementById('cfg-bias-filter').checked,
  };
  await fetchJSON('/api/trading/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings),
  });
  const msg = document.getElementById('trade-save-msg');
  msg.style.display = 'inline';
  setTimeout(() => { msg.style.display = 'none'; }, 2000);
}

// ── Filter pills ───────────────────────────────────────────────────────────────
document.getElementById('scan-filter-pills').addEventListener('click', e => {
  const pill = e.target.closest('.pill');
  if (!pill) return;
  _scanFilter = pill.dataset.filter;
  document.querySelectorAll('#scan-filter-pills .pill').forEach(p => p.classList.remove('active'));
  pill.classList.add('active');
  renderScan();
});

// ── Boot ───────────────────────────────────────────────────────────────────────
document.getElementById('scan-btn').addEventListener('click', triggerScan);
document.getElementById('brief-btn').addEventListener('click', triggerBrief);
document.getElementById('trade-start-btn').addEventListener('click', startTrading);
document.getElementById('trade-stop-btn').addEventListener('click', stopTrading);
document.getElementById('trade-save-btn').addEventListener('click', saveTradingSettings);

// Sidebar TZ + theme
const tzSelect = document.getElementById('tz-select');
tzSelect.value = getTz();
tzSelect.addEventListener('change', () => {
  setTz(tzSelect.value);
  // keep settings TZ in sync
  const sz = document.getElementById('settings-tz-select');
  if (sz) sz.value = tzSelect.value;
  updateThHeader();
  renderBriefing();
  renderScan();
});

applyTheme(getTheme());
document.getElementById('theme-select').addEventListener('change', e => applyTheme(e.target.value));

// Settings page selectors
document.getElementById('settings-theme-select').addEventListener('change', e => {
  applyTheme(e.target.value);
});
document.getElementById('settings-tz-select').addEventListener('change', e => {
  setTz(e.target.value);
  tzSelect.value = e.target.value;
  updateThHeader();
  renderBriefing();
  renderScan();
});

// Initial auth state render (may be null until Firebase resolves)
_updateAuthUI();

(async () => {
  updateThHeader();
  // Briefing + scanner are public — load immediately
  await Promise.all([loadBriefing(), loadScan(), fetchBTCPrice(), pollStatus()]);
  setInterval(() => Promise.all([loadBriefing(), loadScan()]), REFRESH_MS);
  setInterval(fetchBTCPrice, 10_000);
  setInterval(pollStatus, 3000);
  // Trading polling only when signed in
  setInterval(() => { if (_currentUser) loadTrading(); }, 5000);
})();
