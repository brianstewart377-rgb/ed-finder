/* ═══════════════════════════════════════════════════════════════════════════
   ED Finder — Frontend Application
   ═══════════════════════════════════════════════════════════════════════════ */

'use strict';

const API = '';  // Same-origin: '' = relative paths work

// ═══════════════════════════════════════════════════════════════ UTILITIES

function qs(sel, root = document) { return root.querySelector(sel); }
function qsa(sel, root = document) { return [...root.querySelectorAll(sel)]; }

async function apiFetch(path, opts = {}) {
  const res = await fetch(API + path, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

function toast(msg, dur = 3000) {
  const el = qs('#toast');
  el.textContent = msg;
  el.hidden = false;
  clearTimeout(el._t);
  el._t = setTimeout(() => { el.hidden = true; }, dur);
}

function fmtCoord(v) {
  if (v == null) return '—';
  return Number(v).toFixed(2);
}

function fmtDist(v) {
  if (v == null) return '—';
  const n = Number(v);
  return n >= 10 ? n.toFixed(1) + ' ly' : n.toFixed(2) + ' ly';
}

function fmtNum(v) {
  if (v == null) return '—';
  return Number(v).toLocaleString();
}

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
    terraforming: 'Terr', prison: 'Pri',
  };
  if (!eco) return '—';
  return map[eco.toLowerCase()] || eco;
}

function starLabel(type, sub) {
  if (!type) return null;
  let s = type;
  if (sub != null) s += sub;
  return s;
}

function popLabel(pop) {
  if (!pop) return null;
  const n = Number(pop);
  if (n === 0) return null;
  if (n >= 1e9) return (n / 1e9).toFixed(1) + 'B';
  if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M';
  if (n >= 1e3) return (n / 1e3).toFixed(0) + 'K';
  return n.toString();
}

// ═══════════════════════════════════════════════════════════════ NAVBAR

(function initNav() {
  const btns = qsa('.nav-btn');
  const panels = qsa('.tab-panel');

  btns.forEach(btn => {
    btn.addEventListener('click', () => {
      btns.forEach(b => b.classList.remove('active'));
      panels.forEach(p => p.classList.remove('active'));
      btn.classList.add('active');
      qs(`#tab-${btn.dataset.tab}`).classList.add('active');
    });
  });
})();

// ═══════════════════════════════════════════════════════════════ STATUS

(async function initStatus() {
  const dot  = qs('#status-dot');
  const text = qs('#status-text');
  try {
    const h = await apiFetch('/api/health');
    if (h.status === 'ok') {
      dot.className = 'status-dot ok';
      text.textContent = 'Online';
    } else {
      dot.className = 'status-dot warn';
      text.textContent = 'Degraded';
    }
  } catch (e) {
    dot.className = 'status-dot err';
    text.textContent = 'Offline';
  }
})();

// ═══════════════════════════════════════════════════════════════ AUTOCOMPLETE

function makeAutocomplete(inputEl, listEl, onSelect) {
  let debounce;
  let highlighted = -1;
  let items = [];

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
      if (highlighted >= 0 && items[highlighted]) pick(items[highlighted]);
      else if (items[0]) pick(items[0]);
    }
    else if (e.key === 'Escape') { listEl.hidden = true; }
  });

  document.addEventListener('click', (e) => {
    if (!inputEl.contains(e.target) && !listEl.contains(e.target)) {
      listEl.hidden = true;
    }
  });

  function move(dir) {
    highlighted = Math.max(-1, Math.min(items.length - 1, highlighted + dir));
    qsa('li', listEl).forEach((li, i) => {
      li.classList.toggle('focused', i === highlighted);
    });
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
    } catch (e) {
      listEl.hidden = true;
    }
  }

  function pick(sys) {
    inputEl.value = sys.name;
    listEl.hidden = true;
    highlighted = -1;
    onSelect(sys);
  }
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

  // Body pills
  const bodies = [];
  if (r.elw_count > 0)         bodies.push(`🌍 ELW ×${r.elw_count}`);
  if (r.ww_count > 0)          bodies.push(`💧 WW ×${r.ww_count}`);
  if (r.ammonia_count > 0)     bodies.push(`🟣 AW ×${r.ammonia_count}`);
  if (r.gas_giant_count > 0)   bodies.push(`🔵 GG ×${r.gas_giant_count}`);
  if (r.neutron_count > 0)     bodies.push(`💫 NS ×${r.neutron_count}`);
  if (r.black_hole_count > 0)  bodies.push(`⚫ BH ×${r.black_hole_count}`);
  if (r.bio_signal_total > 0)  bodies.push(`🧬 Bio ×${r.bio_signal_total}`);
  if (r.geo_signal_total > 0)  bodies.push(`🌋 Geo ×${r.geo_signal_total}`);
  if (r.terraformable_count > 0) bodies.push(`♻ Terr ×${r.terraformable_count}`);

  // Economy score bars
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
    </div>
    <div class="card-meta">
      ${dist ? `<span class="meta-tag distance">⊕ ${dist}</span>` : ''}
      ${eco && eco !== 'None' ? `<span class="meta-tag economy">${eco}</span>` : ''}
      ${pop === 0 ? `<span class="meta-tag pop-zero">Uncolonised</span>` : (isCol ? `<span class="meta-tag pop-col">Colonised</span>` : (pop > 0 ? `<span class="meta-tag">Pop ${popLabel(pop)}</span>` : ''))}
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

// ═══════════════════════════════════════════════════════════════ MODAL

function openSystemModal(sys) {
  const r = sys._rating || {};
  const coords = sys.coords || { x: sys.x, y: sys.y, z: sys.z };
  const eco = sys.primaryEconomy || sys.primary_economy || '—';
  const eco2 = sys.secondaryEconomy || sys.secondary_economy;
  const edsm = `https://www.edsm.net/en/system/id/${sys.id64}/name/${encodeURIComponent(sys.name || '')}`;
  const inara = `https://inara.cz/elite/starsystem/?search=${encodeURIComponent(sys.name || '')}`;

  const scoreItems = [
    ['Overall', r.score],
    ['Agriculture', r.scoreAgriculture ?? r.score_agriculture],
    ['Refinery',    r.scoreRefinery    ?? r.score_refinery],
    ['Industrial',  r.scoreIndustrial  ?? r.score_industrial],
    ['High Tech',   r.scoreHightech    ?? r.score_hightech],
    ['Military',    r.scoreMilitary    ?? r.score_military],
    ['Tourism',     r.scoreTourism     ?? r.score_tourism],
  ].filter(([, v]) => v != null);

  const bodyRows = [
    ['🌍 Earth-like', r.elw_count],
    ['💧 Water World', r.ww_count],
    ['🟣 Ammonia', r.ammonia_count],
    ['🔵 Gas Giant', r.gas_giant_count],
    ['🌐 Landable', r.landable_count],
    ['♻ Terraformable', r.terraformable_count],
    ['💫 Neutron Star', r.neutron_count],
    ['⚫ Black Hole', r.black_hole_count],
    ['⚪ White Dwarf', r.white_dwarf_count],
    ['🧬 Bio Signals', r.bio_signal_total],
    ['🌋 Geo Signals', r.geo_signal_total],
  ].filter(([, v]) => v > 0);

  const html = `
    <div class="modal-system-name">${sys.name || 'Unknown System'}</div>
    <div class="modal-system-id">ID64: ${sys.id64 || '—'}</div>

    <div class="modal-section">
      <div class="modal-section-title">System Info</div>
      <div class="modal-grid">
        <div class="modal-field">
          <span class="modal-field-label">Coordinates</span>
          <span class="modal-field-value blue" style="font-family:var(--font-mono);font-size:0.78rem">
            ${fmtCoord(coords.x)}, ${fmtCoord(coords.y)}, ${fmtCoord(coords.z)}
          </span>
        </div>
        ${sys.distance != null ? `
        <div class="modal-field">
          <span class="modal-field-label">Distance</span>
          <span class="modal-field-value accent">${fmtDist(sys.distance)}</span>
        </div>` : ''}
        <div class="modal-field">
          <span class="modal-field-label">Primary Economy</span>
          <span class="modal-field-value gold">${eco}</span>
        </div>
        ${eco2 && eco2 !== 'None' ? `
        <div class="modal-field">
          <span class="modal-field-label">Secondary Economy</span>
          <span class="modal-field-value">${eco2}</span>
        </div>` : ''}
        <div class="modal-field">
          <span class="modal-field-label">Population</span>
          <span class="modal-field-value ${Number(sys.population) === 0 ? 'green' : ''}">${Number(sys.population) === 0 ? 'Uncolonised' : fmtNum(sys.population)}</span>
        </div>
        ${sys.security ? `
        <div class="modal-field">
          <span class="modal-field-label">Security</span>
          <span class="modal-field-value">${sys.security}</span>
        </div>` : ''}
        ${sys.allegiance ? `
        <div class="modal-field">
          <span class="modal-field-label">Allegiance</span>
          <span class="modal-field-value">${sys.allegiance}</span>
        </div>` : ''}
        ${sys.main_star_type ? `
        <div class="modal-field">
          <span class="modal-field-label">Main Star</span>
          <span class="modal-field-value" style="color:var(--purple)">${starLabel(sys.main_star_type, sys.main_star_subtype)}</span>
        </div>` : ''}
        ${r.economySuggestion ? `
        <div class="modal-field">
          <span class="modal-field-label">Suggested Economy</span>
          <span class="modal-field-value accent">${r.economySuggestion}</span>
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
            <div class="modal-score-bar">
              <div class="modal-score-bar-fill" style="width:${pct}%;background:${scoreColor(pct)}"></div>
            </div>
          </div>`;
        }).join('')}
      </div>
    </div>` : ''}

    ${bodyRows.length ? `
    <div class="modal-section">
      <div class="modal-section-title">Notable Bodies</div>
      <div class="modal-grid">
        ${bodyRows.map(([label, count]) => `
        <div class="modal-field">
          <span class="modal-field-label">${label}</span>
          <span class="modal-field-value">${count}</span>
        </div>`).join('')}
      </div>
    </div>` : ''}

    <div class="modal-section">
      <div class="modal-section-title">External Links</div>
      <div style="display:flex;gap:0.75rem;flex-wrap:wrap">
        <a href="${edsm}" target="_blank" rel="noopener" class="modal-edsm-link">
          ↗ EDSM
        </a>
        <a href="${inara}" target="_blank" rel="noopener" class="modal-edsm-link">
          ↗ Inara
        </a>
      </div>
    </div>
  `;

  const modal = qs('#system-modal');
  qs('#modal-content').innerHTML = html;
  modal.hidden = false;
  document.body.style.overflow = 'hidden';
}

(function initModal() {
  const modal = qs('#system-modal');
  qs('#modal-close-btn').addEventListener('click', closeModal);
  modal.addEventListener('click', (e) => {
    if (e.target === modal) closeModal();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !modal.hidden) closeModal();
  });

  function closeModal() {
    modal.hidden = true;
    document.body.style.overflow = '';
  }
})();

// ═══════════════════════════════════════════════════════════════ PAGINATION

function buildPagination(container, total, pageSize, currentPage, onPage) {
  container.innerHTML = '';
  const totalPages = Math.ceil(total / pageSize);
  if (totalPages <= 1) return;

  const maxBtns = 7;
  let pages = [];

  if (totalPages <= maxBtns) {
    pages = Array.from({ length: totalPages }, (_, i) => i + 1);
  } else {
    pages = [1];
    if (currentPage > 3) pages.push('…');
    for (let p = Math.max(2, currentPage - 1); p <= Math.min(totalPages - 1, currentPage + 1); p++) {
      pages.push(p);
    }
    if (currentPage < totalPages - 2) pages.push('…');
    pages.push(totalPages);
  }

  pages.forEach(p => {
    const btn = document.createElement('button');
    btn.className = 'page-btn' + (p === currentPage ? ' active' : '');
    btn.textContent = p;
    if (p === '…') {
      btn.disabled = true;
    } else {
      btn.addEventListener('click', () => onPage(p));
    }
    container.appendChild(btn);
  });
}

// ═══════════════════════════════════════════════════════════════ LOCAL SEARCH

(function initLocalSearch() {
  const refInput  = qs('#local-ref-input');
  const refList   = qs('#local-ref-suggestions');
  const distSlider = qs('#local-dist-slider');
  const distVal   = qs('#local-dist-val');
  const coordDisp = qs('#local-coords-display');
  const xSpan     = qs('#local-coord-x');
  const ySpan     = qs('#local-coord-y');
  const zSpan     = qs('#local-coord-z');
  const searchBtn = qs('#local-search-btn');
  const resultsEl = qs('#local-results');
  const headerEl  = qs('#local-results-header');
  const countEl   = qs('#local-results-count');
  const paginEl   = qs('#local-pagination');

  let refCoords = null;
  let currentPage = 1;
  const PAGE_SIZE = 20;
  let lastParams = null;

  distSlider.addEventListener('input', () => {
    distVal.textContent = `${distSlider.value} ly`;
  });

  makeAutocomplete(refInput, refList, (sys) => {
    refCoords = { x: sys.x, y: sys.y, z: sys.z };
    xSpan.textContent = `X: ${fmtCoord(sys.x)}`;
    ySpan.textContent = `Y: ${fmtCoord(sys.y)}`;
    zSpan.textContent = `Z: ${fmtCoord(sys.z)}`;
    coordDisp.hidden = false;
  });

  searchBtn.addEventListener('click', () => {
    currentPage = 1;
    doSearch();
  });

  function getParams() {
    const pop = document.querySelector('input[name="local-pop"]:checked')?.value;
    const sort = document.querySelector('input[name="local-sort"]:checked')?.value;
    const eco = qs('#local-economy').value;

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
      sort_by: sort || 'rating',
      size: PAGE_SIZE,
      from: (currentPage - 1) * PAGE_SIZE,
      galaxy_wide: false,
    };
  }

  async function doSearch() {
    if (!refCoords) {
      toast('Please select a reference system first');
      refInput.focus();
      return;
    }

    lastParams = getParams();
    setLoading(true);

    try {
      const data = await apiFetch('/api/local/search', {
        method: 'POST',
        body: JSON.stringify(lastParams),
      });

      renderResults(data.results || [], data.total || 0);
    } catch (e) {
      showError(e.message);
    } finally {
      setLoading(false);
    }
  }

  function setLoading(on) {
    searchBtn.disabled = on;
    searchBtn.classList.toggle('loading', on);
    if (on) {
      resultsEl.innerHTML = `<div class="loading-state"><div class="spinner"></div>Searching…</div>`;
      headerEl.hidden = true;
    }
  }

  function showError(msg) {
    resultsEl.innerHTML = `<div class="error-state">⚠ Search failed: ${msg}</div>`;
  }

  function renderResults(results, total) {
    resultsEl.innerHTML = '';

    if (!results.length) {
      resultsEl.innerHTML = `<div class="empty-state"><div class="empty-icon">◉</div><div class="empty-title">No systems found</div><div class="empty-sub">Try increasing the search radius or relaxing filters</div></div>`;
      headerEl.hidden = true;
      return;
    }

    countEl.innerHTML = `Found <strong>${fmtNum(total)}</strong> systems — showing ${(currentPage - 1) * PAGE_SIZE + 1}–${Math.min(currentPage * PAGE_SIZE, total)}`;
    headerEl.hidden = false;

    results.forEach((sys, i) => {
      resultsEl.appendChild(buildSystemCard(sys, (currentPage - 1) * PAGE_SIZE + i + 1));
    });

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
  const ecoSel    = qs('#galaxy-economy');
  const scoreSlider = qs('#galaxy-score-slider');
  const scoreVal  = qs('#galaxy-score-val');
  const searchBtn = qs('#galaxy-search-btn');
  const resultsEl = qs('#galaxy-results');
  const headerEl  = qs('#galaxy-results-header');
  const countEl   = qs('#galaxy-results-count');
  const paginEl   = qs('#galaxy-pagination');

  let currentPage = 1;
  const PAGE_SIZE = 20;
  let lastParams = null;

  scoreSlider.addEventListener('input', () => {
    scoreVal.textContent = scoreSlider.value;
  });

  searchBtn.addEventListener('click', () => {
    currentPage = 1;
    doSearch();
  });

  function getParams() {
    return {
      economy: ecoSel.value,
      min_score: Number(scoreSlider.value),
      limit: PAGE_SIZE,
      offset: (currentPage - 1) * PAGE_SIZE,
    };
  }

  async function doSearch() {
    lastParams = getParams();
    setLoading(true);
    try {
      const data = await apiFetch('/api/search/galaxy', {
        method: 'POST',
        body: JSON.stringify(lastParams),
      });
      renderResults(data.results || [], data.total || 0);
    } catch (e) {
      showError(e.message);
    } finally {
      setLoading(false);
    }
  }

  function setLoading(on) {
    searchBtn.disabled = on;
    searchBtn.classList.toggle('loading', on);
    if (on) {
      resultsEl.innerHTML = `<div class="loading-state"><div class="spinner"></div>Searching galaxy…</div>`;
      headerEl.hidden = true;
    }
  }

  function showError(msg) {
    resultsEl.innerHTML = `<div class="error-state">⚠ Search failed: ${msg}</div>`;
  }

  function renderResults(results, total) {
    resultsEl.innerHTML = '';
    if (!results.length) {
      resultsEl.innerHTML = `<div class="empty-state"><div class="empty-icon">✦</div><div class="empty-title">No systems found</div><div class="empty-sub">Try lowering the minimum score</div></div>`;
      headerEl.hidden = true;
      return;
    }

    countEl.innerHTML = `Found <strong>${fmtNum(total)}</strong> systems`;
    headerEl.hidden = false;

    results.forEach((sys, i) => {
      resultsEl.appendChild(buildSystemCard(sys, (currentPage - 1) * PAGE_SIZE + i + 1));
    });

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
      <select class="req-eco">
        ${ECONOMIES.map(e => `<option value="${e}" ${e === eco ? 'selected' : ''}>${e}</option>`).join('')}
      </select>
      <div style="text-align:center">
        <div class="req-label">Min count</div>
        <input type="number" class="req-count" min="1" max="20" value="${minCount}" style="width:50px;text-align:center">
      </div>
      <div style="text-align:center">
        <div class="req-label">Min score</div>
        <input type="number" class="req-score" min="0" max="100" step="5" value="${minScore}" style="width:50px;text-align:center">
      </div>
      <button class="remove-btn" title="Remove">✕</button>
    `;
    row.querySelector('.remove-btn').addEventListener('click', () => row.remove());
    reqs.appendChild(row);
  }

  // Start with two default requirements
  addRow('HighTech', 1, 40);
  addRow('Agriculture', 2, 30);

  addBtn.addEventListener('click', () => {
    if (reqs.children.length >= 6) {
      toast('Maximum 6 economy requirements');
      return;
    }
    addRow();
  });

  searchBtn.addEventListener('click', doSearch);

  async function doSearch() {
    const requirements = qsa('.economy-req-row', reqs).map(row => ({
      economy: row.querySelector('.req-eco').value,
      min_count: Number(row.querySelector('.req-count').value),
      min_score: Number(row.querySelector('.req-score').value),
    }));

    if (!requirements.length) {
      toast('Add at least one economy requirement');
      return;
    }

    setLoading(true);
    try {
      const data = await apiFetch('/api/search/cluster', {
        method: 'POST',
        body: JSON.stringify({ requirements, limit: Number(limitSel.value) }),
      });
      renderResults(data.results || [], data.total || 0);
    } catch (e) {
      showError(e.message);
    } finally {
      setLoading(false);
    }
  }

  function setLoading(on) {
    searchBtn.disabled = on;
    searchBtn.classList.toggle('loading', on);
    if (on) {
      resultsEl.innerHTML = `<div class="loading-state"><div class="spinner"></div>Scanning 73M cluster anchors…</div>`;
      headerEl.hidden = true;
    }
  }

  function showError(msg) {
    resultsEl.innerHTML = `<div class="error-state">⚠ Search failed: ${msg}</div>`;
  }

  function renderResults(results, total) {
    resultsEl.innerHTML = '';
    if (!results.length) {
      resultsEl.innerHTML = `<div class="empty-state"><div class="empty-icon">⬡</div><div class="empty-title">No clusters found</div><div class="empty-sub">Try relaxing count or score requirements</div></div>`;
      headerEl.hidden = true;
      return;
    }

    countEl.innerHTML = `Found <strong>${fmtNum(total)}</strong> matching clusters`;
    headerEl.hidden = false;

    results.forEach((cluster, i) => {
      const card = buildClusterCard(cluster, i + 1);
      resultsEl.appendChild(card);
    });
  }

  function buildClusterCard(c, rank) {
    // Economy chips from the cluster data
    const ecos = [
      ['Agriculture', c.agriculture_count, c.agriculture_best],
      ['Refinery',    c.refinery_count,    c.refinery_best],
      ['Industrial',  c.industrial_count,  c.industrial_best],
      ['HighTech',    c.hightech_count,    c.hightech_best],
      ['Military',    c.military_count,    c.military_best],
      ['Tourism',     c.tourism_count,     c.tourism_best],
    ].filter(([, count]) => count > 0);

    const coverageScore = c.coverage_score != null ? Math.round(c.coverage_score) : null;
    const div = c.economy_diversity || 0;

    const card = document.createElement('article');
    card.className = 'cluster-card';
    card.innerHTML = `
      <div class="cluster-header">
        <span class="card-rank">#${rank}</span>
        <span class="cluster-name">${c.anchor_name || c.name || 'Unknown'}</span>
        ${coverageScore != null ? `<span class="cluster-score">⬡ ${coverageScore}</span>` : ''}
      </div>
      <div class="card-meta" style="margin-bottom:0.6rem">
        ${c.distance_from_bubble != null ? `<span class="meta-tag distance">⊕ ${fmtDist(c.distance_from_bubble)} from bubble</span>` : ''}
        ${div ? `<span class="meta-tag">${div} economies</span>` : ''}
        ${c.total_viable > 0 ? `<span class="meta-tag">${fmtNum(c.total_viable)} viable systems</span>` : ''}
      </div>
      <div class="cluster-economies">
        ${ecos.map(([eco, count, best]) => {
          const cls = best >= 60 ? 'strong' : best >= 35 ? 'medium' : 'weak';
          return `<span class="eco-chip ${cls}">${ecoShort(eco)} ×${count}${best != null ? ` ★${Math.round(best)}` : ''}</span>`;
        }).join('')}
      </div>
    `;

    card.addEventListener('click', () => {
      // Open a synthetic system object for the anchor
      openSystemModal({
        name: c.anchor_name || c.name,
        id64: c.system_id64 || c.anchor_id64,
        x: c.x, y: c.y, z: c.z,
        coords: { x: c.x, y: c.y, z: c.z },
        population: 0,
        _rating: {
          score: c.coverage_score,
          economySuggestion: c.economy_suggestion || null,
        },
      });
    });

    return card;
  }
})();
