export function BlackHole() {
  const css = `
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;600;700&family=Rajdhani:wght@400;500;600&display=swap');

    @keyframes bh-spin {
      from { transform: rotate(0deg); }
      to   { transform: rotate(360deg); }
    }
    @keyframes bh-pulse {
      0%, 100% { opacity: 0.6; transform: scale(1); }
      50%       { opacity: 1.0; transform: scale(1.04); }
    }

    .bh-root {
      font-family: 'Rajdhani', sans-serif;
      background: #000000;
      color: #d4b896;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      position: relative;
      overflow: hidden;
    }

    /* Accretion disk glow layers */
    .bh-bg {
      position: fixed; inset: 0; pointer-events: none; z-index: 0;
      background:
        radial-gradient(ellipse 60% 20% at 50% 52%, rgba(255,180,60,0.18) 0%, transparent 60%),
        radial-gradient(ellipse 80% 10% at 50% 51%, rgba(255,220,120,0.12) 0%, transparent 50%),
        radial-gradient(ellipse 100% 30% at 50% 50%, rgba(200,100,0,0.10) 0%, transparent 65%),
        radial-gradient(ellipse 40% 40% at 50% 50%, rgba(255,255,255,0.04) 0%, transparent 40%),
        radial-gradient(ellipse 30% 30% at 50% 50%, rgba(0,0,0,1) 0%, rgba(0,0,0,0.98) 100%),
        linear-gradient(180deg, #000 0%, #040200 60%, #000 100%);
    }
    .bh-ring {
      position: fixed; pointer-events: none; z-index: 0;
      border-radius: 50%;
      left: 50%; top: 50%;
    }
    .bh-ring-1 {
      width: 700px; height: 140px;
      margin-left: -350px; margin-top: -70px;
      border: 2px solid rgba(255,160,30,0.20);
      box-shadow: 0 0 40px rgba(255,160,30,0.10), inset 0 0 30px rgba(255,160,30,0.05);
      animation: bh-pulse 6s ease-in-out infinite;
    }
    .bh-ring-2 {
      width: 520px; height: 100px;
      margin-left: -260px; margin-top: -50px;
      border: 1px solid rgba(255,200,80,0.15);
      animation: bh-pulse 8s ease-in-out infinite reverse;
    }

    .bh-header {
      position: relative; z-index: 10;
      background: rgba(5,3,0,0.95);
      border-bottom: 1px solid rgba(255,140,0,0.25);
      box-shadow: 0 4px 30px rgba(0,0,0,0.8);
      padding: 0 24px;
      height: 60px;
      display: flex; align-items: center; gap: 16px;
    }
    .bh-logo {
      width: 38px; height: 38px; border-radius: 50%;
      background: radial-gradient(circle, rgba(255,160,30,0.8) 0%, rgba(120,50,0,0.6) 50%, #000 75%);
      border: 1px solid rgba(255,140,0,0.5);
      box-shadow: 0 0 16px rgba(255,140,0,0.4);
    }
    .bh-title { font-family: 'Orbitron', monospace; font-size: 18px; font-weight: 700; color: #e8c070; letter-spacing: 3px; }
    .bh-sub   { font-size: 10px; color: rgba(200,160,80,0.6); letter-spacing: 2px; text-transform: uppercase; margin-top: 2px; }
    .bh-sync  { margin-left: auto; background: rgba(255,140,0,0.12); border: 1px solid rgba(255,140,0,0.35); color: #e8c070; padding: 6px 14px; font-family: 'Orbitron', monospace; font-size: 11px; letter-spacing: 1px; cursor: pointer; }
    .bh-ver   { background: rgba(255,140,0,0.08); border: 1px solid rgba(255,140,0,0.25); color: rgba(200,140,50,0.8); padding: 3px 8px; font-size: 11px; font-family: 'Orbitron', monospace; }

    .bh-body  { display: flex; flex: 1; position: relative; z-index: 2; }
    .bh-side  { width: 280px; background: rgba(8,5,0,0.90); border-right: 1px solid rgba(255,140,0,0.12); padding: 16px; display: flex; flex-direction: column; gap: 14px; }
    .bh-panel { background: rgba(20,12,0,0.70); border: 1px solid rgba(255,140,0,0.15); padding: 14px; }
    .bh-panel-title { font-family: 'Orbitron', monospace; font-size: 10px; letter-spacing: 2px; color: rgba(255,160,40,0.7); margin-bottom: 10px; }
    .bh-label { font-size: 11px; color: rgba(200,160,80,0.6); letter-spacing: 1px; text-transform: uppercase; margin-bottom: 4px; display: block; }
    .bh-input { width: 100%; background: rgba(0,0,0,0.6); border: 1px solid rgba(255,140,0,0.20); color: #d4b896; padding: 7px 10px; font-family: 'Rajdhani', sans-serif; font-size: 13px; box-sizing: border-box; }
    .bh-btn   { width: 100%; background: rgba(255,140,0,0.15); border: 1px solid rgba(255,140,0,0.40); color: #e8c070; padding: 9px; font-family: 'Orbitron', monospace; font-size: 11px; letter-spacing: 2px; cursor: pointer; text-align: center; }
    .bh-btn:hover { background: rgba(255,140,0,0.25); }

    .bh-main  { flex: 1; padding: 20px; display: flex; flex-direction: column; gap: 12px; overflow-y: auto; }
    .bh-card  { background: rgba(15,8,0,0.85); border: 1px solid rgba(255,140,0,0.15); padding: 16px; display: flex; align-items: center; gap: 16px; transition: border-color 0.2s; }
    .bh-card:hover { border-color: rgba(255,160,40,0.40); }
    .bh-rank  { font-family: 'Orbitron', monospace; font-size: 22px; font-weight: 700; color: rgba(255,160,40,0.4); width: 32px; text-align: center; }
    .bh-info  { flex: 1; }
    .bh-sys   { font-family: 'Orbitron', monospace; font-size: 13px; font-weight: 600; color: #e8c070; margin-bottom: 4px; }
    .bh-dist  { font-size: 12px; color: rgba(200,160,80,0.6); }
    .bh-score { font-family: 'Orbitron', monospace; font-size: 20px; font-weight: 700; color: rgba(255,200,80,0.9); }
    .bh-badge { display: inline-block; padding: 2px 8px; border: 1px solid; font-size: 10px; letter-spacing: 1px; margin-right: 4px; }
    .bh-badge-ht   { color: #60c0ff; border-color: rgba(60,160,255,0.4); background: rgba(30,80,160,0.15); }
    .bh-badge-ind  { color: #f5a030; border-color: rgba(200,120,0,0.4); background: rgba(120,60,0,0.15); }
    .bh-badge-agr  { color: #50d090; border-color: rgba(40,160,80,0.4); background: rgba(20,80,40,0.15); }
    .bh-badge-ref  { color: #e07040; border-color: rgba(180,80,30,0.4); background: rgba(90,40,15,0.15); }
  `;

  const systems = [
    { name: "Col 285 Sector XP-O b6-3", dist: "41.2 LY", score: 94, eco: "High Tech", badge: "bh-badge-ht" },
    { name: "Eravate", dist: "14.9 LY", score: 87, eco: "Industrial", badge: "bh-badge-ind" },
    { name: "Kamadhenu", dist: "28.6 LY", score: 81, eco: "Agriculture", badge: "bh-badge-agr" },
    { name: "HIP 20277", dist: "55.3 LY", score: 76, eco: "Refinery", badge: "bh-badge-ref" },
  ];

  return (
    <div className="bh-root">
      <style>{css}</style>
      <div className="bh-bg" />
      <div className="bh-ring bh-ring-1" />
      <div className="bh-ring bh-ring-2" />

      <header className="bh-header">
        <div className="bh-logo" />
        <div>
          <div className="bh-title">ED:FINDER</div>
          <div className="bh-sub">Colonisation Planner</div>
        </div>
        <button className="bh-sync">⟳ SYNC NOW</button>
        <span className="bh-ver">V3.30</span>
      </header>

      <div className="bh-body">
        <aside className="bh-side">
          <div className="bh-panel">
            <div className="bh-panel-title">REFERENCE SYSTEM</div>
            <label className="bh-label">System Name</label>
            <input className="bh-input" defaultValue="Sol" />
          </div>
          <div className="bh-panel">
            <div className="bh-panel-title">SEARCH RADIUS</div>
            <label className="bh-label">Max Distance</label>
            <input className="bh-input" defaultValue="50 LY" />
            <div style={{marginTop:10}}>
              <label className="bh-label">Min Distance</label>
              <input className="bh-input" defaultValue="0 LY" />
            </div>
          </div>
          <div className="bh-panel">
            <div className="bh-panel-title">ECONOMY FILTER</div>
            <label className="bh-label">Type</label>
            <input className="bh-input" defaultValue="All Types" />
          </div>
          <button className="bh-btn">◈ SEARCH SYSTEMS</button>
        </aside>

        <main className="bh-main">
          <div style={{fontFamily:"'Orbitron',monospace",fontSize:11,color:"rgba(255,160,40,0.5)",letterSpacing:2,marginBottom:4}}>SEARCH RESULTS — 4 SYSTEMS FOUND</div>
          {systems.map((s, i) => (
            <div key={i} className="bh-card">
              <div className="bh-rank">{i + 1}</div>
              <div className="bh-info">
                <div className="bh-sys">{s.name}</div>
                <div style={{marginTop:4}}>
                  <span className={`bh-badge ${s.badge}`}>{s.eco}</span>
                </div>
                <div className="bh-dist" style={{marginTop:6}}>{s.dist} from Sol</div>
              </div>
              <div className="bh-score">{s.score}</div>
            </div>
          ))}
        </main>
      </div>
    </div>
  );
}
