export function GuardianRuins() {
  const css = `
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;600;700&family=Rajdhani:wght@400;500;600&display=swap');

    @keyframes gr-drift {
      0%   { transform: translate3d(0,0,0); }
      50%  { transform: translate3d(12%, 8%, 0); }
      100% { transform: translate3d(0,0,0); }
    }
    @keyframes gr-glyph {
      0%, 100% { opacity: 0.15; }
      50%       { opacity: 0.30; }
    }

    .gr-root {
      font-family: 'Rajdhani', sans-serif;
      background: #010a06;
      color: #90e0c0;
      min-height: 100vh;
      display: flex; flex-direction: column;
      position: relative; overflow: hidden;
    }
    .gr-bg {
      position: fixed; inset: -20%; width: 140%; height: 140%; pointer-events: none; z-index: 0;
      background:
        radial-gradient(ellipse 55% 60% at 25% 35%, rgba(0,180,100,0.22) 0%, transparent 60%),
        radial-gradient(ellipse 70% 50% at 80% 20%, rgba(0,200,140,0.16) 0%, transparent 55%),
        radial-gradient(ellipse 50% 70% at 60% 80%, rgba(0,140,80,0.18) 0%, transparent 58%),
        radial-gradient(ellipse 40% 45% at 10% 75%, rgba(20,180,120,0.14) 0%, transparent 52%),
        radial-gradient(ellipse 35% 35% at 85% 60%, rgba(0,160,120,0.14) 0%, transparent 50%),
        linear-gradient(150deg, #010a06 0%, #020d08 50%, #01080a 100%);
      animation: gr-drift 40s linear infinite;
    }
    /* Ancient glyph lines */
    .gr-glyph-layer {
      position: fixed; inset: 0; pointer-events: none; z-index: 0;
      background-image:
        linear-gradient(90deg, transparent 49.8%, rgba(0,200,120,0.06) 50%, transparent 50.2%),
        linear-gradient(0deg,  transparent 49.8%, rgba(0,200,120,0.04) 50%, transparent 50.2%),
        linear-gradient(45deg, transparent 49.6%, rgba(0,180,100,0.03) 50%, transparent 50.4%);
      animation: gr-glyph 6s ease-in-out infinite;
    }

    .gr-header {
      position: relative; z-index: 10;
      background: rgba(0,10,6,0.97);
      border-bottom: 1px solid rgba(0,200,120,0.28);
      box-shadow: 0 0 30px rgba(0,180,100,0.15);
      padding: 0 24px; height: 60px;
      display: flex; align-items: center; gap: 16px;
    }
    .gr-logo {
      width: 38px; height: 38px;
      background: rgba(0,180,100,0.15);
      border: 1px solid rgba(0,200,120,0.50);
      clip-path: polygon(50% 0%, 93% 25%, 93% 75%, 50% 100%, 7% 75%, 7% 25%);
      box-shadow: 0 0 16px rgba(0,200,120,0.30), inset 0 0 10px rgba(0,180,100,0.20);
    }
    .gr-title { font-family: 'Orbitron', monospace; font-size: 18px; font-weight: 700; color: #40e0a0; letter-spacing: 3px; text-shadow: 0 0 12px rgba(0,200,120,0.40); }
    .gr-sub   { font-size: 10px; color: rgba(60,200,140,0.50); letter-spacing: 2px; text-transform: uppercase; margin-top: 2px; }
    .gr-sync  { margin-left: auto; background: rgba(0,180,100,0.12); border: 1px solid rgba(0,200,120,0.38); color: #40e0a0; padding: 6px 14px; font-family: 'Orbitron', monospace; font-size: 11px; letter-spacing: 1px; cursor: pointer; }
    .gr-ver   { background: rgba(0,180,100,0.08); border: 1px solid rgba(0,200,120,0.25); color: rgba(60,200,140,0.80); padding: 3px 8px; font-size: 11px; font-family: 'Orbitron', monospace; }

    .gr-body  { display: flex; flex: 1; position: relative; z-index: 2; }
    .gr-side  { width: 280px; background: rgba(0,8,4,0.92); border-right: 1px solid rgba(0,200,120,0.10); padding: 16px; display: flex; flex-direction: column; gap: 14px; }
    .gr-panel { background: rgba(0,14,8,0.72); border: 1px solid rgba(0,200,120,0.16); padding: 14px; position: relative; }
    .gr-panel::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 1px; background: linear-gradient(90deg, transparent, rgba(0,200,120,0.35), transparent); }
    .gr-panel-title { font-family: 'Orbitron', monospace; font-size: 10px; letter-spacing: 2px; color: rgba(60,200,140,0.62); margin-bottom: 10px; }
    .gr-label { font-size: 11px; color: rgba(60,180,120,0.55); letter-spacing: 1px; text-transform: uppercase; margin-bottom: 4px; display: block; }
    .gr-input { width: 100%; background: rgba(0,8,4,0.75); border: 1px solid rgba(0,200,120,0.20); color: #90e0c0; padding: 7px 10px; font-family: 'Rajdhani', sans-serif; font-size: 13px; box-sizing: border-box; }
    .gr-btn   { width: 100%; background: rgba(0,180,100,0.14); border: 1px solid rgba(0,200,120,0.42); color: #40e0a0; padding: 9px; font-family: 'Orbitron', monospace; font-size: 11px; letter-spacing: 2px; cursor: pointer; text-align: center; }

    .gr-main  { flex: 1; padding: 20px; display: flex; flex-direction: column; gap: 10px; overflow-y: auto; }
    .gr-card  { background: rgba(0,10,6,0.88); border: 1px solid rgba(0,200,120,0.16); padding: 16px; display: flex; align-items: center; gap: 16px; position: relative; }
    .gr-card::before { content: ''; position: absolute; top: 0; left: 0; width: 3px; height: 100%; background: rgba(0,200,120,0.30); }
    .gr-card:hover { border-color: rgba(0,200,120,0.40); }
    .gr-rank  { font-family: 'Orbitron', monospace; font-size: 22px; font-weight: 700; color: rgba(0,180,100,0.35); width: 32px; text-align: center; }
    .gr-info  { flex: 1; }
    .gr-sys   { font-family: 'Orbitron', monospace; font-size: 13px; color: #40e0a0; margin-bottom: 4px; }
    .gr-dist  { font-size: 12px; color: rgba(60,180,120,0.55); }
    .gr-score { font-family: 'Orbitron', monospace; font-size: 20px; font-weight: 700; color: rgba(80,220,160,0.95); }
    .gr-badge { display: inline-block; padding: 2px 8px; border: 1px solid; font-size: 10px; letter-spacing: 1px; margin-right: 4px; }
    .gr-badge-ht   { color: #60c0ff; border-color: rgba(60,160,255,0.35); background: rgba(10,25,60,0.15); }
    .gr-badge-ind  { color: #f5a030; border-color: rgba(200,120,0,0.35); background: rgba(50,25,0,0.15); }
    .gr-badge-agr  { color: #50d090; border-color: rgba(40,160,80,0.40); background: rgba(10,40,20,0.15); }
    .gr-badge-ref  { color: #e07040; border-color: rgba(180,80,30,0.35); background: rgba(40,12,3,0.15); }
  `;

  const systems = [
    { name: "Col 285 Sector XP-O b6-3", dist: "41.2 LY", score: 94, eco: "High Tech", badge: "gr-badge-ht" },
    { name: "Eravate", dist: "14.9 LY", score: 87, eco: "Industrial", badge: "gr-badge-ind" },
    { name: "Kamadhenu", dist: "28.6 LY", score: 81, eco: "Agriculture", badge: "gr-badge-agr" },
    { name: "HIP 20277", dist: "55.3 LY", score: 76, eco: "Refinery", badge: "gr-badge-ref" },
  ];

  return (
    <div className="gr-root">
      <style>{css}</style>
      <div className="gr-bg" />
      <div className="gr-glyph-layer" />

      <header className="gr-header">
        <div className="gr-logo" />
        <div>
          <div className="gr-title">ED:FINDER</div>
          <div className="gr-sub">Colonisation Planner</div>
        </div>
        <button className="gr-sync">⟳ SYNC NOW</button>
        <span className="gr-ver">V3.30</span>
      </header>

      <div className="gr-body">
        <aside className="gr-side">
          <div className="gr-panel">
            <div className="gr-panel-title">REFERENCE SYSTEM</div>
            <label className="gr-label">System Name</label>
            <input className="gr-input" defaultValue="Sol" />
          </div>
          <div className="gr-panel">
            <div className="gr-panel-title">SEARCH RADIUS</div>
            <label className="gr-label">Max Distance</label>
            <input className="gr-input" defaultValue="50 LY" />
            <div style={{marginTop:10}}>
              <label className="gr-label">Min Distance</label>
              <input className="gr-input" defaultValue="0 LY" />
            </div>
          </div>
          <div className="gr-panel">
            <div className="gr-panel-title">ECONOMY FILTER</div>
            <label className="gr-label">Type</label>
            <input className="gr-input" defaultValue="All Types" />
          </div>
          <button className="gr-btn">◈ SEARCH SYSTEMS</button>
        </aside>

        <main className="gr-main">
          <div style={{fontFamily:"'Orbitron',monospace",fontSize:11,color:"rgba(0,180,100,0.45)",letterSpacing:2,marginBottom:4}}>SEARCH RESULTS — 4 SYSTEMS FOUND</div>
          {systems.map((s, i) => (
            <div key={i} className="gr-card">
              <div className="gr-rank">{i + 1}</div>
              <div className="gr-info">
                <div className="gr-sys">{s.name}</div>
                <div style={{marginTop:4}}>
                  <span className={`gr-badge ${s.badge}`}>{s.eco}</span>
                </div>
                <div className="gr-dist" style={{marginTop:6}}>{s.dist} from Sol</div>
              </div>
              <div className="gr-score">{s.score}</div>
            </div>
          ))}
        </main>
      </div>
    </div>
  );
}
