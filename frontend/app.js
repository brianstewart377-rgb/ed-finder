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
  if (!navigator.clipboard) {
    toast('Copy not available (needs HTTPS)', 'warn');
    return;
  }
  navigator.clipboard.writeText(text).then(() => toast('Copied!')).catch(() => {
    toast('Copy failed — check browser permissions', 'warn');
  });
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
    // Redraw map when map tabs are activated so data is always fresh
    if (tabName === 'map')    { setTimeout(() => window.EDMap?.draw2D(), 50); }
    if (tabName === 'map3d')  { setTimeout(() => window.EDMap?.draw3D(), 50); }
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

  // Bodies list — sort: stars first, then planets/moons by distance from star (#11)
  const bodies = [...(sys.bodies || [])].sort((a, b) => {
    const rank = v => v.body_type === 'Star' ? 0 : v.body_type === 'Planet' ? 1 : 2;
    if (rank(a) !== rank(b)) return rank(a) - rank(b);
    return (a.distance_from_star ?? Infinity) - (b.distance_from_star ?? Infinity);
  });
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
      <div class="score-chart">
        ${scoreItems.map(([label, val]) => {
          const pct = Math.round(val);
          const band = pct >= 80 ? 'Excellent' : pct >= 65 ? 'Good' : pct >= 45 ? 'Average' : 'Poor';
          return `
          <div class="score-chart-row">
            <div class="score-chart-label">${label}</div>
            <div class="score-chart-bar-wrap"><div class="score-chart-bar" style="width:${pct}%;background:${scoreColor(pct)}"></div></div>
            <div class="score-chart-val" style="color:${scoreColor(pct)}" title="${band}">${pct}</div>
          </div>`;
        }).join('')}
      </div>
      <div class="score-band-legend">
        <span style="color:#4caf50">■ 80–100 Excellent</span>
        <span style="color:#8bc34a">■ 65–79 Good</span>
        <span style="color:#ff9800">■ 45–64 Average</span>
        <span style="color:#9e9e9e">■ 0–44 Poor</span>
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
        <button class="modal-map-btn" id="modal-show-on-map-btn" title="Show on Map">🌌 Show on Map</button>
        <button class="modal-map-btn" id="modal-add-route-btn" title="Add to Route Planner" style="background:rgba(66,165,245,0.12);border-color:rgba(66,165,245,0.35);color:#42a5f5">🗺️ Add to Route</button>
        <a href="${edsm}" target="_blank" rel="noopener" class="modal-edsm-link">↗ EDSM</a>
        <a href="${inara}" target="_blank" rel="noopener" class="modal-edsm-link">↗ Inara</a>
      </div>
    </div>
    <div class="modal-section modal-notes-section">
      <div class="modal-section-title">Commander Notes</div>
      <textarea id="modal-note-area" class="note-area" placeholder="Add your notes about this system…" rows="3" data-id64="${sys.id64}"></textarea>
      <div class="note-actions">
        <button id="modal-note-save" class="note-save-btn">Save Note</button>
        <button id="modal-note-delete" class="note-delete-btn" hidden>Delete</button>
        <span id="modal-note-status" class="note-status"></span>
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
  // Show on Map button
  const mapBtn = qs('#modal-show-on-map-btn');
  if (mapBtn) {
    mapBtn.addEventListener('click', () => {
      closeModal();
      window.EDMap?.focusSystem(sys);
    });
  }
  // Add to Route (#12)
  const routeBtn = qs('#modal-add-route-btn');
  if (routeBtn) {
    routeBtn.addEventListener('click', () => {
      const coords = sys.coords || {};
      if (typeof selectRouteWaypoint === 'function') {
        selectRouteWaypoint({ name: sys.name, x: sys.x ?? coords.x ?? 0, y: sys.y ?? coords.y ?? 0, z: sys.z ?? coords.z ?? 0, id64: sys.id64 });
        toast('Added to Route');
      }
    });
  }
  // Commander Notes
  const noteArea   = qs('#modal-note-area');
  const noteSave   = qs('#modal-note-save');
  const noteDelete = qs('#modal-note-delete');
  const noteStatus = qs('#modal-note-status');
  if (noteArea && sys.id64) {
    apiFetch(`/api/systems/${sys.id64}/note`)
      .then(d => { if (d.note) { noteArea.value = d.note; if (noteDelete) noteDelete.hidden = false; } })
      .catch(() => {});
    noteArea.addEventListener('input', () => { noteArea.style.height = 'auto'; noteArea.style.height = noteArea.scrollHeight + 'px'; });
    if (noteSave) {
      noteSave.addEventListener('click', async () => {
        const note = noteArea.value.trim();
        noteSave.disabled = true;
        try {
          if (note) {
            await apiFetch(`/api/systems/${sys.id64}/note`, { method: 'POST', body: JSON.stringify({ note }) });
            if (noteDelete) noteDelete.hidden = false;
            if (noteStatus) { noteStatus.textContent = 'Saved ✓'; noteStatus.className = 'note-status saved'; setTimeout(() => { noteStatus.textContent = ''; }, 2000); }
          } else {
            await apiFetch(`/api/systems/${sys.id64}/note`, { method: 'DELETE' });
            if (noteDelete) noteDelete.hidden = true;
            if (noteStatus) { noteStatus.textContent = 'Deleted'; noteStatus.className = 'note-status deleted'; setTimeout(() => { noteStatus.textContent = ''; }, 2000); }
          }
        } catch { if (noteStatus) { noteStatus.textContent = 'Failed'; noteStatus.className = 'note-status error'; } }
        finally { noteSave.disabled = false; }
      });
    }
    if (noteDelete) {
      noteDelete.addEventListener('click', async () => {
        if (!confirm('Delete this note?')) return;
        try {
          await apiFetch(`/api/systems/${sys.id64}/note`, { method: 'DELETE' });
          noteArea.value = '';
          noteDelete.hidden = true;
          if (noteStatus) { noteStatus.textContent = 'Deleted'; noteStatus.className = 'note-status deleted'; setTimeout(() => { noteStatus.textContent = ''; }, 2000); }
        } catch {
          if (noteStatus) { noteStatus.textContent = 'Delete failed'; noteStatus.className = 'note-status error'; }
        }
      });
    }
  }
}
function closeModal() {
  const modal = qs('#system-modal');
  if (modal) modal.hidden = true;
  document.body.style.overflow = '';
  _modalSys = null;
}

(function initModal() {
  const modal = qs('#system-modal');
  qs('#modal-close-btn').addEventListener('click', closeModal);
  modal.addEventListener('click', (e) => { if (e.target === modal) closeModal(); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !modal.hidden) closeModal(); });
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
  const hint      = qs('#watchlist-empty-state');
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
      <button class="card-show-on-map" title="Show on Map" aria-label="Show on Map">🌌</button>
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
  // Show on Map button — stops propagation so it doesn't also open the modal
  const mapBtn = card.querySelector('.card-show-on-map');
  if (mapBtn) {
    mapBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      window.EDMap?.focusSystem(sys);
    });
  }
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
    // Broadcast results to map
    document.dispatchEvent(new CustomEvent('ed:searchresults', { detail: { systems: results, ref: null } }));
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
      max_dist: qs('#cluster-max-dist') ? Number(qs('#cluster-max-dist').value) || null : null,
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
    // Broadcast cluster results to map
    document.dispatchEvent(new CustomEvent('ed:clusterresults', { detail: { clusters: results } }));
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
        <button class="card-show-on-map" title="Show on Map" aria-label="Show on Map">🌌</button>
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
    const clusterSys = { name: anchorName, id64: c.anchor_id64 || c.system_id64, x: cx, y: cy, z: cz, coords: { x: cx, y: cy, z: cz }, population: 0, _rating: { score: coverageScore } };
    // Expand/collapse top systems per economy
    const expandBtn = document.createElement('button');
    expandBtn.className = 'cluster-expand-btn';
    expandBtn.textContent = '▶ Show top systems';
    expandBtn.setAttribute('aria-expanded', 'false');
    card.appendChild(expandBtn);
    const expandPanel = document.createElement('div');
    expandPanel.className = 'cluster-expand-panel';
    expandPanel.hidden = true;
    card.appendChild(expandPanel);
    let expanded = false, loaded = false;
    expandBtn.addEventListener('click', async (e) => {
      e.stopPropagation();
      expanded = !expanded;
      expandBtn.textContent = expanded ? '▼ Hide top systems' : '▶ Show top systems';
      expandBtn.setAttribute('aria-expanded', String(expanded));
      expandPanel.hidden = !expanded;
      if (expanded && !loaded) {
        loaded = true;
        expandPanel.innerHTML = '<div class="loading-state" style="padding:0.5rem"><div class="spinner"></div></div>';
        const ECO_KEYS = ['agriculture', 'refinery', 'industrial', 'hightech', 'military', 'tourism'];
        const topIds = [];
        ECO_KEYS.forEach(eco => { const id = c[`${eco}_top_id`]; if (id) topIds.push({ eco, id64: id }); });
        if (!topIds.length) { expandPanel.innerHTML = '<div class="cluster-top-empty">Top system data not yet available.</div>'; return; }
        try {
          const data = await apiFetch('/api/systems/batch', { method: 'POST', body: JSON.stringify({ ids: topIds.map(t => t.id64) }) });
          const sysMap = {};
          (data.systems || []).forEach(s => { sysMap[String(s.id64)] = s; });
          expandPanel.innerHTML = '';
          topIds.forEach(({ eco, id64 }) => {
            const s = sysMap[String(id64)];
            if (!s) return;
            const score = s.score != null ? Math.round(s.score) : '—';
            const row = document.createElement('div');
            row.className = 'cluster-top-system';
            row.innerHTML = `<span class="cts-eco">${eco.charAt(0).toUpperCase() + eco.slice(1, 4)}</span><span class="cts-name">${s.name || 'Unknown'}</span><span class="cts-score" style="color:${scoreColor(score)}">★${score}</span>`;
            row.addEventListener('click', (ev) => { ev.stopPropagation(); openSystemModal(s); });
            expandPanel.appendChild(row);
          });
        } catch { expandPanel.innerHTML = '<div class="cluster-top-empty">Failed to load top systems.</div>'; }
      }
    });
    card.addEventListener('click', () => openSystemModal(clusterSys));
    const mapBtn = card.querySelector('.card-show-on-map');
    if (mapBtn) {
      mapBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        window.EDMap?.focusSystem(clusterSys);
      });
    }
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

  let feedFilterText = '';
  const feedFilterInput = qs('#live-feed-filter');
  if (feedFilterInput) {
    feedFilterInput.addEventListener('input', () => { feedFilterText = feedFilterInput.value.trim().toLowerCase(); });
  }
  function addEvent(ev) {
    if (paused) return;
    if (feedFilterText && !(ev.system_name || '').toLowerCase().includes(feedFilterText)) return;
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

// ═══════════════════════════════════════════════════════════ UI IMPROVEMENTS v2.0

// ── UI #1: Slider ↔ Number input sync ──────────────────────────────────────
// Keeps range sliders and their companion number inputs in sync bidirectionally
(function initSliderSync() {
  const pairs = [
    ['#local-dist-slider',    '#local-dist-num',    '#local-dist-val',    (v) => `${v} ly`],
    ['#local-rating-slider',  '#local-rating-num',  '#local-rating-val',  (v) => v],
    ['#galaxy-score-slider',  '#galaxy-score-num',  '#galaxy-score-val',  (v) => v],
  ];
  pairs.forEach(([slideSel, numSel, valSel, fmt]) => {
    const slider = qs(slideSel);
    const num    = qs(numSel);
    const label  = qs(valSel);
    if (!slider || !num) return;
    slider.addEventListener('input', () => {
      num.value = slider.value;
      if (label) label.textContent = fmt(slider.value);
    });
    num.addEventListener('input', () => {
      const v = Math.min(Number(num.max), Math.max(Number(num.min), Number(num.value)));
      slider.value = v;
      num.value = v;
      if (label) label.textContent = fmt(v);
    });
  });
})();

// ── UI #2: Clear filter buttons ─────────────────────────────────────────────
(function initClearButtons() {
  // Local search clear
  const localClear = qs('#local-clear-btn');
  if (localClear) {
    localClear.addEventListener('click', () => {
      qs('#local-ref-input').value = '';
      qs('#local-coords-display').hidden = true;
      qs('#local-dist-slider').value = 500;
      qs('#local-dist-num').value = 500;
      qs('#local-dist-val').textContent = '500 ly';
      qs('#local-rating-slider').value = 0;
      qs('#local-rating-num').value = 0;
      qs('#local-rating-val').textContent = '0';
      qs('#local-galaxy-wide').checked = false;
      document.querySelector('input[name="local-pop"][value="any"]').checked = true;
      document.querySelector('input[name="local-sort"][value="rating"]').checked = true;
      qs('#local-economy').value = 'any';
      ['#bf-elw','#bf-ww','#bf-ammonia','#bf-gasgiant','#bf-neutron'].forEach(s => { qs(s).value = 0; });
      ['#bf-bio','#bf-geo','#bf-terra'].forEach(s => { qs(s).checked = false; });
      updateBodyFilterBadge();
      toast('Filters cleared');
    });
  }

  // Galaxy search clear
  const galaxyClear = qs('#galaxy-clear-btn');
  if (galaxyClear) {
    galaxyClear.addEventListener('click', () => {
      qs('#galaxy-economy').value = 'HighTech';
      qs('#galaxy-score-slider').value = 40;
      qs('#galaxy-score-num').value = 40;
      qs('#galaxy-score-val').textContent = '40';
      toast('Filters cleared');
    });
  }

  // Cluster search clear
  const clusterClear = qs('#cluster-clear-btn');
  if (clusterClear) {
    clusterClear.addEventListener('click', () => {
      qs('#cluster-requirements').innerHTML = '';
      qs('#cluster-ref-input').value = '';
      qs('#cluster-coords-display').hidden = true;
      toast('Requirements cleared');
    });
  }
})();

// ── UI #3: Body filter active count badge ───────────────────────────────────
function updateBodyFilterBadge() {
  const badge = qs('#body-filter-active-count');
  if (!badge) return;
  let count = 0;
  ['#bf-elw','#bf-ww','#bf-ammonia','#bf-gasgiant','#bf-neutron'].forEach(s => {
    if (Number(qs(s)?.value) > 0) count++;
  });
  ['#bf-bio','#bf-geo','#bf-terra'].forEach(s => {
    if (qs(s)?.checked) count++;
  });
  badge.textContent = count;
  badge.hidden = count === 0;
}

(function initBodyFilterBadge() {
  ['#bf-elw','#bf-ww','#bf-ammonia','#bf-gasgiant','#bf-neutron','#bf-bio','#bf-geo','#bf-terra'].forEach(s => {
    const el = qs(s);
    if (el) el.addEventListener('change', updateBodyFilterBadge);
    if (el) el.addEventListener('input', updateBodyFilterBadge);
  });
})();

// ── UI #4: Skeleton loader helpers ──────────────────────────────────────────
function showSkeleton(skeletonId, resultsId) {
  const sk = qs(`#${skeletonId}`);
  const rs = qs(`#${resultsId}`);
  if (sk) sk.hidden = false;
  if (rs) rs.style.visibility = 'hidden';
}
function hideSkeleton(skeletonId, resultsId) {
  const sk = qs(`#${skeletonId}`);
  const rs = qs(`#${resultsId}`);
  if (sk) sk.hidden = true;
  if (rs) rs.style.visibility = 'visible';
}

// Patch local search to use skeleton loaders
(function patchLocalSearchSkeleton() {
  const btn = qs('#local-search-btn');
  if (!btn) return;
  const orig = btn.onclick;
  const origClick = btn.addEventListener;
  // We override the setLoading function by patching the search button's loading state
  const observer = new MutationObserver(() => {
    const isLoading = btn.classList.contains('loading');
    if (isLoading) showSkeleton('local-skeleton', 'local-results');
    else hideSkeleton('local-skeleton', 'local-results');
  });
  observer.observe(btn, { attributes: true, attributeFilter: ['class'] });
})();

// ── UI #5: Search history (local search) ────────────────────────────────────
const SearchHistory = {
  _key: 'ed_search_history',
  _max: 8,
  _data: [],
  load() {
    try { this._data = JSON.parse(localStorage.getItem(this._key) || '[]'); }
    catch { this._data = []; }
  },
  add(refName, params) {
    this._data = this._data.filter(h => h.refName !== refName);
    this._data.unshift({ refName, params, ts: Date.now() });
    if (this._data.length > this._max) this._data.length = this._max;
    localStorage.setItem(this._key, JSON.stringify(this._data));
    this.render();
  },
  remove(refName) {
    this._data = this._data.filter(h => h.refName !== refName);
    localStorage.setItem(this._key, JSON.stringify(this._data));
    this.render();
  },
  _restore(h) {
    const p = h.params || {};
    const refInput = qs('#local-ref-input');
    if (refInput) refInput.value = h.refName;
    const distSlider = qs('#local-dist-slider');
    const distVal    = qs('#local-dist-val');
    if (distSlider && p.max_dist != null) { distSlider.value = p.max_dist; if (distVal) distVal.textContent = `${p.max_dist} ly`; }
    const ratingSlider = qs('#local-rating-slider');
    const ratingVal    = qs('#local-rating-val');
    if (ratingSlider && p.min_rating != null) { ratingSlider.value = p.min_rating; if (ratingVal) ratingVal.textContent = p.min_rating; }
    const ecoSel = qs('#local-economy');
    if (ecoSel && p.economy) ecoSel.value = p.economy;
    if (p.population != null) { const r = document.querySelector(`input[name="local-pop"][value="${p.population}"]`); if (r) r.checked = true; }
    const gwCheck = qs('#local-galaxy-wide');
    if (gwCheck && p.galaxy_wide != null) gwCheck.checked = p.galaxy_wide;
    toast(`Restored: ${h.refName}`);
  },
  render() {
    const container = qs('#local-search-history');
    const list = qs('#local-history-list');
    if (!container || !list) return;
    if (!this._data.length) { container.hidden = true; return; }
    container.hidden = false;
    list.innerHTML = '';
    this._data.forEach(h => {
      const li = document.createElement('li');
      const eco = h.params?.economy && h.params.economy !== 'any' ? ` · ${h.params.economy}` : '';
      const dist = h.params?.max_dist ? ` · ${h.params.max_dist} ly` : '';
      li.innerHTML = `<span class="history-icon">⊕</span> <span class="history-name" title="Click to restore all settings">${h.refName}<span class="history-meta">${eco}${dist}</span></span> <button class="history-remove" title="Remove">✕</button>`;
      li.querySelector('.history-name').addEventListener('click', () => SearchHistory._restore(h));
      li.querySelector('.history-remove').addEventListener('click', (e) => { e.stopPropagation(); SearchHistory.remove(h.refName); });
      list.appendChild(li);
    });
  },
};
SearchHistory.load();
SearchHistory.render();
// ── Recently Viewed ─────────────────────────────────────────────────────────
const RecentlyViewed = {
  _key: 'ed_recently_viewed',
  _max: 10,
  _data: [],
  load() {
    try { this._data = JSON.parse(localStorage.getItem(this._key) || '[]'); }
    catch { this._data = []; }
  },
  add(sys) {
    if (!sys || !sys.id64) return;
    this._data = this._data.filter(s => s.id64 !== sys.id64);
    this._data.unshift({ id64: sys.id64, name: sys.name || 'Unknown', ts: Date.now() });
    if (this._data.length > this._max) this._data.length = this._max;
    localStorage.setItem(this._key, JSON.stringify(this._data));
    this.render();
  },
  render() {
    const container = qs('#recently-viewed-panel');
    const list = qs('#recently-viewed-list');
    if (!container || !list) return;
    if (!this._data.length) { container.hidden = true; return; }
    container.hidden = false;
    list.innerHTML = '';
    this._data.forEach(s => {
      const li = document.createElement('li');
      li.className = 'recently-viewed-item';
      li.innerHTML = `<span class="rv-icon">◎</span><span class="rv-name">${s.name}</span>`;
      li.addEventListener('click', () => openSystemModal({ id64: s.id64, name: s.name }));
      list.appendChild(li);
    });
  },
};
RecentlyViewed.load();
RecentlyViewed.render();
// Wrap openSystemModal to track recently viewed
const _origOpenSystemModal = openSystemModal;
openSystemModal = async function(sys) {
  RecentlyViewed.add(sys);
  return _origOpenSystemModal(sys);
};

// Hook into local search to save full params on search
(function hookSearchHistory() {
  const btn = qs('#local-search-btn');
  if (!btn) return;
  btn.addEventListener('click', () => {
    const refInput = qs('#local-ref-input');
    if (!refInput || !refInput.value.trim()) return;
    const distSlider   = qs('#local-dist-slider');
    const ratingSlider = qs('#local-rating-slider');
    const ecoSel       = qs('#local-economy');
    const gwCheck      = qs('#local-galaxy-wide');
    const popRadio     = document.querySelector('input[name="local-pop"]:checked');
    const params = {
      max_dist:    distSlider   ? Number(distSlider.value)   : 500,
      min_rating:  ratingSlider ? Number(ratingSlider.value) : 0,
      economy:     ecoSel ? ecoSel.value : 'any',
      galaxy_wide: gwCheck ? gwCheck.checked : false,
      population:  popRadio ? popRadio.value : 'all',
    };
    SearchHistory.add(refInput.value.trim(), params);
  }, true);
})();

// ── UI #6: Watchlist export / import ────────────────────────────────────────
(function initWatchlistIO() {
  const ioPanel = qs('#watchlist-io-panel');
  const exportBtn = qs('#watchlist-export-btn');
  const importInput = qs('#watchlist-import-input');

  // Show the IO panel when watchlist has items
  function refreshIOPanel() {
    if (ioPanel) ioPanel.hidden = Watchlist.count() === 0;
  }

  // Export
  if (exportBtn) {
    exportBtn.addEventListener('click', () => {
      const data = JSON.stringify({ version: 1, exported: new Date().toISOString(), systems: Watchlist.getAll() }, null, 2);
      const blob = new Blob([data], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `ed-finder-watchlist-${new Date().toISOString().slice(0,10)}.json`;
      a.click();
      URL.revokeObjectURL(url);
      toast('Watchlist exported');
    });
  }

  // Import
  if (importInput) {
    importInput.addEventListener('change', () => {
      const file = importInput.files[0];
      if (!file) return;
      const reader = new FileReader();
      reader.onload = (e) => {
        try {
          const parsed = JSON.parse(e.target.result);
          const systems = parsed.systems || (Array.isArray(parsed) ? parsed : []);
          let added = 0;
          systems.forEach(s => {
            if (s.id64 && s.name && !Watchlist.has(s.id64)) {
              Watchlist._data[String(s.id64)] = { ...s, savedAt: s.savedAt || Date.now() };
              added++;
            }
          });
          Watchlist.save();
          refreshIOPanel();
          renderWatchlistTab();
          toast(`Imported ${added} system${added !== 1 ? 's' : ''}`);
        } catch {
          toast('Import failed — invalid JSON file');
        }
        importInput.value = '';
      };
      reader.readAsText(file);
    });
  }

  // Refresh panel state on tab activation
  qsa('.nav-btn[data-tab="watchlist"]').forEach(btn => {
    btn.addEventListener('click', () => { refreshIOPanel(); });
  });
  refreshIOPanel();
})();


// ── Watchlist Changelog ──────────────────────────────────────────────────────
(function initWatchlistChangelog() {
  function loadChangelog() {
    const panel = qs('#watchlist-changelog-panel');
    const list  = qs('#watchlist-changelog-list');
    if (!panel || !list) return;
    apiFetch('/api/watchlist/changelog')
      .then(data => {
        const changes = data.changes || [];
        if (!changes.length) { panel.hidden = true; return; }
        panel.hidden = false;
        list.innerHTML = '';
        changes.slice(0, 20).forEach(c => {
          const li = document.createElement('li');
          li.className = 'changelog-item';
          const ts = c.detected_at ? new Date(c.detected_at).toLocaleDateString() : '';
          const sysName = c.system_name || c.name || 'Unknown';
          const fieldName = c.change_type || c.field_changed || '';
          li.innerHTML = `<span class="cl-name">${sysName}</span><span class="cl-field">${fieldName}</span><span class="cl-old">${c.old_value ?? '—'}</span><span class="cl-arrow">→</span><span class="cl-new">${c.new_value ?? '—'}</span><span class="cl-ts">${ts}</span>`;
          li.addEventListener('click', () => openSystemModal({ id64: c.system_id64, name: sysName }));
          list.appendChild(li);
        });
      })
      .catch(() => {});
  }
  document.querySelectorAll('.nav-btn[data-tab="watchlist"]').forEach(btn => btn.addEventListener('click', loadChangelog));
  loadChangelog();
})();

// ── UI #7: Compare systems feature ──────────────────────────────────────────
const Compare = {
  _items: [],
  _max: 3,

  add(sys) {
    if (this._items.find(s => s.id64 === sys.id64)) { toast('Already in compare list'); return; }
    if (this._items.length >= this._max) { toast(`Maximum ${this._max} systems to compare`); return; }
    this._items.push(sys);
    this.render();
    toast(`Added ${sys.name} to compare`);
  },

  remove(id64) {
    this._items = this._items.filter(s => s.id64 !== id64);
    this.render();
  },

  clear() {
    this._items = [];
    this.render();
  },

  render() {
    const panel   = qs('#compare-panel');
    const slots   = qs('#compare-slots');
    const count   = qs('#compare-count');
    const runBtn  = qs('#compare-run-btn');
    if (!panel) return;

    panel.hidden = this._items.length === 0;
    if (count) count.textContent = `${this._items.length} / ${this._max}`;
    if (runBtn) runBtn.disabled = this._items.length < 2;

    if (slots) {
      slots.innerHTML = '';
      this._items.forEach(sys => {
        const slot = document.createElement('div');
        slot.className = 'compare-slot';
        slot.innerHTML = `<span>${sys.name}</span><button class="slot-remove" data-id64="${sys.id64}" aria-label="Remove ${sys.name}">✕</button>`;
        slot.querySelector('.slot-remove').addEventListener('click', (e) => {
          e.stopPropagation();
          this.remove(Number(e.target.dataset.id64));
        });
        slots.appendChild(slot);
      });
    }
  },

  async showModal() {
    if (this._items.length < 2) return;
    const modal   = qs('#compare-modal');
    const content = qs('#compare-modal-content');
    if (!modal || !content) return;

    content.innerHTML = '<div class="loading-state"><div class="spinner"></div>Loading comparison…</div>';
    modal.hidden = false;
    document.body.style.overflow = 'hidden';

    // Fetch full data for each system
    const systems = await Promise.all(this._items.map(async (s) => {
      try {
        const data = await apiFetch(`/api/system/${s.id64}`);
        return data.record || data.system || data;
      } catch { return s; }
    }));

    const fields = [
      ['Name',           s => s.name || '—'],
      ['Economy',        s => s.primaryEconomy || s.primary_economy || '—'],
      ['Population',     s => Number(s.population || 0) === 0 ? 'Uncolonised' : fmtNum(s.population)],
      ['Overall Score',  s => s._rating?.score != null ? Math.round(s._rating.score) : '—'],
      ['Agri Score',     s => s._rating?.score_agriculture ?? s._rating?.scoreAgriculture ?? '—'],
      ['Ref Score',      s => s._rating?.score_refinery    ?? s._rating?.scoreRefinery    ?? '—'],
      ['Ind Score',      s => s._rating?.score_industrial  ?? s._rating?.scoreIndustrial  ?? '—'],
      ['HiTec Score',    s => s._rating?.score_hightech    ?? s._rating?.scoreHightech     ?? '—'],
      ['Mil Score',      s => s._rating?.score_military    ?? s._rating?.scoreMilitary     ?? '—'],
      ['Tour Score',     s => s._rating?.score_tourism     ?? s._rating?.scoreTourism      ?? '—'],
      ['ELW Count',      s => s._rating?.elw_count ?? '—'],
      ['WW Count',       s => s._rating?.ww_count  ?? '—'],
      ['Bio Signals',    s => s._rating?.bio_signal_total ?? '—'],
      ['Geo Signals',    s => s._rating?.geo_signal_total ?? '—'],
      ['Terraformable',  s => s._rating?.terraformable_count ?? '—'],
      ['Neutron Stars',  s => s._rating?.neutron_count ?? '—'],
    ];

    const headers = ['Field', ...systems.map(s => s.name || 'Unknown')];
    const rows = fields.map(([label, fn]) => {
      const vals = systems.map(fn);
      const numVals = vals.map(v => typeof v === 'number' ? v : parseFloat(v)).filter(v => !isNaN(v));
      const maxVal = numVals.length ? Math.max(...numVals) : null;
      return [label, ...vals.map(v => {
        const n = typeof v === 'number' ? v : parseFloat(v);
        const isWinner = !isNaN(n) && maxVal !== null && n === maxVal && numVals.length > 1;
        return { value: v, isWinner };
      })];
    });

    content.innerHTML = `
      <div style="padding:1.5rem">
        <h2 style="color:var(--accent);font-size:1rem;text-transform:uppercase;letter-spacing:0.1em;margin-bottom:1.25rem">System Comparison</h2>
        <div style="overflow-x:auto">
          <table class="compare-table">
            <thead><tr>${headers.map((h, i) => `<th${i === 0 ? '' : ' style="text-align:center"'}>${h}</th>`).join('')}</tr></thead>
            <tbody>
              ${rows.map(([label, ...cells]) => `
                <tr>
                  <td style="color:var(--text-dim);font-size:0.75rem;text-transform:uppercase;letter-spacing:0.06em">${label}</td>
                  ${cells.map(c => `<td style="text-align:center" class="${c.isWinner ? 'compare-winner' : ''}">${c.value}</td>`).join('')}
                </tr>`).join('')}
            </tbody>
          </table>
        </div>
      </div>
    `;
  },
};

(function initCompare() {
  const clearBtn = qs('#compare-clear-btn');
  const runBtn   = qs('#compare-run-btn');
  const modal    = qs('#compare-modal');
  const closeBtn = qs('#compare-modal-close');

  if (clearBtn) clearBtn.addEventListener('click', () => Compare.clear());
  if (runBtn)   runBtn.addEventListener('click', () => Compare.showModal());
  if (closeBtn) closeBtn.addEventListener('click', () => {
    modal.hidden = true;
    document.body.style.overflow = '';
  });
  if (modal) modal.addEventListener('click', (e) => {
    if (e.target === modal) { modal.hidden = true; document.body.style.overflow = ''; }
  });

  // Add compare checkboxes to system cards
  // We patch buildSystemCard to add a compare checkbox
  const _origBuildCard = buildSystemCard;
  window.buildSystemCard = function(sys, rank) {
    const card = _origBuildCard(sys, rank);
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.className = 'card-compare-check';
    checkbox.title = 'Add to compare';
    checkbox.setAttribute('aria-label', `Compare ${sys.name}`);
    checkbox.addEventListener('change', (e) => {
      e.stopPropagation();
      if (checkbox.checked) Compare.add(sys);
      else Compare.remove(sys.id64);
    });
    card.appendChild(checkbox);
    return card;
  };
})();

// ── UI #8: Mobile bottom nav wiring ─────────────────────────────────────────
(function initMobileNav() {
  const mobileBtns = qsa('.mobile-nav-btn');
  const desktopBtns = qsa('.nav-btn');
  const panels = qsa('.tab-panel');
  function activateTab(tabName) {
    mobileBtns.forEach(b => b.classList.toggle('active', b.dataset.tab === tabName));
    desktopBtns.forEach(b => b.classList.toggle('active', b.dataset.tab === tabName));
    panels.forEach(p => {
      p.classList.toggle('active', p.id === `tab-${tabName}`);
      p.hidden = p.id !== `tab-${tabName}`;
    });
    if (tabName === 'watchlist') renderWatchlistTab();
    if (tabName === 'map')   { setTimeout(() => window.EDMap?.draw2D(), 50); }
    if (tabName === 'map3d') { setTimeout(() => window.EDMap?.draw3D(), 50); }
    _setUrlParam('tab', tabName === 'local' ? null : tabName);
  }
  mobileBtns.forEach(btn => {
    btn.addEventListener('click', () => activateTab(btn.dataset.tab));
  });
})();

// ── UI #9: Toast queue (replace single toast with stacked queue) ─────────────
(function initToastQueue() {
  // Create toast stack container
  const stack = document.createElement('div');
  stack.id = 'toast-stack';
  stack.className = 'toast-stack';
  document.body.appendChild(stack);

  // Override the global toast() function
  window.toast = function(msg, type = 'default', dur = 3500) {
    const item = document.createElement('div');
    item.className = `toast-item${type !== 'default' ? ` ${type}` : ''}`;
    item.textContent = msg;
    stack.appendChild(item);
    setTimeout(() => {
      item.style.opacity = '0';
      item.style.transition = 'opacity 0.3s';
      setTimeout(() => item.remove(), 300);
    }, dur);
  };
})();

// ── UI #10: Cluster ref system autocomplete ──────────────────────────────────
(function initClusterRefAutocomplete() {
  const input = qs('#cluster-ref-input');
  const list  = qs('#cluster-ref-suggestions');
  const disp  = qs('#cluster-coords-display');
  const xSpan = qs('#cluster-coord-x');
  const ySpan = qs('#cluster-coord-y');
  const zSpan = qs('#cluster-coord-z');
  if (!input || !list) return;

  makeAutocomplete(input, list, (sys) => {
    if (xSpan) xSpan.textContent = `X: ${fmtCoord(sys.x)}`;
    if (ySpan) ySpan.textContent = `Y: ${fmtCoord(sys.y)}`;
    if (zSpan) zSpan.textContent = `Z: ${fmtCoord(sys.z)}`;
    if (disp) disp.hidden = false;
    // Broadcast the cluster ref coords
    document.dispatchEvent(new CustomEvent('ed:clusterrefcoords', { detail: { x: sys.x, y: sys.y, z: sys.z } }));
  });
})();


// ═══════════════════════════════════════════════════════════ ED MAP MODULE
// Shared Three.js scene for both 2D galactic map and 3D star map tabs.
// 2D view: orthographic camera, top-down (X/Z plane), pan + zoom.
// 3D view: perspective camera, orbit controls (drag to rotate, scroll to zoom).
// All 10 map improvements are implemented here.

const EDMap = (function () {
  'use strict';

  // ── State ──────────────────────────────────────────────────────────────────
  let _scene2d = null, _renderer2d = null, _camera2d = null;
  let _scene3d = null, _renderer3d = null, _camera3d = null;
  let _controls3d = null;
  let _points2d = null, _points3d = null;
  let _watchlistPoints2d = null, _watchlistPoints3d = null;
  let _radiusMesh2d = null, _radiusMesh3d = null;
  let _landmarkLabels2d = [];
  let _selectedSystem = null;
  let _resultSystems = [];   // last search results
  let _clusterSystems = [];  // last cluster results
  let _refCoords = null;     // reference system coords
  let _animFrameId2d = null, _animFrameId3d = null;

  // Galaxy scale: ED coords → Three.js units (1 unit = 100 ly)
  const SCALE = 0.01;

  // Landmark systems for orientation
  const LANDMARKS = [
    { name: 'Sol',              x: 0,       y: 0,      z: 0 },
    { name: 'Colonia',          x: -9530.5, y: -910.3, z: 19808.1 },
    { name: 'Sagittarius A*',   x: 25.22,   y: -20.9,  z: 25899.97 },
    { name: 'Beagle Point',     x: -1111.6, y: -134.2, z: 65269.8 },
    { name: 'Jaques Station',   x: -9530.5, y: -910.3, z: 19808.1 },
    { name: 'Bubble',           x: 0,       y: 0,      z: 0 },  // alias
  ];

  // Approximate nebula regions (centre + radius in ly)
  const NEBULAE = [
    { name: 'Orion Nebula',     x: -342,    y: -46,    z: 1344,   r: 200 },
    { name: 'Pleiades',         x: -81.1,   y: -149.4, z: 378.2,  r: 150 },
    { name: 'California Neb.',  x: -299,    y: -78,    z: 1000,   r: 120 },
    { name: 'Rosette Nebula',   x: -461,    y: -1.4,   z: 5198,   r: 180 },
    { name: 'Eagle Nebula',     x: 2088,    y: 0,      z: 6514,   r: 160 },
    { name: 'Lagoon Nebula',    x: 4093,    y: -209,   z: 5765,   r: 140 },
    { name: 'Crab Nebula',      x: 5765,    y: 2035,   z: 3310,   r: 100 },
  ];

  // Economy colour map
  const ECO_COLORS = {
    agriculture: 0x22c55e,
    refinery:    0xf97316,
    industrial:  0x3b82f6,
    hightech:    0xa855f7,
    'high tech': 0xa855f7,
    military:    0xef4444,
    tourism:     0xd4a832,
    extraction:  0x6b7280,
    colony:      0x14b8a6,
  };

  function ecoColor(eco) {
    if (!eco) return 0x6b8599;
    return ECO_COLORS[eco.toLowerCase()] || 0x6b8599;
  }

  function scoreToColor(s) {
    if (s == null) return 0x6b8599;
    if (s >= 75) return 0x22c55e;
    if (s >= 50) return 0xd4a832;
    if (s >= 25) return 0xf97316;
    return 0x6b8599;
  }

  function distToColor(d, maxD) {
    if (d == null || maxD === 0) return 0x6b8599;
    const t = Math.min(d / maxD, 1);
    // blue → green → yellow → red
    const r = Math.round(t * 255);
    const g = Math.round((1 - Math.abs(t - 0.5) * 2) * 255);
    const b = Math.round((1 - t) * 255);
    return (r << 16) | (g << 8) | b;
  }

  // Convert ED coords to Three.js coords (X=X, Y=Z, Z=-Y for top-down view)
  function toScene(x, y, z) {
    return {
      sx: (x || 0) * SCALE,
      sy: (y || 0) * SCALE,
      sz: (z || 0) * SCALE,
    };
  }

  // ── 2D MAP SETUP ───────────────────────────────────────────────────────────

  function init2D() {
    const canvas = document.getElementById('galactic-map');
    if (!canvas || !window.THREE) return false;
    if (_renderer2d) return true;  // already initialised

    const w = canvas.clientWidth  || canvas.parentElement.clientWidth  || 800;
    const h = canvas.clientHeight || canvas.parentElement.clientHeight || 600;

    _renderer2d = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false, preserveDrawingBuffer: true });
    _renderer2d.setPixelRatio(window.devicePixelRatio);
    _renderer2d.setSize(w, h);
    _renderer2d.setClearColor(0x060d14, 1);

    const aspect = w / h;
    const viewSize = 800;  // ly visible at default zoom
    _camera2d = new THREE.OrthographicCamera(
      -viewSize * aspect * SCALE / 2, viewSize * aspect * SCALE / 2,
       viewSize * SCALE / 2,         -viewSize * SCALE / 2,
      -1000, 1000
    );
    _camera2d.position.set(0, 100, 0);
    _camera2d.lookAt(0, 0, 0);
    _camera2d.up.set(0, 0, -1);

    _scene2d = new THREE.Scene();

    // Pan & zoom
    _init2DControls(canvas);

    // Resize observer
    new ResizeObserver(() => _resize2D()).observe(canvas.parentElement);

    return true;
  }

  function _resize2D() {
    if (!_renderer2d || !_camera2d) return;
    const canvas = document.getElementById('galactic-map');
    if (!canvas) return;
    const w = canvas.parentElement.clientWidth  || 800;
    const h = canvas.parentElement.clientHeight || 600;
    _renderer2d.setSize(w, h);
    const aspect = w / h;
    const viewSize = (_camera2d.top - _camera2d.bottom);
    _camera2d.left   = -viewSize * aspect / 2;
    _camera2d.right  =  viewSize * aspect / 2;
    _camera2d.updateProjectionMatrix();
  }

  function _init2DControls(canvas) {
    let dragging = false, lastX = 0, lastY = 0;

    canvas.addEventListener('mousedown', (e) => {
      dragging = true;
      lastX = e.clientX;
      lastY = e.clientY;
    });
    window.addEventListener('mouseup', () => { dragging = false; });
    canvas.addEventListener('mousemove', (e) => {
      if (!dragging) { _handle2DHover(e, canvas); return; }
      const dx = e.clientX - lastX;
      const dy = e.clientY - lastY;
      lastX = e.clientX; lastY = e.clientY;
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      const viewW = _camera2d.right - _camera2d.left;
      const viewH = _camera2d.top - _camera2d.bottom;
      _camera2d.position.x -= (dx / w) * viewW;
      _camera2d.position.z += (dy / h) * viewH;
      document.dispatchEvent(new Event('ed:panned'));
    });
    canvas.addEventListener('wheel', (e) => {
      e.preventDefault();
      const factor = e.deltaY > 0 ? 1.15 : 0.87;
      const aspect = canvas.clientWidth / canvas.clientHeight;
      const viewH = (_camera2d.top - _camera2d.bottom) * factor;
      const viewW = viewH * aspect;
      _camera2d.left   = -viewW / 2 + _camera2d.position.x;
      _camera2d.right  =  viewW / 2 + _camera2d.position.x;
      _camera2d.top    =  viewH / 2 - _camera2d.position.z;
      _camera2d.bottom = -viewH / 2 - _camera2d.position.z;
      _camera2d.updateProjectionMatrix();
      document.dispatchEvent(new Event('ed:panned'));
    }, { passive: false });
    canvas.addEventListener('click', (e) => { _handle2DClick(e, canvas); });
  }

  // ── 3D MAP SETUP ───────────────────────────────────────────────────────────

  function init3D() {
    const canvas = document.getElementById('map3d-canvas');
    if (!canvas || !window.THREE) return false;
    if (_renderer3d) return true;

    const w = canvas.clientWidth  || canvas.parentElement.clientWidth  || 800;
    const h = canvas.clientHeight || canvas.parentElement.clientHeight || 600;

    _renderer3d = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: false, preserveDrawingBuffer: true });
    _renderer3d.setPixelRatio(window.devicePixelRatio);
    _renderer3d.setSize(w, h);
    _renderer3d.setClearColor(0x060d14, 1);

    _camera3d = new THREE.PerspectiveCamera(60, w / h, 0.01, 5000);
    _camera3d.position.set(0, 80, 120);
    _camera3d.lookAt(0, 0, 0);

    _scene3d = new THREE.Scene();

    // Ambient light for any mesh objects
    _scene3d.add(new THREE.AmbientLight(0xffffff, 0.6));

    // Orbit controls (manual implementation — no OrbitControls import needed)
    _init3DControls(canvas);

    new ResizeObserver(() => _resize3D()).observe(canvas.parentElement);

    return true;
  }

  function _resize3D() {
    if (!_renderer3d || !_camera3d) return;
    const canvas = document.getElementById('map3d-canvas');
    if (!canvas) return;
    const w = canvas.parentElement.clientWidth  || 800;
    const h = canvas.parentElement.clientHeight || 600;
    _renderer3d.setSize(w, h);
    _camera3d.aspect = w / h;
    _camera3d.updateProjectionMatrix();
  }

  function _init3DControls(canvas) {
    let isDragging = false, lastX = 0, lastY = 0;
    let spherical = { theta: 0.5, phi: 1.0, radius: 150 };
    let target = new THREE.Vector3(0, 0, 0);

    function updateCamera() {
      const x = spherical.radius * Math.sin(spherical.phi) * Math.sin(spherical.theta);
      const y = spherical.radius * Math.cos(spherical.phi);
      const z = spherical.radius * Math.sin(spherical.phi) * Math.cos(spherical.theta);
      _camera3d.position.set(target.x + x, target.y + y, target.z + z);
      _camera3d.lookAt(target);
    }
    updateCamera();

    canvas.addEventListener('mousedown', (e) => {
      isDragging = true; lastX = e.clientX; lastY = e.clientY;
    });
    window.addEventListener('mouseup', () => { isDragging = false; });
    canvas.addEventListener('mousemove', (e) => {
      if (!isDragging) { _handle3DHover(e, canvas); return; }
      const dx = e.clientX - lastX;
      const dy = e.clientY - lastY;
      lastX = e.clientX; lastY = e.clientY;
      spherical.theta -= dx * 0.005;
      spherical.phi   = Math.max(0.1, Math.min(Math.PI - 0.1, spherical.phi + dy * 0.005));
      updateCamera();
    });
    canvas.addEventListener('wheel', (e) => {
      e.preventDefault();
      spherical.radius = Math.max(2, Math.min(2000, spherical.radius * (e.deltaY > 0 ? 1.1 : 0.9)));
      updateCamera();
    }, { passive: false });
    canvas.addEventListener('click', (e) => { _handle3DClick(e, canvas); });

    // Store updateCamera so reset can use it
    canvas._resetCamera = () => {
      spherical = { theta: 0.5, phi: 1.0, radius: 150 };
      target = new THREE.Vector3(0, 0, 0);
      updateCamera();
    };
  }

  // ── POINT CLOUD BUILDER ────────────────────────────────────────────────────

  function _buildPointCloud(systems, colourMode, sizeMode, refCoords) {
    if (!systems.length) return null;

    const maxDist = refCoords ? Math.max(...systems.map(s => {
      const dx = (s.x || 0) - refCoords.x;
      const dy = (s.y || 0) - refCoords.y;
      const dz = (s.z || 0) - refCoords.z;
      return Math.sqrt(dx*dx + dy*dy + dz*dz);
    })) : 1;

    const positions = new Float32Array(systems.length * 3);
    const colors    = new Float32Array(systems.length * 3);
    const sizes     = new Float32Array(systems.length);

    systems.forEach((s, i) => {
      const { sx, sy, sz } = toScene(s.x, s.y, s.z);
      positions[i*3]   = sx;
      positions[i*3+1] = sy;
      positions[i*3+2] = sz;

      let col;
      if (colourMode === 'economy') {
        col = new THREE.Color(ecoColor(s.primaryEconomy || s.primary_economy));
      } else if (colourMode === 'distance' && refCoords) {
        const dx = (s.x||0)-refCoords.x, dy = (s.y||0)-refCoords.y, dz = (s.z||0)-refCoords.z;
        col = new THREE.Color(distToColor(Math.sqrt(dx*dx+dy*dy+dz*dz), maxDist));
      } else if (colourMode === 'population') {
        col = new THREE.Color(Number(s.population||0) === 0 ? 0x22c55e : 0x6b8599);
      } else {
        const score = s._rating?.score ?? s.score;
        col = new THREE.Color(scoreToColor(score));
      }
      colors[i*3]   = col.r;
      colors[i*3+1] = col.g;
      colors[i*3+2] = col.b;

      let sz2 = 3;
      if (sizeMode === 'rating') {
        const score = s._rating?.score ?? s.score ?? 0;
        sz2 = 2 + (score / 100) * 6;
      } else if (sizeMode === 'population') {
        const pop = Number(s.population || 0);
        sz2 = pop === 0 ? 4 : Math.min(2 + Math.log10(pop + 1), 8);
      }
      sizes[i] = sz2;
    });

    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    geo.setAttribute('color',    new THREE.BufferAttribute(colors, 3));
    geo.setAttribute('size',     new THREE.BufferAttribute(sizes, 1));

    // Store system data for raycasting
    geo._systems = systems;

    const mat = new THREE.PointsMaterial({
      size: 3,
      vertexColors: true,
      sizeAttenuation: false,
      transparent: true,
      opacity: 0.85,
    });

    return new THREE.Points(geo, mat);
  }

  // ── LANDMARK SPRITES ───────────────────────────────────────────────────────

  function _buildLandmarkSprites(scene, is3d) {
    LANDMARKS.forEach(lm => {
      const { sx, sy, sz } = toScene(lm.x, lm.y, lm.z);
      const geo = new THREE.SphereGeometry(is3d ? 0.5 : 0.3, 8, 8);
      const mat = new THREE.MeshBasicMaterial({ color: 0xffd700 });
      const mesh = new THREE.Mesh(geo, mat);
      mesh.position.set(sx, is3d ? sy : 0.1, sz);
      mesh._landmark = lm;
      scene.add(mesh);
    });
  }

  // ── DENSITY HEAT OVERLAY (2D only) ───────────────────────────────────────
  // Renders a low-res heatmap as a canvas overlay behind the Three.js canvas.
  // Uses a separate 2D canvas element positioned absolutely over the map canvas.

  function _buildHeatOverlay(systems) {
    const mapCanvas = document.getElementById('galactic-map');
    if (!mapCanvas || !_camera2d) return;
    let heatCanvas = document.getElementById('map-heat-canvas');
    if (!heatCanvas) {
      heatCanvas = document.createElement('canvas');
      heatCanvas.id = 'map-heat-canvas';
      heatCanvas.style.cssText = 'position:absolute;top:0;left:0;pointer-events:none;opacity:0.45;';
      mapCanvas.parentElement.style.position = 'relative';
      mapCanvas.parentElement.insertBefore(heatCanvas, mapCanvas);
    }
    const w = mapCanvas.clientWidth;
    const h = mapCanvas.clientHeight;
    heatCanvas.width  = w;
    heatCanvas.height = h;
    const ctx = heatCanvas.getContext('2d');
    ctx.clearRect(0, 0, w, h);
    if (!systems.length) return;

    // Convert world coords to screen coords using the current camera frustum
    function worldToScreen(wx, wz) {
      const frustumW = _camera2d.right - _camera2d.left;
      const frustumH = _camera2d.top   - _camera2d.bottom;
      const sx2 = ((wx - _camera2d.left) / frustumW) * w;
      const sy2 = ((1 - (wz - _camera2d.bottom) / frustumH)) * h;
      return [sx2, sy2];
    }

    const RADIUS = Math.max(20, Math.min(80, w / 12));
    systems.forEach(sys => {
      const { sx, sz } = toScene(sys.x || 0, 0, sys.z || 0);
      const [px, py] = worldToScreen(sx, sz);
      const grad = ctx.createRadialGradient(px, py, 0, px, py, RADIUS);
      grad.addColorStop(0, 'rgba(56,189,248,0.35)');
      grad.addColorStop(1, 'rgba(56,189,248,0)');
      ctx.fillStyle = grad;
      ctx.beginPath();
      ctx.arc(px, py, RADIUS, 0, Math.PI * 2);
      ctx.fill();
    });
  }

  function _clearHeatOverlay() {
    const heatCanvas = document.getElementById('map-heat-canvas');
    if (heatCanvas) heatCanvas.getContext('2d').clearRect(0, 0, heatCanvas.width, heatCanvas.height);
  }

  // ── NEBULA RINGS (2D only) ─────────────────────────────────────────────────

  function _buildNebulaeOverlay(scene) {
    NEBULAE.forEach(neb => {
      const { sx, sz } = toScene(neb.x, 0, neb.z);
      const r = neb.r * SCALE;
      const geo = new THREE.RingGeometry(r * 0.85, r, 48);
      const mat = new THREE.MeshBasicMaterial({
        color: 0x7c3aed, transparent: true, opacity: 0.18, side: THREE.DoubleSide,
      });
      const mesh = new THREE.Mesh(geo, mat);
      mesh.rotation.x = -Math.PI / 2;
      mesh.position.set(sx, 0.05, sz);
      scene.add(mesh);
    });
  }

  // ── RADIUS SPHERE / CIRCLE ─────────────────────────────────────────────────

  function _buildRadiusIndicator(scene, cx, cy, cz, is3d) {
    const { sx, sy, sz } = toScene(cx, cy, cz);
    const r = 500 * SCALE;
    if (is3d) {
      const geo = new THREE.SphereGeometry(r, 32, 16);
      const mat = new THREE.MeshBasicMaterial({
        color: 0x38bdf8, wireframe: true, transparent: true, opacity: 0.15,
      });
      const mesh = new THREE.Mesh(geo, mat);
      mesh.position.set(sx, sy, sz);
      return mesh;
    } else {
      const geo = new THREE.RingGeometry(r * 0.98, r, 64);
      const mat = new THREE.MeshBasicMaterial({
        color: 0x38bdf8, transparent: true, opacity: 0.5, side: THREE.DoubleSide,
      });
      const mesh = new THREE.Mesh(geo, mat);
      mesh.rotation.x = -Math.PI / 2;
      mesh.position.set(sx, 0.2, sz);
      return mesh;
    }
  }

  // ── RAYCASTING HELPERS ─────────────────────────────────────────────────────

  function _pickSystem(event, canvas, camera, scene) {
    const rect = canvas.getBoundingClientRect();
    const x = ((event.clientX - rect.left) / rect.width)  * 2 - 1;
    const y = -((event.clientY - rect.top)  / rect.height) * 2 + 1;
    const mouse = new THREE.Vector2(x, y);
    const raycaster = new THREE.Raycaster();
    raycaster.setFromCamera(mouse, camera);
    raycaster.params.Points.threshold = 0.5;

    const pointObjects = scene.children.filter(c => c instanceof THREE.Points);
    const hits = raycaster.intersectObjects(pointObjects);
    if (!hits.length) return null;
    const hit = hits[0];
    const systems = hit.object.geometry._systems;
    if (!systems) return null;
    return systems[hit.index];
  }

  // ── TOOLTIP ────────────────────────────────────────────────────────────────

  function _showTooltip(tooltipEl, event, canvas, sys) {
    if (!sys) { tooltipEl.hidden = true; return; }
    const rect = canvas.getBoundingClientRect();
    const score = sys._rating?.score ?? sys.score;
    const eco   = sys.primaryEconomy || sys.primary_economy || '';
    tooltipEl.innerHTML = `
      <strong>${sys.name || 'Unknown'}</strong>
      ${score != null ? `<br>★ ${Math.round(score)}` : ''}
      ${eco ? `<br>${eco}` : ''}
    `;
    tooltipEl.hidden = false;
    tooltipEl.style.left = (event.clientX - rect.left + 12) + 'px';
    tooltipEl.style.top  = (event.clientY - rect.top  - 8)  + 'px';
  }

  function _handle2DHover(e, canvas) {
    const tooltipEl = document.getElementById('map-tooltip');
    if (!_scene2d || !_camera2d) return;
    const sys = _pickSystem(e, canvas, _camera2d, _scene2d);
    _showTooltip(tooltipEl, e, canvas, sys);
  }

  function _handle3DHover(e, canvas) {
    const tooltipEl = document.getElementById('map3d-tooltip');
    if (!_scene3d || !_camera3d) return;
    const sys = _pickSystem(e, canvas, _camera3d, _scene3d);
    _showTooltip(tooltipEl, e, canvas, sys);
  }

  function _handle2DClick(e, canvas) {
    if (!_scene2d || !_camera2d) return;
    const sys = _pickSystem(e, canvas, _camera2d, _scene2d);
    if (sys) { _selectedSystem = sys; openSystemModal(sys); }
  }

  function _handle3DClick(e, canvas) {
    if (!_scene3d || !_camera3d) return;
    const sys = _pickSystem(e, canvas, _camera3d, _scene3d);
    if (sys) { _selectedSystem = sys; openSystemModal(sys); }
  }

  // ── RENDER LOOPS ───────────────────────────────────────────────────────────

  function _startRender2D() {
    if (_animFrameId2d) cancelAnimationFrame(_animFrameId2d);
    function loop() {
      _animFrameId2d = requestAnimationFrame(loop);
      if (_renderer2d && _scene2d && _camera2d) _renderer2d.render(_scene2d, _camera2d);
    }
    loop();
  }

  function _startRender3D() {
    if (_animFrameId3d) cancelAnimationFrame(_animFrameId3d);
    function loop() {
      _animFrameId3d = requestAnimationFrame(loop);
      if (_renderer3d && _scene3d && _camera3d) _renderer3d.render(_scene3d, _camera3d);
    }
    loop();
  }

  // ── SCENE BUILDERS ─────────────────────────────────────────────────────────

  function _buildScene2D() {
    if (!_scene2d) return;
    // Clear existing dynamic objects
    const toRemove = _scene2d.children.filter(c => c._dynamic);
    toRemove.forEach(c => _scene2d.remove(c));

    const colourMode = document.getElementById('map-colour-mode')?.value || 'rating';
    const showWatchlist = document.getElementById('map-show-watchlist')?.checked;
    const showClusters  = document.getElementById('map-show-clusters')?.checked;
    const showRadius    = document.getElementById('map-show-radius')?.checked;
    const showNebulae   = document.getElementById('map-nebula-overlay')?.checked;
    const showLandmarks = document.getElementById('map-show-landmarks')?.checked;
    const showHeat      = document.getElementById('map-show-heat')?.checked;

    const allSystems = [
      ..._resultSystems,
      ...(showClusters ? _clusterSystems : []),
    ];

    const emptyEl = document.getElementById('map-empty');
    if (emptyEl) emptyEl.hidden = allSystems.length > 0;

    if (allSystems.length) {
      const pts = _buildPointCloud(allSystems, colourMode, 'uniform', _refCoords);
      if (pts) { pts._dynamic = true; _scene2d.add(pts); _points2d = pts; }
    }

    if (showWatchlist) {
      const wlSystems = Watchlist.getAll().map(e => ({
        id64: e.id64, name: e.name, x: e.x, y: e.y, z: e.z,
        primaryEconomy: e.economy, _rating: { score: e.score },
      }));
      if (wlSystems.length) {
        const wlPts = _buildPointCloud(wlSystems, 'rating', 'uniform', _refCoords);
        if (wlPts) {
          // Override colour to gold
          const colors = wlPts.geometry.attributes.color;
          for (let i = 0; i < colors.count; i++) {
            colors.setXYZ(i, 0.83, 0.66, 0.20);
          }
          colors.needsUpdate = true;
          wlPts._dynamic = true;
          _scene2d.add(wlPts);
        }
      }
    }

    if (showRadius && _selectedSystem) {
      const rm = _buildRadiusIndicator(_scene2d,
        _selectedSystem.x || 0, _selectedSystem.y || 0, _selectedSystem.z || 0, false);
      rm._dynamic = true;
      _scene2d.add(rm);
    }

    if (showNebulae) {
      const nebGroup = new THREE.Group();
      nebGroup._dynamic = true;
      _buildNebulaeOverlay(nebGroup);
      _scene2d.add(nebGroup);
    }

    if (showLandmarks) {
      const lmGroup = new THREE.Group();
      lmGroup._dynamic = true;
      _buildLandmarkSprites(lmGroup, false);
      _scene2d.add(lmGroup);
    }

    // Reference system marker (crosshair ring)
    if (_refCoords) {
      const { sx, sz } = toScene(_refCoords.x, 0, _refCoords.z);
      const refGeo = new THREE.RingGeometry(0.12, 0.18, 32);
      const refMat = new THREE.MeshBasicMaterial({ color: 0xf97316, transparent: true, opacity: 0.9, side: THREE.DoubleSide });
      const refMesh = new THREE.Mesh(refGeo, refMat);
      refMesh.rotation.x = -Math.PI / 2;
      refMesh.position.set(sx, 0.3, sz);
      refMesh._dynamic = true;
      _scene2d.add(refMesh);
    }

    // Jump route line from ref to selected system
    if (_refCoords && _selectedSystem) {
      const jumpRange = Number(document.getElementById('map-jump-range')?.value || 50);
      const r0 = toScene(_refCoords.x, 0, _refCoords.z);
      const r1 = toScene(_selectedSystem.x || 0, 0, _selectedSystem.z || 0);
      const pts = [new THREE.Vector3(r0.sx, 0.25, r0.sz), new THREE.Vector3(r1.sx, 0.25, r1.sz)];
      const lineGeo = new THREE.BufferGeometry().setFromPoints(pts);
      const lineMat = new THREE.LineDashedMaterial({ color: 0xf97316, dashSize: 0.3, gapSize: 0.15, opacity: 0.6, transparent: true });
      const line = new THREE.Line(lineGeo, lineMat);
      line.computeLineDistances();
      line._dynamic = true;
      _scene2d.add(line);
      // Jump count label
      const dx = (_selectedSystem.x || 0) - _refCoords.x;
      const dy = (_selectedSystem.y || 0) - _refCoords.y;
      const dz = (_selectedSystem.z || 0) - _refCoords.z;
      const dist = Math.sqrt(dx*dx + dy*dy + dz*dz);
      const jumps = jumpRange > 0 ? Math.ceil(dist / jumpRange) : '?';
      const detailEl = document.getElementById('map-detail-panel');
      if (detailEl && _selectedSystem) {
        detailEl.hidden = false;
        detailEl.innerHTML = `<strong>${_selectedSystem.name || 'Selected'}</strong><br>
          ${Math.round(dist)} ly from ref · ~${jumps} jumps @ ${jumpRange} ly`;
      }
    }

    _buildLegend2D(colourMode);

    // Density heat overlay (2D canvas overlay)
    if (showHeat && allSystems.length) {
      // Defer slightly so the Three.js frame has rendered first
      setTimeout(() => _buildHeatOverlay(allSystems), 50);
    } else {
      _clearHeatOverlay();
    }
  }

  function _buildScene3D() {
    if (!_scene3d) return;
    const toRemove = _scene3d.children.filter(c => c._dynamic);
    toRemove.forEach(c => _scene3d.remove(c));

    const colourMode = document.getElementById('map3d-colour-mode')?.value || 'rating';
    const sizeMode   = document.getElementById('map3d-size-mode')?.value   || 'uniform';
    const showWatchlist = document.getElementById('map3d-show-watchlist')?.checked;
    const showClusters  = document.getElementById('map3d-show-clusters')?.checked;
    const showRadius    = document.getElementById('map3d-show-radius')?.checked;
    const showLandmarks = document.getElementById('map3d-show-landmarks')?.checked;

    const allSystems = [
      ..._resultSystems,
      ...(showClusters ? _clusterSystems : []),
    ];

    const emptyEl = document.getElementById('map3d-empty');
    if (emptyEl) emptyEl.hidden = allSystems.length > 0;

    if (allSystems.length) {
      const pts = _buildPointCloud(allSystems, colourMode, sizeMode, _refCoords);
      if (pts) { pts._dynamic = true; _scene3d.add(pts); _points3d = pts; }
    }

    if (showWatchlist) {
      const wlSystems = Watchlist.getAll().map(e => ({
        id64: e.id64, name: e.name, x: e.x, y: e.y, z: e.z,
        primaryEconomy: e.economy, _rating: { score: e.score },
      }));
      if (wlSystems.length) {
        const wlPts = _buildPointCloud(wlSystems, 'rating', 'uniform', _refCoords);
        if (wlPts) {
          const colors = wlPts.geometry.attributes.color;
          for (let i = 0; i < colors.count; i++) colors.setXYZ(i, 0.83, 0.66, 0.20);
          colors.needsUpdate = true;
          wlPts._dynamic = true;
          _scene3d.add(wlPts);
        }
      }
    }

    if (showRadius && _selectedSystem) {
      const rm = _buildRadiusIndicator(_scene3d,
        _selectedSystem.x || 0, _selectedSystem.y || 0, _selectedSystem.z || 0, true);
      rm._dynamic = true;
      _scene3d.add(rm);
    }

    if (showLandmarks) {
      const lmGroup = new THREE.Group();
      lmGroup._dynamic = true;
      _buildLandmarkSprites(lmGroup, true);
      _scene3d.add(lmGroup);
    }

    // Reference system marker (orange sphere)
    if (_refCoords) {
      const { sx, sy, sz } = toScene(_refCoords.x, _refCoords.y || 0, _refCoords.z);
      const refGeo = new THREE.SphereGeometry(0.4, 12, 8);
      const refMat = new THREE.MeshBasicMaterial({ color: 0xf97316 });
      const refMesh = new THREE.Mesh(refGeo, refMat);
      refMesh.position.set(sx, sy, sz);
      refMesh._dynamic = true;
      _scene3d.add(refMesh);
    }

    // Jump route line from ref to selected system (3D)
    if (_refCoords && _selectedSystem) {
      const r0 = toScene(_refCoords.x, _refCoords.y || 0, _refCoords.z);
      const r1 = toScene(_selectedSystem.x || 0, _selectedSystem.y || 0, _selectedSystem.z || 0);
      const pts3 = [new THREE.Vector3(r0.sx, r0.sy, r0.sz), new THREE.Vector3(r1.sx, r1.sy, r1.sz)];
      const lg3 = new THREE.BufferGeometry().setFromPoints(pts3);
      const lm3 = new THREE.LineDashedMaterial({ color: 0xf97316, dashSize: 0.4, gapSize: 0.2, opacity: 0.7, transparent: true });
      const line3 = new THREE.Line(lg3, lm3);
      line3.computeLineDistances();
      line3._dynamic = true;
      _scene3d.add(line3);
    }
  }

  // ── LEGEND ─────────────────────────────────────────────────────────────────

  function _buildLegend2D(colourMode) {
    const legendEl = document.getElementById('map-legend');
    if (!legendEl) return;
    let items = [];
    if (colourMode === 'rating') {
      items = [
        { color: '#22c55e', label: 'Score ≥ 75' },
        { color: '#d4a832', label: 'Score 50–74' },
        { color: '#f97316', label: 'Score 25–49' },
        { color: '#6b8599', label: 'Score < 25' },
      ];
    } else if (colourMode === 'economy') {
      items = Object.entries(ECO_COLORS).slice(0, 7).map(([eco, hex]) => ({
        color: '#' + hex.toString(16).padStart(6, '0'),
        label: eco.charAt(0).toUpperCase() + eco.slice(1),
      }));
    } else if (colourMode === 'population') {
      items = [
        { color: '#22c55e', label: 'Uncolonised' },
        { color: '#6b8599', label: 'Colonised' },
      ];
    }
    items.push({ color: '#ffd700', label: 'Watchlist' });
    legendEl.innerHTML = items.map(i =>
      `<div class="legend-item"><span class="legend-dot" style="background:${i.color}"></span>${i.label}</div>`
    ).join('');
  }

  // ── SAVE PNG ───────────────────────────────────────────────────────────────

  function _savePng(renderer, filename) {
    if (!renderer) return;
    renderer.render(renderer._scene, renderer._camera);
    const url = renderer.domElement.toDataURL('image/png');
    const a = document.createElement('a');
    a.href = url; a.download = filename; a.click();
  }

  // ── PUBLIC API ─────────────────────────────────────────────────────────────

  function setResults(systems) {
    _resultSystems = systems || [];
  }

  function setClusters(clusters) {
    _clusterSystems = (clusters || []).map(c => ({
      id64: c.anchor_id64 || c.system_id64,
      name: c.anchor_name || c.name,
      x: c.anchor_coords?.x ?? c.x,
      y: c.anchor_coords?.y ?? c.y,
      z: c.anchor_coords?.z ?? c.z,
      primaryEconomy: null,
      _rating: { score: c.total_best_score ?? c.coverage_score },
    }));
  }

  function setRef(coords) {
    _refCoords = coords ? { x: coords.x ?? 0, y: coords.y ?? 0, z: coords.z ?? 0 } : null;
  }

  function setSelected(sys) {
    _selectedSystem = sys;
  }

  // Focus the 2D map on a specific system: switch to map tab, pan camera, highlight, redraw
  function focusSystem(sys) {
    if (!sys) return;
    _selectedSystem = sys;
    // Switch to map tab
    const mapTab = document.querySelector('.nav-btn[data-tab="map"]');
    if (mapTab) mapTab.click();
    // Pan 2D camera to the system after a short delay (tab switch needs time)
    setTimeout(() => {
      if (!_camera2d) { draw2D(); return; }
      const { sx, sz } = toScene(sys.x || 0, 0, sys.z || 0);
      const viewW = _camera2d.right - _camera2d.left;
      const viewH = _camera2d.top - _camera2d.bottom;
      _camera2d.position.x = sx;
      _camera2d.position.z = sz;
      _camera2d.left   = sx - viewW / 2;
      _camera2d.right  = sx + viewW / 2;
      _camera2d.top    = -sz + viewH / 2;
      _camera2d.bottom = -sz - viewH / 2;
      _camera2d.updateProjectionMatrix();
      _buildScene2D();
      // Also enable the 500 ly radius overlay
      const radiusChk = document.getElementById('map-show-radius');
      if (radiusChk && !radiusChk.checked) { radiusChk.checked = true; }
      _buildScene2D();
    }, 120);
  }

  // Viewport persistence: save/restore camera state to localStorage
  function saveViewport() {
    if (!_camera2d) return;
    try {
      const vp = {
        x: _camera2d.position.x, z: _camera2d.position.z,
        viewH: _camera2d.top - _camera2d.bottom,
      };
      localStorage.setItem('edmap_viewport', JSON.stringify(vp));
    } catch (e) { /* ignore */ }
  }

  function restoreViewport() {
    if (!_camera2d) return;
    try {
      const raw = localStorage.getItem('edmap_viewport');
      if (!raw) return;
      const vp = JSON.parse(raw);
      const canvas = document.getElementById('galactic-map');
      const aspect = canvas ? canvas.clientWidth / canvas.clientHeight : 4/3;
      const viewH = vp.viewH || 8;
      const viewW = viewH * aspect;
      _camera2d.position.x = vp.x || 0;
      _camera2d.position.z = vp.z || 0;
      _camera2d.left   = vp.x - viewW / 2;
      _camera2d.right  = vp.x + viewW / 2;
      _camera2d.top    = -vp.z + viewH / 2;
      _camera2d.bottom = -vp.z - viewH / 2;
      _camera2d.updateProjectionMatrix();
    } catch (e) { /* ignore */ }
  }

  function draw2D() {
    if (!init2D()) return;
    _buildScene2D();
    _startRender2D();
  }

  function draw3D() {
    if (!init3D()) return;
    _buildScene3D();
    _startRender3D();
  }

  function reset2D() {
    if (!_camera2d) return;
    const aspect = (document.getElementById('galactic-map')?.clientWidth || 800) /
                   (document.getElementById('galactic-map')?.clientHeight || 600);
    const viewSize = 800;
    _camera2d.left   = -viewSize * aspect * SCALE / 2;
    _camera2d.right  =  viewSize * aspect * SCALE / 2;
    _camera2d.top    =  viewSize * SCALE / 2;
    _camera2d.bottom = -viewSize * SCALE / 2;
    _camera2d.position.set(0, 100, 0);
    _camera2d.updateProjectionMatrix();
  }

  function reset3D() {
    const canvas = document.getElementById('map3d-canvas');
    if (canvas?._resetCamera) canvas._resetCamera();
  }

  // ── WIRE UP CONTROLS ───────────────────────────────────────────────────────

  (function wireControls() {
    // 2D controls
    const redrawBtn  = document.getElementById('map-redraw-btn');
    const resetBtn   = document.getElementById('map-reset-btn');
    const savePngBtn = document.getElementById('map-save-png-btn');
    const colourSel  = document.getElementById('map-colour-mode');
    const topNSlider = document.getElementById('map-top-n');
    const topNVal    = document.getElementById('map-top-n-val');

    if (redrawBtn)  redrawBtn.addEventListener('click',  () => draw2D());
    if (resetBtn)   resetBtn.addEventListener('click',   () => { reset2D(); draw2D(); });
    if (savePngBtn) savePngBtn.addEventListener('click', () => {
      if (_renderer2d) { _renderer2d._scene = _scene2d; _renderer2d._camera = _camera2d; _savePng(_renderer2d, 'ed-finder-map.png'); }
    });
    if (colourSel)  colourSel.addEventListener('change', () => { if (_scene2d) _buildScene2D(); });
    if (topNSlider) topNSlider.addEventListener('input', () => {
      if (topNVal) topNVal.textContent = topNSlider.value;
    });

    // Overlay checkboxes 2D
    ['map-show-watchlist','map-show-clusters','map-show-radius','map-nebula-overlay','map-show-landmarks','map-show-heat'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.addEventListener('change', () => { if (_scene2d) _buildScene2D(); });
    });

    // 3D controls
    const reset3dBtn   = document.getElementById('map3d-reset-btn');
    const savePng3dBtn = document.getElementById('map3d-save-png-btn');
    const colour3dSel  = document.getElementById('map3d-colour-mode');
    const size3dSel    = document.getElementById('map3d-size-mode');

    if (reset3dBtn)   reset3dBtn.addEventListener('click',   () => { reset3D(); });
    if (savePng3dBtn) savePng3dBtn.addEventListener('click', () => {
      if (_renderer3d) { _renderer3d._scene = _scene3d; _renderer3d._camera = _camera3d; _savePng(_renderer3d, 'ed-finder-3d.png'); }
    });
    if (colour3dSel)  colour3dSel.addEventListener('change', () => { if (_scene3d) _buildScene3D(); });
    if (size3dSel)    size3dSel.addEventListener('change',   () => { if (_scene3d) _buildScene3D(); });

    ['map3d-show-watchlist','map3d-show-clusters','map3d-show-radius','map3d-show-landmarks'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.addEventListener('change', () => { if (_scene3d) _buildScene3D(); });
    });
  })();

  // ── LISTEN FOR SEARCH RESULTS ─────────────────────────────────────────────

  // When local search or cluster search completes, update the map data
  document.addEventListener('ed:searchresults', (e) => {
    setResults(e.detail.systems || []);
    if (e.detail.ref) setRef(e.detail.ref);
    // If map tab is active, redraw immediately
    if (document.getElementById('tab-map')?.classList.contains('active')) draw2D();
    if (document.getElementById('tab-map3d')?.classList.contains('active')) draw3D();
  });

  document.addEventListener('ed:clusterresults', (e) => {
    setClusters(e.detail.clusters || []);
    // Auto-enable cluster overlay when cluster results arrive
    const clChk2d = document.getElementById('map-show-clusters');
    const clChk3d = document.getElementById('map3d-show-clusters');
    if (clChk2d) clChk2d.checked = true;
    if (clChk3d) clChk3d.checked = true;
    if (document.getElementById('tab-map')?.classList.contains('active')) draw2D();
    if (document.getElementById('tab-map3d')?.classList.contains('active')) draw3D();
  });

  document.addEventListener('ed:clusterrefcoords', (e) => {
    setRef(e.detail);
  });

  // Jump range slider wiring (map tab)
  (function wireJumpRange() {
    const slider = document.getElementById('map-jump-range');
    const valEl  = document.getElementById('map-jump-range-val');
    if (!slider) return;
    slider.addEventListener('input', () => {
      if (valEl) valEl.textContent = slider.value + ' ly';
      if (_scene2d) _buildScene2D();
    });
  })();

  // Save viewport on pan/zoom (throttled)
  let _vpSaveTimer = null;
  function _scheduleViewportSave() {
    clearTimeout(_vpSaveTimer);
    _vpSaveTimer = setTimeout(saveViewport, 800);
  }
  document.addEventListener('ed:panned', _scheduleViewportSave);
  // Restore viewport when 2D map first draws
  const _origDraw2D = draw2D;
  function draw2DWithRestore() {
    _origDraw2D();
    setTimeout(restoreViewport, 80);
  }

  // Keyboard shortcuts
  document.addEventListener('keydown', (e) => {
    // Ignore when typing in an input
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') return;
    if (e.key === 'm' || e.key === 'M') {
      if (e.shiftKey) {
        document.querySelector('.nav-btn[data-tab="map3d"]')?.click();
      } else {
        document.querySelector('.nav-btn[data-tab="map"]')?.click();
      }
    }
  });

  return { draw2D: draw2DWithRestore, draw3D, reset2D, reset3D, setResults, setClusters, setRef, setSelected, focusSystem, saveViewport, restoreViewport };
})();

window.EDMap = EDMap;

// ═══════════════════════════════════════════════════════════ KEYBOARD NAVIGATION
(function initKeyboardNav() {
  let focusedIdx = -1;
  function getCards() {
    const activePanel = document.querySelector('.tab-panel.active .results-list');
    if (!activePanel) return [];
    return Array.from(activePanel.querySelectorAll('.system-card, .cluster-card'));
  }
  function setFocus(idx) {
    const cards = getCards();
    if (!cards.length) return;
    focusedIdx = Math.max(0, Math.min(idx, cards.length - 1));
    cards.forEach((c, i) => c.classList.toggle('keyboard-focused', i === focusedIdx));
    cards[focusedIdx].scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
  function clearFocus() {
    getCards().forEach(c => c.classList.remove('keyboard-focused'));
    focusedIdx = -1;
  }
  document.addEventListener('keydown', (e) => {
    if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') return;
    if (qs('#system-modal') && !qs('#system-modal').hidden) return;
    const cards = getCards();
    if (!cards.length) return;
    if (e.key === 'ArrowDown' || e.key === 'j') { e.preventDefault(); setFocus(focusedIdx < 0 ? 0 : focusedIdx + 1); }
    else if (e.key === 'ArrowUp' || e.key === 'k') { e.preventDefault(); setFocus(focusedIdx <= 0 ? 0 : focusedIdx - 1); }
    else if (e.key === 'Enter' && focusedIdx >= 0) { e.preventDefault(); cards[focusedIdx]?.click(); }
    else if (e.key === 'Escape') clearFocus();
  });
  document.querySelectorAll('.nav-btn').forEach(btn => btn.addEventListener('click', clearFocus));
})();


// ═══════════════════════════════════════════════════════════ HELP POPOVER SYSTEM
(function initHelpSystem() {
  const HELP = {
    'ref-system': {
      title: 'Reference System',
      body: '<p>The system you are searching <em>from</em>. Start typing any system name — the field autocompletes from the database of 186 million systems.</p><p>Common starting points: <strong>Sol</strong> (human bubble), <strong>Colonia</strong> (~22,000 ly from Sol), <strong>Sagittarius A*</strong> (galactic centre).</p><p>Once selected, the system coordinates are shown below the field and used for all distance calculations.</p>'
    },
    'distance': {
      title: 'Max Distance',
      body: '<p>Only return systems within this many light years of your reference system.</p><ul><li><strong>50–200 ly</strong> — immediate neighbourhood, easy supply runs</li><li><strong>500 ly</strong> — standard colonisation bubble</li><li><strong>1,000+ ly</strong> — deep space expansion</li></ul><p>Enable <strong>Galaxy-wide</strong> to ignore this limit and search all 186 million systems.</p>'
    },
    'population': {
      title: 'Population Filter',
      body: '<p><strong>Any</strong> — returns all systems regardless of colonisation status.</p><p><strong>Uncolonised</strong> — only returns systems with population = 0. These are available for colonisation. Already-colonised systems cannot be claimed.</p>'
    },
    'economy': {
      title: 'Economy Types',
      body: '<p>The primary economy type determines what a colonised station produces and what commodities it demands.</p><table style="width:100%;border-collapse:collapse;font-size:0.82rem"><tr style="border-bottom:1px solid #334"><th style="text-align:left;padding:3px 6px">Economy</th><th style="text-align:left;padding:3px 6px">Key output</th></tr><tr><td style="padding:3px 6px">Agriculture</td><td style="padding:3px 6px">Food, Grain, CMM Composites</td></tr><tr><td style="padding:3px 6px">Refinery</td><td style="padding:3px 6px">Metals, Steel, Titanium</td></tr><tr><td style="padding:3px 6px">Industrial</td><td style="padding:3px 6px">Machinery, Consumer goods</td></tr><tr><td style="padding:3px 6px">High Tech</td><td style="padding:3px 6px">Technology, Computers</td></tr><tr><td style="padding:3px 6px">Military</td><td style="padding:3px 6px">Weapons, Battle weapons</td></tr><tr><td style="padding:3px 6px">Tourism</td><td style="padding:3px 6px">Passenger cabins, Luxury goods</td></tr><tr><td style="padding:3px 6px">Extraction</td><td style="padding:3px 6px">Ore, Minerals</td></tr><tr><td style="padding:3px 6px">Colony</td><td style="padding:3px 6px">Basic essentials</td></tr></table>'
    },
    'rating': {
      title: 'Suitability Score (0–100)',
      body: '<p>A composite score measuring how suitable a system is for a given economy type.</p><p><strong>Factors:</strong> star type, planetary bodies (Earth-likes, water worlds, terraformables boost the score), biological/geological signals, distance from the bubble.</p><ul><li><span style="color:#22c55e">■</span> <strong>80–100</strong> — Excellent: rare, highly desirable</li><li><span style="color:#a3e635">■</span> <strong>65–79</strong> — Good: strong candidate</li><li><span style="color:#facc15">■</span> <strong>45–64</strong> — Average: viable</li><li><span style="color:#f97316">■</span> <strong>0–44</strong> — Poor: limited suitability</li></ul><p>A threshold of <strong>65+</strong> is a good starting point.</p>'
    },
    'body-filters': {
      title: 'Body Filters',
      body: '<p>Filter systems by the types of bodies they contain. Set a minimum count — only systems with at least that many of that body type are returned.</p><ul><li><strong>Earth-like</strong> — Rare worlds with breathable atmospheres</li><li><strong>Water World</strong> — Ocean worlds</li><li><strong>Ammonia World</strong> — Ammonia-atmosphere worlds</li><li><strong>Gas Giant</strong> — Any gas giant (Class I–V)</li><li><strong>Neutron Star</strong> — Useful for FSD supercharging</li><li><strong>Bio Signals</strong> — Has biological signals (Odyssey)</li><li><strong>Geo Signals</strong> — Has geological signals</li><li><strong>Terraformable</strong> — Has at least one terraformable body</li></ul>'
    },
    'presets': {
      title: 'Quick Presets',
      body: '<p>Presets fill in the economy requirements automatically for common colony configurations:</p><ul><li><strong>Full Colony Stack</strong> — All six types: Agriculture, Refinery, Industrial, High Tech, Military, Tourism.</li><li><strong>Industry + Refinery</strong> — Core production chain for manufacturing colonies.</li><li><strong>Agri + HiTech</strong> — Food production paired with advanced technology.</li><li><strong>Military + Tourism</strong> — Defence and passenger income.</li><li><strong>Core Three</strong> — Agriculture, Industrial, High Tech — minimum viable diversified colony.</li></ul>'
    },
    'cluster-sort': {
      title: 'Sort Options',
      body: '<ul><li><strong>Coverage Score</strong> — Composite: how many required economy types are satisfied + quality of the best system for each type + diversity. Best overall ranking.</li><li><strong>Total Viable</strong> — Total systems in the 500 ly bubble scoring 65+ for any economy.</li><li><strong>Distance</strong> — Distance from your reference system (set in Local Search first).</li><li><strong>Diversity</strong> — Number of distinct economy types present in the bubble.</li></ul>'
    },
    'map-colour': {
      title: 'Map Colour Modes',
      body: '<ul><li><strong>Rating</strong> — Green (high score) to orange to grey (low score).</li><li><strong>Economy</strong> — Each economy type has a distinct colour: Agriculture (green), Refinery (orange), Industrial (blue), High Tech (cyan), Military (red), Tourism (pink).</li><li><strong>Distance from Ref</strong> — Blue (close) to red (far). Requires a reference system.</li><li><strong>Population</strong> — Bright green = uncolonised, dim = already colonised.</li></ul>'
    },
    'jump-range': {
      title: 'Jump Range',
      body: '<p>Your ship maximum jump range in light years. Used to estimate the hop count to reach a selected system from your reference point.</p><p>When you click a dot on the map, a dashed line appears labelled with the estimated hops (straight-line distance divided by jump range).</p><p>Typical ranges: 30–50 ly (standard), 60–80 ly (engineered), 80–120 ly (exploration builds).</p>'
    }
  };

  const popover    = document.getElementById('help-popover');
  const popContent = document.getElementById('help-popover-content');
  const popClose   = document.getElementById('help-popover-close');
  if (!popover || !popContent) return;

  function showHelp(key, anchorEl) {
    const data = HELP[key];
    if (!data) return;
    popContent.innerHTML = '<h3 class="help-popover-title">' + data.title + '</h3>' + data.body;
    popover.hidden = false;
    const rect = anchorEl.getBoundingClientRect();
    const pw = 320;
    let left = rect.right + 10;
    let top  = rect.top;
    if (left + pw > window.innerWidth - 12) left = rect.left - pw - 10;
    if (left < 8) left = 8;
    const ph = popover.offsetHeight || 200;
    if (top + ph > window.innerHeight - 12) top = window.innerHeight - ph - 12;
    if (top < 8) top = 8;
    popover.style.left = left + 'px';
    popover.style.top  = top  + 'px';
  }

  function hideHelp() { popover.hidden = true; }

  document.addEventListener('click', (e) => {
    const btn = e.target.closest('.help-icon');
    if (btn) {
      e.preventDefault();
      e.stopPropagation();
      const key = btn.dataset.help;
      if (!popover.hidden && popover.dataset.activeKey === key) {
        hideHelp();
      } else {
        popover.dataset.activeKey = key;
        showHelp(key, btn);
      }
      return;
    }
    if (!popover.hidden && !popover.contains(e.target)) hideHelp();
  });

  if (popClose) popClose.addEventListener('click', hideHelp);

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !popover.hidden) hideHelp();
  });
})();
