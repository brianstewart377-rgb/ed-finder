export function DeepVoid() {
  const css = `
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;600;700&family=Rajdhani:wght@400;500;600&display=swap');

    .dv-root {
      font-family: 'Rajdhani', sans-serif;
      background: #000000;
      color: #c8d8e8;
      min-height: 100vh;
      display: flex; flex-direction: column;
      position: relative; overflow: hidden;
    }
    .dv-bg {
      position: fixed; inset: 0; pointer-events: none; z-index: 0;
      background:
        radial-gradient(1px 1px at 15% 22%, rgba(255,255,255,0.70) 0%, transparent 100%),
        radial-gradient(1px 1px at 35% 8%,  rgba(255,255,255,0.50) 0%, transparent 100%),
        radial-gradient(1px 1px at 60% 35%, rgba(255,255,255,0.65) 0%, transparent 100%),
        radial-gradient(1px 1px at 80% 15%, rgba(255,255,255,0.55) 0%, transparent 100%),
        radial-gradient(1px 1px at 92% 62%, rgba(255,255,255,0.60) 0%, transparent 100%),
        radial-gradient(1px 1px at 10% 70%, rgba(255,255,255,0.45) 0%, transparent 100%),
        radial-gradient(1px 1px at 45% 88%, rgba(255,255,255,0.50) 0%, transparent 100%),
        radial-gradient(1px 1px at 73% 80%, rgba(255,255,255,0.55) 0%, transparent 100%),
        radial-gradient(1px 1px at 28% 52%, rgba(180,220,255,0.40) 0%, transparent 100%),
        radial-gradient(1px 1px at 55% 60%, rgba(180,220,255,0.35) 0%, transparent 100%),
        radial-gradient(ellipse 40% 20% at 50% 50%, rgba(0,180,220,0.04) 0%, transparent 60%),
        #000000;
    }
    /* Horizon line */
    .dv-horizon {
      position: fixed; pointer-events: none; z-index: 0;
      left: 0; right: 0; bottom: 30%;
      height: 1px;
      background: linear-gradient(90deg, transparent, rgba(0,200,255,0.08) 30%, rgba(0,200,255,0.12) 50%, rgba(0,200,255,0.08) 70%, transparent);
    }

    .dv-header {
      position: relative; z-index: 10;
      background: #000;
      border-bottom: 1px solid rgba(0,180,220,0.22);
      padding: 0 24px; height: 60px;
      display: flex; align-items: center; gap: 16px;
    }
    .dv-logo {
      width: 38px; height: 38px;
      border: 1px solid rgba(0,200,255,0.40);
      background: rgba(0,180,220,0.06);
      display: flex; align-items: center; justify-content: center;
      font-family: 'Orbitron', monospace; font-size: 16px; color: rgba(0,200,255,0.7);
    }
    .dv-title { font-family: 'Orbitron', monospace; font-size: 18px; font-weight: 700; color: rgba(0,200,255,0.85); letter-spacing: 3px; }
    .dv-sub   { font-size: 10px; color: rgba(0,160,200,0.45); letter-spacing: 2px; text-transform: uppercase; margin-top: 2px; }
    .dv-sync  { margin-left: auto; background: rgba(0,180,220,0.08); border: 1px solid rgba(0,180,220,0.30); color: rgba(0,200,255,0.80); padding: 6px 14px; font-family: 'Orbitron', monospace; font-size: 11px; letter-spacing: 1px; cursor: pointer; }
    .dv-ver   { background: rgba(0,180,220,0.05); border: 1px solid rgba(0,180,220,0.20); color: rgba(0,180,220,0.65); padding: 3px 8px; font-size: 11px; font-family: 'Orbitron', monospace; }

    .dv-body  { display: flex; flex: 1; position: relative; z-index: 2; }
    .dv-side  { width: 280px; background: rgba(0,0,0,0.95); border-right: 1px solid rgba(0,180,220,0.10); padding: 16px; display: flex; flex-direction: column; gap: 12px; }
    .dv-panel { background: transparent; border: 1px solid rgba(0,180,220,0.12); padding: 14px; }
    .dv-panel-title { font-family: 'Orbitron', monospace; font-size: 10px; letter-spacing: 2px; color: rgba(0,180,220,0.50); margin-bottom: 10px; }
    .dv-label { font-size: 11px; color: rgba(0,160,200,0.48); letter-spacing: 1px; text-transform: uppercase; margin-bottom: 4px; display: block; }
    .dv-input { width: 100%; background: rgba(0,0,0,0.8); border: 1px solid rgba(0,180,220,0.18); color: #c8d8e8; padding: 7px 10px; font-family: 'Rajdhani', sans-serif; font-size: 13px; box-sizing: border-box; }
    .dv-btn   { width: 100%; background: rgba(0,180,220,0.08); border: 1px solid rgba(0,180,220,0.30); color: rgba(0,200,255,0.80); padding: 9px; font-family: 'Orbitron', monospace; font-size: 11px; letter-spacing: 2px; cursor: pointer; text-align: center; }

    .dv-main  { flex: 1; padding: 20px; display: flex; flex-direction: column; gap: 8px; overflow-y: auto; }
    .dv-card  { background: rgba(0,0,0,0.0); border-bottom: 1px solid rgba(0,180,220,0.10); padding: 14px 4px; display: flex; align-items: center; gap: 16px; }
    .dv-card:hover { border-bottom-color: rgba(0,200,255,0.25); }
    .dv-rank  { font-family: 'Orbitron', monospace; font-size: 12px; color: rgba(0,180,220,0.30); width: 22px; text-align: center; }
    .dv-info  { flex: 1; }
    .dv-sys   { font-family: 'Orbitron', monospace; font-size: 12px; color: rgba(200,230,255,0.88); margin-bottom: 4px; letter-spacing: 0.5px; }
    .dv-dist  { font-size: 11px; color: rgba(0,160,200,0.45); }
    .dv-score { font-family: 'Orbitron', monospace; font-size: 18px; font-weight: 700; color: rgba(0,200,255,0.80); }
    .dv-badge { display: inline-block; padding: 1px 6px; border: 1px solid; font-size: 10px; letter-spacing: 1px; margin-right: 4px; }
    .dv-badge-ht   { color: rgba(60,160,255,0.80); border-color: rgba(60,160,255,0.25); }
    .dv-badge-ind  { color: rgba(200,140,40,0.80); border-color: rgba(200,120,0,0.25); }
    .dv-badge-agr  { color: rgba(50,180,90,0.80); border-color: rgba(40,160,80,0.25); }
    .dv-badge-ref  { color: rgba(200,100,50,0.80); border-color: rgba(180,80,30,0.25); }
  `;

  const systems = [
    { name: "Col 285 Sector XP-O b6-3", dist: "41.2 LY", score: 94, eco: "High Tech", badge: "dv-badge-ht" },
    { name: "Eravate", dist: "14.9 LY", score: 87, eco: "Industrial", badge: "dv-badge-ind" },
    { name: "Kamadhenu", dist: "28.6 LY", score: 81, eco: "Agriculture", badge: "dv-badge-agr" },
    { name: "HIP 20277", dist: "55.3 LY", score: 76, eco: "Refinery", badge: "dv-badge-ref" },
  ];

  return (
    <div className="dv-root">
      <style>{css}</style>
      <div className="dv-bg" />
      <div className="dv-horizon" />

      <header className="dv-header">
        <div className="dv-logo">◈</div>
        <div>
          <div className="dv-title">ED:FINDER</div>
          <div className="dv-sub">Colonisation Planner</div>
        </div>
        <button className="dv-sync">⟳ SYNC NOW</button>
        <span className="dv-ver">V3.30</span>
      </header>

      <div className="dv-body">
        <aside className="dv-side">
          <div className="dv-panel">
            <div className="dv-panel-title">REFERENCE SYSTEM</div>
            <label className="dv-label">System Name</label>
            <input className="dv-input" defaultValue="Sol" />
          </div>
          <div className="dv-panel">
            <div className="dv-panel-title">SEARCH RADIUS</div>
            <label className="dv-label">Max Distance</label>
            <input className="dv-input" defaultValue="50 LY" />
            <div style={{marginTop:10}}>
              <label className="dv-label">Min Distance</label>
              <input className="dv-input" defaultValue="0 LY" />
            </div>
          </div>
          <div className="dv-panel">
            <div className="dv-panel-title">ECONOMY FILTER</div>
            <label className="dv-label">Type</label>
            <input className="dv-input" defaultValue="All Types" />
          </div>
          <button className="dv-btn">◈ SEARCH SYSTEMS</button>
        </aside>

        <main className="dv-main">
          <div style={{fontFamily:"'Orbitron',monospace",fontSize:11,color:"rgba(0,180,220,0.35)",letterSpacing:2,marginBottom:8}}>SEARCH RESULTS — 4 SYSTEMS FOUND</div>
          {systems.map((s, i) => (
            <div key={i} className="dv-card">
              <div className="dv-rank">{i + 1}</div>
              <div className="dv-info">
                <div className="dv-sys">{s.name}</div>
                <div style={{marginTop:4}}>
                  <span className={`dv-badge ${s.badge}`}>{s.eco}</span>
                </div>
                <div className="dv-dist" style={{marginTop:4}}>{s.dist} from Sol</div>
              </div>
              <div className="dv-score">{s.score}</div>
            </div>
          ))}
        </main>
      </div>
    </div>
  );
}
