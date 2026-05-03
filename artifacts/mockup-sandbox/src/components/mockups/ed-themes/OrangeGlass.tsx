export function OrangeGlass() {
  const css = `
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;600;700&family=Rajdhani:wght@400;500;600&display=swap');

    .og-root {
      font-family: 'Rajdhani', sans-serif;
      background: radial-gradient(ellipse at 15% 10%, #2a0e00 0%, #0d0a06 35%, #080b12 70%, #050810 100%);
      color: #d8e4f0;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }

    /* subtle star field */
    .og-root::before {
      content: '';
      position: fixed;
      inset: 0;
      background-image:
        radial-gradient(1px 1px at 12% 18%, rgba(255,255,255,0.18) 0%, transparent 100%),
        radial-gradient(1px 1px at 47% 62%, rgba(255,255,255,0.12) 0%, transparent 100%),
        radial-gradient(1px 1px at 73% 28%, rgba(255,255,255,0.15) 0%, transparent 100%),
        radial-gradient(1px 1px at 88% 74%, rgba(255,255,255,0.10) 0%, transparent 100%),
        radial-gradient(1px 1px at 31% 85%, rgba(255,255,255,0.13) 0%, transparent 100%),
        radial-gradient(1px 1px at 63% 9%,  rgba(255,255,255,0.11) 0%, transparent 100%);
      pointer-events: none;
      z-index: 0;
    }

    /* ── Header ── */
    .og-header {
      background: rgba(255, 90, 0, 0.07);
      backdrop-filter: blur(24px);
      -webkit-backdrop-filter: blur(24px);
      border-bottom: 1px solid rgba(255, 106, 0, 0.28);
      padding: 14px 24px;
      display: flex;
      align-items: center;
      gap: 16px;
      position: relative;
      z-index: 10;
      box-shadow: 0 4px 32px rgba(255, 90, 0, 0.12), 0 1px 0 rgba(255,255,255,0.04) inset;
    }
    .og-logo {
      width: 42px; height: 42px;
      border: 1.5px solid rgba(255, 120, 0, 0.75);
      border-radius: 50%;
      display: flex; align-items: center; justify-content: center;
      font-size: 18px; color: #ff7a00;
      box-shadow: 0 0 22px rgba(255, 106, 0, 0.45), inset 0 0 14px rgba(255, 106, 0, 0.08);
    }
    .og-title {
      font-family: 'Orbitron', monospace;
      font-size: 20px; font-weight: 700;
      color: #fff; letter-spacing: 2px;
      text-shadow: 0 0 24px rgba(255, 106, 0, 0.5);
    }
    .og-sub { font-size: 10px; color: rgba(210, 180, 150, 0.5); letter-spacing: 3px; text-transform: uppercase; }
    .og-spacer { flex: 1; }
    .og-badge {
      font-family: 'Orbitron', monospace; font-size: 10px;
      color: #ff8c33; border: 1px solid rgba(255,106,0,0.45);
      border-radius: 6px; padding: 4px 10px;
      background: rgba(255, 90, 0, 0.1);
      backdrop-filter: blur(8px);
    }
    .og-syncbtn {
      background: linear-gradient(135deg, rgba(255,106,0,0.85), rgba(180,60,0,0.85));
      color: #fff; border: 1px solid rgba(255,130,0,0.5);
      border-radius: 10px; padding: 8px 18px;
      font-family: 'Orbitron', monospace; font-size: 10px;
      font-weight: 600; letter-spacing: 1px; cursor: pointer;
      backdrop-filter: blur(8px);
      box-shadow: 0 2px 18px rgba(255,90,0,0.35);
    }

    /* ── Tabs ── */
    .og-tabs {
      background: rgba(255, 60, 0, 0.04);
      backdrop-filter: blur(16px);
      -webkit-backdrop-filter: blur(16px);
      border-bottom: 1px solid rgba(255, 106, 0, 0.14);
      padding: 0 20px;
      display: flex; gap: 2px;
      overflow-x: auto;
      position: relative; z-index: 10;
    }
    .og-tab {
      font-family: 'Orbitron', monospace; font-size: 10px;
      letter-spacing: 1px; text-transform: uppercase;
      padding: 13px 16px;
      background: none; border: none;
      border-bottom: 2px solid transparent;
      color: rgba(200, 160, 120, 0.42);
      cursor: pointer; white-space: nowrap; transition: all 0.2s;
    }
    .og-tab.active {
      color: #ff8c33;
      border-bottom-color: #ff6a00;
      background: linear-gradient(180deg, rgba(255,100,0,0.07) 0%, transparent 100%);
      text-shadow: 0 0 10px rgba(255,110,0,0.55);
    }
    .og-tab:hover:not(.active) { color: rgba(230, 195, 160, 0.75); }

    /* ── Layout ── */
    .og-body { display: flex; flex: 1; min-height: 0; position: relative; z-index: 1; }

    /* ── Sidebar ── */
    .og-sidebar {
      width: 300px;
      background: rgba(255, 60, 0, 0.03);
      backdrop-filter: blur(18px);
      -webkit-backdrop-filter: blur(18px);
      border-right: 1px solid rgba(255, 106, 0, 0.12);
      padding: 18px 14px;
      overflow-y: auto;
      display: flex; flex-direction: column; gap: 14px;
    }

    /* ── Glass panel ── */
    .og-panel {
      background: rgba(255, 80, 0, 0.05);
      backdrop-filter: blur(14px);
      -webkit-backdrop-filter: blur(14px);
      border: 1px solid rgba(255, 106, 0, 0.16);
      border-radius: 16px;
      overflow: hidden;
    }
    .og-panel-hdr {
      background: rgba(255, 80, 0, 0.07);
      border-bottom: 1px solid rgba(255, 106, 0, 0.12);
      padding: 10px 14px;
      display: flex; align-items: center; gap: 8px;
    }
    .og-panel-icon { color: #ff7a00; font-size: 14px; filter: drop-shadow(0 0 6px rgba(255,110,0,0.65)); }
    .og-panel-title {
      font-family: 'Orbitron', monospace; font-size: 10px;
      font-weight: 600; letter-spacing: 1.5px; text-transform: uppercase;
      color: rgba(235, 210, 185, 0.9); flex: 1;
    }
    .og-panel-body { padding: 14px; }

    /* ── Form controls ── */
    .og-label {
      font-size: 11px; font-weight: 600;
      color: rgba(200, 160, 120, 0.55); letter-spacing: 1px;
      text-transform: uppercase; margin-bottom: 6px; display: block;
    }
    .og-input {
      width: 100%;
      background: rgba(255, 60, 0, 0.07);
      border: 1px solid rgba(255, 106, 0, 0.2);
      border-radius: 10px; color: #e8d8c8;
      font-family: 'Rajdhani', sans-serif; font-size: 14px;
      padding: 9px 12px; outline: none;
      backdrop-filter: blur(8px);
    }
    .og-input:focus { border-color: rgba(255,106,0,0.5); box-shadow: 0 0 14px rgba(255,90,0,0.18); }
    .og-slider-row { display: flex; align-items: center; gap: 10px; margin-top: 6px; }
    .og-slider { flex: 1; accent-color: #ff6a00; }
    .og-slider-val {
      font-family: 'Orbitron', monospace; font-size: 12px;
      color: #ff8c33; min-width: 32px; text-align: right;
      text-shadow: 0 0 8px rgba(255,110,0,0.5);
    }
    .og-searchbtn {
      width: 100%;
      background: linear-gradient(135deg, rgba(255,106,0,0.82), rgba(180,58,0,0.82));
      color: #fff; border: 1px solid rgba(255,130,0,0.5);
      border-radius: 12px; padding: 12px;
      font-family: 'Orbitron', monospace; font-size: 11px;
      font-weight: 700; letter-spacing: 1.5px; cursor: pointer;
      backdrop-filter: blur(8px);
      box-shadow: 0 4px 24px rgba(255,90,0,0.32);
      margin-top: 4px;
    }

    /* ── Content area ── */
    .og-content { flex: 1; padding: 20px; overflow-y: auto; display: flex; flex-direction: column; gap: 12px; }

    .og-summary {
      display: flex; align-items: center; gap: 12px;
      padding: 10px 16px;
      background: rgba(255, 60, 0, 0.05);
      backdrop-filter: blur(10px);
      border: 1px solid rgba(255, 106, 0, 0.13);
      border-radius: 12px; font-size: 13px;
      color: rgba(200, 160, 120, 0.65);
    }
    .og-summary strong {
      color: #ff8c33; font-family: 'Orbitron', monospace; font-size: 12px;
      text-shadow: 0 0 8px rgba(255,110,0,0.5);
    }

    /* ── Result card ── */
    .og-card {
      background: rgba(255, 70, 0, 0.05);
      backdrop-filter: blur(16px);
      -webkit-backdrop-filter: blur(16px);
      border: 1px solid rgba(255, 106, 0, 0.13);
      border-radius: 18px;
      overflow: hidden;
      transition: all 0.22s ease;
    }
    .og-card:hover {
      transform: translateY(-4px);
      background: rgba(255, 80, 0, 0.08);
      border-color: rgba(255, 106, 0, 0.35);
      box-shadow: 0 14px 42px rgba(255, 90, 0, 0.14), 0 2px 8px rgba(0,0,0,0.5);
    }
    .og-card-hdr {
      padding: 13px 16px; display: flex; align-items: center; gap: 10px;
      border-bottom: 1px solid rgba(255, 106, 0, 0.1);
    }
    .og-rating {
      color: #fff; font-family: 'Orbitron', monospace;
      font-size: 14px; font-weight: 700;
      border-radius: 10px; padding: 5px 11px;
      min-width: 46px; text-align: center;
    }
    .og-sys-name {
      font-family: 'Orbitron', monospace; font-size: 13px;
      color: rgba(235, 215, 195, 0.97); font-weight: 600; flex: 1;
    }
    .og-dist { font-size: 12px; color: rgba(200, 160, 120, 0.52); }
    .og-card-body { padding: 12px 16px; }

    /* ── Tags ── */
    .og-tags { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; }
    .og-tag {
      font-size: 11px; padding: 3px 10px; border-radius: 20px;
      background: rgba(255, 90, 0, 0.1);
      border: 1px solid rgba(255, 106, 0, 0.28);
      color: #ff9944;
    }
    .og-tag.g { background: rgba(61,220,132,0.1); border-color: rgba(61,220,132,0.28); color: #3ddc84; }
    .og-tag.b { background: rgba(77,166,255,0.09); border-color: rgba(77,166,255,0.25); color: #70b8ff; }

    /* ── Stats ── */
    .og-stat-row { display: flex; gap: 20px; margin-top: 8px; }
    .og-stat { display: flex; flex-direction: column; gap: 2px; }
    .og-stat-lbl { font-size: 10px; color: rgba(190,150,110,0.5); text-transform: uppercase; letter-spacing: 1px; }
    .og-stat-val { font-size: 13px; color: rgba(230,210,190,0.88); font-weight: 600; }

    /* ── Card footer ── */
    .og-card-footer {
      padding: 10px 16px;
      border-top: 1px solid rgba(255, 106, 0, 0.09);
      display: flex; gap: 8px; justify-content: flex-end;
    }
    .og-btn {
      font-size: 11px; padding: 6px 14px;
      border-radius: 10px;
      border: 1px solid rgba(255, 106, 0, 0.17);
      background: rgba(255, 80, 0, 0.07);
      color: rgba(220, 180, 140, 0.7);
      cursor: pointer; font-family: 'Rajdhani', sans-serif;
      font-weight: 600; backdrop-filter: blur(6px);
      transition: all 0.15s;
    }
    .og-btn:hover { background: rgba(255,90,0,0.14); color: rgba(240,200,160,0.9); }
    .og-btn.primary {
      background: rgba(255, 106, 0, 0.16);
      border-color: rgba(255, 106, 0, 0.42);
      color: #ff9944;
    }
    .og-btn.primary:hover { background: rgba(255,106,0,0.25); }
  `;

  const systems = [
    { name: 'Colonia Gateway', rating: 94, ratingBg: 'linear-gradient(135deg,#ff6a00,#c44d00)', glow: 'rgba(255,90,0,0.55)', dist: '22,000.4 ly', tags: ['High Tech', 'Industrial'], tagClass: ['','b'], pop: '2.1B', slots: 7, bodies: 23 },
    { name: 'Eravate',         rating: 88, ratingBg: 'linear-gradient(135deg,#d4800a,#a65800)', glow: 'rgba(210,130,0,0.5)',  dist: '34.2 ly',      tags: ['Agriculture', 'Refinery'],  tagClass: ['',''],  pop: '450M', slots: 5, bodies: 14 },
    { name: 'Lave',            rating: 81, ratingBg: 'linear-gradient(135deg,#2e9e5e,#1e6e42)', glow: 'rgba(50,180,100,0.45)', dist: '108.5 ly',    tags: ['Agriculture'],              tagClass: [''],     pop: '1.2B', slots: 6, bodies: 18 },
  ];

  return (
    <div className="og-root">
      <style dangerouslySetInnerHTML={{ __html: css }} />

      {/* Header */}
      <div className="og-header">
        <div className="og-logo">🎯</div>
        <div>
          <div className="og-title">ED:FINDER</div>
          <div className="og-sub">Advanced System Finder &amp; Optimizer</div>
        </div>
        <div className="og-spacer" />
        <span style={{ fontSize: 12, color: 'rgba(200,160,120,0.45)', marginRight: 8 }}>· Never synced yet</span>
        <button className="og-syncbtn">⟳ SYNC NOW</button>
        <span className="og-badge">v3.90</span>
      </div>

      {/* Tabs */}
      <div className="og-tabs">
        {['🎯 SYSTEM FINDER','⚙️ OPTIMIZER','📊 ECONOMY','📌 PINNED','⚖️ COMPARE','👁 WATCHLIST','🗺️ ROUTE','🛸 FC PLANNER','🌐 MAP','✨ 3D MAP','🏗️ COLONIES'].map((t, i) => (
          <button key={i} className={`og-tab${i === 0 ? ' active' : ''}`}>{t}</button>
        ))}
      </div>

      <div className="og-body">
        {/* Sidebar */}
        <div className="og-sidebar">
          {/* Reference System */}
          <div className="og-panel">
            <div className="og-panel-hdr">
              <span className="og-panel-icon">📍</span>
              <span className="og-panel-title">Reference System</span>
              <span style={{ fontSize: 10, color: 'rgba(200,150,100,0.38)' }}>▼</span>
            </div>
            <div className="og-panel-body">
              <label className="og-label">System Name</label>
              <input className="og-input" defaultValue="Sol" />
              <div style={{ marginTop: 8, padding: '7px 11px', background: 'rgba(255,106,0,0.08)', borderRadius: 10, border: '1px solid rgba(255,106,0,0.22)', fontSize: 13, color: '#ff9944', display: 'flex', alignItems: 'center', gap: 8 }}>
                <span>📍</span><span>Sol — 0, 0, 0</span>
              </div>
            </div>
          </div>

          {/* Search Radius */}
          <div className="og-panel">
            <div className="og-panel-hdr">
              <span className="og-panel-icon">📡</span>
              <span className="og-panel-title">Search Radius</span>
              <span style={{ fontSize: 10, color: 'rgba(200,150,100,0.38)' }}>▼</span>
            </div>
            <div className="og-panel-body">
              {([['Max Distance (ly)', 50], ['Min Distance (ly)', 0], ['Results Per Page', 50]] as [string,number][]).map(([lbl, val], i) => (
                <div key={i} style={{ marginBottom: i < 2 ? 12 : 0 }}>
                  <label className="og-label">{lbl}</label>
                  <div className="og-slider-row">
                    <input type="range" className="og-slider" defaultValue={val} />
                    <span className="og-slider-val">{val}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Rating */}
          <div className="og-panel">
            <div className="og-panel-hdr">
              <span className="og-panel-icon">⭐</span>
              <span className="og-panel-title">Rating Filter</span>
              <span style={{ fontSize: 10, color: 'rgba(200,150,100,0.38)' }}>▼</span>
            </div>
            <div className="og-panel-body">
              <label className="og-label">Minimum Rating</label>
              <div className="og-slider-row">
                <input type="range" className="og-slider" defaultValue={60} />
                <span className="og-slider-val">60</span>
              </div>
            </div>
          </div>

          <button className="og-searchbtn">🔍 SEARCH SYSTEMS</button>
        </div>

        {/* Content */}
        <div className="og-content">
          <div className="og-summary">
            <span>Found <strong>247 SYSTEMS</strong></span>
            <span>·</span>
            <span>⏱ 843ms</span>
            <div style={{ flex: 1 }} />
            <button className="og-btn">👁 Watch All</button>
            <button className="og-btn">📋 Copy Names</button>
          </div>

          {systems.map((sys, i) => (
            <div className="og-card" key={i}>
              <div className="og-card-hdr">
                <span className="og-rating" style={{ background: sys.ratingBg, boxShadow: `0 2px 16px ${sys.glow}` }}>
                  {sys.rating}
                </span>
                <span className="og-sys-name">{sys.name}</span>
                <span className="og-dist">📡 {sys.dist}</span>
                <button style={{ background: 'none', border: 'none', color: 'rgba(200,150,100,0.42)', cursor: 'pointer', fontSize: 16 }}>📌</button>
              </div>
              <div className="og-card-body">
                <div className="og-tags">
                  {sys.tags.map((t, j) => (
                    <span key={j} className={`og-tag ${sys.tagClass[j] ?? ''}`}>{t}</span>
                  ))}
                  <span className="og-tag g">⭐ Landable</span>
                  <span className="og-tag">💰 {sys.pop}</span>
                </div>
                <div className="og-stat-row">
                  <div className="og-stat"><span className="og-stat-lbl">Slots</span><span className="og-stat-val">{sys.slots}</span></div>
                  <div className="og-stat"><span className="og-stat-lbl">Bodies</span><span className="og-stat-val">{sys.bodies}</span></div>
                  <div className="og-stat"><span className="og-stat-lbl">Stars</span><span className="og-stat-val">F-class</span></div>
                  <div className="og-stat"><span className="og-stat-lbl">Security</span><span className="og-stat-val">High</span></div>
                </div>
              </div>
              <div className="og-card-footer">
                <button className="og-btn">👁 Watch</button>
                <button className="og-btn">⚖️ Compare</button>
                <button className="og-btn primary">📋 Briefing</button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
