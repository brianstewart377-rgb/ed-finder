/* ═══════════════════════════════════════════════════════════════════════════
   ED Finder — Frontend Application v2.1
   ═══════════════════════════════════════════════════════════════════════════ */

'use strict';

// ═══════════════════════════════════════════════════════════════ UTILITIES

function qs(sel, root = document) { return root.querySelector(sel); }
function qsa(sel, root = document) { return [...root.querySelectorAll(sel)]; }

async function apiFetch(path, opts = {}) {
  const res = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

let _toastTimer;
function toast(msg, dur = 3000) {
  const el = qs('#toast');
  if (!el) return;
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
    if (badge) {
      badge.textContent = n;
      badge.hidden = n === 0;
    }
  },
};
Watchlist.load();

// ═══════════════════════════════════════════════════════════════ NAVBAR

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
    if (tabName === 'map')    { setTimeout(() => window.EDMap?.draw2D(), 50); }
    if (tabName === 'map3d')  { setTimeout(() => window.EDMap?.draw3D(), 50); }
    _setUrlParam('tab', tabName === 'local' ? null : tabName);
  }
  btns.forEach(btn => {
    btn.addEventListener('click', () => activateTab(btn.dataset.tab));
  });
  const savedTab = _getUrlParam('tab');
  if (savedTab && qs(`#tab-${savedTab}`)) activateTab(savedTab);
})();

// ═══════════════════════════════════════════════════════════════ STATUS

(async function initStatus() {
  const dot  = qs('#status-dot');
  const text = qs('#status-text');
  if (!dot || !text) return;
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
  if (!modal || !content) return;
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

    const wlBtn = qs('#modal-watchlist-btn');
    if (wlBtn) {
      wlBtn.addEventListener('click', () => {
        const saved = Watchlist.toggle(sys);
        wlBtn.classList.toggle('saved', saved);
        wlBtn.textContent = saved ? '★ Saved — click to remove' : '☆ Save to Watchlist';
        if (qs('#tab-watchlist.active')) renderWatchlistTab();
      });
    }
    const mapBtn = qs('#modal-show-on-map-btn');
    if (mapBtn) {
      mapBtn.addEventListener('click', () => {
        closeModal();
        window.EDMap?.focusSystem(sys);
      });
    }
    const noteArea   = qs('#modal-note-area');
    const noteSave   = qs('#modal-note-save');
    const noteDelete = qs('#modal-note-delete');
    const noteStatus = qs('#modal-note-status');
    if (noteArea && sys.id64) {
      apiFetch(`/api/systems/${sys.id64}/note`)
        .then(d => { if (d.note) { noteArea.value = d.note; if (noteDelete) noteDelete.hidden = false; } })
        .catch(() => {});
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
    }
  } catch (err) {
    content.innerHTML = `<div class="error-state">⚠ Failed to load system data: ${err.message}</div>`;
  }
}

function closeModal() {
  const modal = qs('#system-modal');
  if (modal) {
    modal.hidden = true;
    document.body.style.overflow = '';
    _modalSys = null;
  }
}

(function initModal() {
  const modal = qs('#system-modal');
  if (!modal) return;
  const closeBtn = qs('#modal-close-btn');
  if (closeBtn) closeBtn.addEventListener('click', closeModal);
  modal.addEventListener('click', (e) => { if (e.target === modal) closeModal(); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape' && !modal.hidden) closeModal(); });
})();

// ═══════════════════════════════════════════════════════════════ PAGINATION

function buildPagination(container, total, pageSize, currentPage, onPage) {
  if (!container) return;
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

  if (!searchBtn) return;

  let refCoords = null;

  makeAutocomplete(refInput, refList, (item) => {
    refCoords = { x: item.x, y: item.y, z: item.z };
    coordDisp.hidden = false;
    qs('#local-coord-x').textContent = `X: ${fmtCoord(item.x)}`;
    qs('#local-coord-y').textContent = `Y: ${fmtCoord(item.y)}`;
    qs('#local-coord-z').textContent = `Z: ${fmtCoord(item.z)}`;
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

  if (!searchBtn) return;

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

  if (!searchBtn) return;

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

  let _clusterRefCoords = null;
  document.addEventListener('ed:refcoords', (e) => { _clusterRefCoords = e.detail; });

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
    document.dispatchEvent(new CustomEvent('ed:clusterresults', { detail: { clusters: results } }));
  }

  function buildClusterCard(c, rank) {
    let ecos = Array.isArray(c.economy_breakdown) ? c.economy_breakdown.map(e => [e.economy, e.count, e.best_score]).filter(([, count]) => count > 0) : [];
    const coverageScore = c.total_best_score != null ? Math.round(c.total_best_score) : (c.coverage_score != null ? Math.round(c.coverage_score) : null);
    const anchorName = c.anchor_name || c.name || 'Unknown';
    const coords = c.anchor_coords || {};
    const cx = coords.x ?? c.x;
    const cy = coords.y ?? c.y;
    const cz = coords.z ?? c.z;
    const dSol = distFromSol(cx, cy, cz);
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
      </div>
      <div class="cluster-economies">
        ${ecos.map(([eco, count, best]) => `<span class="eco-chip">${ecoShort(eco)} ×${count} ★${Math.round(best)}</span>`).join('')}
      </div>
    `;
    card.addEventListener('click', () => openSystemModal({ name: anchorName, id64: c.anchor_id64 || c.system_id64, x: cx, y: cy, z: cz }));
    return card;
  }
})();

// ═══════════════════════════════════════════════════════════ LIVE EDDN FEED

(function initLiveFeed() {
  const feedEl   = qs('#live-feed-list');
  const countEl  = qs('#live-feed-count');
  const dotEl    = qs('#live-feed-dot');
  if (!feedEl) return;

  const MAX_EVENTS = 50;
  let eventCount = 0;
  let es = null;

  function addEvent(event) {
    eventCount++;
    if (countEl) countEl.textContent = eventCount;
    const li = document.createElement('li');
    li.className = 'feed-item';
    li.innerHTML = `<div class="feed-item-name">${event.system_name || 'Unknown'}</div>`;
    li.addEventListener('click', () => openSystemModal({ id64: event.id64, name: event.system_name }));
    feedEl.prepend(li);
    if (feedEl.children.length > MAX_EVENTS) feedEl.lastElementChild.remove();
  }

  function connect() {
    if (es) es.close();
    if (dotEl) dotEl.className = 'feed-dot connecting';
    es = new EventSource('/api/events/live');
    es.onopen = () => { if (dotEl) dotEl.className = 'feed-dot active'; };
    es.onerror = () => { if (dotEl) dotEl.className = 'feed-dot inactive'; setTimeout(connect, 5000); };
    es.onmessage = (e) => { try { const data = JSON.parse(e.data); if (data && data.id64) addEvent(data); } catch {} };
  }
  connect();
})();

// ═══════════════════════════════════════════════════════════════ WATCHLIST TAB

const WL_PAGE_SIZE = 20;
let _wlPage = 1;

function renderWatchlistTab(page) {
  if (page !== undefined) _wlPage = page;
  const allItems  = Watchlist.getAll();
  const resultsEl = qs('#watchlist-results');
  const headerEl  = qs('#watchlist-results-header');
  const countEl   = qs('#watchlist-results-count');
  if (!resultsEl) return;

  if (!allItems.length) {
    resultsEl.innerHTML = `<div class="empty-state">Your watchlist is empty</div>`;
    if (headerEl) headerEl.hidden = true;
    return;
  }

  const total = allItems.length;
  const start = (_wlPage - 1) * WL_PAGE_SIZE;
  const items = allItems.slice(start, start + WL_PAGE_SIZE);

  if (countEl) countEl.innerHTML = `<strong>${total}</strong> saved systems`;
  if (headerEl) headerEl.hidden = false;
  resultsEl.innerHTML = '';

  items.forEach((entry, i) => {
    const fakeSys = { id64: entry.id64, name: entry.name, x: entry.x, y: entry.y, z: entry.z, primaryEconomy: entry.economy, _rating: { score: entry.score } };
    resultsEl.appendChild(buildSystemCard(fakeSys, start + i + 1));
  });

  const paginEl = qs('#watchlist-pagination');
  if (paginEl) buildPagination(paginEl, total, WL_PAGE_SIZE, _wlPage, (p) => renderWatchlistTab(p));
}

(function initWatchlistClear() {
  const btn = qs('#watchlist-clear-btn');
  if (btn) btn.addEventListener('click', () => {
    if (!confirm('Clear all?')) return;
    Watchlist._data = {};
    Watchlist.save();
    renderWatchlistTab();
  });
})();
