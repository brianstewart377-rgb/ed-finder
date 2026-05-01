/**
 * ED Finder — Frontend Application v2.2
 * ═══════════════════════════════════════════════════════════════════════════
 * This version is designed for maximum robustness, ensuring the UI always 
 * renders even if some subsystems (like the live feed) fail.
 */

// ═══════════════════════════════════════════════════════════════ UTILS
const qs = (sel) => document.querySelector(sel);
const qsa = (sel) => document.querySelectorAll(sel);
const fmtNum = (n) => new Intl.NumberFormat().format(n);
const fmtDist = (n) => n != null ? `${n.toFixed(1)} ly` : 'Unknown';
const fmtCoord = (n) => n != null ? n.toFixed(2) : '0.00';

const toast = (msg, type = 'info') => {
  const el = qs('#toast');
  if (!el) return;
  el.textContent = msg;
  el.className = `toast show ${type}`;
  el.hidden = false;
  setTimeout(() => { el.classList.remove('show'); setTimeout(() => el.hidden = true, 300); }, 3000);
};

// ═══════════════════════════════════════════════════════════════ API
async function apiFetch(url, options = {}) {
  try {
    const res = await fetch(url, {
      ...options,
      headers: { 'Content-Type': 'application/json', ...options.headers }
    });
    if (!res.ok) throw new Error(`Server returned ${res.status}`);
    return await res.json();
  } catch (e) {
    console.error(`API Error [${url}]:`, e);
    throw e;
  }
}

// ═══════════════════════════════════════════════════════════════ WATCHLIST
const Watchlist = {
  _data: {},
  load() {
    try {
      this._data = JSON.parse(localStorage.getItem('ed_watchlist') || '{}');
    } catch (e) { this._data = {}; }
  },
  save() {
    localStorage.setItem('ed_watchlist', JSON.stringify(this._data));
  },
  has(id64) { return !!this._data[id64]; },
  toggle(sys) {
    const id64 = sys.id64;
    if (this.has(id64)) { delete this._data[id64]; }
    else { this._data[id64] = { ...sys, _saved_at: Date.now() }; }
    this.save();
    return this.has(id64);
  },
  getAll() { return Object.values(this._data).sort((a, b) => b._saved_at - a._saved_at); }
};

// ═══════════════════════════════════════════════════════════════ NAVIGATION
function initNavigation() {
  const navBtns = qsa('.nav-btn, .mobile-nav-btn');
  const panels = qsa('.tab-panel');

  function switchTab(tabId) {
    panels.forEach(p => {
      p.classList.toggle('active', p.id === `tab-${tabId}`);
      p.hidden = p.id !== `tab-${tabId}`;
    });
    navBtns.forEach(b => b.classList.toggle('active', b.dataset.tab === tabId));
    localStorage.setItem('ed_active_tab', tabId);
    
    // Trigger tab-specific logic
    if (tabId === 'watchlist') renderWatchlistTab();
  }

  navBtns.forEach(btn => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });

  const lastTab = localStorage.getItem('ed_active_tab') || 'local';
  switchTab(lastTab);
}

// ═══════════════════════════════════════════════════════════════ INITIALIZATION
function initApp() {
  console.log('ED Finder: Initializing components...');
  
  // 1. Load data
  Watchlist.load();
  
  // 2. Setup Navigation
  initNavigation();
  
  // 3. Reveal App
  const container = qs('#app-container');
  if (container) {
    container.style.display = 'block';
    container.style.opacity = '1';
    console.log('ED Finder: UI revealed.');
  } else {
    console.error('ED Finder: #app-container not found!');
  }

  // 4. Check API health
  apiFetch('/api/health')
    .then(() => qs('#status-badge')?.classList.add('online'))
    .catch(() => qs('#status-badge')?.classList.add('offline'));
}

// ═══════════════════════════════════════════════════════════════ DOM READY
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initApp);
} else {
  initApp();
}

// Helper functions for UI (placeholders to prevent errors)
function renderWatchlistTab() { console.log('Watchlist tab rendered'); }
function starLabel(type, sub) { return type || 'Unknown'; }
function popLabel(pop) { return pop > 1e9 ? (pop/1e9).toFixed(1)+'B' : (pop > 1e6 ? (pop/1e6).toFixed(1)+'M' : fmtNum(pop)); }
function scoreColor(val) { return val > 80 ? 'var(--green)' : (val > 50 ? 'var(--gold)' : 'var(--red)'); }
function openSystemModal(sys) { console.log('Opening modal for', sys.name); }
function closeModal() { qs('#system-modal').hidden = true; }
function makeAutocomplete(input, list, onSelect) { /* ... */ }
