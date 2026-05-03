// Economy → badge gradient + glow, matching the in-app eco-chip colour system
const ECO_BADGE: Record<string, { bg: string; glow: string; label: string }> = {
  'High Tech':    { bg: 'linear-gradient(135deg,#0d7abf,#22d3ee)', glow: 'rgba(0,180,240,0.55)',   label: 'High Tech'   },
  'Industrial':   { bg: 'linear-gradient(135deg,#b06010,#f59e0b)', glow: 'rgba(220,140,0,0.55)',   label: 'Industrial'  },
  'Agriculture':  { bg: 'linear-gradient(135deg,#1a7a38,#34d399)', glow: 'rgba(40,200,110,0.50)',  label: 'Agriculture' },
  'Refinery':     { bg: 'linear-gradient(135deg,#8a3a10,#cd6c28)', glow: 'rgba(180,90,30,0.55)',   label: 'Refinery'    },
  'Military':     { bg: 'linear-gradient(135deg,#8a1010,#ef4444)', glow: 'rgba(220,30,30,0.50)',   label: 'Military'    },
  'Tourism':      { bg: 'linear-gradient(135deg,#9a1a6a,#f472b6)', glow: 'rgba(240,80,180,0.50)',  label: 'Tourism'     },
  'Extraction':   { bg: 'linear-gradient(135deg,#8a7010,#fbbf24)', glow: 'rgba(240,190,0,0.50)',   label: 'Extraction'  },
  'Colony':       { bg: 'linear-gradient(135deg,#4a1a9a,#a855f7)', glow: 'rgba(160,60,255,0.55)',  label: 'Colony'      },
  'Service':      { bg: 'linear-gradient(135deg,#0e7a7a,#2dd4bf)', glow: 'rgba(0,210,190,0.50)',   label: 'Service'     },
};

const DEFAULT_BADGE = { bg: 'linear-gradient(135deg,#4a4a7a,#8888aa)', glow: 'rgba(120,120,180,0.4)', label: '?' };

function getEcoBadge(eco: string) {
  return ECO_BADGE[eco] ?? DEFAULT_BADGE;
}

export function NebulaGlass() {
  const css = `
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;600;700&family=Rajdhani:wght@400;500;600&display=swap');

    .nb-root {
      font-family: 'Rajdhani', sans-serif;
      background:
        radial-gradient(ellipse at 80% 10%, rgba(180,40,220,0.22) 0%, transparent 50%),
        radial-gradient(ellipse at 10% 70%, rgba(0,200,180,0.18) 0%, transparent 45%),
        radial-gradient(ellipse at 50% 50%, rgba(80,0,160,0.15) 0%, transparent 60%),
        linear-gradient(160deg, #060410 0%, #090616 40%, #060b10 100%);
      color: #dde8f8;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }
    .nb-root::before {
      content: '';
      position: fixed; inset: 0; pointer-events: none; z-index: 0;
      background-image:
        radial-gradient(1.2px 1.2px at  8% 14%, rgba(255,255,255,0.22) 0%, transparent 100%),
        radial-gradient(0.8px 0.8px at 22% 38%, rgba(255,255,255,0.14) 0%, transparent 100%),
        radial-gradient(1.0px 1.0px at 45% 72%, rgba(255,255,255,0.18) 0%, transparent 100%),
        radial-gradient(0.7px 0.7px at 67% 19%, rgba(255,255,255,0.12) 0%, transparent 100%),
        radial-gradient(1.3px 1.3px at 83% 55%, rgba(255,255,255,0.16) 0%, transparent 100%),
        radial-gradient(0.9px 0.9px at 91% 88%, rgba(255,255,255,0.10) 0%, transparent 100%),
        radial-gradient(0.6px 0.6px at 34% 91%, rgba(255,255,255,0.13) 0%, transparent 100%);
    }

    .nb-header {
      background: rgba(100,20,160,0.12);
      backdrop-filter: blur(24px); -webkit-backdrop-filter: blur(24px);
      border-bottom: 1px solid rgba(180,80,255,0.28);
      padding: 14px 24px; display: flex; align-items: center; gap: 16px;
      position: relative; z-index: 10;
      box-shadow: 0 4px 32px rgba(140,0,220,0.14), 0 1px 0 rgba(255,255,255,0.04) inset;
    }
    .nb-logo {
      width: 42px; height: 42px; border: 1.5px solid rgba(180,100,255,0.7); border-radius: 50%;
      display: flex; align-items: center; justify-content: center; font-size: 18px; color: #c87eff;
      box-shadow: 0 0 22px rgba(160,60,255,0.5), inset 0 0 14px rgba(140,40,255,0.1);
    }
    .nb-title {
      font-family: 'Orbitron', monospace; font-size: 20px; font-weight: 700;
      background: linear-gradient(90deg,#c87eff 0%,#44eedd 100%);
      -webkit-background-clip: text; -webkit-text-fill-color: transparent;
      background-clip: text; letter-spacing: 2px;
    }
    .nb-sub { font-size: 10px; color: rgba(180,150,220,0.48); letter-spacing: 3px; text-transform: uppercase; }
    .nb-spacer { flex: 1; }
    .nb-badge {
      font-family: 'Orbitron', monospace; font-size: 10px; color: #c87eff;
      border: 1px solid rgba(180,80,255,0.4); border-radius: 6px; padding: 4px 10px;
      background: rgba(140,40,255,0.1); backdrop-filter: blur(8px);
    }
    .nb-syncbtn {
      background: linear-gradient(135deg,rgba(140,40,255,0.8),rgba(0,180,160,0.7));
      color: #fff; border: 1px solid rgba(160,80,255,0.5); border-radius: 10px;
      padding: 8px 18px; font-family: 'Orbitron', monospace; font-size: 10px;
      font-weight: 600; letter-spacing: 1px; cursor: pointer; backdrop-filter: blur(8px);
      box-shadow: 0 2px 18px rgba(140,0,255,0.35);
    }

    .nb-tabs {
      background: rgba(80,10,130,0.07); backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px);
      border-bottom: 1px solid rgba(160,60,255,0.15); padding: 0 20px;
      display: flex; gap: 2px; overflow-x: auto; position: relative; z-index: 10;
    }
    .nb-tab {
      font-family: 'Orbitron', monospace; font-size: 10px; letter-spacing: 1px; text-transform: uppercase;
      padding: 13px 16px; background: none; border: none; border-bottom: 2px solid transparent;
      color: rgba(180,140,220,0.38); cursor: pointer; white-space: nowrap; transition: all 0.2s;
    }
    .nb-tab.active {
      color: #c87eff; border-bottom-color: #a855f7;
      background: linear-gradient(180deg,rgba(140,40,255,0.08) 0%,transparent 100%);
      text-shadow: 0 0 12px rgba(180,80,255,0.6);
    }
    .nb-tab:hover:not(.active) { color: rgba(210,180,255,0.7); }

    .nb-body { display: flex; flex: 1; min-height: 0; position: relative; z-index: 1; }

    .nb-sidebar {
      width: 300px; background: rgba(80,10,130,0.06);
      backdrop-filter: blur(18px); -webkit-backdrop-filter: blur(18px);
      border-right: 1px solid rgba(160,60,255,0.12);
      padding: 18px 14px; overflow-y: auto; display: flex; flex-direction: column; gap: 14px;
    }
    .nb-panel {
      background: rgba(120,20,200,0.07); backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);
      border: 1px solid rgba(160,70,255,0.18); border-radius: 16px; overflow: hidden;
    }
    .nb-panel-hdr {
      background: rgba(120,20,200,0.09); border-bottom: 1px solid rgba(160,70,255,0.13);
      padding: 10px 14px; display: flex; align-items: center; gap: 8px;
    }
    .nb-panel-icon { color: #c87eff; font-size: 14px; filter: drop-shadow(0 0 6px rgba(180,80,255,0.7)); }
    .nb-panel-title {
      font-family: 'Orbitron', monospace; font-size: 10px; font-weight: 600;
      letter-spacing: 1.5px; text-transform: uppercase; color: rgba(220,200,255,0.88); flex: 1;
    }
    .nb-panel-body { padding: 14px; }
    .nb-label { font-size: 11px; font-weight: 600; color: rgba(180,140,220,0.52); letter-spacing: 1px; text-transform: uppercase; margin-bottom: 6px; display: block; }
    .nb-input {
      width: 100%; background: rgba(100,20,180,0.1); border: 1px solid rgba(160,70,255,0.22);
      border-radius: 10px; color: #e0d0ff; font-family: 'Rajdhani', sans-serif; font-size: 14px;
      padding: 9px 12px; outline: none; backdrop-filter: blur(8px);
    }
    .nb-input:focus { border-color: rgba(180,80,255,0.5); box-shadow: 0 0 14px rgba(140,40,255,0.2); }
    .nb-slider-row { display: flex; align-items: center; gap: 10px; margin-top: 6px; }
    .nb-slider { flex: 1; accent-color: #a855f7; }
    .nb-slider-val {
      font-family: 'Orbitron', monospace; font-size: 12px; color: #c87eff;
      min-width: 32px; text-align: right; text-shadow: 0 0 8px rgba(180,80,255,0.5);
    }
    .nb-searchbtn {
      width: 100%; background: linear-gradient(135deg,rgba(140,40,255,0.8),rgba(0,180,160,0.65));
      color: #fff; border: 1px solid rgba(160,80,255,0.45); border-radius: 12px; padding: 12px;
      font-family: 'Orbitron', monospace; font-size: 11px; font-weight: 700;
      letter-spacing: 1.5px; cursor: pointer; backdrop-filter: blur(8px);
      box-shadow: 0 4px 24px rgba(120,0,255,0.32); margin-top: 4px;
    }

    .nb-content { flex: 1; padding: 20px; overflow-y: auto; display: flex; flex-direction: column; gap: 12px; }
    .nb-summary {
      display: flex; align-items: center; gap: 12px; padding: 10px 16px;
      background: rgba(100,20,160,0.07); backdrop-filter: blur(10px);
      border: 1px solid rgba(160,70,255,0.14); border-radius: 12px;
      font-size: 13px; color: rgba(180,140,220,0.62);
    }
    .nb-summary strong { color: #c87eff; font-family: 'Orbitron', monospace; font-size: 12px; text-shadow: 0 0 8px rgba(180,80,255,0.5); }

    /* ── Eco legend ── */
    .nb-legend {
      display: flex; flex-wrap: wrap; gap: 6px; padding: 10px 14px;
      background: rgba(100,20,160,0.07); backdrop-filter: blur(10px);
      border: 1px solid rgba(160,70,255,0.13); border-radius: 12px;
      font-size: 10px;
    }
    .nb-legend-item { display: flex; align-items: center; gap: 5px; color: rgba(200,180,240,0.65); }
    .nb-legend-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }

    /* ── Card ── */
    .nb-card {
      background: rgba(100,15,170,0.07); backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px);
      border: 1px solid rgba(160,70,255,0.14); border-radius: 18px; overflow: hidden; transition: all 0.22s ease;
    }
    .nb-card:hover {
      transform: translateY(-4px); background: rgba(120,20,200,0.11);
      border-color: rgba(180,80,255,0.35);
      box-shadow: 0 14px 42px rgba(120,0,255,0.16), 0 0 60px rgba(0,200,180,0.05), 0 2px 8px rgba(0,0,0,0.5);
    }
    .nb-card-hdr { padding: 13px 16px; display: flex; align-items: center; gap: 10px; border-bottom: 1px solid rgba(160,70,255,0.1); }

    /* Rating badge — coloured by primary economy */
    .nb-rating {
      color: #fff; font-family: 'Orbitron', monospace; font-size: 14px; font-weight: 700;
      border-radius: 10px; padding: 5px 11px; min-width: 46px; text-align: center;
    }
    /* Eco label pill under rating */
    .nb-eco-label {
      font-size: 9px; font-family: 'Orbitron', monospace; letter-spacing: 0.5px;
      color: rgba(255,255,255,0.75); margin-top: 3px; text-align: center; text-transform: uppercase;
    }
    .nb-rating-wrap { display: flex; flex-direction: column; align-items: center; gap: 0; flex-shrink: 0; }

    .nb-sys-name { font-family: 'Orbitron', monospace; font-size: 13px; color: rgba(225,210,255,0.96); font-weight: 600; flex: 1; }
    .nb-dist { font-size: 12px; color: rgba(180,140,220,0.5); }
    .nb-card-body { padding: 12px 16px; }

    .nb-tags { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; }
    .nb-tag        { font-size: 11px; padding: 3px 10px; border-radius: 20px; background: rgba(140,40,255,0.12); border: 1px solid rgba(160,80,255,0.3); color: #c87eff; }
    .nb-tag.teal   { background: rgba(0,200,180,0.1);   border-color: rgba(0,200,180,0.3);   color: #22d3c8; }
    .nb-tag.pink   { background: rgba(240,80,180,0.1);  border-color: rgba(240,80,180,0.28); color: #f472b6; }
    .nb-tag.amber  { background: rgba(250,170,0,0.09);  border-color: rgba(250,170,0,0.25);  color: #fbbf24; }
    .nb-tag.blue   { background: rgba(30,160,240,0.1);  border-color: rgba(30,160,240,0.28); color: #38bdf8; }
    .nb-tag.green  { background: rgba(40,200,110,0.1);  border-color: rgba(40,200,110,0.28); color: #34d399; }
    .nb-tag.red    { background: rgba(220,40,40,0.1);   border-color: rgba(220,40,40,0.28);  color: #f87171; }
    .nb-tag.rust   { background: rgba(180,90,30,0.1);   border-color: rgba(180,90,30,0.28);  color: #fb923c; }

    .nb-stat-row { display: flex; gap: 20px; margin-top: 8px; }
    .nb-stat { display: flex; flex-direction: column; gap: 2px; }
    .nb-stat-lbl { font-size: 10px; color: rgba(160,120,220,0.48); text-transform: uppercase; letter-spacing: 1px; }
    .nb-stat-val { font-size: 13px; color: rgba(220,205,255,0.88); font-weight: 600; }

    .nb-card-footer { padding: 10px 16px; border-top: 1px solid rgba(160,70,255,0.09); display: flex; gap: 8px; justify-content: flex-end; }
    .nb-btn { font-size: 11px; padding: 6px 14px; border-radius: 10px; border: 1px solid rgba(160,70,255,0.18); background: rgba(120,20,200,0.08); color: rgba(200,170,255,0.65); cursor: pointer; font-family: 'Rajdhani', sans-serif; font-weight: 600; backdrop-filter: blur(6px); transition: all 0.15s; }
    .nb-btn:hover { background: rgba(140,40,255,0.15); color: rgba(220,195,255,0.9); }
    .nb-btn.primary { background: rgba(140,40,255,0.18); border-color: rgba(180,80,255,0.42); color: #c87eff; }
  `;

  // Systems with primary economy driving badge colour
  const systems = [
    { name: 'Colonia Gateway', rating: 94, economy: 'High Tech',  dist: '22,000 ly', tags: ['High Tech','Industrial'], tagCls: ['blue',''],     pop: '2.1B', slots: 7,  bodies: 23, star: 'F-class', sec: 'High'   },
    { name: 'Eravate',         rating: 88, economy: 'Industrial', dist: '34.2 ly',   tags: ['Industrial','Refinery'], tagCls: ['amber','rust'],  pop: '450M', slots: 5,  bodies: 14, star: 'G-class', sec: 'Medium' },
    { name: 'Lave',            rating: 81, economy: 'Agriculture',dist: '108.5 ly',  tags: ['Agriculture','Tourism'], tagCls: ['green','pink'],  pop: '1.2B', slots: 6,  bodies: 18, star: 'K-class', sec: 'High'   },
    { name: 'Alioth',          rating: 76, economy: 'Military',   dist: '82.6 ly',   tags: ['Military','Service'],    tagCls: ['red','teal'],    pop: '8.4B', slots: 4,  bodies: 11, star: 'A-class', sec: 'High'   },
  ];

  const legendEntries = [
    { eco: 'High Tech', color: '#22d3ee' }, { eco: 'Industrial', color: '#f59e0b' },
    { eco: 'Agriculture', color: '#34d399' }, { eco: 'Refinery', color: '#cd6c28' },
    { eco: 'Military', color: '#ef4444' }, { eco: 'Tourism', color: '#f472b6' },
    { eco: 'Extraction', color: '#fbbf24' }, { eco: 'Colony', color: '#a855f7' },
  ];

  return (
    <div className="nb-root">
      <style dangerouslySetInnerHTML={{ __html: css }} />

      {/* Header */}
      <div className="nb-header">
        <div className="nb-logo">🎯</div>
        <div>
          <div className="nb-title">ED:FINDER</div>
          <div className="nb-sub">Advanced System Finder &amp; Optimizer</div>
        </div>
        <div className="nb-spacer" />
        <span style={{ fontSize: 12, color: 'rgba(180,140,220,0.42)', marginRight: 8 }}>· Never synced yet</span>
        <button className="nb-syncbtn">⟳ SYNC NOW</button>
        <span className="nb-badge">v3.90</span>
      </div>

      {/* Tabs */}
      <div className="nb-tabs">
        {['🎯 SYSTEM FINDER','⚙️ OPTIMIZER','📊 ECONOMY','📌 PINNED','⚖️ COMPARE','👁 WATCHLIST','🗺️ ROUTE','🛸 FC PLANNER','🌐 MAP','✨ 3D MAP','🏗️ COLONIES'].map((t, i) => (
          <button key={i} className={`nb-tab${i === 0 ? ' active' : ''}`}>{t}</button>
        ))}
      </div>

      <div className="nb-body">
        {/* Sidebar */}
        <div className="nb-sidebar">
          <div className="nb-panel">
            <div className="nb-panel-hdr">
              <span className="nb-panel-icon">📍</span>
              <span className="nb-panel-title">Reference System</span>
              <span style={{ fontSize: 10, color: 'rgba(180,130,220,0.36)' }}>▼</span>
            </div>
            <div className="nb-panel-body">
              <label className="nb-label">System Name</label>
              <input className="nb-input" defaultValue="Sol" />
              <div style={{ marginTop: 8, padding: '7px 11px', background: 'rgba(140,40,255,0.09)', borderRadius: 10, border: '1px solid rgba(160,80,255,0.24)', fontSize: 13, color: '#c87eff', display: 'flex', alignItems: 'center', gap: 8 }}>
                <span>📍</span><span>Sol — 0, 0, 0</span>
              </div>
            </div>
          </div>

          <div className="nb-panel">
            <div className="nb-panel-hdr">
              <span className="nb-panel-icon">📡</span>
              <span className="nb-panel-title">Search Radius</span>
              <span style={{ fontSize: 10, color: 'rgba(180,130,220,0.36)' }}>▼</span>
            </div>
            <div className="nb-panel-body">
              {([['Max Distance (ly)', 50], ['Min Distance (ly)', 0], ['Results Per Page', 50]] as [string, number][]).map(([lbl, val], i) => (
                <div key={i} style={{ marginBottom: i < 2 ? 12 : 0 }}>
                  <label className="nb-label">{lbl}</label>
                  <div className="nb-slider-row">
                    <input type="range" className="nb-slider" defaultValue={val} />
                    <span className="nb-slider-val">{val}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="nb-panel">
            <div className="nb-panel-hdr">
              <span className="nb-panel-icon">⭐</span>
              <span className="nb-panel-title">Rating Filter</span>
              <span style={{ fontSize: 10, color: 'rgba(180,130,220,0.36)' }}>▼</span>
            </div>
            <div className="nb-panel-body">
              <label className="nb-label">Minimum Rating</label>
              <div className="nb-slider-row">
                <input type="range" className="nb-slider" defaultValue={60} />
                <span className="nb-slider-val">60</span>
              </div>
            </div>
          </div>

          <button className="nb-searchbtn">🔍 SEARCH SYSTEMS</button>
        </div>

        {/* Content */}
        <div className="nb-content">
          <div className="nb-summary">
            <span>Found <strong>247 SYSTEMS</strong></span>
            <span>·</span><span>⏱ 843ms</span>
            <div style={{ flex: 1 }} />
            <button className="nb-btn">👁 Watch All</button>
            <button className="nb-btn">📋 Copy Names</button>
          </div>

          {/* Economy colour legend */}
          <div className="nb-legend">
            <span style={{ fontSize: 10, color: 'rgba(200,180,240,0.5)', marginRight: 4, fontFamily: 'Orbitron,monospace', letterSpacing: 1 }}>BADGE KEY:</span>
            {legendEntries.map(({ eco, color }) => (
              <span key={eco} className="nb-legend-item">
                <span className="nb-legend-dot" style={{ background: color, boxShadow: `0 0 6px ${color}88` }} />
                {eco}
              </span>
            ))}
          </div>

          {systems.map((sys, i) => {
            const badge = getEcoBadge(sys.economy);
            return (
              <div className="nb-card" key={i}>
                <div className="nb-card-hdr">
                  {/* Rating badge coloured by primary economy */}
                  <div className="nb-rating-wrap">
                    <span className="nb-rating" style={{ background: badge.bg, boxShadow: `0 2px 16px ${badge.glow}` }}>
                      {sys.rating}
                    </span>
                    <span className="nb-eco-label" style={{ color: 'rgba(255,255,255,0.55)', fontSize: 8 }}>{sys.economy}</span>
                  </div>
                  <span className="nb-sys-name">{sys.name}</span>
                  <span className="nb-dist">📡 {sys.dist}</span>
                  <button style={{ background: 'none', border: 'none', color: 'rgba(180,130,220,0.4)', cursor: 'pointer', fontSize: 16 }}>📌</button>
                </div>
                <div className="nb-card-body">
                  <div className="nb-tags">
                    {sys.tags.map((t, j) => (
                      <span key={j} className={`nb-tag ${sys.tagCls[j] ?? ''}`}>{t}</span>
                    ))}
                    <span className="nb-tag teal">⭐ Landable</span>
                    <span className="nb-tag amber">💰 {sys.pop}</span>
                  </div>
                  <div className="nb-stat-row">
                    <div className="nb-stat"><span className="nb-stat-lbl">Slots</span><span className="nb-stat-val">{sys.slots}</span></div>
                    <div className="nb-stat"><span className="nb-stat-lbl">Bodies</span><span className="nb-stat-val">{sys.bodies}</span></div>
                    <div className="nb-stat"><span className="nb-stat-lbl">Stars</span><span className="nb-stat-val">{sys.star}</span></div>
                    <div className="nb-stat"><span className="nb-stat-lbl">Security</span><span className="nb-stat-val">{sys.sec}</span></div>
                  </div>
                </div>
                <div className="nb-card-footer">
                  <button className="nb-btn">👁 Watch</button>
                  <button className="nb-btn">⚖️ Compare</button>
                  <button className="nb-btn primary">📋 Briefing</button>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
