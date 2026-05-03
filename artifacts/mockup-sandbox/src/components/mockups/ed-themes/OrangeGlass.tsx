const ECO_BADGE: Record<string, { bg: string; glow: string }> = {
  'High Tech':   { bg: 'linear-gradient(135deg,#0d7abf,#22d3ee)', glow: 'rgba(0,180,240,0.55)'  },
  'Industrial':  { bg: 'linear-gradient(135deg,#b06010,#f59e0b)', glow: 'rgba(220,140,0,0.55)'  },
  'Agriculture': { bg: 'linear-gradient(135deg,#1a7a38,#34d399)', glow: 'rgba(40,200,110,0.50)' },
  'Refinery':    { bg: 'linear-gradient(135deg,#8a3a10,#cd6c28)', glow: 'rgba(180,90,30,0.55)'  },
  'Military':    { bg: 'linear-gradient(135deg,#8a1010,#ef4444)', glow: 'rgba(220,30,30,0.50)'  },
  'Tourism':     { bg: 'linear-gradient(135deg,#9a1a6a,#f472b6)', glow: 'rgba(240,80,180,0.50)' },
  'Extraction':  { bg: 'linear-gradient(135deg,#8a7010,#fbbf24)', glow: 'rgba(240,190,0,0.50)'  },
  'Colony':      { bg: 'linear-gradient(135deg,#4a1a9a,#a855f7)', glow: 'rgba(160,60,255,0.55)' },
  'Service':     { bg: 'linear-gradient(135deg,#0e7a7a,#2dd4bf)', glow: 'rgba(0,210,190,0.50)'  },
};
const DEFAULT_BADGE = { bg: 'linear-gradient(135deg,#334,#556)', glow: 'rgba(100,110,140,0.4)' };
function getEcoBadge(eco: string) { return ECO_BADGE[eco] ?? DEFAULT_BADGE; }

export function OrangeGlass() {
  const css = `
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;600;700&family=Rajdhani:wght@400;500;600&display=swap');

    /* ── Nebula animation layers ── */
    @keyframes og-drift-a {
      0%   { transform: rotate(0deg)   scale(1.0); }
      50%  { transform: rotate(180deg) scale(1.15); }
      100% { transform: rotate(360deg) scale(1.0); }
    }
    @keyframes og-drift-b {
      0%   { transform: rotate(0deg)   scale(1.1); }
      50%  { transform: rotate(-200deg) scale(0.95); }
      100% { transform: rotate(-360deg) scale(1.1); }
    }
    @keyframes og-drift-c {
      0%   { transform: rotate(0deg) translateX(0px); }
      33%  { transform: rotate(120deg) translateX(30px); }
      66%  { transform: rotate(240deg) translateX(-20px); }
      100% { transform: rotate(360deg) translateX(0px); }
    }
    @keyframes og-twinkle {
      0%, 100% { opacity: 1; }
      50%       { opacity: 0.4; }
    }

    /* ── Root wrapper ── */
    .og-root {
      font-family: 'Rajdhani', sans-serif;
      color: #d0d8e8;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      position: relative;
      overflow: hidden;
      /* base layer — near-black void */
      background: #04050a;
    }

    /* ── Layer 1: deep nebula base colours ── */
    .og-nebula-base {
      position: fixed; inset: -20%; width: 140%; height: 140%;
      pointer-events: none; z-index: 0;
      background:
        radial-gradient(ellipse 70% 55% at 20% 30%,  rgba(180,60,0,0.28)    0%, transparent 65%),
        radial-gradient(ellipse 80% 60% at 75% 20%,  rgba(80,10,120,0.32)   0%, transparent 60%),
        radial-gradient(ellipse 60% 70% at 55% 75%,  rgba(10,50,140,0.26)   0%, transparent 60%),
        radial-gradient(ellipse 90% 45% at 10% 80%,  rgba(140,30,0,0.22)    0%, transparent 55%),
        radial-gradient(ellipse 55% 65% at 85% 65%,  rgba(50,0,100,0.20)    0%, transparent 55%),
        linear-gradient(170deg, #04060e 0%, #060408 40%, #050610 100%);
      animation: og-drift-a 80s linear infinite;
      transform-origin: 50% 50%;
    }

    /* ── Layer 2: swirling orange/amber arm ── */
    .og-nebula-arm {
      position: fixed; inset: -30%; width: 160%; height: 160%;
      pointer-events: none; z-index: 0;
      background:
        radial-gradient(ellipse 40% 80% at 35% 55%,  rgba(255,100,0,0.14)   0%, transparent 55%),
        radial-gradient(ellipse 60% 40% at 65% 30%,  rgba(255,140,0,0.10)   0%, transparent 50%),
        radial-gradient(ellipse 30% 60% at 80% 75%,  rgba(200,60,0,0.12)    0%, transparent 50%),
        radial-gradient(ellipse 50% 35% at 15% 40%,  rgba(255,80,0,0.09)    0%, transparent 45%);
      animation: og-drift-b 110s linear infinite;
      transform-origin: 45% 55%;
      mix-blend-mode: screen;
    }

    /* ── Layer 3: cool blue/teal wisps ── */
    .og-nebula-wisps {
      position: fixed; inset: -20%; width: 140%; height: 140%;
      pointer-events: none; z-index: 0;
      background:
        radial-gradient(ellipse 45% 30% at 60% 15%,  rgba(0,120,200,0.16)   0%, transparent 50%),
        radial-gradient(ellipse 35% 55% at 90% 50%,  rgba(0,180,160,0.12)   0%, transparent 45%),
        radial-gradient(ellipse 50% 30% at 25% 90%,  rgba(60,0,180,0.14)    0%, transparent 50%),
        radial-gradient(ellipse 30% 40% at 50% 50%,  rgba(0,80,160,0.10)    0%, transparent 40%);
      animation: og-drift-c 140s linear infinite;
      transform-origin: 55% 45%;
      mix-blend-mode: screen;
    }

    /* ── Layer 4: star field ── */
    .og-stars {
      position: fixed; inset: 0; pointer-events: none; z-index: 0;
      background-image:
        radial-gradient(1.2px 1.2px at  6% 12%, rgba(255,255,255,0.90) 0%, transparent 100%),
        radial-gradient(0.8px 0.8px at 19% 34%, rgba(255,255,255,0.60) 0%, transparent 100%),
        radial-gradient(1.0px 1.0px at 43% 68%, rgba(255,255,255,0.75) 0%, transparent 100%),
        radial-gradient(0.7px 0.7px at 67% 22%, rgba(255,255,255,0.50) 0%, transparent 100%),
        radial-gradient(1.3px 1.3px at 82% 57%, rgba(255,255,255,0.80) 0%, transparent 100%),
        radial-gradient(0.9px 0.9px at 91% 85%, rgba(255,255,255,0.55) 0%, transparent 100%),
        radial-gradient(0.6px 0.6px at 33% 91%, rgba(255,255,255,0.45) 0%, transparent 100%),
        radial-gradient(1.1px 1.1px at 55% 44%, rgba(255,255,255,0.65) 0%, transparent 100%),
        radial-gradient(0.8px 0.8px at 74% 08%, rgba(255,255,255,0.50) 0%, transparent 100%),
        radial-gradient(0.7px 0.7px at 12% 76%, rgba(255,255,255,0.55) 0%, transparent 100%),
        radial-gradient(1.0px 1.0px at 28% 58%, rgba(255,220,180,0.50) 0%, transparent 100%),
        radial-gradient(0.9px 0.9px at 78% 38%, rgba(180,200,255,0.55) 0%, transparent 100%),
        radial-gradient(1.2px 1.2px at 48% 82%, rgba(255,180,150,0.45) 0%, transparent 100%),
        radial-gradient(0.6px 0.6px at 92% 25%, rgba(200,220,255,0.40) 0%, transparent 100%),
        radial-gradient(0.8px 0.8px at 37% 15%, rgba(255,255,255,0.60) 0%, transparent 100%),
        radial-gradient(1.1px 1.1px at 60% 94%, rgba(255,255,255,0.45) 0%, transparent 100%);
      animation: og-twinkle 7s ease-in-out infinite alternate;
    }

    /* ── Darkening overlay so UI remains readable ── */
    .og-overlay {
      position: fixed; inset: 0; pointer-events: none; z-index: 1;
      background: rgba(4,5,10,0.45);
    }

    /* all UI above the nebula */
    .og-header, .og-tabs, .og-body { position: relative; z-index: 2; }

    /* ── Header: grey glass + orange accent ── */
    .og-header {
      background: rgba(255,255,255,0.04);
      backdrop-filter: blur(28px); -webkit-backdrop-filter: blur(28px);
      border-bottom: 1px solid rgba(255,106,0,0.30);
      padding: 14px 24px; display: flex; align-items: center; gap: 16px;
      position: sticky; top: 0; z-index: 100;
      box-shadow: 0 4px 40px rgba(0,0,0,0.5), 0 1px 0 rgba(255,255,255,0.06) inset;
    }
    .og-logo {
      width: 42px; height: 42px;
      border: 2px solid #ff6a00; border-radius: 50%;
      display: flex; align-items: center; justify-content: center;
      font-size: 18px; color: #ff7a00;
      box-shadow: 0 0 20px rgba(255,106,0,0.45), inset 0 0 12px rgba(255,106,0,0.08);
      flex-shrink: 0;
    }
    .og-title {
      font-family: 'Orbitron', monospace; font-size: 20px; font-weight: 700;
      color: #ffffff; letter-spacing: 2px; text-transform: uppercase;
      text-shadow: 0 0 24px rgba(255,106,0,0.40);
    }
    .og-sub { font-size: 11px; color: rgba(155,170,187,0.60); letter-spacing: 3px; text-transform: uppercase; }
    .og-spacer { flex: 1; }
    .og-badge {
      font-family: 'Orbitron', monospace; font-size: 10px;
      color: #ff8c33; border: 1px solid rgba(255,106,0,0.40); border-radius: 6px;
      padding: 4px 10px; background: rgba(255,106,0,0.08); backdrop-filter: blur(8px);
    }
    .og-syncbtn {
      background: linear-gradient(135deg, rgba(196,77,0,0.9), rgba(255,106,0,0.85));
      color: #fff; border: 1px solid rgba(255,130,0,0.45); border-radius: 8px;
      padding: 8px 18px; font-family: 'Orbitron', monospace; font-size: 10px;
      font-weight: 600; letter-spacing: 1px; cursor: pointer;
      box-shadow: 0 2px 20px rgba(255,90,0,0.35);
    }

    /* ── Tabs ── */
    .og-tabs {
      background: rgba(255,255,255,0.025);
      backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
      border-bottom: 1px solid rgba(255,255,255,0.07);
      padding: 0 24px; display: flex; gap: 4px; overflow-x: auto;
    }
    .og-tab {
      font-family: 'Orbitron', monospace; font-size: 11px; letter-spacing: 1.5px;
      text-transform: uppercase; padding: 12px 20px; background: none; border: none;
      border-bottom: 3px solid transparent; color: rgba(155,170,187,0.48);
      cursor: pointer; white-space: nowrap; transition: all 0.2s;
    }
    .og-tab.active { color: #ff8c33; border-bottom-color: #ff6a00; }
    .og-tab:hover:not(.active) { color: #d0d8e8; border-bottom-color: rgba(255,255,255,0.12); }

    /* ── Layout ── */
    .og-body { display: flex; flex: 1; min-height: 0; }

    /* ── Sidebar ── */
    .og-sidebar {
      width: 300px;
      background: rgba(255,255,255,0.025);
      backdrop-filter: blur(24px); -webkit-backdrop-filter: blur(24px);
      border-right: 1px solid rgba(255,255,255,0.07);
      padding: 18px 14px; overflow-y: auto;
      display: flex; flex-direction: column; gap: 14px;
    }

    /* ── Panels ── */
    .og-panel {
      background: rgba(255,255,255,0.045);
      backdrop-filter: blur(18px); -webkit-backdrop-filter: blur(18px);
      border: 1px solid rgba(255,255,255,0.09);
      border-radius: 12px; overflow: hidden;
    }
    .og-panel-hdr {
      background: rgba(255,255,255,0.04); border-bottom: 1px solid rgba(255,255,255,0.07);
      padding: 10px 14px; display: flex; align-items: center; gap: 8px;
    }
    .og-panel-icon { color: #ff7a00; font-size: 14px; filter: drop-shadow(0 0 5px rgba(255,106,0,0.6)); }
    .og-panel-title { font-family: 'Orbitron', monospace; font-size: 10px; font-weight: 600; letter-spacing: 1.5px; text-transform: uppercase; color: rgba(208,216,232,0.88); flex: 1; }
    .og-panel-body { padding: 14px; }

    .og-label { font-size: 11px; font-weight: 600; color: rgba(155,170,187,0.55); letter-spacing: 1px; text-transform: uppercase; margin-bottom: 6px; display: block; }
    .og-input {
      width: 100%; background: rgba(255,255,255,0.055); border: 1px solid rgba(255,255,255,0.10);
      border-radius: 8px; color: #d0d8e8; font-family: 'Rajdhani', sans-serif; font-size: 14px;
      padding: 9px 12px; outline: none;
    }
    .og-input:focus { border-color: rgba(255,106,0,0.50); box-shadow: 0 0 14px rgba(255,106,0,0.14); }
    .og-slider-row { display: flex; align-items: center; gap: 10px; margin-top: 6px; }
    .og-slider { flex: 1; accent-color: #ff6a00; }
    .og-slider-val { font-family: 'Orbitron', monospace; font-size: 12px; color: #ff8c33; min-width: 32px; text-align: right; }
    .og-searchbtn {
      width: 100%;
      background: linear-gradient(135deg, rgba(196,77,0,0.9), rgba(255,106,0,0.85));
      color: #fff; border: 1px solid rgba(255,130,0,0.40); border-radius: 10px; padding: 12px;
      font-family: 'Orbitron', monospace; font-size: 11px; font-weight: 700;
      letter-spacing: 1.5px; cursor: pointer; box-shadow: 0 4px 24px rgba(255,90,0,0.30);
      margin-top: 4px;
    }

    /* ── Content ── */
    .og-content { flex: 1; padding: 20px; overflow-y: auto; display: flex; flex-direction: column; gap: 12px; }

    .og-summary {
      display: flex; align-items: center; gap: 12px; padding: 10px 16px;
      background: rgba(255,255,255,0.04); backdrop-filter: blur(12px);
      border: 1px solid rgba(255,255,255,0.08); border-radius: 10px;
      font-size: 13px; color: rgba(155,170,187,0.65);
    }
    .og-summary strong { color: #ff8c33; font-family: 'Orbitron', monospace; font-size: 12px; }

    /* ── Cards ── */
    .og-card {
      background: rgba(255,255,255,0.045);
      backdrop-filter: blur(20px); -webkit-backdrop-filter: blur(20px);
      border: 1px solid rgba(255,255,255,0.09);
      border-radius: 14px; overflow: hidden; transition: all 0.22s ease;
    }
    .og-card:hover {
      transform: translateY(-4px);
      background: rgba(255,255,255,0.07);
      border-color: rgba(255,106,0,0.38);
      box-shadow: 0 16px 48px rgba(0,0,0,0.55), 0 0 0 1px rgba(255,106,0,0.12), 0 4px 28px rgba(255,90,0,0.12);
    }
    .og-card-hdr {
      padding: 12px 16px; display: flex; align-items: center; gap: 12px;
      background: rgba(255,255,255,0.04); border-bottom: 1px solid rgba(255,255,255,0.07);
    }

    .og-rating-wrap { display: flex; flex-direction: column; align-items: center; flex-shrink: 0; }
    .og-rating { color: #fff; font-family: 'Orbitron', monospace; font-size: 14px; font-weight: 700; border-radius: 8px; padding: 5px 11px; min-width: 46px; text-align: center; }
    .og-eco-lbl { font-size: 8px; color: rgba(255,255,255,0.50); font-family: 'Orbitron', monospace; text-transform: uppercase; margin-top: 2px; }

    .og-sys-name { font-family: 'Orbitron', monospace; font-size: 14px; font-weight: 600; color: #ffffff; flex: 1; }
    .og-dist { font-size: 12px; color: #ff8c33; font-weight: 600; }
    .og-card-body { padding: 14px 16px; }

    .og-tags { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 10px; }
    .og-tag { font-size: 12px; font-weight: 600; padding: 3px 10px; border-radius: 4px; background: rgba(255,255,255,0.06); border: 1px solid rgba(255,255,255,0.12); color: rgba(208,216,232,0.80); }
    .og-tag.eco-refinery    { background: rgba(255,106,0,0.12);  border-color: rgba(255,106,0,0.28);  color: #ff9133; }
    .og-tag.eco-agriculture { background: rgba(61,220,132,0.10); border-color: rgba(61,220,132,0.28); color: #3ddc84; }
    .og-tag.eco-industrial  { background: rgba(77,166,255,0.10); border-color: rgba(77,166,255,0.25); color: #4da6ff; }
    .og-tag.eco-hightech    { background: rgba(187,119,255,0.10);border-color: rgba(187,119,255,0.28);color: #bb77ff; }
    .og-tag.eco-military    { background: rgba(255,68,85,0.10);  border-color: rgba(255,68,85,0.28);  color: #ff4455; }
    .og-tag.eco-tourism     { background: rgba(244,114,182,0.10);border-color: rgba(244,114,182,0.26);color: #f472b6; }
    .og-tag.green { background: rgba(61,220,132,0.10); border-color: rgba(61,220,132,0.28); color: #3ddc84; }
    .og-tag.gold  { background: rgba(255,215,0,0.10);  border-color: rgba(255,215,0,0.26);  color: #ffd700; }

    .og-stat-row { display: flex; gap: 22px; margin-top: 8px; }
    .og-stat { display: flex; flex-direction: column; gap: 2px; }
    .og-stat-lbl { font-size: 10px; color: rgba(155,170,187,0.50); text-transform: uppercase; letter-spacing: 1px; }
    .og-stat-val { font-size: 13px; color: rgba(208,216,232,0.90); font-weight: 600; }

    .og-card-footer { padding: 10px 16px; border-top: 1px solid rgba(255,255,255,0.06); display: flex; gap: 8px; justify-content: flex-end; }
    .og-btn { font-size: 11px; padding: 6px 14px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.11); background: rgba(255,255,255,0.05); color: rgba(208,216,232,0.65); cursor: pointer; font-family: 'Rajdhani', sans-serif; font-weight: 600; transition: all 0.15s; }
    .og-btn:hover { background: rgba(255,255,255,0.10); border-color: rgba(255,255,255,0.20); color: #d0d8e8; }
    .og-btn.primary { background: rgba(255,106,0,0.14); border-color: rgba(255,106,0,0.40); color: #ff8c33; }
    .og-btn.primary:hover { background: rgba(255,106,0,0.24); }
  `;

  const systems = [
    { name: 'Colonia Gateway', economy: 'High Tech',   dist: '22,000 ly', tags: [['High Tech','eco-hightech'],['Industrial','eco-industrial']], pop: '2.1B', slots: 7,  bodies: 23, star: 'F-class', sec: 'High',   score: 94 },
    { name: 'Eravate',         economy: 'Industrial',  dist: '34.2 ly',   tags: [['Industrial','eco-industrial'],['Refinery','eco-refinery']],  pop: '450M', slots: 5,  bodies: 14, star: 'G-class', sec: 'Medium', score: 88 },
    { name: 'Lave',            economy: 'Agriculture', dist: '108.5 ly',  tags: [['Agriculture','eco-agriculture'],['Tourism','eco-tourism']],   pop: '1.2B', slots: 6,  bodies: 18, star: 'K-class', sec: 'High',   score: 81 },
    { name: 'Alioth',          economy: 'Military',    dist: '82.6 ly',   tags: [['Military','eco-military'],['Service','']],                   pop: '8.4B', slots: 4,  bodies: 11, star: 'A-class', sec: 'High',   score: 76 },
  ];

  return (
    <div className="og-root">
      <style dangerouslySetInnerHTML={{ __html: css }} />

      {/* Nebula background layers */}
      <div className="og-nebula-base" />
      <div className="og-nebula-arm" />
      <div className="og-nebula-wisps" />
      <div className="og-stars" />
      <div className="og-overlay" />

      {/* Header */}
      <div className="og-header">
        <div className="og-logo">🎯</div>
        <div>
          <div className="og-title">ED:Finder</div>
          <div className="og-sub">Advanced System Finder &amp; Optimizer</div>
        </div>
        <div className="og-spacer" />
        <span style={{ fontSize: 12, color: 'rgba(155,170,187,0.45)', marginRight: 8 }}>· Never synced yet</span>
        <button className="og-syncbtn">⟳ SYNC NOW</button>
        <span className="og-badge">v3.90</span>
      </div>

      {/* Tabs */}
      <div className="og-tabs">
        {['🎯 System Finder','⚙️ Optimizer','📊 Economy','📌 Pinned','⚖️ Compare','👁 Watchlist','🗺️ Route','🛸 FC Planner','🌐 Map','✨ 3D Map','🏗️ Colonies'].map((t, i) => (
          <button key={i} className={`og-tab${i === 0 ? ' active' : ''}`}>{t}</button>
        ))}
      </div>

      <div className="og-body">
        {/* Sidebar */}
        <div className="og-sidebar">
          <div className="og-panel">
            <div className="og-panel-hdr">
              <span className="og-panel-icon">📍</span>
              <span className="og-panel-title">Reference System</span>
              <span style={{ fontSize: 10, color: 'rgba(155,170,187,0.35)' }}>▼</span>
            </div>
            <div className="og-panel-body">
              <label className="og-label">System Name</label>
              <input className="og-input" defaultValue="Sol" />
              <div style={{ marginTop: 8, padding: '7px 11px', background: 'rgba(255,106,0,0.09)', borderRadius: 8, border: '1px solid rgba(255,106,0,0.22)', fontSize: 13, color: '#ff8c33', display: 'flex', alignItems: 'center', gap: 8 }}>
                <span>📍</span><span>Sol — 0, 0, 0</span>
              </div>
            </div>
          </div>
          <div className="og-panel">
            <div className="og-panel-hdr">
              <span className="og-panel-icon">📡</span>
              <span className="og-panel-title">Search Radius</span>
              <span style={{ fontSize: 10, color: 'rgba(155,170,187,0.35)' }}>▼</span>
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
          <div className="og-panel">
            <div className="og-panel-hdr">
              <span className="og-panel-icon">⭐</span>
              <span className="og-panel-title">Rating Filter</span>
              <span style={{ fontSize: 10, color: 'rgba(155,170,187,0.35)' }}>▼</span>
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
            <span>Found <strong>247 systems</strong></span>
            <span>·</span>
            <span style={{ color: 'rgba(155,170,187,0.50)' }}>⏱ 843ms</span>
            <div style={{ flex: 1 }} />
            <button className="og-btn">👁 Watch All</button>
            <button className="og-btn">📋 Copy Names</button>
          </div>

          {systems.map((sys, i) => {
            const badge = getEcoBadge(sys.economy);
            return (
              <div className="og-card" key={i}>
                <div className="og-card-hdr">
                  <div className="og-rating-wrap">
                    <span className="og-rating" style={{ background: badge.bg, boxShadow: `0 2px 14px ${badge.glow}` }}>{sys.score}</span>
                    <span className="og-eco-lbl">{sys.economy}</span>
                  </div>
                  <span className="og-sys-name">{sys.name}</span>
                  <span className="og-dist">📡 {sys.dist}</span>
                  <button style={{ background: 'none', border: 'none', color: 'rgba(155,170,187,0.38)', cursor: 'pointer', fontSize: 16 }}>📌</button>
                </div>
                <div className="og-card-body">
                  <div className="og-tags">
                    {sys.tags.map(([label, cls], j) => (
                      <span key={j} className={`og-tag ${cls}`}>{label}</span>
                    ))}
                    <span className="og-tag green">⭐ Landable</span>
                    <span className="og-tag gold">💰 {sys.pop}</span>
                  </div>
                  <div className="og-stat-row">
                    <div className="og-stat"><span className="og-stat-lbl">Slots</span><span className="og-stat-val">{sys.slots}</span></div>
                    <div className="og-stat"><span className="og-stat-lbl">Bodies</span><span className="og-stat-val">{sys.bodies}</span></div>
                    <div className="og-stat"><span className="og-stat-lbl">Stars</span><span className="og-stat-val">{sys.star}</span></div>
                    <div className="og-stat"><span className="og-stat-lbl">Security</span><span className="og-stat-val">{sys.sec}</span></div>
                  </div>
                </div>
                <div className="og-card-footer">
                  <button className="og-btn">👁 Watch</button>
                  <button className="og-btn">⚖️ Compare</button>
                  <button className="og-btn primary">📋 Briefing</button>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
