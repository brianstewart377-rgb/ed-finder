export function CrimsonFleet() {
  const css = `
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;600;700&family=Rajdhani:wght@400;500;600&display=swap');

    @keyframes cf-flicker {
      0%, 95%, 100% { opacity: 1; }
      96%            { opacity: 0.85; }
      97%            { opacity: 1; }
      98%            { opacity: 0.90; }
    }

    .cf-root {
      font-family: 'Rajdhani', sans-serif;
      background: #050000;
      color: #e0b0b0;
      min-height: 100vh;
      display: flex; flex-direction: column;
      position: relative; overflow: hidden;
    }
    .cf-bg {
      position: fixed; inset: 0; pointer-events: none; z-index: 0;
      background:
        radial-gradient(ellipse 60% 50% at 15% 20%, rgba(180,0,0,0.22) 0%, transparent 60%),
        radial-gradient(ellipse 50% 60% at 85% 75%, rgba(140,0,0,0.18) 0%, transparent 60%),
        radial-gradient(ellipse 80% 40% at 50% 90%, rgba(100,0,0,0.12) 0%, transparent 55%),
        radial-gradient(ellipse 30% 50% at 70% 15%, rgba(80,0,0,0.15) 0%, transparent 50%),
        linear-gradient(160deg, #050000 0%, #080000 40%, #030000 100%);
    }
    /* Scan lines */
    .cf-scanlines {
      position: fixed; inset: 0; pointer-events: none; z-index: 1;
      background: repeating-linear-gradient(0deg, transparent, transparent 2px, rgba(0,0,0,0.04) 2px, rgba(0,0,0,0.04) 4px);
    }

    .cf-header {
      position: relative; z-index: 10;
      background: rgba(10,0,0,0.97);
      border-bottom: 1px solid rgba(200,0,0,0.35);
      box-shadow: 0 0 30px rgba(180,0,0,0.20), 0 4px 60px rgba(0,0,0,0.9);
      padding: 0 24px; height: 60px;
      display: flex; align-items: center; gap: 16px;
      animation: cf-flicker 8s infinite;
    }
    .cf-logo {
      width: 38px; height: 38px;
      background: rgba(180,0,0,0.8);
      clip-path: polygon(50% 0%, 100% 25%, 100% 75%, 50% 100%, 0% 75%, 0% 25%);
      box-shadow: 0 0 16px rgba(220,0,0,0.5);
      display: flex; align-items: center; justify-content: center;
    }
    .cf-title { font-family: 'Orbitron', monospace; font-size: 18px; font-weight: 700; color: #ff4040; letter-spacing: 3px; text-shadow: 0 0 10px rgba(255,0,0,0.4); }
    .cf-sub   { font-size: 10px; color: rgba(200,80,80,0.55); letter-spacing: 2px; text-transform: uppercase; margin-top: 2px; }
    .cf-sync  { margin-left: auto; background: rgba(180,0,0,0.18); border: 1px solid rgba(200,0,0,0.45); color: #ff6060; padding: 6px 14px; font-family: 'Orbitron', monospace; font-size: 11px; letter-spacing: 1px; cursor: pointer; }
    .cf-ver   { background: rgba(180,0,0,0.10); border: 1px solid rgba(200,0,0,0.28); color: rgba(220,80,80,0.8); padding: 3px 8px; font-size: 11px; font-family: 'Orbitron', monospace; }

    .cf-body  { display: flex; flex: 1; position: relative; z-index: 2; }
    .cf-side  { width: 280px; background: rgba(8,0,0,0.92); border-right: 1px solid rgba(200,0,0,0.14); padding: 16px; display: flex; flex-direction: column; gap: 14px; }
    .cf-panel { background: rgba(18,4,4,0.75); border: 1px solid rgba(200,0,0,0.16); border-left: 2px solid rgba(200,0,0,0.40); padding: 14px; }
    .cf-panel-title { font-family: 'Orbitron', monospace; font-size: 10px; letter-spacing: 2px; color: rgba(220,60,60,0.70); margin-bottom: 10px; }
    .cf-label { font-size: 11px; color: rgba(200,100,100,0.58); letter-spacing: 1px; text-transform: uppercase; margin-bottom: 4px; display: block; }
    .cf-input { width: 100%; background: rgba(5,0,0,0.75); border: 1px solid rgba(200,0,0,0.22); color: #e0b0b0; padding: 7px 10px; font-family: 'Rajdhani', sans-serif; font-size: 13px; box-sizing: border-box; }
    .cf-btn   { width: 100%; background: rgba(180,0,0,0.22); border: 1px solid rgba(200,0,0,0.50); color: #ff6060; padding: 9px; font-family: 'Orbitron', monospace; font-size: 11px; letter-spacing: 2px; cursor: pointer; text-align: center; }

    .cf-main  { flex: 1; padding: 20px; display: flex; flex-direction: column; gap: 10px; overflow-y: auto; }
    .cf-card  { background: rgba(12,2,2,0.88); border: 1px solid rgba(180,0,0,0.18); border-left: 2px solid rgba(200,0,0,0.40); padding: 16px; display: flex; align-items: center; gap: 16px; }
    .cf-card:hover { border-color: rgba(220,0,0,0.45); box-shadow: 0 0 20px rgba(180,0,0,0.10); }
    .cf-rank  { font-family: 'Orbitron', monospace; font-size: 22px; font-weight: 700; color: rgba(200,0,0,0.38); width: 32px; text-align: center; }
    .cf-info  { flex: 1; }
    .cf-sys   { font-family: 'Orbitron', monospace; font-size: 13px; color: #ff6060; margin-bottom: 4px; }
    .cf-dist  { font-size: 12px; color: rgba(200,100,100,0.55); }
    .cf-score { font-family: 'Orbitron', monospace; font-size: 20px; font-weight: 700; color: rgba(255,100,100,0.95); }
    .cf-badge { display: inline-block; padding: 2px 8px; border: 1px solid; font-size: 10px; letter-spacing: 1px; margin-right: 4px; }
    .cf-badge-ht   { color: #60c0ff; border-color: rgba(60,160,255,0.35); background: rgba(10,30,80,0.15); }
    .cf-badge-ind  { color: #f5a030; border-color: rgba(200,120,0,0.35); background: rgba(60,30,0,0.15); }
    .cf-badge-agr  { color: #50d090; border-color: rgba(40,160,80,0.35); background: rgba(10,50,25,0.15); }
    .cf-badge-ref  { color: #e07040; border-color: rgba(180,80,30,0.35); background: rgba(50,15,5,0.15); }
  `;

  const systems = [
    { name: "Col 285 Sector XP-O b6-3", dist: "41.2 LY", score: 94, eco: "High Tech", badge: "cf-badge-ht" },
    { name: "Eravate", dist: "14.9 LY", score: 87, eco: "Industrial", badge: "cf-badge-ind" },
    { name: "Kamadhenu", dist: "28.6 LY", score: 81, eco: "Agriculture", badge: "cf-badge-agr" },
    { name: "HIP 20277", dist: "55.3 LY", score: 76, eco: "Refinery", badge: "cf-badge-ref" },
  ];

  return (
    <div className="cf-root">
      <style>{css}</style>
      <div className="cf-bg" />
      <div className="cf-scanlines" />

      <header className="cf-header">
        <div className="cf-logo" />
        <div>
          <div className="cf-title">ED:FINDER</div>
          <div className="cf-sub">Colonisation Planner</div>
        </div>
        <button className="cf-sync">⟳ SYNC NOW</button>
        <span className="cf-ver">V3.30</span>
      </header>

      <div className="cf-body">
        <aside className="cf-side">
          <div className="cf-panel">
            <div className="cf-panel-title">REFERENCE SYSTEM</div>
            <label className="cf-label">System Name</label>
            <input className="cf-input" defaultValue="Sol" />
          </div>
          <div className="cf-panel">
            <div className="cf-panel-title">SEARCH RADIUS</div>
            <label className="cf-label">Max Distance</label>
            <input className="cf-input" defaultValue="50 LY" />
            <div style={{marginTop:10}}>
              <label className="cf-label">Min Distance</label>
              <input className="cf-input" defaultValue="0 LY" />
            </div>
          </div>
          <div className="cf-panel">
            <div className="cf-panel-title">ECONOMY FILTER</div>
            <label className="cf-label">Type</label>
            <input className="cf-input" defaultValue="All Types" />
          </div>
          <button className="cf-btn">◈ SEARCH SYSTEMS</button>
        </aside>

        <main className="cf-main">
          <div style={{fontFamily:"'Orbitron',monospace",fontSize:11,color:"rgba(200,0,0,0.50)",letterSpacing:2,marginBottom:4}}>SEARCH RESULTS — 4 SYSTEMS FOUND</div>
          {systems.map((s, i) => (
            <div key={i} className="cf-card">
              <div className="cf-rank">{i + 1}</div>
              <div className="cf-info">
                <div className="cf-sys">{s.name}</div>
                <div style={{marginTop:4}}>
                  <span className={`cf-badge ${s.badge}`}>{s.eco}</span>
                </div>
                <div className="cf-dist" style={{marginTop:6}}>{s.dist} from Sol</div>
              </div>
              <div className="cf-score">{s.score}</div>
            </div>
          ))}
        </main>
      </div>
    </div>
  );
}
