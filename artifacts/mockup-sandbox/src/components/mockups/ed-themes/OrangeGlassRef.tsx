export function OrangeGlassRef() {
  const css = `
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;600;700&family=Rajdhani:wght@400;500;600&display=swap');

    @keyframes ogr-drift-a {
      0%   { transform: translate3d(0,    0,   0); }
      50%  { transform: translate3d(16%, 12%,  0); }
      100% { transform: translate3d(0,    0,   0); }
    }
    @keyframes ogr-drift-b {
      0%   { transform: translate3d(0,    0,   0); }
      50%  { transform: translate3d(-18%,-13%, 0); }
      100% { transform: translate3d(0,    0,   0); }
    }
    @keyframes ogr-drift-c {
      0%   { transform: translate3d(0,    0,   0); }
      50%  { transform: translate3d(14%, -16%, 0); }
      100% { transform: translate3d(0,    0,   0); }
    }

    .ogr-root {
      font-family: 'Rajdhani', sans-serif;
      background: #04050a;
      color: #d0d8e8;
      min-height: 100vh;
      display: flex; flex-direction: column;
      position: relative; overflow: hidden;
    }
    .ogr-wrapper { position: fixed; inset: 0; z-index: 0; pointer-events: none; overflow: hidden; }
    .ogr-drift-a {
      position: absolute; inset: -25%; width: 150%; height: 150%;
      background:
        radial-gradient(ellipse 70% 55% at 20% 30%, rgba(220,80,0,0.40)  0%, transparent 65%),
        radial-gradient(ellipse 90% 45% at 10% 80%, rgba(180,40,0,0.32)  0%, transparent 55%),
        radial-gradient(ellipse 40% 80% at 35% 55%, rgba(255,130,0,0.26) 0%, transparent 55%);
      animation: ogr-drift-a 28s linear infinite;
    }
    .ogr-drift-b {
      position: absolute; inset: -30%; width: 160%; height: 160%;
      background:
        radial-gradient(ellipse 80% 60% at 75% 20%, rgba(150,40,210,0.50) 0%, transparent 60%),
        radial-gradient(ellipse 55% 65% at 85% 65%, rgba(110,15,190,0.42) 0%, transparent 55%),
        radial-gradient(ellipse 65% 50% at 30% 75%, rgba(125,25,200,0.36) 0%, transparent 60%),
        radial-gradient(ellipse 60% 40% at 65% 30%, rgba(255,160,0,0.20)  0%, transparent 50%);
      animation: ogr-drift-b 36s linear infinite;
    }
    .ogr-drift-c {
      position: absolute; inset: -20%; width: 140%; height: 140%;
      background:
        radial-gradient(ellipse 60% 70% at 55% 75%, rgba(20,80,200,0.36)  0%, transparent 60%),
        radial-gradient(ellipse 45% 30% at 60% 15%, rgba(0,160,240,0.26)  0%, transparent 50%),
        radial-gradient(ellipse 35% 55% at 90% 50%, rgba(0,220,190,0.22)  0%, transparent 45%),
        radial-gradient(ellipse 50% 30% at 25% 90%, rgba(130,15,235,0.38) 0%, transparent 50%);
      animation: ogr-drift-c 44s linear infinite;
    }

    .ogr-header {
      position: relative; z-index: 10;
      background: #06070e;
      border-bottom: 1px solid rgba(255,106,0,0.30);
      box-shadow: 0 4px 40px rgba(0,0,0,0.50);
      padding: 0 24px; height: 60px;
      display: flex; align-items: center; gap: 16px;
    }
    .ogr-logo {
      width: 38px; height: 38px; border-radius: 50%;
      background: radial-gradient(circle, rgba(255,120,0,0.7) 0%, rgba(100,20,0,0.5) 60%, transparent 100%);
      border: 1px solid rgba(255,106,0,0.50);
      box-shadow: 0 0 14px rgba(255,100,0,0.35);
    }
    .ogr-title { font-family: 'Orbitron', monospace; font-size: 18px; font-weight: 700; color: #ffe8d0; letter-spacing: 3px; text-shadow: 0 0 12px rgba(255,140,40,0.55); }
    .ogr-sub   { font-size: 10px; color: rgba(200,160,100,0.55); letter-spacing: 2px; text-transform: uppercase; margin-top: 2px; }
    .ogr-sync  { margin-left: auto; background: rgba(255,106,0,0.12); border: 1px solid rgba(255,106,0,0.38); color: #ffe8d0; padding: 6px 14px; font-family: 'Orbitron', monospace; font-size: 11px; letter-spacing: 1px; cursor: pointer; }
    .ogr-ver   { background: rgba(255,106,0,0.08); border: 1px solid rgba(255,106,0,0.28); color: rgba(255,160,80,0.80); padding: 3px 8px; font-size: 11px; font-family: 'Orbitron', monospace; }

    .ogr-body  { display: flex; flex: 1; position: relative; z-index: 2; }
    .ogr-side  {
      width: 280px;
      background: rgba(4,5,12,0.88);
      border-right: 1px solid rgba(255,106,0,0.12);
      padding: 16px; display: flex; flex-direction: column; gap: 14px;
    }
    .ogr-panel { background: rgba(10,8,18,0.70); border: 1px solid rgba(255,106,0,0.14); padding: 14px; }
    .ogr-panel-title { font-family: 'Orbitron', monospace; font-size: 10px; letter-spacing: 2px; color: rgba(255,140,40,0.62); margin-bottom: 10px; }
    .ogr-label { font-size: 11px; color: rgba(210,170,120,0.60); letter-spacing: 1px; text-transform: uppercase; margin-bottom: 4px; display: block; }
    .ogr-input { width: 100%; background: rgba(4,5,12,0.80); border: 1px solid rgba(255,106,0,0.18); color: #d0d8e8; padding: 7px 10px; font-family: 'Rajdhani', sans-serif; font-size: 13px; box-sizing: border-box; }
    .ogr-btn   { width: 100%; background: rgba(255,106,0,0.14); border: 1px solid rgba(255,106,0,0.42); color: #ffe8d0; padding: 9px; font-family: 'Orbitron', monospace; font-size: 11px; letter-spacing: 2px; cursor: pointer; text-align: center; }

    .ogr-main  { flex: 1; padding: 20px; display: flex; flex-direction: column; gap: 10px; overflow-y: auto; }
    .ogr-card  { background: rgba(8,6,16,0.82); border: 1px solid rgba(255,106,0,0.14); padding: 16px; display: flex; align-items: center; gap: 16px; }
    .ogr-card:hover { border-color: rgba(255,140,40,0.35); }
    .ogr-rank  { font-family: 'Orbitron', monospace; font-size: 22px; font-weight: 700; color: rgba(255,120,0,0.35); width: 32px; text-align: center; }
    .ogr-info  { flex: 1; }
    .ogr-sys   { font-family: 'Orbitron', monospace; font-size: 13px; color: #ffe8d0; margin-bottom: 4px; }
    .ogr-dist  { font-size: 12px; color: rgba(200,160,100,0.58); }
    .ogr-score { font-family: 'Orbitron', monospace; font-size: 20px; font-weight: 700; color: rgba(255,180,80,0.95); }
    .ogr-badge { display: inline-block; padding: 2px 8px; border: 1px solid; font-size: 10px; letter-spacing: 1px; margin-right: 4px; }
    .ogr-badge-ht   { color: #60c0ff; border-color: rgba(60,160,255,0.38); background: rgba(20,60,140,0.12); }
    .ogr-badge-ind  { color: #f5a030; border-color: rgba(200,120,0,0.38); background: rgba(80,40,0,0.12); }
    .ogr-badge-agr  { color: #50d090; border-color: rgba(40,160,80,0.38); background: rgba(15,60,30,0.12); }
    .ogr-badge-ref  { color: #e07040; border-color: rgba(180,80,30,0.38); background: rgba(60,20,5,0.12); }
  `;

  const systems = [
    { name: "Col 285 Sector XP-O b6-3", dist: "41.2 LY", score: 94, eco: "High Tech", badge: "ogr-badge-ht" },
    { name: "Eravate", dist: "14.9 LY", score: 87, eco: "Industrial", badge: "ogr-badge-ind" },
    { name: "Kamadhenu", dist: "28.6 LY", score: 81, eco: "Agriculture", badge: "ogr-badge-agr" },
    { name: "HIP 20277", dist: "55.3 LY", score: 76, eco: "Refinery", badge: "ogr-badge-ref" },
  ];

  return (
    <div className="ogr-root">
      <style>{css}</style>
      <div className="ogr-wrapper">
        <div className="ogr-drift-a" />
        <div className="ogr-drift-b" />
        <div className="ogr-drift-c" />
      </div>

      <header className="ogr-header">
        <div className="ogr-logo" />
        <div>
          <div className="ogr-title">ED:FINDER</div>
          <div className="ogr-sub">Colonisation Planner</div>
        </div>
        <button className="ogr-sync">⟳ SYNC NOW</button>
        <span className="ogr-ver">V3.30</span>
      </header>

      <div className="ogr-body">
        <aside className="ogr-side">
          <div className="ogr-panel">
            <div className="ogr-panel-title">REFERENCE SYSTEM</div>
            <label className="ogr-label">System Name</label>
            <input className="ogr-input" defaultValue="Sol" />
          </div>
          <div className="ogr-panel">
            <div className="ogr-panel-title">SEARCH RADIUS</div>
            <label className="ogr-label">Max Distance</label>
            <input className="ogr-input" defaultValue="50 LY" />
            <div style={{marginTop:10}}>
              <label className="ogr-label">Min Distance</label>
              <input className="ogr-input" defaultValue="0 LY" />
            </div>
          </div>
          <div className="ogr-panel">
            <div className="ogr-panel-title">ECONOMY FILTER</div>
            <label className="ogr-label">Type</label>
            <input className="ogr-input" defaultValue="All Types" />
          </div>
          <button className="ogr-btn">◈ SEARCH SYSTEMS</button>
        </aside>

        <main className="ogr-main">
          <div style={{fontFamily:"'Orbitron',monospace",fontSize:11,color:"rgba(255,120,0,0.45)",letterSpacing:2,marginBottom:4}}>SEARCH RESULTS — 4 SYSTEMS FOUND</div>
          {systems.map((s, i) => (
            <div key={i} className="ogr-card">
              <div className="ogr-rank">{i + 1}</div>
              <div className="ogr-info">
                <div className="ogr-sys">{s.name}</div>
                <div style={{marginTop:4}}>
                  <span className={`ogr-badge ${s.badge}`}>{s.eco}</span>
                </div>
                <div className="ogr-dist" style={{marginTop:6}}>{s.dist} from Sol</div>
              </div>
              <div className="ogr-score">{s.score}</div>
            </div>
          ))}
        </main>
      </div>
    </div>
  );
}
