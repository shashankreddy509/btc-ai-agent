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
  if (user) fetchJSON('/api/trading/autostart', { method: 'POST' }).catch(() => {});
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

  // Admin-only buttons — re-evaluate once auth state is known
  const admin = _isAdmin();
  const scanBtn  = document.getElementById('scan-btn');
  const briefBtn = document.getElementById('brief-btn');
  if (scanBtn)  scanBtn.style.display  = admin ? '' : 'none';
  if (briefBtn) briefBtn.style.display = admin ? '' : 'none';

  // Trail offset visible to all logged-in users
  const trailRow = document.getElementById('cfg-trail-offset-row');
  if (trailRow) trailRow.style.display = 'flex';

  // Admin-only nav items
  const navUsers  = document.getElementById('nav-users');
  const navRegime = document.getElementById('nav-regime');
  const navMarkov = document.getElementById('nav-markov');
  if (navUsers)  navUsers.style.display  = admin ? '' : 'none';
  if (navRegime) navRegime.style.display = admin ? '' : 'none';
  if (navMarkov) navMarkov.style.display = admin ? '' : 'none';
}

const ADMIN_EMAILS = ['shashankreddy509@gmail.com', 'gsreddy509@gmail.com'];
function _isAdmin() { return ADMIN_EMAILS.includes(_currentUser?.email); }

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
    sp('s-pepperstone-client-secret', d.pepperstone_client_secret);
    const sv2 = (id, v) => { const el = document.getElementById(id); if (el && v) el.value = v; };
    sv2('s-pepperstone-client-id',  d.pepperstone_client_id);
    sv2('s-pepperstone-account-id', d.pepperstone_account_id);
    if (d.pepperstone_is_live !== undefined) {
      sv2('s-pepperstone-is-live', d.pepperstone_is_live);
      _updatePepperstoneMode(d.pepperstone_is_live);
    }
    const statusEl = document.getElementById('s-pepperstone-status');
    if (statusEl) {
      const connected = d.pepperstone_refresh_token && d.pepperstone_refresh_token.includes('*');
      statusEl.textContent  = connected ? '✅ Connected' : '⚠️ Not connected';
      statusEl.style.color  = connected ? 'var(--green, #4caf50)' : 'var(--text-3)';
    }
    const hintEl = document.getElementById('s-pepperstone-redirect-hint');
    if (hintEl) hintEl.textContent = `${location.origin}/auth/pepperstone/callback`;
    const broker = d.broker || '';
    const sel = document.getElementById('s-broker-select');
    if (sel) sel.value = broker;
    onBrokerChange(broker);
    const nickEl = document.getElementById('s-broker-nickname');
    if (nickEl && d.broker_nickname) nickEl.value = d.broker_nickname;
  } catch (_) {}
}

const _BROKER_CRED_CARDS = ['binance','bybit','delta','coindcx','pepperstone'];

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
  const broker   = _gv('s-broker-select');
  if (!broker) return;
  const nickname = _gv('s-broker-nickname');
  const payload  = { broker };
  if (nickname !== undefined) payload.broker_nickname = nickname;
  await fetchJSON('/api/trading/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
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

function _updatePepperstoneMode(isLive) {
  const live = isLive === true || isLive === 'true';
  const liveEl = document.getElementById('s-pp-instructions-live');
  const demoEl = document.getElementById('s-pp-instructions-demo');
  const btnEl  = document.getElementById('s-pepperstone-connect-btn');
  if (liveEl) liveEl.style.display = live ? '' : 'none';
  if (demoEl) demoEl.style.display = live ? 'none' : '';
  if (btnEl)  btnEl.style.display  = live ? '' : 'none';
}

async function savePepperstoneCreds() {
  if (!_currentUser) return;
  const clientId    = document.getElementById('s-pepperstone-client-id')?.value.trim()    || '';
  const clientSec   = document.getElementById('s-pepperstone-client-secret')?.value.trim() || '';
  const accountId   = document.getElementById('s-pepperstone-account-id')?.value.trim()   || '';
  const isLive      = document.getElementById('s-pepperstone-is-live')?.value              || 'true';
  const contractRaw = document.getElementById('s-pepperstone-contract')?.value;
  const contract    = contractRaw ? parseFloat(contractRaw) : null;
  const errEl = document.getElementById('s-err-broker-pepperstone');
  if (!clientId || !accountId) {
    if (errEl) { errEl.textContent = 'Client ID and Account ID are required.'; errEl.style.display = 'inline'; }
    return;
  }
  const payload = {
    pepperstone_client_id:  clientId,
    pepperstone_account_id: accountId,
    pepperstone_is_live:    isLive,
  };
  if (clientSec) payload.pepperstone_client_secret = clientSec;
  if (contract)  payload.pepperstone_contract_size  = contract;
  const sandboxToken = document.getElementById('s-pepperstone-sandbox-token')?.value.trim();
  if (sandboxToken) payload.pepperstone_refresh_token = sandboxToken;
  await _saveSettings('/api/settings/user', payload, 'broker-pepperstone');
  const secEl = document.getElementById('s-pepperstone-client-secret');
  if (secEl) secEl.value = '';
  const stEl = document.getElementById('s-pepperstone-sandbox-token');
  if (stEl) stEl.value = '';
}

async function connectPepperstone() {
  if (!_currentUser) return;
  const { url } = await fetchJSON('/api/settings/pepperstone/auth-url', { method: 'POST' });
  if (!url) return;
  const popup = window.open(url, 'pepperstone_auth', 'width=600,height=700,noopener=no');
  const timer = setInterval(() => {
    if (!popup || popup.closed) {
      clearInterval(timer);
      loadUserSettings();
    }
  }, 1000);
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

const SECTION_TITLES = { briefing: 'Morning Briefing', scanner: 'Pattern Scanner', trading: 'Live Trading', settings: 'Settings', users: 'Users', regime: 'Regime Analytics', markov: 'Markov Analytics' };

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
  } else if (section === 'users') {
    _showPage('users');
    subTabsEl.style.display = 'none';
    _setTopbarTitle('Users');
    _setSidebarActive('nav-users');
    _showUsersPage();
  } else if (section === 'regime') {
    _showPage('regime');
    subTabsEl.style.display = 'none';
    _setTopbarTitle('Regime Analytics');
    _setSidebarActive('nav-regime');
    loadRegimeLog().then(renderRegimePage);
  } else if (section === 'markov') {
    _showPage('markov');
    subTabsEl.style.display = 'none';
    _setTopbarTitle('Markov Analytics');
    _setSidebarActive('nav-markov');
    loadMarkovTickers();
  } else if (section === 'settings') {
    _showPage('settings');
    subTabsEl.style.display = 'none';
    _setTopbarTitle('Settings');
    _setSidebarActive('nav-settings');
    _setMobTabActive('mob-tab-settings');
    _renderSettingsPage();
  } else if (section === 'liquidity') {
    _showPage('liquidity');
    subTabsEl.style.display = 'none';
    _setTopbarTitle('Liquidation Heatmap');
    _setSidebarActive('nav-liquidity');
    _setMobTabActive('mob-tab-liquidity');
    loadLiquidity();
    clearInterval(window._liqInterval);
    window._liqInterval = setInterval(() => { if (!document.hidden) loadLiquidity(); }, 30_000);
  } else if (section === 'oi') {
    _showPage('oi');
    subTabsEl.style.display = 'none';
    _setTopbarTitle('OI Flow');
    _setSidebarActive('nav-oi');
    loadOIStatus();
    loadOISettingsInputs();
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
  if (id !== 'liquidity') { clearInterval(window._liqInterval); window._liqInterval = null; }
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

// ── Liquidity Heatmap ──────────────────────────────────────────────────────────
const LIQ_COLORS = {
  YELLOW: '#facc15', LIME: '#a3e635', ORANGE: '#fb923c',
  RED: '#f87171', TEAL: '#2dd4bf', NAVY: '#6366f1', BLACK: '#94a3b8',
};

async function loadLiquidity() {
  const status = document.getElementById('liq-status');
  const tbody  = document.getElementById('liq-tbody');
  if (!tbody) return;
  if (status) status.textContent = 'Fetching…';
  try {
    const d = await fetchJSON('/api/liquidity');
    if (d.status === 'no_data') {
      tbody.innerHTML = '<tr><td colspan="2" style="text-align:center;color:var(--text-3)">No data yet — run <code>uv run liquidity-collect</code> to start collecting.</td></tr>';
      if (status) status.textContent = '';
      return;
    }
    const latest = d.rows.at(-1)?.timestamp;
    // Filter to latest scan, deduplicate by price, sort by price descending
    const seen = new Set();
    const rows = d.rows
      .filter(r => r.timestamp === latest && r.price && r.price !== 'N/A')
      .filter(r => { const k = r.price; if (seen.has(k)) return false; seen.add(k); return true; })
      .sort((a, b) => Number(b.price) - Number(a.price));

    // Find max leverage value for relative highlighting
    const levNums = rows.map(r => parseFloat(r.leverage?.replace(/[^0-9.]/g, '') || '0')).filter(v => v > 0);
    const maxLev = levNums.length ? Math.max(...levNums) : 1;

    const currentPrice = _wsPrice || 0;

    // Find closest row to current price for scroll anchor
    let closestIdx = 0;
    let closestDiff = Infinity;
    rows.forEach((r, i) => {
      const diff = Math.abs(Number(r.price) - currentPrice);
      if (diff < closestDiff) { closestDiff = diff; closestIdx = i; }
    });

    tbody.innerHTML = rows.map((r, i) => {
      const priceNum = Number(r.price);
      const priceFmt = '$' + priceNum.toLocaleString('en-US', {minimumFractionDigits: 1, maximumFractionDigits: 1});
      const levNum   = parseFloat(r.leverage?.replace(/[^0-9.]/g, '') || '0');
      const ratio    = maxLev > 0 ? levNum / maxLev : 0;
      const levColor  = ratio >= 0.7 ? '#f97316' : ratio >= 0.4 ? '#e2a86b' : 'var(--text-2)';
      const levWeight = ratio >= 0.7 ? '700' : '400';

      // Current price marker — insert above the row closest to live price
      const isClosest = currentPrice > 0 && i === closestIdx;
      const priceMarker = isClosest ? `<tr id="liq-price-marker" style="background:rgba(247,147,26,0.12)">
        <td colspan="2" style="font-size:12px;color:#f97316;font-weight:600;padding:4px 12px;text-align:center">
          ▶ Current Price: $${currentPrice.toLocaleString('en-US',{minimumFractionDigits:2,maximumFractionDigits:2})}
        </td></tr>` : '';

      return `${priceMarker}<tr>
        <td style="font-size:14px;font-variant-numeric:tabular-nums;font-weight:600">${priceFmt}</td>
        <td style="font-size:14px;font-variant-numeric:tabular-nums;color:${levColor};font-weight:${levWeight}">${r.leverage}</td>
      </tr>`;
    }).join('');

    // Scroll to current price marker
    if (currentPrice > 0) {
      requestAnimationFrame(() => {
        const marker = document.getElementById('liq-price-marker');
        if (marker) marker.scrollIntoView({ behavior: 'smooth', block: 'center' });
      });
    }

    const lastTs = rows[0]?.timestamp ? formatTs(rows[0].timestamp.replace(' UTC','Z').replace(' ','T')) : '—';
    const curFmt = currentPrice ? ` · BTC $${currentPrice.toLocaleString('en-US',{minimumFractionDigits:0,maximumFractionDigits:0})}` : '';
    if (status) status.textContent = `${rows.length} levels · last: ${lastTs}${curFmt}`;
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="2" style="color:var(--red)">${e}</td></tr>`;
  }
}

async function loadOIStatus() {
  const grid = document.getElementById('oi-status-grid');
  const msg  = document.getElementById('oi-status-msg');
  if (!grid) return;
  if (msg) msg.textContent = 'Fetching…';
  try {
    const d = await fetchJSON('/api/trading/oi/status');
    if (!d.ok) {
      grid.innerHTML = '<div style="color:var(--red);grid-column:1/-1">OI data unavailable — Binance API error.</div>';
      if (msg) msg.textContent = '';
      return;
    }
    const col = (v, t, f) => v ? t : f;
    const fmtDelta = v => `<span style="color:${v >= 0 ? 'var(--green)' : 'var(--red)'}">${v >= 0 ? '+' : ''}${v.toFixed(2)}</span>`;
    const last3 = d.last3_deltas || [];
    const candleBoxes = last3.map((v, i) => `
      <div class="oi-stat-box">
        <div class="oi-stat-label">Candle −${last3.length - i - 1 === 0 ? '0 (now)' : (last3.length - i - 1)}</div>
        <div class="oi-stat-val">${fmtDelta(v)}</div>
      </div>`).join('');
    grid.innerHTML = candleBoxes + `
      <div class="oi-stat-box">
        <div class="oi-stat-label">OI Δ (M USD)</div>
        <div class="oi-stat-val" style="color:${d.latest_delta >= 0 ? 'var(--green)' : 'var(--red)'}">${d.latest_delta >= 0 ? '+' : ''}${d.latest_delta.toFixed(2)}</div>
      </div>
      <div class="oi-stat-box">
        <div class="oi-stat-label">+ Threshold</div>
        <div class="oi-stat-val">${d.p_thresh.toFixed(2)}</div>
      </div>
      <div class="oi-stat-box">
        <div class="oi-stat-label">− Threshold</div>
        <div class="oi-stat-val">${d.n_thresh.toFixed(2)}</div>
      </div>
      <div class="oi-stat-box">
        <div class="oi-stat-label">Large OI Up</div>
        <div class="oi-stat-val" style="color:${col(d.large_oi_up,'#00BCD4','var(--text3)')}">${d.large_oi_up ? '▲ YES' : '—'}</div>
      </div>
      <div class="oi-stat-box">
        <div class="oi-stat-label">Large OI Down</div>
        <div class="oi-stat-val" style="color:${col(d.large_oi_down,'#00897B','var(--text3)')}">${d.large_oi_down ? '▼ YES' : '—'}</div>
      </div>
      <div class="oi-stat-box">
        <div class="oi-stat-label">Bullish Div</div>
        <div class="oi-stat-val" style="color:${col(d.bull_div,'var(--green)','var(--text3)')}">${d.bull_div ? '⚡ YES' : '—'}</div>
      </div>
      <div class="oi-stat-box">
        <div class="oi-stat-label">Bearish Div</div>
        <div class="oi-stat-val" style="color:${col(d.bear_div,'var(--red)','var(--text3)')}">${d.bear_div ? '⚡ YES' : '—'}</div>
      </div>
      <div class="oi-stat-box">
        <div class="oi-stat-label">TF used</div>
        <div class="oi-stat-val">${d.tf}m</div>
      </div>
    `;
    if (msg) msg.textContent = `Last fetched: ${formatTs(d.fetched_at)}`;
  } catch(e) {
    if (grid) grid.innerHTML = `<div style="color:var(--red);grid-column:1/-1">${e}</div>`;
    if (msg) msg.textContent = '';
  }
}

async function loadOISettingsInputs() {
  try {
    const d = await fetchJSON('/api/trading/state');
    if (!d.settings) return;
    const s = d.settings;
    const en = document.getElementById('cfg-oi-filter-enabled');
    if (en) en.checked = !!s.oi_filter_enabled;
    const m = document.getElementById('cfg-oi-threshold-mult');
    if (m && document.activeElement !== m) m.value = s.oi_threshold_mult ?? 4.0;
    const lb = document.getElementById('cfg-oi-lookback-bars');
    if (lb && document.activeElement !== lb) lb.value = s.oi_lookback_bars ?? 300;
    const dv = document.getElementById('cfg-oi-div-lookback');
    if (dv && document.activeElement !== dv) dv.value = s.oi_div_lookback ?? 5;
    const tf = document.getElementById('cfg-oi-tf');
    if (tf) tf.value = s.oi_tf ?? 5;
  } catch(_) {}
}

async function saveOISettings() {
  const payload = {
    oi_filter_enabled: !!document.getElementById('cfg-oi-filter-enabled')?.checked,
    oi_threshold_mult: parseFloat(document.getElementById('cfg-oi-threshold-mult')?.value) || 4.0,
    oi_lookback_bars:  parseInt(document.getElementById('cfg-oi-lookback-bars')?.value) || 300,
    oi_div_lookback:   parseInt(document.getElementById('cfg-oi-div-lookback')?.value) || 5,
    oi_tf:             parseInt(document.getElementById('cfg-oi-tf')?.value) || 5,
  };
  try {
    await fetchJSON('/api/trading/settings', { method: 'POST', body: JSON.stringify(payload) });
    const msg = document.getElementById('oi-save-msg');
    if (msg) { msg.style.display = ''; setTimeout(() => msg.style.display = 'none', 2000); }
  } catch(e) { alert('Save failed: ' + e); }
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
    const labelRetracement = document.getElementById('label-pattern-retracement');
    if (labelRetracement) labelRetracement.style.display = s.retracement_enabled ? '' : 'none';
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
  const ac = new AbortController();
  const _t = setTimeout(() => ac.abort(), 5000);
  try {
    const r = await fetch('/api/price', { signal: ac.signal });
    if (!r.ok) return;
    const { price } = await r.json();
    if (price) _applyPrice(price);
  } catch (_) {
  } finally {
    clearTimeout(_t);
  }
}

let _wsPrice = null;
let _priceSocket = null;
let _lastPriceTick = 0;

function _connectPriceWS() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const ws = new WebSocket(`${proto}://${location.host}/ws/price`);
  _priceSocket = ws;
  ws.onmessage = (e) => {
    try {
      const { price } = JSON.parse(e.data);
      if (price) { _lastPriceTick = Date.now(); _applyPrice(price); }
    } catch (_) {}
  };
  ws.onclose = () => { _priceSocket = null; setTimeout(_connectPriceWS, 5000); };
  ws.onerror = () => ws.close();
}

function _applyPrice(price) {
  _wsPrice = price;
  const fmt = '$' + price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  ['btc-price', 'btc-price-mobile', 'trade-live-price'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.textContent = fmt;
  });
  document.querySelectorAll('[data-pos-pts]').forEach(td => {
    const entry = parseFloat(td.dataset.entry);
    const dir   = td.dataset.dir;
    const pts   = dir === 'long' ? price - entry : entry - price;
    td.innerHTML = `<span style="color:${pts >= 0 ? 'var(--green)' : 'var(--red)'}">${pts >= 0 ? '+' : ''}${pts.toFixed(1)}</span>`;
  });
}


// ── Trading scanner ────────────────────────────────────────────────────────────
let _tradingData = null;
let _histPage    = 0;
const _HIST_PAGE_SIZE = 20;

function fmtPrice(v) {
  return v != null
    ? Number(v).toLocaleString('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 1 })
    : '—';
}

function renderLevels(levels, running, regime) {
  const el = document.getElementById('levels-row');
  if (!el) return;
  if (!running) { el.style.display = 'none'; return; }
  el.style.display = '';
  const mrpStr  = levels.mrp        ? `<span style="color:var(--accent)">$${fmtPrice(levels.mrp)}</span>`        : '<span style="color:var(--text-3)">—</span>';
  const dpocStr = levels.daily_poc  ? `<span style="color:var(--green)">$${fmtPrice(levels.daily_poc)}</span>`   : '<span style="color:var(--text-3)">—</span>';
  const wpocStr = levels.weekly_poc ? `<span style="color:#c084fc">$${fmtPrice(levels.weekly_poc)}</span>`       : '<span style="color:var(--text-3)">—</span>';
  const h4pocStr = levels['4h_poc'] ? `<span style="color:#fb923c">$${fmtPrice(levels['4h_poc'])}</span>`        : '<span style="color:var(--text-3)">—</span>';
  const duStr   = levels.depo_upper ? `<span style="color:#f97316">$${fmtPrice(levels.depo_upper)}</span>`       : '<span style="color:var(--text-3)">—</span>';
  const dlStr   = levels.depo_lower ? `<span style="color:#38bdf8">$${fmtPrice(levels.depo_lower)}</span>`       : '<span style="color:var(--text-3)">—</span>';

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
    <span class="level-item">4H-POC: ${h4pocStr}</span><span class="level-sep">·</span>
    <span class="level-item">W-POC: ${wpocStr}</span><span class="level-sep">·</span>
    <span class="level-item">DEPO ↑: ${duStr}</span><span class="level-sep">·</span>
    <span class="level-item">DEPO ↓: ${dlStr}</span><span class="level-sep">·</span>
    <span class="level-item">Bias: <span style="color:${biasColor}">${bias}</span></span>${(() => {
      if (!regime?.regime || regime?.error) return '';
      const cls = regime.regime === 'Bull' ? 'badge-bull' : regime.regime === 'Bear' ? 'badge-bear' : 'badge-neutral';
      const pct = regime.conviction != null ? `${(regime.conviction * 100) >= 0 ? '+' : ''}${(regime.conviction * 100).toFixed(0)}%` : '';
      return `<span class="level-sep">·</span><span class="level-item">Regime: <span class="badge ${cls}">${regime.regime}</span><span style="font-size:11px;color:var(--text-3);margin-left:4px">${pct}</span></span>`;
    })()}`;
}

let _ptsModeFilter = 'live';

function _renderPointsStats(history) {
  const todayEl = document.getElementById('pts-today');
  const weekEl  = document.getElementById('pts-week');
  const monthEl = document.getElementById('pts-month');
  if (!todayEl) return;

  const tz  = localStorage.getItem(TZ_KEY) || DEFAULT_TZ;
  const now = new Date();

  const toDateStr = (d) => new Intl.DateTimeFormat('en-CA', { timeZone: tz }).format(d);
  const todayStr  = toDateStr(now);

  const nowLocal   = new Date(now.toLocaleString('en-US', { timeZone: tz }));
  const dowMon     = (nowLocal.getDay() + 6) % 7; // 0 = Monday
  const weekStart  = new Date(nowLocal); weekStart.setDate(weekStart.getDate() - dowMon); weekStart.setHours(0,0,0,0);
  const monthStart = new Date(nowLocal); monthStart.setDate(1); monthStart.setHours(0,0,0,0);

  let todayPts = 0, weekPts = 0, monthPts = 0;
  let todayN = 0, weekN = 0, monthN = 0;

  for (const r of history) {
    if (r.close_reason === 'stopped_by_user') continue;
    if (_ptsModeFilter !== 'all' && (r.mode || 'paper') !== _ptsModeFilter) continue;
    const p   = r.position;
    const pts = p.direction === 'long' ? r.close_price - p.entry_price : p.entry_price - r.close_price;
    const closedAt    = new Date(r.closed_at);
    const closedLocal = new Date(closedAt.toLocaleString('en-US', { timeZone: tz }));
    if (toDateStr(closedAt) === todayStr)  { todayPts += pts; todayN++; }
    if (closedLocal >= weekStart)          { weekPts  += pts; weekN++;  }
    if (closedLocal >= monthStart)         { monthPts += pts; monthN++; }
  }

  const fmt = (v, n) => n === 0
    ? '<span style="color:var(--text-3)">—</span>'
    : `<span class="${v >= 0 ? 'pnl-pos' : 'pnl-neg'}">${v >= 0 ? '+' : ''}${v.toFixed(1)}</span>`
      + `<span style="font-size:11px;color:var(--text-3);margin-left:4px">(${n})</span>`;

  todayEl.innerHTML = fmt(todayPts, todayN);
  weekEl.innerHTML  = fmt(weekPts,  weekN);
  monthEl.innerHTML = fmt(monthPts, monthN);

  const sel = document.getElementById('pts-mode-filter');
  if (sel && sel.value !== _ptsModeFilter) sel.value = _ptsModeFilter;
}

let _regimeData = null;

async function loadRegimeLog() {
  try {
    _regimeData = await fetchJSON('/api/regime-log');
    renderRegimeLog();
  } catch (e) { /* regime log is observational — swallow silently */ }
}

function renderRegimeLog() {
  if (!_regimeData) return;
  const { rows = [], accuracy, graded_count } = _regimeData;
  const accEl = document.getElementById('regime-accuracy');
  if (accEl) {
    if (accuracy !== null && accuracy !== undefined) {
      const pct = (accuracy * 100).toFixed(1);
      const color = accuracy >= 0.6 ? 'var(--green)' : accuracy >= 0.45 ? 'var(--accent)' : 'var(--red)';
      accEl.innerHTML = `<span style="color:${color};font-weight:600">${pct}%</span><span style="font-size:11px;color:var(--text-3);margin-left:4px">(${graded_count} graded)</span>`;
    } else {
      accEl.innerHTML = '<span style="color:var(--text-3)">—</span>';
    }
  }
  const tbody = document.getElementById('regime-log-body');
  if (!tbody) return;
  if (!rows.length) { tbody.innerHTML = '<tr class="empty-row"><td colspan="5">No data yet</td></tr>'; return; }
  tbody.innerHTML = rows.map(r => {
    const predCls = r.predicted_regime === 'Bull' ? 'badge-bull' : r.predicted_regime === 'Bear' ? 'badge-bear' : 'badge-neutral';
    const actCls  = r.actual_regime === 'Bull' ? 'badge-bull' : r.actual_regime === 'Bear' ? 'badge-bear' : 'badge-neutral';
    const correctCell = r.correct === null || r.correct === undefined
      ? '<span style="color:var(--text-3)">—</span>'
      : r.correct ? '<span style="color:var(--green)">✓</span>' : '<span style="color:var(--red)">✗</span>';
    const conv = r.conviction != null ? `${(r.conviction * 100) >= 0 ? '+' : ''}${(r.conviction * 100).toFixed(0)}%` : '—';
    return `<tr>
      <td style="font-variant-numeric:tabular-nums;color:var(--text-3)">${r.date}</td>
      <td>${r.predicted_regime ? `<span class="badge ${predCls}">${r.predicted_regime}</span>` : '—'}</td>
      <td style="color:var(--text-3);font-size:12px">${conv}</td>
      <td>${r.actual_regime ? `<span class="badge ${actCls}">${r.actual_regime}</span>` : '<span style="color:var(--text-3)">pending</span>'}</td>
      <td>${correctCell}</td>
    </tr>`;
  }).join('');
}

// ── Markov Analytics ──────────────────────────────────────────────────────────

let _markovData   = null;
let _markovFilter = 'all';
let _markovExpanded = null;

async function loadMarkovTickers() {
  try {
    _markovData = await fetchJSON('/api/markov/tickers');
    renderMarkovPage();
  } catch (e) { /* observational — swallow */ }
}

function setMarkovFilter(f) {
  _markovFilter = f;
  ['all','US','IN','custom'].forEach(k => {
    const el = document.getElementById(`markov-pill-${k}`);
    if (el) el.className = 'pill' + (k === f ? ' active' : '');
  });
  renderMarkovPage();
}

function renderMarkovPage() {
  if (!_markovData) return;
  const { tickers = [] } = _markovData;

  // Summary strip
  const sumEl = document.getElementById('markov-summary');
  if (sumEl) {
    const bulls = tickers.filter(t => t.regime === 'Bull').length;
    const bears = tickers.filter(t => t.regime === 'Bear').length;
    const sides = tickers.filter(t => t.regime === 'Sideways').length;
    const errs  = tickers.filter(t => t.error).length;
    sumEl.innerHTML = [
      `<span class="badge badge-neutral">${tickers.length} tickers</span>`,
      `<span class="badge badge-bull">Bull: ${bulls}</span>`,
      `<span class="badge badge-bear">Bear: ${bears}</span>`,
      `<span class="badge badge-neutral">Sideways: ${sides}</span>`,
      errs ? `<span class="badge badge-neutral" style="color:var(--red)">${errs} errors</span>` : '',
    ].join('');
  }

  // Filter
  const filtered = tickers.filter(t => {
    if (_markovFilter === 'all') return true;
    return (t.market || 'US') === _markovFilter;
  });

  const tbody = document.getElementById('markov-tickers-body');
  if (!tbody) return;
  if (!filtered.length) {
    tbody.innerHTML = '<tr class="empty-row"><td colspan="7">No tickers in this filter</td></tr>';
    return;
  }

  const rows = [];
  for (const t of filtered) {
    const tid = t.ticker || '';
    const isExp = _markovExpanded === tid;
    if (t.error) {
      rows.push(`<tr>
        <td><span style="font-size:11px">${t.market === 'IN' ? '🇮🇳' : t.market === 'custom' ? '⭐' : '🇺🇸'}</span></td>
        <td style="font-weight:600">${tid}</td>
        <td colspan="4" style="color:var(--red);font-size:12px">${t.error}</td>
        <td>${t.market === 'custom' ? `<button class="btn btn-danger" style="font-size:11px;padding:2px 8px" onclick="removeMarkovCustomTicker('${tid}')">✕</button>` : ''}</td>
      </tr>`);
      continue;
    }
    const regCls = t.regime === 'Bull' ? 'badge-bull' : t.regime === 'Bear' ? 'badge-bear' : 'badge-neutral';
    const conv = t.conviction != null ? `${(t.conviction * 100) >= 0 ? '+' : ''}${(t.conviction * 100).toFixed(1)}%` : '—';
    const acc = t.accuracy != null ? `${(t.accuracy * 100).toFixed(0)}% (${t.graded_count}d)` : '—';
    const updAt = t.computed_at ? new Date(t.computed_at).toLocaleString() : '—';
    const flag = t.market === 'IN' ? '🇮🇳' : t.market === 'custom' ? '⭐' : '🇺🇸';
    rows.push(`<tr style="cursor:pointer" onclick="toggleMarkovExpand('${tid}')">
      <td><span style="font-size:13px">${flag}</span></td>
      <td style="font-weight:600;font-variant-numeric:tabular-nums">${tid}</td>
      <td><span class="badge ${regCls}">${t.regime || '—'}</span></td>
      <td style="color:var(--text-2)">${conv}</td>
      <td style="color:var(--text-2)">${acc}</td>
      <td style="font-size:11px;color:var(--text-3)">${updAt}</td>
      <td style="display:flex;gap:4px;align-items:center">
        <span style="font-size:10px;color:var(--text-3)">${isExp ? '▲' : '▼'}</span>
        ${t.market === 'custom' ? `<button class="btn btn-danger" style="font-size:11px;padding:2px 8px" onclick="event.stopPropagation();removeMarkovCustomTicker('${tid}')">✕</button>` : ''}
      </td>
    </tr>`);
    if (isExp) {
      rows.push(`<tr id="markov-exp-${tid.replace(/[^a-z0-9]/gi,'_')}">
        <td colspan="7" style="padding:12px 16px;background:var(--surface-2)">
          <div style="font-size:11px;color:var(--text-3);margin-bottom:8px">30-day prediction log for ${tid}</div>
          <div id="markov-hist-${tid.replace(/[^a-z0-9]/gi,'_')}"><span style="color:var(--text-3)">Loading…</span></div>
        </td>
      </tr>`);
    }
  }
  tbody.innerHTML = rows.join('');

  // Load history for expanded ticker
  if (_markovExpanded) {
    _loadMarkovHistory(_markovExpanded);
  }
}

async function toggleMarkovExpand(ticker) {
  _markovExpanded = _markovExpanded === ticker ? null : ticker;
  renderMarkovPage();
}

async function _loadMarkovHistory(ticker) {
  const safeId = ticker.replace(/[^a-z0-9]/gi, '_');
  const el = document.getElementById(`markov-hist-${safeId}`);
  if (!el) return;
  try {
    const data = await fetchJSON(`/api/markov/tickers/${encodeURIComponent(ticker)}/history`);
    const { rows = [], accuracy, graded_count } = data;
    if (!rows.length) { el.innerHTML = '<span style="color:var(--text-3)">No history yet</span>'; return; }
    const accLine = accuracy != null
      ? `<div style="font-size:11px;color:var(--text-3);margin-bottom:6px">Accuracy: <strong style="color:${accuracy>=0.6?'var(--green)':accuracy>=0.45?'var(--accent)':'var(--red)'}">${(accuracy*100).toFixed(1)}%</strong> (${graded_count} graded)</div>`
      : '';
    el.innerHTML = accLine + `<table style="font-size:12px;width:100%;border-collapse:collapse">
      <thead><tr style="color:var(--text-3)"><th style="text-align:left;padding:4px 8px">Date</th><th>Predicted</th><th>Conviction</th><th>Actual</th><th>Result</th></tr></thead>
      <tbody>${rows.map(r => {
        const predCls = r.predicted_regime === 'Bull' ? 'badge-bull' : r.predicted_regime === 'Bear' ? 'badge-bear' : 'badge-neutral';
        const actCls  = r.actual_regime === 'Bull' ? 'badge-bull' : r.actual_regime === 'Bear' ? 'badge-bear' : 'badge-neutral';
        const ok = r.correct === null || r.correct === undefined ? '<span style="color:var(--text-3)">—</span>' : r.correct ? '<span style="color:var(--green)">✓</span>' : '<span style="color:var(--red)">✗</span>';
        const conv = r.conviction != null ? `${(r.conviction*100)>=0?'+':''}${(r.conviction*100).toFixed(1)}%` : '—';
        const bg = r.correct === true ? 'background:rgba(34,197,94,0.05)' : r.correct === false ? 'background:rgba(239,68,68,0.05)' : '';
        return `<tr style="${bg}">
          <td style="padding:4px 8px;color:var(--text-3)">${r.date}</td>
          <td style="text-align:center">${r.predicted_regime ? `<span class="badge ${predCls}">${r.predicted_regime}</span>` : '—'}</td>
          <td style="text-align:center;color:var(--text-2)">${conv}</td>
          <td style="text-align:center">${r.actual_regime ? `<span class="badge ${actCls}">${r.actual_regime}</span>` : '<span style="color:var(--text-3)">pending</span>'}</td>
          <td style="text-align:center">${ok}</td>
        </tr>`;
      }).join('')}</tbody>
    </table>`;
  } catch (e) {
    if (el) el.innerHTML = '<span style="color:var(--red)">Failed to load history</span>';
  }
}

async function addMarkovCustomTicker() {
  const input = document.getElementById('markov-custom-input');
  const ticker = (input?.value || '').trim().toUpperCase();
  if (!ticker) return;
  try {
    await fetchJSON('/api/settings/markov/custom-ticker', { method: 'POST', body: JSON.stringify({ ticker }) });
    if (input) input.value = '';
    await loadMarkovTickers();
  } catch (e) {
    alert(`Failed to add ticker: ${e.message || e}`);
  }
}

async function removeMarkovCustomTicker(ticker) {
  if (!confirm(`Remove ${ticker} from custom tickers?`)) return;
  try {
    await fetchJSON(`/api/settings/markov/custom-ticker/${encodeURIComponent(ticker)}`, { method: 'DELETE' });
    await loadMarkovTickers();
  } catch (e) {
    alert(`Failed to remove ticker: ${e.message || e}`);
  }
}

function renderRegimePage() {
  if (!_regimeData) return;
  const { rows = [], accuracy, graded_count, live_regime } = _regimeData;

  // Live regime card
  const liveEl = document.getElementById('regime-page-live');
  if (liveEl && live_regime) {
    if (live_regime.error) {
      liveEl.innerHTML = `<span style="color:var(--red)">Regime unavailable: ${live_regime.error}</span>`;
    } else {
      const cls = live_regime.regime === 'Bull' ? 'badge-bull' : live_regime.regime === 'Bear' ? 'badge-bear' : 'badge-neutral';
      const pct = live_regime.conviction != null ? `${(live_regime.conviction * 100) >= 0 ? '+' : ''}${(live_regime.conviction * 100).toFixed(1)}%` : '—';
      const ts  = live_regime.computed_at ? new Date(live_regime.computed_at).toLocaleString() : '—';
      liveEl.innerHTML = `
        <span class="badge ${cls}" style="font-size:15px;padding:4px 14px">${live_regime.regime}</span>
        <span style="font-size:13px;color:var(--text-2);margin-left:10px">Conviction: <strong>${pct}</strong></span>
        <span style="font-size:11px;color:var(--text-3);margin-left:12px">computed ${ts}</span>`;
    }
  }

  // Accuracy summary
  const accEl = document.getElementById('regime-page-accuracy');
  if (accEl) {
    if (accuracy !== null && accuracy !== undefined) {
      const pct   = (accuracy * 100).toFixed(1);
      const color = accuracy >= 0.6 ? 'var(--green)' : accuracy >= 0.45 ? 'var(--accent)' : 'var(--red)';
      accEl.innerHTML = `<span style="font-size:28px;font-weight:700;color:${color}">${pct}%</span>
        <span style="font-size:12px;color:var(--text-3);margin-left:8px">${graded_count} graded days</span>`;
    } else {
      accEl.innerHTML = '<span style="color:var(--text-3)">No graded data yet</span>';
    }
  }

  // Regime distribution from graded rows
  const graded = rows.filter(r => r.actual_regime != null);
  const distEl = document.getElementById('regime-page-dist');
  if (distEl && graded.length) {
    const counts = { Bull: 0, Bear: 0, Sideways: 0 };
    graded.forEach(r => { if (counts[r.actual_regime] != null) counts[r.actual_regime]++; });
    const total = graded.length;
    distEl.innerHTML = ['Bull','Sideways','Bear'].map(s => {
      const cls = s === 'Bull' ? 'badge-bull' : s === 'Bear' ? 'badge-bear' : 'badge-neutral';
      const pct = total ? ((counts[s] / total) * 100).toFixed(0) : 0;
      return `<div style="text-align:center;padding:10px 20px">
        <div style="font-size:22px;font-weight:700">${pct}%</div>
        <div style="margin-top:4px"><span class="badge ${cls}">${s}</span></div>
        <div style="font-size:11px;color:var(--text-3);margin-top:4px">${counts[s]} days</div>
      </div>`;
    }).join('<div style="width:1px;background:var(--border)"></div>');
  }

  // Full log table
  const tbody = document.getElementById('regime-page-body');
  if (!tbody) return;
  if (!rows.length) { tbody.innerHTML = '<tr class="empty-row"><td colspan="6">No data yet</td></tr>'; return; }
  tbody.innerHTML = rows.map(r => {
    const predCls = r.predicted_regime === 'Bull' ? 'badge-bull' : r.predicted_regime === 'Bear' ? 'badge-bear' : 'badge-neutral';
    const actCls  = r.actual_regime === 'Bull' ? 'badge-bull' : r.actual_regime === 'Bear' ? 'badge-bear' : 'badge-neutral';
    const correctCell = r.correct === null || r.correct === undefined
      ? '<span style="color:var(--text-3)">pending</span>'
      : r.correct
        ? '<span style="color:var(--green);font-weight:600">✓ Correct</span>'
        : '<span style="color:var(--red)">✗ Wrong</span>';
    const conv = r.conviction != null ? `${(r.conviction * 100) >= 0 ? '+' : ''}${(r.conviction * 100).toFixed(1)}%` : '—';
    const row_bg = r.correct === true ? 'background:rgba(34,197,94,0.04)' : r.correct === false ? 'background:rgba(239,68,68,0.04)' : '';
    return `<tr style="${row_bg}">
      <td style="font-variant-numeric:tabular-nums;color:var(--text-3)">${r.date}</td>
      <td>${r.predicted_regime ? `<span class="badge ${predCls}">${r.predicted_regime}</span>` : '—'}</td>
      <td style="color:var(--text-2)">${conv}</td>
      <td>${r.actual_regime ? `<span class="badge ${actCls}">${r.actual_regime}</span>` : '<span style="color:var(--text-3)">—</span>'}</td>
      <td>${correctCell}</td>
      <td style="font-size:11px;color:var(--text-3)">${r.computed_at ? new Date(r.computed_at).toLocaleString() : '—'}</td>
    </tr>`;
  }).join('');
}

function renderTrading() {
  if (!_tradingData) return;
  const { signals = [], positions = [], history = [], running, settings = {}, levels = {}, current_regime = {}, current_price = 0, broker_account_name = '' } = _tradingData;

  _setText('trade-mode-label', (settings.mode || 'paper').toUpperCase());
  const acctLabel = document.getElementById('trade-account-label');
  const acctName  = document.getElementById('trade-account-name');
  if (acctLabel && acctName) {
    const displayName = settings.broker_nickname || _currentUser?.displayName || _currentUser?.email || broker_account_name;
    const showAcct = running && settings.mode === 'live' && displayName;
    acctLabel.style.display = showAcct ? '' : 'none';
    acctName.textContent = displayName;
  }
  if (current_price) _applyPrice(current_price);

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

  renderLevels(levels, running, current_regime);

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
      const m = s.meta || {};
      const patternCell = (s.pattern === 'Retracement' && m.sw_hi)
        ? `<td>
            <div style="font-weight:500">Retracement</div>
            <div style="font-size:10px;margin-top:3px;display:flex;gap:10px">
              <span style="color:var(--green)">▲ SW High: ${Math.round(m.sw_hi).toLocaleString('en-US')}</span>
              <span style="color:var(--red)">▼ SW Low: ${Math.round(m.sw_lo).toLocaleString('en-US')}</span>
            </div>
            <div style="font-size:10px;color:var(--text-3);margin-top:1px;display:flex;gap:10px">
              <span>50%: ${Math.round(m.fib_50).toLocaleString('en-US')}</span>
              <span>61.8%: ${Math.round(m.fib_618).toLocaleString('en-US')}</span>
            </div>
           </td>`
        : `<td>${s.pattern}</td>`;
      return `<tr>
        ${patternCell}
        <td><span class="badge badge-neutral">${s.tf}m</span></td>
        <td>${dirBadge}</td>
        <td style="text-align:right;font-variant-numeric:tabular-nums">${Number(s.entry_trigger).toLocaleString('en-US',{minimumFractionDigits:1,maximumFractionDigits:1})}</td>
        <td style="text-align:right;color:var(--red);font-variant-numeric:tabular-nums">${Number(s.sl_wick).toLocaleString('en-US',{minimumFractionDigits:1,maximumFractionDigits:1})}</td>
        <td style="color:var(--text-3);font-size:12px">${formatTs(s.expires_at)}</td>
        <td style="color:var(--accent)">
          ${s.status}
          ${s.note ? `<div style="font-size:10px;color:#f5a623;margin-top:2px">${s.note}</div>` : ''}
        </td>
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
        <td style="text-align:right" data-pos-pts data-entry="${p.entry_price}" data-dir="${p.direction}">${ptsStr}</td>
        <td style="text-align:right;color:var(--text-3)">${remQty}</td>
        <td>${phaseHtml}</td>
        <td style="color:var(--text-3);font-size:12px">${formatTs(p.opened_at)}</td>
        <td><button class="btn btn-danger" style="font-size:11px;padding:3px 10px" onclick="cancelPosition('${p.signal_id}')">Cancel</button></td>
      </tr>`;
    }).join('');
  }

  _renderPointsStats(history);

  // history table
  const histBody  = document.getElementById('trade-history-body');
  const histPager = document.getElementById('hist-pagination');
  const sorted    = _applyHistFilters([...history].reverse());
  const totalPages = Math.max(1, Math.ceil(sorted.length / _HIST_PAGE_SIZE));
  _histPage = Math.min(_histPage, totalPages - 1);
  if (!sorted.length) {
    histBody.innerHTML = '<tr class="empty-row"><td colspan="12">No completed trades</td></tr>';
    if (histPager) histPager.style.display = 'none';
  } else {
    const start = _histPage * _HIST_PAGE_SIZE;
    const page  = sorted.slice(start, start + _HIST_PAGE_SIZE);
    const prevBtn = document.getElementById('hist-prev');
    const nextBtn = document.getElementById('hist-next');
    const label   = document.getElementById('hist-page-label');
    if (histPager) histPager.style.display = totalPages > 1 ? 'flex' : 'none';
    if (label)   label.textContent  = `Page ${_histPage + 1} of ${totalPages}  (${history.length} trades)`;
    if (prevBtn) prevBtn.disabled   = _histPage === 0;
    if (nextBtn) nextBtn.disabled   = _histPage >= totalPages - 1;
    histBody.innerHTML = page.map(r => {
      const p          = r.position;
      const isPartial  = r.close_reason === 'tp_partial';
      const isStopped  = r.close_reason === 'stopped_by_user';
      const dirBadge   = p.direction === 'long'
        ? '<span class="badge badge-bull">▲ Long</span>'
        : '<span class="badge badge-bear">▼ Short</span>';
      const reasonColor = isStopped ? 'var(--text-3)' : r.close_reason === 'sl' ? 'var(--red)' : 'var(--green)';
      const reasonLabel = isPartial ? 'TP 50%' : isStopped ? 'Stopped by user' : r.close_reason.toUpperCase();
      const tradeMode  = r.mode || 'paper';
      const modeBadge  = tradeMode === 'live'
        ? '<span class="badge badge-bull" style="font-size:10px">Live</span>'
        : '<span class="badge badge-neutral" style="font-size:10px">Paper</span>';
      const pts        = isStopped ? null :
        (p.direction === 'long' ? r.close_price - p.entry_price : p.entry_price - r.close_price);
      const ptsStr     = pts === null ? '—' : (pts >= 0 ? '+' : '') + pts.toFixed(1);
      const ptsClass   = pts === null ? '' : pts >= 0 ? 'pnl-pos' : 'pnl-neg';
      return `<tr style="${isPartial || isStopped ? 'opacity:0.75' : ''}">
        <td>${dirBadge}</td>
        <td><span class="badge badge-neutral">${p.tf ? p.tf + 'm' : '—'}</span></td>
        <td>${p.pattern || '—'}</td>
        <td>${modeBadge}</td>
        <td style="text-align:right;font-variant-numeric:tabular-nums">$${fmtPrice(p.entry_price)}</td>
        <td style="text-align:right;font-variant-numeric:tabular-nums">${isStopped ? '—' : '$' + fmtPrice(r.close_price)}</td>
        <td style="text-align:right;font-variant-numeric:tabular-nums" class="${ptsClass}">${ptsStr}</td>
        <td style="text-align:right;color:var(--text-3)">${r.qty_closed ?? p.qty}</td>
        <td style="color:${reasonColor}">${reasonLabel}</td>
        <td style="color:var(--text-3);font-size:12px">${formatTs(p.opened_at)}</td>
        <td style="color:var(--text-3);font-size:12px">${formatTs(r.closed_at)}</td>
      </tr>`;
    }).join('');
  }

  // BSG alerts
  const bsgAlerts  = _tradingData?.bsg_alerts || [];
  const bsgEnabled = !!_tradingData?.settings?.bsg_enabled;
  const bsgSection = document.getElementById('bsg-section');
  if (bsgSection) {
    bsgSection.style.display = bsgEnabled ? '' : 'none';
    const tbody = document.getElementById('bsg-alerts-body');
    if (tbody) {
      if (!bsgAlerts.length) {
        tbody.innerHTML = '<tr class="empty-row"><td colspan="4">No crossovers detected yet — waiting for 15m or 30m SuperTrend flip</td></tr>';
      } else {
        tbody.innerHTML = [...bsgAlerts].reverse().map(a => `<tr>
          <td>${a.direction === 'long'
            ? '<span class="badge badge-bull">▲ Long</span>'
            : '<span class="badge badge-bear">▼ Short</span>'}</td>
          <td><span class="badge badge-neutral">${a.tf}m</span></td>
          <td style="text-align:right;font-variant-numeric:tabular-nums">$${fmtPrice(a.price)}</td>
          <td style="color:var(--text-3);font-size:12px">${formatTs(a.bar_time)}</td>
        </tr>`).join('');
      }
    }
  }
}

function histPageNav(delta) {
  const history = (_tradingData?.history) || [];
  const totalPages = Math.max(1, Math.ceil(history.length / _HIST_PAGE_SIZE));
  _histPage = Math.max(0, Math.min(_histPage + delta, totalPages - 1));
  renderTrading();
}

function histFilterChanged() {
  _histPage = 0;
  renderTrading();
}

function _applyHistFilters(history) {
  const modeVal    = document.getElementById('hist-filter-mode')?.value    || 'all';
  const patternVal = document.getElementById('hist-filter-pattern')?.value || 'all';
  return history.filter(r => {
    if (modeVal    !== 'all' && (r.mode || 'paper') !== modeVal)          return false;
    if (patternVal !== 'all' && (r.position?.pattern || '') !== patternVal) return false;
    return true;
  });
}

async function loadTrading() {
  try {
    const fresh  = await fetchJSON('/api/trading/state');
    const prevLen = (_tradingData?.history || []).length;
    _tradingData  = fresh;
    if ((fresh.history || []).length !== prevLen) _histPage = 0;
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
  document.getElementById('cfg-pattern-4flag').checked       = activePatterns.includes('4-Flag');
  document.getElementById('cfg-pattern-engulfing').checked    = activePatterns.includes('Engulfing');
  document.getElementById('cfg-pattern-retracement').checked  = activePatterns.includes('Retracement');
  document.getElementById('cfg-bias-filter').checked = !!settings.bias_filter;
  const depoFiltEl = document.getElementById('cfg-depo-entry-filter');
  if (depoFiltEl) depoFiltEl.checked = !!settings.depo_entry_filter;
  const pocFiltEl = document.getElementById('cfg-poc-entry-filter');
  if (pocFiltEl) pocFiltEl.checked = !!settings.poc_entry_filter;
  const compressionEl = document.getElementById('cfg-compression-enabled');
  if (compressionEl) compressionEl.checked = !!settings.compression_enabled;
  const cmeEl = document.getElementById('cfg-cme-close-skip');
  if (cmeEl) cmeEl.checked = !!settings.cme_close_skip;
  const bsgEl = document.getElementById('cfg-bsg-enabled');
  if (bsgEl) bsgEl.checked = !!settings.bsg_enabled;
  const bsgTradeEl = document.getElementById('cfg-bsg-trade-enabled');
  if (bsgTradeEl) bsgTradeEl.checked = !!settings.bsg_trade_enabled;
  const trailEl = document.getElementById('cfg-trail-offset');
  if (trailEl && document.activeElement !== trailEl)
    trailEl.value = settings.trail_offset ?? 50;
  const lcEl = document.getElementById('cfg-lookback-candles');
  if (lcEl && document.activeElement !== lcEl)
    lcEl.value = settings.lookback_candles ?? 3;
  const emEl = document.getElementById('cfg-entry-mode');
  if (emEl) emEl.value = settings.entry_mode ?? 'immediate';
  const dptEl = document.getElementById('cfg-daily-pts');
  if (dptEl && document.activeElement !== dptEl)
    dptEl.value = settings.daily_pts_target ?? 0;
  const slMode = (settings.daily_sl_pts > 0) ? 'pts' : (settings.daily_sl_limit > 0) ? 'count' : 'off';
  const slModeEl = document.getElementById('cfg-daily-sl-mode');
  if (slModeEl) slModeEl.value = slMode;
  const dslPtsEl = document.getElementById('cfg-daily-sl-pts');
  if (dslPtsEl && document.activeElement !== dslPtsEl)
    dslPtsEl.value = settings.daily_sl_pts ?? 0;
  const dslCntEl = document.getElementById('cfg-daily-sl-limit');
  if (dslCntEl && document.activeElement !== dslCntEl)
    dslCntEl.value = settings.daily_sl_limit ?? 1;
  _updateSlStopRow(slMode);
  const osaEl = document.getElementById('cfg-opposite-signal-action');
  if (osaEl) osaEl.value = settings.opposite_signal_action ?? 'skip';
}

function _updateSlStopRow(mode) {
  const ptsRow   = document.getElementById('cfg-sl-pts-row');
  const countRow = document.getElementById('cfg-sl-count-row');
  if (ptsRow)   ptsRow.style.display   = mode === 'pts'   ? 'flex' : 'none';
  if (countRow) countRow.style.display = mode === 'count' ? 'flex' : 'none';
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
      ...(document.getElementById('cfg-pattern-4flag').checked       ? ['4-Flag']      : []),
      ...(document.getElementById('cfg-pattern-engulfing').checked    ? ['Engulfing']   : []),
      ...(document.getElementById('cfg-pattern-retracement').checked  ? ['Retracement'] : []),
    ],
    bias_filter:        document.getElementById('cfg-bias-filter').checked,
    depo_entry_filter:   !!document.getElementById('cfg-depo-entry-filter')?.checked,
    poc_entry_filter:    !!document.getElementById('cfg-poc-entry-filter')?.checked,
    compression_enabled: !!document.getElementById('cfg-compression-enabled')?.checked,
    cme_close_skip:     !!document.getElementById('cfg-cme-close-skip')?.checked,
    bsg_enabled:       !!document.getElementById('cfg-bsg-enabled')?.checked,
    bsg_trade_enabled: !!document.getElementById('cfg-bsg-trade-enabled')?.checked,
    lookback_candles: parseInt(document.getElementById('cfg-lookback-candles')?.value) || 3,
    entry_mode:       document.getElementById('cfg-entry-mode')?.value || 'immediate',
    trail_offset: parseInt(document.getElementById('cfg-trail-offset')?.value || '50'),
    daily_pts_target: parseFloat(document.getElementById('cfg-daily-pts')?.value) || 0,
    daily_sl_pts:  (() => { const m = document.getElementById('cfg-daily-sl-mode')?.value; return m === 'pts'   ? (parseFloat(document.getElementById('cfg-daily-sl-pts')?.value)   || 0) : 0; })(),
    daily_sl_limit: (() => { const m = document.getElementById('cfg-daily-sl-mode')?.value; return m === 'count' ? (parseInt(document.getElementById('cfg-daily-sl-limit')?.value) || 0) : 0; })(),
    opposite_signal_action:  document.getElementById('cfg-opposite-signal-action')?.value || 'skip',
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
  _connectPriceWS();
  // Fallback: if WebSocket goes silent for 3s (browser throttle), poll REST
  setInterval(() => { if (!document.hidden && Date.now() - _lastPriceTick > 3000) fetchBTCPrice(); }, 2000);
  setInterval(() => { if (!document.hidden) Promise.all([loadBriefing(), loadScan()]); }, REFRESH_MS);
  setInterval(() => { if (!document.hidden) pollStatus(); }, 3000);
  // Trading polling only when signed in
  setInterval(() => { if (!document.hidden && _currentUser) loadTrading(); }, 5000);
  // Regime log — load once, then once per minute (changes at most daily)
  if (_currentUser) loadRegimeLog();
  setInterval(() => { if (!document.hidden && _currentUser) loadRegimeLog(); }, 60_000);
  // Markov analytics — refresh every 5 min when page is active
  setInterval(() => { if (!document.hidden && _currentUser && _currentSection === 'markov') loadMarkovTickers(); }, 5 * 60_000);
  // Users page auto-refresh when visible
  setInterval(() => {
    if (!document.hidden && document.getElementById('page-users')?.classList.contains('active')) _showUsersPage();
  }, 8000);
})();

// ── Admin Users Page ───────────────────────────────────────────────────────────

async function _showUsersPage() {
  const tbody = document.getElementById('users-tbody');
  if (!tbody) return;

  // Skip auto-refresh while any trade panel is open — avoids collapsing expanded rows
  const anyOpen = [...tbody.querySelectorAll('tr[id^="utr-"]')].some(r => r.style.display !== 'none');
  if (anyOpen) return;

  try {
    const users = await fetchJSON('/api/admin/users');
    if (!users.length) {
      tbody.innerHTML = '<tr class="empty-row"><td colspan="5">No users found</td></tr>';
      return;
    }
    tbody.innerHTML = users.map(u => {
      const uid = u.uid;
      const runBadge = u.scanner_running
        ? '<span class="badge badge-bull">Running</span>'
        : '<span class="badge" style="background:var(--surface-3);color:var(--text-2)">Stopped</span>';
      const modeBadge = u.mode === 'live'
        ? '<span class="badge badge-bear">Live</span>'
        : '<span class="badge" style="background:var(--surface-3);color:var(--text-2)">Paper</span>';
      const stopBtn = u.scanner_running
        ? `<button class="btn btn-danger" style="font-size:11px;padding:3px 10px" onclick="event.stopPropagation();_adminStopUser('${uid}')">Stop</button>`
        : '';
      const modeBtn = u.mode === 'live'
        ? `<button class="btn" style="font-size:11px;padding:3px 10px" onclick="event.stopPropagation();_adminSetMode('${uid}','paper')">→ Paper</button>`
        : `<button class="btn" style="font-size:11px;padding:3px 10px" onclick="event.stopPropagation();_adminSetMode('${uid}','live')">→ Live</button>`;
      const chevron = `<svg id="uch-${uid}" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="transition:transform 0.2s;transform:rotate(-90deg);flex-shrink:0"><polyline points="6 9 12 15 18 9"/></svg>`;
      return `
        <tr style="cursor:pointer" onclick="_toggleUserTrades('${uid}')">
          <td>
            <div style="display:flex;align-items:center;gap:8px">
              ${chevron}
              <div>
                <div style="font-weight:500">${u.display_name}</div>
                <div style="font-size:11px;color:var(--text-3)">${u.email}</div>
              </div>
            </div>
          </td>
          <td>${modeBadge}</td>
          <td style="text-transform:capitalize">${u.broker}</td>
          <td>${runBadge}</td>
          <td style="display:flex;gap:6px;flex-wrap:wrap;align-items:center">${stopBtn}${modeBtn}</td>
        </tr>
        <tr id="utr-${uid}" style="display:none">
          <td colspan="5" style="padding:0;background:var(--surface-2)">
            <div id="utd-${uid}" style="padding:14px 18px">
              <span style="color:var(--text-3);font-size:12px">Loading…</span>
            </div>
          </td>
        </tr>`;
    }).join('');
  } catch(e) {
    tbody.innerHTML = `<tr class="empty-row"><td colspan="5">Error: ${e.message}</td></tr>`;
  }
}

async function _toggleUserTrades(uid) {
  const row     = document.getElementById(`utr-${uid}`);
  const chevron = document.getElementById(`uch-${uid}`);
  const detail  = document.getElementById(`utd-${uid}`);
  if (!row) return;
  const isOpen = row.style.display !== 'none';
  row.style.display = isOpen ? 'none' : '';
  if (chevron) chevron.style.transform = isOpen ? 'rotate(-90deg)' : 'rotate(0deg)';
  if (!isOpen && detail && !detail.dataset.loaded) {
    detail.dataset.loaded = '1';
    try {
      const state = await fetchJSON(`/api/admin/users/${uid}/state`);
      detail.innerHTML = _renderUserTrades(state);
    } catch(e) {
      detail.innerHTML = `<span style="color:var(--bear);font-size:12px">Error loading trades: ${e.message}</span>`;
    }
  }
}

function _renderUserTrades(state) {
  const fmt    = n => n == null ? '—' : Number(n).toFixed(1);
  const fmtPnl = n => {
    if (n == null) return '—';
    const col = Number(n) >= 0 ? 'var(--bull)' : 'var(--bear)';
    return `<span style="color:${col}">${Number(n) >= 0 ? '+' : ''}${Number(n).toFixed(4)}</span>`;
  };
  const fmtDate = s => s ? new Date(s).toLocaleString([], {month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}) : '—';
  const dirBadge = d => d === 'long'
    ? '<span class="badge badge-bull" style="font-size:10px;padding:1px 6px">Long</span>'
    : '<span class="badge badge-bear" style="font-size:10px;padding:1px 6px">Short</span>';

  const positions = state.positions || [];
  const posHtml = positions.length
    ? `<div style="overflow-x:auto"><table class="scan-table" style="font-size:11px">
        <thead><tr><th>Dir</th><th>Pattern</th><th>TF</th><th>Entry</th><th>SL</th><th>TP</th><th>PnL</th><th>Opened</th></tr></thead>
        <tbody>${positions.map(p => `<tr>
          <td>${dirBadge(p.direction)}</td>
          <td>${p.pattern}</td><td>${p.tf}m</td>
          <td>${fmt(p.entry_price)}</td><td>${fmt(p.sl)}</td><td>${fmt(p.tp)}</td>
          <td>${fmtPnl(p.pnl)}</td><td>${fmtDate(p.opened_at)}</td>
        </tr>`).join('')}</tbody>
      </table></div>`
    : '<p style="color:var(--text-3);font-size:12px;margin:4px 0 0">No open positions</p>';

  const history = state.history || [];
  const histHtml = history.length
    ? `<div style="overflow-x:auto"><table class="scan-table" style="font-size:11px">
        <thead><tr><th>Dir</th><th>Pattern</th><th>TF</th><th>Entry</th><th>Close</th><th>Reason</th><th>PnL</th><th>Closed</th></tr></thead>
        <tbody>${history.map(h => {
          const p = h.position || {};
          return `<tr>
            <td>${dirBadge(p.direction)}</td>
            <td>${p.pattern || '—'}</td><td>${p.tf ? p.tf + 'm' : '—'}</td>
            <td>${fmt(p.entry_price)}</td><td>${fmt(h.close_price)}</td>
            <td style="text-transform:capitalize">${(h.close_reason || '').replace(/_/g,' ')}</td>
            <td>${fmtPnl(h.pnl_closed)}</td><td>${fmtDate(h.closed_at)}</td>
          </tr>`;
        }).join('')}</tbody>
      </table></div>`
    : '<p style="color:var(--text-3);font-size:12px;margin:4px 0 0">No completed trades</p>';

  const label = s => `<div style="font-size:10px;font-weight:600;color:var(--text-3);text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px">${s}</div>`;
  return `
    <div style="margin-bottom:14px">${label(`Open Positions (${positions.length})`)}${posHtml}</div>
    <div>${label(`Completed Trades (${history.length})`)}${histHtml}</div>`;
}

async function _adminStopUser(uid) {
  await fetchJSON(`/api/admin/users/${uid}/stop`, { method: 'POST' });
  _showUsersPage();
}

async function _adminSetMode(uid, mode) {
  await fetchJSON(`/api/admin/users/${uid}/mode`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ mode }),
  });
  _showUsersPage();
}

function _refreshUsers() { _showUsersPage(); }
