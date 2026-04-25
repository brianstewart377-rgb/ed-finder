/* ═══════════════════════════════════════════════════════════════════════════
   ED Finder — Frontend Application v2.1
   ═══════════════════════════════════════════════════════════════════════════ */

'use strict';

// ═══════════════════════════════════════════════════════════════ UTILITIES

function qs(sel, root = document) { return root.querySelector(sel); }
function qsa(sel, root = document) { return [...root.querySelectorAll(sel)]; }

// Improvement #4: AbortController-aware fetch — callers can cancel in-flight requests
async function apiFetch(path, opts = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

// Returns a {fetch, abort} pair. Calling abort() cancels the in-flight request.
function abortableFetch(path, opts = {}) {
  const controller = new AbortController();
  const promise = apiFetch(path, { ...opts, signal: controller.signal });
  return { promise, abort: () => controller.abort() };
}

let _toastTimer;
function toast(msg, dur = 3000) {
  const el = qs('#toast');
  el.textContent = msg;
  el.hidden = false;
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => { el.hidden = true; }, dur);
}

function copyText(text) {
  navigator.clipboard.writeText(text).then(() => toast('Copied!')).catch(() => {});
}

function fmtCoord(v) { return v == null ? '—' : Number(v).toFixed(2); }
function fmtDist(v) {
  if (v == null) return '—';
  const n = Number(v);
  return n >= 10 ? n.toFixed(1) + ' ly' : n.toFixed(2) + ' ly';
}
function fmtNum(v) { return v == null ? '—' : Number(v).toLocaleString(); }

function scoreColor(s) {
  if (s >= 75) return '#22c55e';
  if (s >= 50) return '#d4a832';
  if (s >= 25) return '#f97316';
  return '#6b8599';
}

function ecoShort(eco) {
  const map = {
    agriculture: 'Agri', refinery: 'Ref', industrial: 'Ind',
    hightech: 'HiTec', 'high tech': 'HiTec', military: 'Mil',
    tourism: 'Tour', extraction: 'Ext', colony: 'Col',
  };
  if (!eco) return '—';
  return map[eco.toLowerCase()] || eco;
}

function starLabel(type, sub) {
  if (!type) return null;
  return sub != null ? `${type}${sub}` : type;
}

function popLabel(pop) {
  const n = Number(pop || 0);
  if (n === 0) return null;
  if (n >= 1e9) return (n / 1e9).toFixed(1) + 'B';
  if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M';
  if (n >= 1e3) return (n / 1e3).toFixed(0) + 'K';
  return n.toString();
}

function distFromSol(x, y, z) {
  if (x == null) return null;
  return Math.sqrt(x * x + y * y + z * z);
}

// ═══════════════════════════════════════════════════════════════ WATCHLIST

const Watchlist = {
  _key: 'ed_watchlist',
  _data: {},

  load() {
    try { this._data = JSON.parse(localStorage.getItem(this._key) || '{}'); }
    catch { this._data = {}; }
    this._updateBadge();
  },

  save() {
    localStorage.setItem(this._key, JSON.stringify(this._data));
    this._updateBadge();
  },

  has(id64) { return !!this._data[String(id64)]; },

  add(sys) {
    this._data[String(sys.id64)] = {
      id64: sys.id64, name: sys.name,
      x: sys.x ?? sys.coords?.x,
      y: sys.y ?? sys.coords?.y,
      z: sys.z ?? sys.coords?.z,
      economy: sys.primaryEconomy || sys.primary_economy,
      score: sys._rating?.score,
      savedAt: Date.now(),
    };
    this.save();
    toast(`★ ${sys.name} added to watchlist`);
  },

  remove(id64) {
    const name = this._data[String(id64)]?.name || 'System';
    delete this._data[String(id64)];
    this.save();
    toast(`Removed ${name} from watchlist`);
  },

  toggle(sys) {
    if (this.has(sys.id64)) { this.remove(sys.id64); return false; }
    else { this.add(sys); return true; }
  },

  getAll() { return Object.values(this._data).sort((a, b) => b.savedAt - a.savedAt); },
  count() { return Object.keys(this._data).length; },

  _updateBadge() {
    const n = this.count();
    const badge = qs('#watchlist-count-badge');
    badge.textContent = n;
    badge.hidden = n === 0;
  },
};
Watchlist.load();

// ═══════════════════════════════════════════════════════════════ NAVBAR

// Improvement #5: URL deep linking helpers
function _setUrlParam(key, value) {
  const url = new URL(window.location);
  if (value == null || value === '' || value === 'any') { url.searchParams.delete(key); }
  else { url.searchParams.set(key, value); }
  history.replaceState(null, '', url);
}
function _getUrlParam(key) {
  return new URL(window.location).searchParams.get(key);
}

(function initNav() {
  const btns = qsa('.nav-btn');
  const panels = qsa('.tab-panel');

  function activateTab(tabName) {
    btns.forEach(b => b.classList.toggle('active', b.dataset.tab === tabName));
    panels.forEach(p => p.classList.toggle('active', p.id === `tab-${tabName}`));
    if (tabName === 'watchlist') renderWatchlistTab();
    _setUrlParam('tab', tabName === 'local' ? null : tabName);
  }

  btns.forEach(btn => {
    btn.addEventListener('click', () => activateTab(btn.dataset.tab));
  });

  // Restore tab from URL on load
  const savedTab = _getUrlParam('tab');
  if (savedTab && qs(`#tab-${savedTab}`)) activateTab(savedTab);
})();

// ═══════════════════════════════════════════════════════════════ STATUS

(async function initStatus() {
  const dot  = qs('#status-dot');
  const text = qs('#status-text');
  try {
    const h = await apiFetch('/api/health');
    if (h.status === 'ok') {
      dot.className = 'status-dot ok';
      text.textContent = h.database === 'connected' ? 'Online' : 'DB Error';
    } else {
      dot.className = 'status-dot warn';
      text.textContent = 'Degraded';
    }
  } catch {
    dot.className = 'status-dot err';
    text.textContent = 'Offline';
  }
})();

// ═══════════════════════════════════════════════════════════════ AUTOCOMPLETE

function makeAutocomplete(inputEl, listEl, onSelect) {
  let debounce, highlighted = -1, items = [];

  inputEl.addEventListener('input', () => {
    clearTimeout(debounce);
    const q = inputEl.value.trim();
    if (q.length < 2) { listEl.hidden = true; items = []; return; }
    debounce = setTimeout(() => fetchSuggestions(q), 200);
  });

  inputEl.addEventListener('keydown', (e) => {
    if (listEl.hidden) return;
    if (e.key === 'ArrowDown') { e.preventDefault(); move(1); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); move(-1); }
    else if (e.key === 'Enter') {
      e.preventDefault();
      const item = items[highlighted] || items[0];
      if (item) pick(item);
    } else if (e.key === 'Escape') listEl.hidden = true;
  });

  document.addEventListener('click', (e) => {
    if (!inputEl.contains(e.target) && !listEl.contains(e.target)) listEl.hidden = true;
  });

  function move(dir) {
    highlighted = Math.max(-1, Math.min(items.length - 1, highlighted + dir));
    qsa('li', listEl).forEach((li, i) => li.classList.toggle('focused', i === highlighted));
  }

  async function fetchSuggestions(q) {
    try {
      const data = await apiFetch(`/api/local/autocomplete?q=${encodeURIComponent(q)}&limit=8`);
      items = data.results || [];
      listEl.innerHTML = '';
      if (!items.length) { listEl.hidden = true; return; }
      items.forEach((sys, i) => {
        const li = document.createElement('li');
        li.innerHTML = `${sys.name} <span class="sys-coords">${fmtCoord(sys.x)}, ${fmtCoord(sys.y)}, ${fmtCoord(sys.z)}</span>`;
        li.addEventListener('mouseenter', () => { highlighted = i; move(0); });
        li.addEventListener('click', () => pick(sys));
        listEl.appendChild(li);
      });
      highlighted = -1;
      listEl.hidden = false;
    } catch { listEl.hidden = true; }
  }

  function pick(sys) {
    inputEl.value = sys.name;
    listEl.hidden = true;
    highlighted = -1;
    onSelect(sys);
  }
}

// ═══════════════════════════════════════════════════════════════ SYSTEM MODAL

let _modalSys = null;  // currently open system data

async function openSystemModal(sys) {
  const modal = qs('#system-modal');
  const content = qs('#modal-content');

  // Show loading immediately, open modal
  content.innerHTML = `<div class="loading-state"><div class="spinner"></div>Loading system data…</div>`;
  modal.hidden = false;
  document.body.style.overflow = 'hidden';
  _modalSys = sys;

  // Fetch full system detail
  let full = sys;
  try {
    if (sys.id64) {
      const data = await apiFetch(`/api/system/${sys.id64}`);
      full = data.record || data.system || data;

      // The API returns flat snake_case fields at the top level (score, score_agriculture, etc.)
      // AND a nested _rating object. We normalise into a single _rating with both naming styles
      // so the modal always finds what it needs regardless of which keys are present.
      const existingRating = full._rating || {};
      full._rating = {
        // Flat top-level fields (authoritative from DB)
        score:           full.score           ?? existingRating.score,
        score_agriculture: full.score_agriculture ?? existingRating.score_agriculture ?? existingRating.scoreAgriculture,
        score_refinery:  full.score_refinery  ?? existingRating.score_refinery  ?? existingRating.scoreRefinery,
        score_industrial: full.score_industrial ?? existingRating.score_industrial ?? existingRating.scoreIndustrial,
        score_hightech:  full.score_hightech  ?? existingRating.score_hightech  ?? existingRating.scoreHightech,
        score_military:  full.score_military  ?? existingRating.score_military  ?? existingRating.scoreMilitary,
        score_tourism:   full.score_tourism   ?? existingRating.score_tourism   ?? existingRating.scoreTourism,
        economy_suggestion: full.economy_suggestion ?? existingRating.economy_suggestion ?? existingRating.economySuggestion,
        // camelCase aliases for modal rendering
        scoreAgriculture: full.score_agriculture ?? existingRating.scoreAgriculture,
        scoreRefinery:    full.score_refinery    ?? existingRating.scoreRefinery,
        scoreIndustrial:  full.score_industrial  ?? existingRating.scoreIndustrial,
        scoreHightech:    full.score_hightech    ?? existingRating.scoreHightech,
        scoreMilitary:    full.score_military    ?? existingRating.scoreMilitary,
        scoreTourism:     full.score_tourism     ?? existingRating.scoreTourism,
        economySuggestion: full.economy_suggestion ?? existingRating.economySuggestion,
        // Body counts
        elw_count:          full.elw_count          ?? existingRating.elw_count,
        ww_count:           full.ww_count            ?? existingRating.ww_count,
        ammonia_count:      full.ammonia_count       ?? existingRating.ammonia_count,
        gas_giant_count:    full.gas_giant_count     ?? existingRating.gas_giant_count,
        landable_count:     full.landable_count      ?? existingRating.landable_count,
        terraformable_count: full.terraformable_count ?? existingRating.terraformable_count,
        bio_signal_total:   full.bio_signal_total    ?? existingRating.bio_signal_total,
        geo_signal_total:   full.geo_signal_total    ?? existingRating.geo_signal_total,
        neutron_count:      full.neutron_count       ?? existingRating.neutron_count,
        black_hole_count:   full.black_hole_count    ?? existingRating.black_hole_count,
        white_dwarf_count:  full.white_dwarf_count   ?? existingRating.white_dwarf_count,
      };
    }
  } catch (e) {
    // Use the card data we already have (don't blank the modal on network error)
    full = sys;
  }

  _modalSys = full;
  try {
    content.innerHTML = buildModalHTML(full);
    attachModalEvents(full);
  } catch (err) {
    console.error('Modal render error:', err);
    content.innerHTML = `<div class="error-state">⚠ Failed to render system detail: ${err.message}</div>`;
  }
}

// Helper: return value only if it's a non-null, non-"None" string or non-zero number
function val(v) { return (v != null && v !== 'None' && v !== '' && v !== 0) ? v : null; }

function buildModalHTML(sys) {
  const r = sys._rating || {};
  const coords = sys.coords || { x: sys.x, y: sys.y, z: sys.z };
  // Handle both camelCase (from search results) and snake_case (from /api/system/)
  const eco  = val(sys.primaryEconomy)   || val(sys.primary_economy)   || '—';
  const eco2 = val(sys.secondaryEconomy) || val(sys.secondary_economy) || null;
  const security   = val(sys.security);
  const allegiance = val(sys.allegiance);
  const government = val(sys.government);
  const mainStar   = val(sys.main_star_type);
  const edsm  = `https://www.edsm.net/en/system/id/${sys.id64}/name/${encodeURIComponent(sys.name || '')}`;
  const inara = `https://inara.cz/elite/starsystem/?search=${encodeURIComponent(sys.name || '')}`;
  const isSaved = Watchlist.has(sys.id64);
  const dSol = distFromSol(coords.x, coords.y, coords.z);

  const scoreItems = [
    ['Overall', r.score],
    ['Agriculture', r.scoreAgriculture ?? r.score_agriculture],
    ['Refinery',    r.scoreRefinery    ?? r.score_refinery],
    ['Industrial',  r.scoreIndustrial  ?? r.score_industrial],
    ['High Tech',   r.scoreHightech    ?? r.score_hightech],
    ['Military',    r.scoreMilitary    ?? r.score_military],
    ['Tourism',     r.scoreTourism     ?? r.score_tourism],
  ].filter(([, v]) => v != null);

  // Bodies list — built via DOM to avoid nested template literal issues
  const bodies = sys.bodies || [];
  console.log('[ED Finder] bodies array:', bodies.length, 'entries', bodies[0]);
  let bodiesHTML = '';
  if (bodies.length) {
    const rows = bodies.map(b => {
      const flags = [];
      if (b.is_earth_like)    flags.push('🌍 ELW');
      if (b.is_water_world)   flags.push('💧 WW');
      if (b.is_ammonia_world) flags.push('🟣 AW');
      if (b.is_landable)      flags.push('⬇ Land');
      if (b.is_terraformable) flags.push('♻ Terr');
      if (b.bio_signal_count > 0) flags.push('🧬 ×' + b.bio_signal_count);
      if (b.geo_signal_count > 0) flags.push('🌋 ×' + b.geo_signal_count);
      if (b.spectral_class)   flags.push(b.spectral_class + (b.is_scoopable ? ' ⛽' : ''));
      const distStr = b.distance_from_star != null ? Number(b.distance_from_star).toFixed(0) + ' ls' : '';
      return '<div class="body-row">'
        + '<span class="body-row-name">' + (b.name || '—') + '</span>'
        + '<span class="body-row-type">' + (b.subtype || b.body_type || '—') + '</span>'
        + (flags.length ? '<span style="font-size:0.7rem;color:var(--text-dim)">' + flags.join(' · ') + '</span>' : '')
        + (distStr ? '<span class="body-row-dist">' + distStr + '</span>' : '')
        + '</div>';
    });
    console.log('[ED Finder] body rows generated:', rows.length, 'first row preview:', rows[0]?.substring(0, 80));
    bodiesHTML = '<div class="modal-section"><div class="modal-section-title">Bodies (' + bodies.length + ')</div><div class="body-list">' + rows.join('') + '</div></div>';
  }

  // Stations list
  const stations = sys.stations || [];
  let stationsHTML = '';
  if (stations.length) {
    const rows = stations.map(s => {
      const svcTags = '<span class="svc-tag ' + (s.landing_pad_size === 'L' ? 'active' : '') + '">' + (s.landing_pad_size || '?') + ' pad</span>'
        + (s.has_market     ? '<span class="svc-tag active">Market</span>' : '')
        + (s.has_shipyard   ? '<span class="svc-tag active">Shipyard</span>' : '')
        + (s.has_outfitting ? '<span class="svc-tag active">Outfitting</span>' : '');
      const distStr = s.distance_from_star != null ? Number(s.distance_from_star).toFixed(0) + ' ls' : '';
      return '<div class="station-row">'
        + '<span class="station-row-name">' + (s.name || '—') + '</span>'
        + '<div class="station-services">' + svcTags + '</div>'
        + (distStr ? '<span class="body-row-dist">' + distStr + '</span>' : '')
        + '</div>';
    });
    stationsHTML = '<div class="modal-section"><div class="modal-section-title">Stations (' + stations.length + ')</div><div class="station-list">' + rows.join('') + '</div></div>';
  }

  return `
    <div class="modal-system-name">
      ${sys.name || 'Unknown System'}
      <button class="copy-btn" data-copy="${sys.name}" title="Copy name">⎘</button>
    </div>
    <div class="modal-system-id">
      ID64: ${sys.id64 || '—'}
      ${dSol != null ? ` · ${fmtDist(dSol)} from Sol` : ''}
    </div>

    <div class="modal-section">
      <div class="modal-section-title">System Info</div>
      <div class="modal-grid">
        <div class="modal-field">
          <span class="modal-field-label">Coordinates</span>
          <span class="modal-field-value blue" style="font-family:var(--font-mono);font-size:0.78rem">
            ${fmtCoord(coords.x)}, ${fmtCoord(coords.y)}, ${fmtCoord(coords.z)}
            <button class="copy-btn" data-copy="${fmtCoord(coords.x)}, ${fmtCoord(coords.y)}, ${fmtCoord(coords.z)}" title="Copy coords">⎘</button>
          </span>
        </div>
        ${sys.distance != null ? `
        <div class="modal-field">
          <span class="modal-field-label">Distance (search ref)</span>
          <span class="modal-field-value accent">${fmtDist(sys.distance)}</span>
        </div>` : ''}
        <div class="modal-field">
          <span class="modal-field-label">Primary Economy</span>
          <span class="modal-field-value gold">${eco}</span>
        </div>
        ${eco2 ? `
        <div class="modal-field">
          <span class="modal-field-label">Secondary Economy</span>
          <span class="modal-field-value">${eco2}</span>
        </div>` : ''}
        <div class="modal-field">
          <span class="modal-field-label">Population</span>
          <span class="modal-field-value ${Number(sys.population) === 0 ? 'green' : ''}">
            ${Number(sys.population) === 0 ? 'Uncolonised' : fmtNum(sys.population)}
          </span>
        </div>
        ${security ? `<div class="modal-field"><span class="modal-field-label">Security</span><span class="modal-field-value">${security}</span></div>` : ''}
        ${allegiance ? `<div class="modal-field"><span class="modal-field-label">Allegiance</span><span class="modal-field-value">${allegiance}</span></div>` : ''}
        ${government ? `<div class="modal-field"><span class="modal-field-label">Government</span><span class="modal-field-value">${government}</span></div>` : ''}
        ${mainStar ? `<div class="modal-field"><span class="modal-field-label">Main Star</span><span class="modal-field-value" style="color:var(--purple)">${starLabel(mainStar, sys.main_star_subtype)}</span></div>` : ''}
        ${(r.economySuggestion || r.economy_suggestion) ? `
        <div class="modal-field">
          <span class="modal-field-label">Suggested Economy</span>
          <span class="modal-field-value accent">${r.economySuggestion || r.economy_suggestion}</span>
        </div>` : ''}
      </div>
    </div>

    ${scoreItems.length ? `
    <div class="modal-section">
      <div class="modal-section-title">Suitability Scores</div>
      <div class="modal-score-grid">
        ${scoreItems.map(([label, val]) => {
          const pct = Math.round(val);
          return `
          <div class="modal-score-item">
            <div class="modal-score-label">${label}</div>
            <div class="modal-score-value" style="color:${scoreColor(pct)}">${pct}</div>
            <div class="modal-score-bar"><div class="modal-score-bar-fill" style="width:${pct}%;background:${scoreColor(pct)}"></div></div>
          </div>`;
        }).join('')}
      </div>
    </div>` : ''}

    ${bodiesHTML}
    ${stationsHTML}

    <div class="modal-section">
      <div class="modal-section-title">Actions</div>
      <div style="display:flex;gap:0.75rem;flex-wrap:wrap;align-items:center">
        <button class="watchlist-add-btn ${isSaved ? 'saved' : ''}" id="modal-watchlist-btn" data-id64="${sys.id64}">
          ${isSaved ? '★ Saved — click to remove' : '☆ Save to Watchlist'}
        </button>
        <a href="${edsm}" target="_blank" rel="noopener" class="modal-edsm-link">↗ EDSM</a>
        <a href="${inara}" target="_blank" rel="noopener" class="modal-edsm-link">↗ Inara</a>
      </div>
    </div>
  `;
}

function attachModalEvents(sys) {
  // Copy buttons
  qsa('.copy-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      copyText(btn.dataset.copy);
    });
  });

  // Watchlist toggle
  const wlBtn = qs('#modal-watchlist-btn');
  if (wlBtn) {
    wlBtn.addEventListener('click', () => {
      const saved = Watchlist.toggle(sys);
      wlBtn.classList.toggle('saved', saved);
      wlBtn.textContent = saved ? '★ Saved — click to remove' : '☆ Save to Watchlist';
      if (qs('#tab-watchlist.active')) renderWatchlistTab();
    });
  }
}

(function initModal() {
  const modal = qs('#system-modal');
  qs('#modal-close-btn').addEventListener('click', closeModal);
  modal.addEventListener('click', (e) => { if (e.target === modal) closeModal(); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !modal.hidden) closeModal(); });

  function closeModal() {
    modal.hidden = true;
    document.body.style.overflow = '';
    _modalSys = null;
  }
})();

// ═══════════════════════════════════════════════════════════════ WATCHLIST TAB

// Improvement #8: Watchlist pagination
const WL_PAGE_SIZE = 20;
let _wlPage = 1;

function renderWatchlistTab(page) {
  if (page !== undefined) _wlPage = page;
  const allItems  = Watchlist.getAll();
  const resultsEl = qs('#watchlist-results');
  const headerEl  = qs('#watchlist-results-header');
  const countEl   = qs('#watchlist-results-count');
  const hint      = qs('#watchlist-empty-hint');
  const clearBtn  = qs('#watchlist-clear-btn');

  if (!allItems.length) {
    resultsEl.innerHTML = `<div class="empty-state"><div class="empty-icon">★</div><div class="empty-title">Your watchlist is empty</div><div class="empty-sub">Save systems from any search result</div></div>`;
    headerEl.hidden = true;
    hint.hidden = false;
    clearBtn.hidden = true;
    return;
  }

  const total = allItems.length;
  const start = (_wlPage - 1) * WL_PAGE_SIZE;
  const items = allItems.slice(start, start + WL_PAGE_SIZE);

  hint.hidden = true;
  clearBtn.hidden = false;
  countEl.innerHTML = `<strong>${total}</strong> saved ${total === 1 ? 'system' : 'systems'} — showing ${start + 1}–${Math.min(start + WL_PAGE_SIZE, total)}`;
  headerEl.hidden = false;
  resultsEl.innerHTML = '';

  items.forEach((entry, i) => {
    const fakeSys = {
      id64: entry.id64,
      name: entry.name,
      x: entry.x, y: entry.y, z: entry.z,
      coords: { x: entry.x, y: entry.y, z: entry.z },
      primaryEconomy: entry.economy,
      population: 0,
      _rating: { score: entry.score },
    };
    resultsEl.appendChild(buildSystemCard(fakeSys, start + i + 1));
  });

  // Render pagination below results
  let paginEl = qs('#watchlist-pagination');
  if (!paginEl) {
    paginEl = document.createElement('div');
    paginEl.id = 'watchlist-pagination';
    paginEl.className = 'pagination';
    headerEl.appendChild(paginEl);
  }
  buildPagination(paginEl, total, WL_PAGE_SIZE, _wlPage, (p) => {
    renderWatchlistTab(p);
    resultsEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
}

(function initWatchlistClear() {
  qs('#watchlist-clear-btn').addEventListener('click', () => {
    if (!confirm('Clear all saved systems?')) return;
    Watchlist._data = {};
    Watchlist.save();
    renderWatchlistTab();
  });
})();

// ═══════════════════════════════════════════════════════════════ PAGINATION

function buildPagination(container, total, pageSize, currentPage, onPage) {
  container.innerHTML = '';
  const totalPages = Math.ceil(total / pageSize);
  if (totalPages <= 1) return;

  const pages = [];
  if (totalPages <= 7) {
    for (let i = 1; i <= totalPages; i++) pages.push(i);
  } else {
    pages.push(1);
    if (currentPage > 3) pages.push('…');
    for (let p = Math.max(2, currentPage - 1); p <= Math.min(totalPages - 1, currentPage + 1); p++) pages.push(p);
    if (currentPage < totalPages - 2) pages.push('…');
    pages.push(totalPages);
  }

  pages.forEach(p => {
    const btn = document.createElement('button');
    btn.className = 'page-btn' + (p === currentPage ? ' active' : '');
    btn.textContent = p;
    if (p === '…') { btn.disabled = true; }
    else { btn.addEventListener('click', () => onPage(p)); }
    container.appendChild(btn);
  });
}

// ═══════════════════════════════════════════════════════════════ SYSTEM CARD

function buildSystemCard(sys, rank) {
  const r = sys._rating || {};
  const score = r.score != null ? Math.round(r.score) : null;
  const dist = sys.distance != null ? fmtDist(sys.distance) : null;
  const eco = sys.primaryEconomy || sys.primary_economy;
  const star = starLabel(sys.main_star_type, sys.main_star_subtype);
  const pop = Number(sys.population || 0);
  const isCol = sys.is_colonised || sys.is_being_colonised;
  const isSaved = Watchlist.has(sys.id64);

  const bodies = [];
  if (r.elw_count > 0)           bodies.push(`🌍 ×${r.elw_count}`);
  if (r.ww_count > 0)            bodies.push(`💧 ×${r.ww_count}`);
  if (r.ammonia_count > 0)       bodies.push(`🟣 ×${r.ammonia_count}`);
  if (r.gas_giant_count > 0)     bodies.push(`🔵 ×${r.gas_giant_count}`);
  if (r.neutron_count > 0)       bodies.push(`💫 ×${r.neutron_count}`);
  if (r.black_hole_count > 0)    bodies.push(`⚫ ×${r.black_hole_count}`);
  if (r.bio_signal_total > 0)    bodies.push(`🧬 ×${r.bio_signal_total}`);
  if (r.geo_signal_total > 0)    bodies.push(`🌋 ×${r.geo_signal_total}`);
  if (r.terraformable_count > 0) bodies.push(`♻ ×${r.terraformable_count}`);

  const ecoScores = [
    ['Agri', r.scoreAgriculture ?? r.score_agriculture],
    ['Ref',  r.scoreRefinery   ?? r.score_refinery],
    ['Ind',  r.scoreIndustrial ?? r.score_industrial],
    ['HiTec',r.scoreHightech   ?? r.score_hightech],
    ['Mil',  r.scoreMilitary   ?? r.score_military],
    ['Tour', r.scoreTourism    ?? r.score_tourism],
  ].filter(([, v]) => v != null);

  const card = document.createElement('article');
  card.className = 'system-card';
  card.innerHTML = `
    <div class="card-header">
      <span class="card-rank">#${rank}</span>
      <span class="card-name">${sys.name || 'Unknown'}</span>
      ${score != null ? `<span class="card-score">★ ${score}</span>` : ''}
      ${isSaved ? `<span title="Saved" style="color:var(--gold);font-size:0.8rem;margin-left:0.25rem">★</span>` : ''}
    </div>
    <div class="card-meta">
      ${dist ? `<span class="meta-tag distance">⊕ ${dist}</span>` : ''}
      ${eco && eco !== 'None' ? `<span class="meta-tag economy">${eco}</span>` : ''}
      ${pop === 0 ? `<span class="meta-tag pop-zero">Uncolonised</span>` : (isCol ? `<span class="meta-tag pop-col">Colonised</span>` : (pop > 0 ? `<span class="meta-tag">${popLabel(pop)}</span>` : ''))}
      ${star ? `<span class="meta-tag star">${star}</span>` : ''}
    </div>
    ${bodies.length ? `<div class="card-bodies">${bodies.map(b => `<span class="body-tag">${b}</span>`).join(' · ')}</div>` : ''}
    ${ecoScores.length ? `
    <div class="score-bars">
      ${ecoScores.map(([label, val]) => `
        <div class="score-bar-item">
          <div class="score-bar-track"><div class="score-bar-fill" style="width:${val}%;background:${scoreColor(val)}"></div></div>
          <span class="score-bar-label">${label}</span>
        </div>`).join('')}
    </div>` : ''}
  `;
  card.addEventListener('click', () => openSystemModal(sys));
  return card;
}

// ═══════════════════════════════════════════════════════════════ LOCAL SEARCH

(function initLocalSearch() {
  const refInput    = qs('#local-ref-input');
  const refList     = qs('#local-ref-suggestions');
  const distSlider  = qs('#local-dist-slider');
  const distVal     = qs('#local-dist-val');
  const galaxyWide  = qs('#local-galaxy-wide');
  const ratingSlider = qs('#local-rating-slider');
  const ratingVal   = qs('#local-rating-val');
  const coordDisp   = qs('#local-coords-display');
  const xSpan       = qs('#local-coord-x');
  const ySpan       = qs('#local-coord-y');
  const zSpan       = qs('#local-coord-z');
  const searchBtn   = qs('#local-search-btn');
  const resultsEl   = qs('#local-results');
  const headerEl    = qs('#local-results-header');
  const countEl     = qs('#local-results-count');
  const paginEl     = qs('#local-pagination');

  let refCoords = null, currentPage = 1, lastParams = null;
  let _activeSearch = null;  // Improvement #4: track in-flight request for cancellation
  const PAGE_SIZE = 20;

  distSlider.addEventListener('input', () => { distVal.textContent = `${distSlider.value} ly`; });
  ratingSlider.addEventListener('input', () => { ratingVal.textContent = ratingSlider.value; });

  // Disable distance slider when galaxy-wide is on
  galaxyWide.addEventListener('change', () => {
    distSlider.disabled = galaxyWide.checked;
    distVal.style.opacity = galaxyWide.checked ? '0.4' : '1';
  });

  makeAutocomplete(refInput, refList, (sys) => {
    refCoords = { x: sys.x, y: sys.y, z: sys.z };
    xSpan.textContent = `X: ${fmtCoord(sys.x)}`;
    ySpan.textContent = `Y: ${fmtCoord(sys.y)}`;
    zSpan.textContent = `Z: ${fmtCoord(sys.z)}`;
    coordDisp.hidden = false;
    // Improvement #6: broadcast reference coords so cluster search can use them
    document.dispatchEvent(new CustomEvent('ed:refcoords', { detail: refCoords }));
  });

  searchBtn.addEventListener('click', () => { currentPage = 1; doSearch(); });

  // Allow Enter key in the reference input to trigger search
  refInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && refCoords) { currentPage = 1; doSearch(); }
  });

  function getParams() {
    const pop  = document.querySelector('input[name="local-pop"]:checked')?.value;
    const sort = document.querySelector('input[name="local-sort"]:checked')?.value;
    const eco  = qs('#local-economy').value;
    return {
      reference_coords: refCoords || { x: 0, y: 0, z: 0 },
      filters: {
        distance: { min: 0, max: Number(distSlider.value) },
        population: pop === 'zero' ? { comparison: 'equal', value: 0 } : {},
        economy: eco === 'any' ? 'any' : eco,
      },
      body_filters: {
        elw:      { min: Number(qs('#bf-elw').value) },
        ww:       { min: Number(qs('#bf-ww').value) },
        ammonia:  { min: Number(qs('#bf-ammonia').value) },
        gasGiant: { min: Number(qs('#bf-gasgiant').value) },
        neutron:  { min: Number(qs('#bf-neutron').value) },
      },
      require_bio:   qs('#bf-bio').checked,
      require_geo:   qs('#bf-geo').checked,
      require_terra: qs('#bf-terra').checked,
      min_rating:    Number(ratingSlider.value),
      sort_by:       sort || 'rating',
      size:          PAGE_SIZE,
      from:          (currentPage - 1) * PAGE_SIZE,
      galaxy_wide:   galaxyWide.checked,
    };
  }

  async function doSearch() {
    if (!refCoords) { toast('Please select a reference system first'); refInput.focus(); return; }
    // Improvement #4: cancel any previous in-flight search before starting a new one
    if (_activeSearch) { _activeSearch.abort(); _activeSearch = null; }
    lastParams = getParams();
    setLoading(true);
    const req = abortableFetch('/api/local/search', { method: 'POST', body: JSON.stringify(lastParams) });
    _activeSearch = req;
    try {
      const data = await req.promise;
      renderResults(data.results || [], data.total || 0);
    } catch (e) {
      if (e.name === 'AbortError') return;  // Silently ignore cancelled requests
      showError(e.message);
    } finally {
      _activeSearch = null;
      setLoading(false);
    }
  }

  function setLoading(on) {
    searchBtn.disabled = on;
    searchBtn.classList.toggle('loading', on);
    if (on) { resultsEl.innerHTML = `<div class="loading-state"><div class="spinner"></div>Searching…</div>`; headerEl.hidden = true; }
  }

  function showError(msg) { resultsEl.innerHTML = `<div class="error-state">⚠ Search failed: ${msg}</div>`; }

  function renderResults(results, total) {
    resultsEl.innerHTML = '';
    if (!results.length) {
      resultsEl.innerHTML = `<div class="empty-state"><div class="empty-icon">◉</div><div class="empty-title">No systems found</div><div class="empty-sub">Try increasing the search radius or relaxing filters</div></div>`;
      headerEl.hidden = true;
      return;
    }
    countEl.innerHTML = `Found <strong>${fmtNum(total)}</strong> systems — showing ${(currentPage - 1) * PAGE_SIZE + 1}–${Math.min(currentPage * PAGE_SIZE, total)}`;
    headerEl.hidden = false;
    results.forEach((sys, i) => resultsEl.appendChild(buildSystemCard(sys, (currentPage - 1) * PAGE_SIZE + i + 1)));
    buildPagination(paginEl, total, PAGE_SIZE, currentPage, (p) => {
      currentPage = p;
      lastParams.from = (p - 1) * PAGE_SIZE;
      apiFetch('/api/local/search', { method: 'POST', body: JSON.stringify(lastParams) })
        .then(d => renderResults(d.results || [], d.total || 0))
        .catch(e => showError(e.message));
      resultsEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  }
})();

// ═══════════════════════════════════════════════════════════════ GALAXY SEARCH

(function initGalaxySearch() {
  const ecoSel      = qs('#galaxy-economy');
  const scoreSlider = qs('#galaxy-score-slider');
  const scoreVal    = qs('#galaxy-score-val');
  const searchBtn   = qs('#galaxy-search-btn');
  const resultsEl   = qs('#galaxy-results');
  const headerEl    = qs('#galaxy-results-header');
  const countEl     = qs('#galaxy-results-count');
  const paginEl     = qs('#galaxy-pagination');

  let currentPage = 1, lastParams = null;
  const PAGE_SIZE = 20;

  scoreSlider.addEventListener('input', () => { scoreVal.textContent = scoreSlider.value; });
  searchBtn.addEventListener('click', () => { currentPage = 1; doSearch(); });

  function getParams() {
    return { economy: ecoSel.value, min_score: Number(scoreSlider.value), limit: PAGE_SIZE, offset: (currentPage - 1) * PAGE_SIZE };
  }

  async function doSearch() {
    lastParams = getParams();
    setLoading(true);
    try {
      const data = await apiFetch('/api/search/galaxy', { method: 'POST', body: JSON.stringify(lastParams) });
      renderResults(data.results || [], data.total || 0);
    } catch (e) { showError(e.message); }
    finally { setLoading(false); }
  }

  function setLoading(on) {
    searchBtn.disabled = on;
    searchBtn.classList.toggle('loading', on);
    if (on) { resultsEl.innerHTML = `<div class="loading-state"><div class="spinner"></div>Searching galaxy…</div>`; headerEl.hidden = true; }
  }

  function showError(msg) { resultsEl.innerHTML = `<div class="error-state">⚠ Search failed: ${msg}</div>`; }

  function renderResults(results, total) {
    resultsEl.innerHTML = '';
    if (!results.length) {
      resultsEl.innerHTML = `<div class="empty-state"><div class="empty-icon">✦</div><div class="empty-title">No systems found</div><div class="empty-sub">Try lowering the minimum score</div></div>`;
      headerEl.hidden = true; return;
    }
    countEl.innerHTML = `Found <strong>${fmtNum(total)}</strong> systems`;
    headerEl.hidden = false;
    results.forEach((sys, i) => resultsEl.appendChild(buildSystemCard(sys, (currentPage - 1) * PAGE_SIZE + i + 1)));
    buildPagination(paginEl, total, PAGE_SIZE, currentPage, (p) => {
      currentPage = p;
      lastParams.offset = (p - 1) * PAGE_SIZE;
      apiFetch('/api/search/galaxy', { method: 'POST', body: JSON.stringify(lastParams) })
        .then(d => renderResults(d.results || [], d.total || 0))
        .catch(e => showError(e.message));
      resultsEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  }
})();

// ═══════════════════════════════════════════════════════════════ CLUSTER SEARCH

(function initClusterSearch() {
  const reqs      = qs('#cluster-requirements');
  const addBtn    = qs('#add-economy-btn');
  const searchBtn = qs('#cluster-search-btn');
  const limitSel  = qs('#cluster-limit');
  const resultsEl = qs('#cluster-results');
  const headerEl  = qs('#cluster-results-header');
  const countEl   = qs('#cluster-results-count');

  const ECONOMIES = ['Agriculture', 'Refinery', 'Industrial', 'HighTech', 'Military', 'Tourism'];

  function addRow(eco = 'Agriculture', minCount = 1, minScore = 30) {
    const row = document.createElement('div');
    row.className = 'economy-req-row';
    row.innerHTML = `
      <select class="req-eco">${ECONOMIES.map(e => `<option value="${e}" ${e === eco ? 'selected' : ''}>${e}</option>`).join('')}</select>
      <div style="text-align:center"><div class="req-label">Min count</div><input type="number" class="req-count" min="1" max="20" value="${minCount}" style="width:50px;text-align:center"></div>
      <div style="text-align:center"><div class="req-label">Min score</div><input type="number" class="req-score" min="0" max="100" step="5" value="${minScore}" style="width:50px;text-align:center"></div>
      <button class="remove-btn" title="Remove">✕</button>
    `;
    row.querySelector('.remove-btn').addEventListener('click', () => row.remove());
    reqs.appendChild(row);
  }

  addRow('HighTech', 1, 40);
  addRow('Agriculture', 2, 30);

  addBtn.addEventListener('click', () => {
    if (reqs.children.length >= 6) { toast('Maximum 6 economy requirements'); return; }
    addRow();
  });

  searchBtn.addEventListener('click', doSearch);

  // Improvement #6: cluster search sends reference coords for distance-sorted results
  // The reference coords come from the local search reference system (shared state)
  let _clusterRefCoords = null;

  // Listen for local search reference system selection to share coords with cluster search
  document.addEventListener('ed:refcoords', (e) => {
    _clusterRefCoords = e.detail;
  });

  async function doSearch() {
    const requirements = qsa('.economy-req-row', reqs).map(row => ({
      economy:   row.querySelector('.req-eco').value,
      min_count: Number(row.querySelector('.req-count').value),
      min_score: Number(row.querySelector('.req-score').value),
    }));
    if (!requirements.length) { toast('Add at least one economy requirement'); return; }

    const payload = {
      requirements,
      limit: Number(limitSel.value),
      // Improvement #6: include reference coords if available for distance sorting
      reference_coords: _clusterRefCoords || null,
    };

    setLoading(true);
    try {
      const data = await apiFetch('/api/search/cluster', { method: 'POST', body: JSON.stringify(payload) });
      renderResults(data.clusters || data.results || [], (data.clusters || data.results || []).length);
    } catch (e) { showError(e.message); }
    finally { setLoading(false); }
  }

  function setLoading(on) {
    searchBtn.disabled = on;
    searchBtn.classList.toggle('loading', on);
    if (on) { resultsEl.innerHTML = `<div class="loading-state"><div class="spinner"></div>Scanning 73M cluster anchors…</div>`; headerEl.hidden = true; }
  }

  function showError(msg) { resultsEl.innerHTML = `<div class="error-state">⚠ Search failed: ${msg}</div>`; }

  function renderResults(results, total) {
    resultsEl.innerHTML = '';
    if (!results.length) {
      resultsEl.innerHTML = `<div class="empty-state"><div class="empty-icon">⬡</div><div class="empty-title">No clusters found</div><div class="empty-sub">Try relaxing count or score requirements</div></div>`;
      headerEl.hidden = true; return;
    }
    countEl.innerHTML = `Found <strong>${fmtNum(total)}</strong> matching clusters`;
    headerEl.hidden = false;
    results.forEach((cluster, i) => resultsEl.appendChild(buildClusterCard(cluster, i + 1)));
  }

  function buildClusterCard(c, rank) {
    // Support both old (flat) and new (economy_breakdown array) API response formats
    let ecos = [];
    if (Array.isArray(c.economy_breakdown)) {
      // New format from local_search.py v3.0
      ecos = c.economy_breakdown.map(e => [e.economy, e.count, e.best_score]).filter(([, count]) => count > 0);
    } else {
      // Legacy flat format
      ecos = [
        ['Agriculture', c.agriculture_count, c.agriculture_best],
        ['Refinery',    c.refinery_count,    c.refinery_best],
        ['Industrial',  c.industrial_count,  c.industrial_best],
        ['HighTech',    c.hightech_count,    c.hightech_best],
        ['Military',    c.military_count,    c.military_best],
        ['Tourism',     c.tourism_count,     c.tourism_best],
      ].filter(([, count]) => count > 0);
    }

    const coverageScore = c.total_best_score != null ? Math.round(c.total_best_score) : (c.coverage_score != null ? Math.round(c.coverage_score) : null);
    const anchorName = c.anchor_name || c.name || 'Unknown';
    const coords = c.anchor_coords || {};
    const cx = coords.x ?? c.x;
    const cy = coords.y ?? c.y;
    const cz = coords.z ?? c.z;
    const dSol = distFromSol(cx, cy, cz);
    // Improvement #6: show distance from reference if available
    const dRef = c.distance_ly != null ? c.distance_ly : null;

    const card = document.createElement('article');
    card.className = 'cluster-card';
    card.innerHTML = `
      <div class="cluster-header">
        <span class="card-rank">#${rank}</span>
        <span class="cluster-name">${anchorName}</span>
        ${coverageScore != null ? `<span class="cluster-score">⧡ ${coverageScore}</span>` : ''}
      </div>
      <div class="card-meta" style="margin-bottom:0.6rem">
        ${dRef != null ? `<span class="meta-tag distance">⊕ ${fmtDist(dRef)} from ref</span>` : (dSol != null ? `<span class="meta-tag distance">⊕ ${fmtDist(dSol)} from Sol</span>` : '')}
        ${c.economies_satisfied > 0 ? `<span class="meta-tag">${c.economies_satisfied} econ types</span>` : (c.economy_diversity ? `<span class="meta-tag">${c.economy_diversity} econ types</span>` : '')}
      </div>
      <div class="cluster-economies">
        ${ecos.map(([eco, count, best]) => {
          const cls = best >= 60 ? 'strong' : best >= 35 ? 'medium' : 'weak';
          return `<span class="eco-chip ${cls}">${ecoShort(eco)} ×${count}${best != null ? ` ★${Math.round(best)}` : ''}</span>`;
        }).join('')}
      </div>
    `;
    card.addEventListener('click', () => {
      openSystemModal({
        name: anchorName,
        id64: c.anchor_id64 || c.system_id64,
        x: cx, y: cy, z: cz,
        coords: { x: cx, y: cy, z: cz },
        population: 0,
        _rating: { score: coverageScore, economySuggestion: null },
      });
    });
    return card;
  }
})();

// ═══════════════════════════════════════════════════════════ LIVE EDDN FEED
// Improvement #9: Real-time EDDN event feed via Server-Sent Events
// Shows live system/body updates as they arrive from the EDDN network.

(function initLiveFeed() {
  const feedEl   = qs('#live-feed-list');
  const countEl  = qs('#live-feed-count');
  const dotEl    = qs('#live-feed-dot');
  const toggleEl = qs('#live-feed-toggle');

  if (!feedEl) return;  // Element not present in this build of index.html

  const MAX_EVENTS = 50;
  let eventCount = 0;
  let es = null;
  let paused = false;

  function fmtRelTime(isoStr) {
    if (!isoStr) return '';
    const diff = Math.round((Date.now() - new Date(isoStr)) / 1000);
    if (diff < 60)  return `${diff}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    return `${Math.floor(diff / 3600)}h ago`;
  }

  function addEvent(ev) {
    if (paused) return;
    eventCount++;
    if (countEl) countEl.textContent = eventCount;

    const item = document.createElement('li');
    item.className = 'feed-item';
    item.innerHTML = `
      <span class="feed-type feed-type-${(ev.type || 'update').toLowerCase()}">${ev.type || 'update'}</span>
      <span class="feed-name" title="${ev.system_name || ''}">${ev.system_name || 'Unknown'}</span>
      <span class="feed-time">${fmtRelTime(ev.timestamp)}</span>
    `;
    item.addEventListener('click', () => {
      if (ev.id64) openSystemModal({ id64: ev.id64, name: ev.system_name, coords: {}, _rating: {} });
    });

    feedEl.prepend(item);

    // Cap list length
    while (feedEl.children.length > MAX_EVENTS) {
      feedEl.removeChild(feedEl.lastChild);
    }

    // Flash the live dot
    if (dotEl) {
      dotEl.classList.add('pulse');
      setTimeout(() => dotEl.classList.remove('pulse'), 600);
    }
  }

  // Load recent events on startup
  apiFetch('/api/events/recent?limit=20')
    .then(data => (data.events || []).reverse().forEach(addEvent))
    .catch(() => {});  // Silently ignore if endpoint not yet deployed

  // Connect SSE stream
  function connect() {
    if (es) { es.close(); es = null; }
    es = new EventSource('/api/events/live');
    es.onmessage = (e) => {
      try { addEvent(JSON.parse(e.data)); } catch (_) {}
    };
    es.onerror = () => {
      // Reconnect after 10s on error
      es.close();
      es = null;
      setTimeout(connect, 10000);
    };
  }

  connect();

  // Pause/resume toggle
  if (toggleEl) {
    toggleEl.addEventListener('click', () => {
      paused = !paused;
      toggleEl.textContent = paused ? 'Resume' : 'Pause';
      toggleEl.classList.toggle('paused', paused);
    });
  }
})();
