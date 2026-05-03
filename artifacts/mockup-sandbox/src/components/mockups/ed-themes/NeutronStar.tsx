export function NeutronStar() {
  const css = `
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;600;700&family=Rajdhani:wght@400;500;600&display=swap');

    @keyframes ns-pulse {
      0%, 100% { opacity: 0.5; transform: scale(1); }
      50%       { opacity: 1.0; transform: scale(1.08); }
    }
    @keyframes ns-sweep {
      0%   { transform: rotate(0deg); }
      100% { transform: rotate(360deg); }
    }

    .ns-root {
      font-family: 'Rajdhani', sans-serif;
      background: #020408;
      color: #c0e4ff;
      min-height: 100vh;
      display: flex; flex-direction: column;
      position: relative; overflow: hidden;
    }
    .ns-bg {
      position: fixed; inset: 0; pointer-events: none; z-index: 0;
      background:
        radial-gradient(ellipse 25% 25% at 72% 50%, rgba(80,160,255,0.20) 0%, transparent 60%),
        radial-gradient(ellipse 50% 50% at 72% 50%, rgba(40,100,220,0.12) 0%, transparent 65%),
        radial-gradient(ellipse 80% 80% at 72% 50%, rgba(20,60,180,0.08) 0%, transparent 70%),
        radial-gradient(ellipse 15% 15% at 72% 50%, rgba(200,240,255,0.30) 0%, rgba(80,160,255,0.10) 50%, transparent 80%),
        linear-gradient(135deg, #020408 0%, #030610 50%, #020306 100%);
    }
    /* Jet beam */
    .ns-jet {
      position: fixed; pointer-events: none; z-index: 0;
      left: 50%; top: 0; bottom: 0;
      width: 3px; margin-left: -1.5px;
      background: linear-gradient(180deg, rgba(120,200,255,0.0) 0%, rgba(120,200,255,0.15) 30%, rgba(200,240,255,0.50) 50%, rgba(120,200,255,0.15) 70%, rgba(120,200,255,0.0) 100%);
      filter: blur(2px);
    }

    .ns-header {
      position: relative; z-index: 10;
      background: rgba(2,4,12,0.96);
      border-bottom: 1px solid rgba(80,160,255,0.30);
      box-shadow: 0 0 30px rgba(60,120,255,0.15);
      padding: 0 24px; height: 60px;
      display: flex; align-items: center; gap: 16px;
    }
    .ns-logo {
      width: 38px; height: 38px; border-radius: 50%;
      background: radial-gradient(circle, rgba(200,240,255,1) 0%, rgba(80,160,255,0.8) 30%, rgba(20,60,200,0.4) 70%, transparent 100%);
      box-shadow: 0 0 20px rgba(120,200,255,0.7), 0 0 40px rgba(80,160,255,0.3);
      animation: ns-pulse 3s ease-in-out infinite;
    }
    .ns-title { font-family: 'Orbitron', monospace; font-size: 18px; font-weight: 700; color: #a0d4ff; letter-spacing: 3px; }
    .ns-sub   { font-size: 10px; color: rgba(100,180,255,0.55); letter-spacing: 2px; text-transform: uppercase; margin-top: 2px; }
    .ns-sync  { margin-left: auto; background: rgba(80,160,255,0.12); border: 1px solid rgba(80,160,255,0.40); color: #a0d4ff; padding: 6px 14px; font-family: 'Orbitron', monospace; font-size: 11px; letter-spacing: 1px; cursor: pointer; }
    .ns-ver   { background: rgba(80,160,255,0.08); border: 1px solid rgba(80,160,255,0.28); color: rgba(120,180,255,0.8); padding: 3px 8px; font-size: 11px; font-family: 'Orbitron', monospace; }

    .ns-body  { display: flex; flex: 1; position: relative; z-index: 2; }
    .ns-side  { width: 280px; background: rgba(2,6,16,0.92); border-right: 1px solid rgba(80,160,255,0.12); padding: 16px; display: flex; flex-direction: column; gap: 14px; }
    .ns-panel { background: rgba(5,12,30,0.70); border: 1px solid rgba(80,160,255,0.18); padding: 14px; }
    .ns-panel-title { font-family: 'Orbitron', monospace; font-size: 10px; letter-spacing: 2px; color: rgba(100,180,255,0.65); margin-bottom: 10px; }
    .ns-label { font-size: 11px; color: rgba(120,180,255,0.55); letter-spacing: 1px; text-transform: uppercase; margin-bottom: 4px; display: block; }
    .ns-input { width: 100%; background: rgba(2,6,20,0.7); border: 1px solid rgba(80,160,255,0.22); color: #c0e4ff; padding: 7px 10px; font-family: 'Rajdhani', sans-serif; font-size: 13px; box-sizing: border-box; }
    .ns-btn   { width: 100%; background: rgba(60,120,255,0.15); border: 1px solid rgba(80,160,255,0.45); color: #a0d4ff; padding: 9px; font-family: 'Orbitron', monospace; font-size: 11px; letter-spacing: 2px; cursor: pointer; text-align: center; }

    .ns-main  { flex: 1; padding: 20px; display: flex; flex-direction: column; gap: 10px; overflow-y: auto; }
    .ns-card  { background: rgba(4,10,24,0.88); border: 1px solid rgba(60,120,255,0.18); padding: 16px; display: flex; align-items: center; gap: 16px; }
    .ns-card:hover { border-color: rgba(80,160,255,0.45); box-shadow: 0 0 20px rgba(60,120,255,0.08); }
    .ns-rank  { font-family: 'Orbitron', monospace; font-size: 22px; font-weight: 700; color: rgba(80,160,255,0.35); width: 32px; text-align: center; }
    .ns-info  { flex: 1; }
    .ns-sys   { font-family: 'Orbitron', monospace; font-size: 13px; color: #a0d4ff; margin-bottom: 4px; }
    .ns-dist  { font-size: 12px; color: rgba(100,160,255,0.55); }
    .ns-score { font-family: 'Orbitron', monospace; font-size: 20px; font-weight: 700; color: rgba(140,200,255,0.95); }
    .ns-badge { display: inline-block; padding: 2px 8px; border: 1px solid; font-size: 10px; letter-spacing: 1px; margin-right: 4px; }
    .ns-badge-ht   { color: #60c0ff; border-color: rgba(60,160,255,0.4); background: rgba(20,60,160,0.15); }
    .ns-badge-ind  { color: #f5a030; border-color: rgba(200,120,0,0.4); background: rgba(80,40,0,0.15); }
    .ns-badge-agr  { color: #50d090; border-color: rgba(40,160,80,0.4); background: rgba(10,60,30,0.15); }
    .ns-badge-ref  { color: #e07040; border-color: rgba(180,80,30,0.4); background: rgba(60,20,5,0.15); }
  `;

  const systems = [
    { name: "Col 285 Sector XP-O b6-3", dist: "41.2 LY", score: 94, eco: "High Tech", badge: "ns-badge-ht" },
    { name: "Eravate", dist: "14.9 LY", score: 87, eco: "Industrial", badge: "ns-badge-ind" },
    { name: "Kamadhenu", dist: "28.6 LY", score: 81, eco: "Agriculture", badge: "ns-badge-agr" },
    { name: "HIP 20277", dist: "55.3 LY", score: 76, eco: "Refinery", badge: "ns-badge-ref" },
  ];

  return (
    <div className="ns-root">
      <style>{css}</style>
      <div className="ns-bg" />
      <div className="ns-jet" />

      <header className="ns-header">
        <div className="ns-logo" />
        <div>
          <div className="ns-title">ED:FINDER</div>
          <div className="ns-sub">Colonisation Planner</div>
        </div>
        <button className="ns-sync">⟳ SYNC NOW</button>
        <span className="ns-ver">V3.30</span>
      </header>

      <div className="ns-body">
        <aside className="ns-side">
          <div className="ns-panel">
            <div className="ns-panel-title">REFERENCE SYSTEM</div>
            <label className="ns-label">System Name</label>
            <input className="ns-input" defaultValue="Sol" />
          </div>
          <div className="ns-panel">
            <div className="ns-panel-title">SEARCH RADIUS</div>
            <label className="ns-label">Max Distance</label>
            <input className="ns-input" defaultValue="50 LY" />
            <div style={{marginTop:10}}>
              <label className="ns-label">Min Distance</label>
              <input className="ns-input" defaultValue="0 LY" />
            </div>
          </div>
          <div className="ns-panel">
            <div className="ns-panel-title">ECONOMY FILTER</div>
            <label className="ns-label">Type</label>
            <input className="ns-input" defaultValue="All Types" />
          </div>
          <button className="ns-btn">◈ SEARCH SYSTEMS</button>
        </aside>

        <main className="ns-main">
          <div style={{fontFamily:"'Orbitron',monospace",fontSize:11,color:"rgba(80,160,255,0.45)",letterSpacing:2,marginBottom:4}}>SEARCH RESULTS — 4 SYSTEMS FOUND</div>
          {systems.map((s, i) => (
            <div key={i} className="ns-card">
              <div className="ns-rank">{i + 1}</div>
              <div className="ns-info">
                <div className="ns-sys">{s.name}</div>
                <div style={{marginTop:4}}>
                  <span className={`ns-badge ${s.badge}`}>{s.eco}</span>
                </div>
                <div className="ns-dist" style={{marginTop:6}}>{s.dist} from Sol</div>
              </div>
              <div className="ns-score">{s.score}</div>
            </div>
          ))}
        </main>
      </div>
    </div>
  );
}
