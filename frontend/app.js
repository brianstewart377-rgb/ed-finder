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
    if (q.length < 2) { listEl.hidden = true; return; }
    debounce = setTimeout(async () => {
      try {
        const d = await apiFetch(`/api/autocomplete?q=${encodeURIComponent(q)}`);
        items = d.results || [];
        render();
      } catch {}
    }, 200);
  });

  function render() {
    if (!items.length) { listEl.hidden = true; return; }
    listEl.innerHTML = '';
    listEl.hidden = false;
    highlighted = -1;
    items.forEach((item, i) => {
      const li = document.createElement('li');
      li.className = 'autocomplete-item';
      li.textContent = item.name;
      li.addEventListener('click', () => select(i));
      listEl.appendChild(li);
    });
  }

  function select(idx) {
    const item = items[idx];
    if (!item) return;
    inputEl.value = item.name;
    listEl.hidden = true;
    onSelect(item);
  }

  inputEl.addEventListener('keydown', (e) => {
    if (listEl.hidden) return;
    const lis = listEl.querySelectorAll('li');
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      highlighted = (highlighted + 1) % lis.length;
      updateHighlight(lis);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      highlighted = (highlighted - 1 + lis.length) % lis.length;
      updateHighlight(lis);
    } else if (e.key === 'Enter' && highlighted >= 0) {
      e.preventDefault();
      select(highlighted);
    } else if (e.key === 'Escape') {
      listEl.hidden = true;
    }
  });

  function updateHighlight(lis) {
    lis.forEach((li, i) => li.classList.toggle('highlighted', i === highlighted));
  }

  document.addEventListener('click', (e) => { if (e.target !== inputEl) listEl.hidden = true; });
}

// ═══════════════════════════════════════════════════════════════ SYSTEM MODAL

let _modalSys = null;
async function openSystemModal(sys) {
  _modalSys = sys;
  const modal = qs('#system-modal');
  const content = qs('#modal-content');
  modal.hidden = false;
  document.body.style.overflow = 'hidden';
  content.innerHTML = `<div class="loading-state"><div class="spinner"></div>Loading system data…</div>`;

  try {
    const d = await apiFetch(`/api/systems/${sys.id64}`);
    const r = d._rating || {};
    const score = r.score != null ? Math.round(r.score) : '—';
    const eco = d.primary_economy || d.primaryEconomy;
    const star = starLabel(d.main_star_type, d.main_star_subtype);
    const pop = Number(d.population || 0);

    content.innerHTML = `
      <div class="modal-header">
        <h2 class="modal-system-name" id="modal-system-name">${d.name}</h2>
        <div class="modal-system-id">ID64: ${d.id64}</div>
      </div>

      <div class="modal-grid">
        <div class="modal-field"><span class="modal-field-label">Coords</span><span class="modal-field-value">${fmtCoord(d.x)}, ${fmtCoord(d.y)}, ${fmtCoord(d.z)}</span></div>
        <div class="modal-field"><span class="modal-field-label">Distance</span><span class="modal-field-value">${fmtDist(distFromSol(d.x, d.y, d.z))} from Sol</span></div>
        <div class="modal-field"><span class="modal-field-label">Economy</span><span class="modal-field-value accent">${eco || 'None'}</span></div>
        <div class="modal-field"><span class="modal-field-label">Population</span><span class="modal-field-value">${pop === 0 ? 'Uncolonised' : popLabel(pop)}</span></div>
        <div class="modal-field"><span class="modal-field-label">Star Type</span><span class="modal-field-value">${star || 'Unknown'}</span></div>
        <div class="modal-field"><span class="modal-field-label">Security</span><span class="modal-field-value">${d.security || 'Unknown'}</span></div>
      </div>

      <div class="modal-section">
        <h3 class="modal-section-title">Colonisation Rating</h3>
        <div class="modal-score-grid">
          <div class="modal-score-item">
            <div class="modal-score-label">Overall</div>
            <div class="modal-score-value" style="color:${scoreColor(score)}">${score}</div>
            <div class="modal-score-bar"><div class="modal-score-bar-fill" style="width:${score}%;background:${scoreColor(score)}"></div></div>
          </div>
          <div class="modal-score-item">
            <div class="modal-score-label">Diversity</div>
            <div class="modal-score-value">${r.economy_diversity || 0}</div>
            <div class="modal-score-bar"><div class="modal-score-bar-fill" style="width:${(r.economy_diversity / 6) * 100}%;background:var(--blue)"></div></div>
          </div>
          <div class="modal-score-item">
            <div class="modal-score-label">Body Count</div>
            <div class="modal-score-value">${d.body_count || 0}</div>
          </div>
        </div>
      </div>

      <div class="modal-section">
        <h3 class="modal-section-title">Notable Bodies</h3>
        <div class="body-list">
          ${(d.bodies || []).filter(b => b.is_notable).map(b => `
            <div class="body-row">
              <span class="body-row-name">${b.name}</span>
              <span class="body-row-type">${b.type}</span>
              <span class="body-row-dist">${fmtNum(b.distance_to_arrival)} ls</span>
            </div>
          `).join('') || '<div class="empty-state">No notable bodies found</div>'}
        </div>
      </div>

      <div class="modal-footer" style="margin-top:2rem;display:flex;gap:1rem">
        <button id="modal-watchlist-btn" class="watchlist-add-btn ${Watchlist.has(d.id64) ? 'saved' : ''}">
          ${Watchlist.has(d.id64) ? '★ Saved — click to remove' : '☆ Save to Watchlist'}
        </button>
        <button id="modal-show-on-map-btn" class="io-btn">🌌 Show on Map</button>
        <a href="https://www.edsm.net/en/system/id/${d.id64}/name/${encodeURIComponent(d.name)}" target="_blank" class="modal-edsm-link">View on EDSM ↗</a>
      </div>

      <div class="modal-section" style="margin-top:2rem">
        <h3 class="modal-section-title">Commander Notes</h3>
        <textarea id="modal-note-area" class="num-input" placeholder="Add your notes about this system..." style="min-height:80px;resize:vertical"></textarea>
        <div style="display:flex;justify-content:space-between;align-items:center;margin-top:0.5rem">
          <span id="modal-note-status" class="note-status"></span>
          <div style="display:flex;gap:0.5rem">
            <button id="modal-note-delete" class="remove-btn" hidden style="font-size:0.8rem">Delete</button>
            <button id="modal-note-save" class="search-btn" style="margin:0;padding:0.4rem 1rem;width:auto">Save Note</button>
          </div>
        </div>
      </div>
    `;

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
          await apiFetch(`/api/systems/${sys.id64}/note`, { method: 'DELETE' });
          noteArea.value = '';
          noteDelete.hidden = true;
          if (noteStatus) { noteStatus.textContent = 'Deleted'; noteStatus.className = 'note-status deleted'; setTimeout(() => { noteStatus.textContent = ''; }, 2000); }
        });
      }
    }
  } catch (err) {
    content.innerHTML = `<div class="error-state">⚠ Failed to load system data: ${err.message}</div>`;
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
  const resultsEl   = qs('#local-results');
  const headerEl    = qs('#local-results-header');
  const countEl     = qs('#local-results-count');
  const searchBtn   = qs('#local-search-btn');

  let refCoords = null;

  makeAutocomplete(refInput, refList, (item) => {
    refCoords = { x: item.x, y: item.y, z: item.z };
    coordDisp.hidden = false;
    qs('#local-coord-x').textContent = `X: ${fmtCoord(item.x)}`;
    qs('#local-coord-y').textContent = `Y: ${fmtCoord(item.y)}`;
    qs('#local-coord-z').textContent = `Z: ${fmtCoord(item.z)}`;
    // Broadcast ref coords to other components
    document.dispatchEvent(new CustomEvent('ed:refcoords', { detail: refCoords }));
  });

  distSlider.addEventListener('input', () => { distVal.textContent = `${distSlider.value} ly`; });
  ratingSlider.addEventListener('input', () => { ratingVal.textContent = ratingSlider.value; });

  searchBtn.addEventListener('click', async () => {
    if (!refCoords && !galaxyWide.checked) { toast('Select a reference system or enable Galaxy-wide'); return; }

    const popRadio = document.querySelector('input[name="local-pop"]:checked');
    const payload = {
      x: refCoords?.x, y: refCoords?.y, z: refCoords?.z,
      max_dist:    galaxyWide.checked ? null : Number(distSlider.value),
      min_rating:  Number(ratingSlider.value),
      economy:     qs('#local-economy').value,
      population:  popRadio ? popRadio.value : 'any',
      limit:       50,
    };

    setLoading(true);
    try {
      const d = await apiFetch('/api/local/search', { method: 'POST', body: JSON.stringify(payload) });
      renderResults(d.results || [], d.total || 0);
    } catch (e) { showError(e.message); }
    finally { setLoading(false); }
  });

  function setLoading(on) {
    searchBtn.disabled = on;
    searchBtn.classList.toggle('loading', on);
    if (on) { resultsEl.innerHTML = `<div class="loading-state"><div class="spinner"></div>Searching systems…</div>`; headerEl.hidden = true; }
  }

  function showError(msg) { resultsEl.innerHTML = `<div class="error-state">⚠ Search failed: ${msg}</div>`; }

  function renderResults(results, total) {
    resultsEl.innerHTML = '';
    if (!results.length) {
      resultsEl.innerHTML = `<div class="empty-state"><div class="empty-icon">⊕</div><div class="empty-title">No systems found</div><div class="empty-sub">Try increasing distance or lowering rating</div></div>`;
      headerEl.hidden = true; return;
    }
    countEl.innerHTML = `Found <strong>${fmtNum(total)}</strong> systems`;
    headerEl.hidden = false;
    results.forEach((sys, i) => resultsEl.appendChild(buildSystemCard(sys, i + 1)));
    // Broadcast results to map
    document.dispatchEvent(new CustomEvent('ed:searchresults', { detail: { systems: results, ref: refCoords } }));
  }
})();

// ═══════════════════════════════════════════════════════════════ GALAXY SEARCH

(function initGalaxySearch() {
  const searchBtn = qs('#galaxy-search-btn');
  const resultsEl = qs('#galaxy-results');
  const headerEl  = qs('#galaxy-results-header');
  const countEl   = qs('#galaxy-results-count');
  const paginEl  = qs('#galaxy-pagination');

  const PAGE_SIZE = 50;
  let currentPage = 1;
  let lastParams = {};

  searchBtn.addEventListener('click', () => { currentPage = 1; doSearch(); });

  async function doSearch() {
    const popRadio = document.querySelector('input[name="galaxy-pop"]:checked');
    const params = {
      economy:    qs('#galaxy-economy').value,
      min_rating: Number(qs('#galaxy-rating-slider').value),
      population: popRadio ? popRadio.value : 'any',
      limit:      PAGE_SIZE,
      offset:     (currentPage - 1) * PAGE_SIZE,
    };
    lastParams = params;

    setLoading(true);
    try {
      const d = await apiFetch('/api/search/galaxy', { method: 'POST', body: JSON.stringify(params) });
      renderResults(d.results || [], d.total || 0);
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

  function addEvent(event) {
    if (paused) return;
    eventCount++;
    countEl.textContent = eventCount;

    const li = document.createElement('li');
    li.className = 'feed-item';
    li.innerHTML = `
      <div class="feed-item-header">
        <span class="feed-item-type">${event.type || 'Event'}</span>
        <span class="feed-item-time">${fmtRelTime(event.timestamp)}</span>
      </div>
      <div class="feed-item-name">${event.system_name || 'Unknown'}</div>
    `;
    li.addEventListener('click', () => openSystemModal({ id64: event.id64, name: event.system_name }));

    feedEl.prepend(li);
    if (feedEl.children.length > MAX_EVENTS) feedEl.lastElementChild.remove();
  }

  function connect() {
    if (es) es.close();
    dotEl.className = 'feed-dot connecting';
    es = new EventSource('/api/events/live');

    es.onopen = () => { dotEl.className = 'feed-dot active'; };
    es.onerror = () => {
      dotEl.className = 'feed-dot inactive';
      setTimeout(connect, 5000);
    };
    es.onmessage = (e) => {
      try { const data = JSON.parse(e.data); if (data && data.id64) addEvent(data); }
      catch {}
    };
  }

  toggleEl.addEventListener('click', () => {
    paused = !paused;
    toggleEl.textContent = paused ? 'Resume' : 'Pause';
    toggleEl.classList.toggle('paused', paused);
  });

  connect();

  // Load initial recent events
  apiFetch('/api/events/recent')
    .then(data => { (data.events || []).reverse().forEach(addEvent); })
    .catch(() => {});
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
          li.innerHTML = `<span class="cl-name">${c.name || 'Unknown'}</span><span class="cl-field">${c.field_changed || ''}</span><span class="cl-old">${c.old_value ?? '—'}</span><span class="cl-arrow">→</span><span class="cl-new">${c.new_value ?? '—'}</span><span class="cl-ts">${ts}</span>`;
          li.addEventListener('click', () => openSystemModal({ id64: c.system_id64, name: c.name }));
          list.appendChild(li);
        });
      })
      .catch(() => {});
  }
  document.querySelectorAll('.nav-btn[data-tab="watchlist"]').forEach(btn => btn.addEventListener('click', loadChangelog));
  loadChangelog();
})();
