export function ArcticVoid() {
  const css = `
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;600;700&family=Rajdhani:wght@400;500;600&display=swap');

    .av-root {
      font-family: 'Rajdhani', sans-serif;
      background:
        radial-gradient(ellipse at 20% 10%, rgba(80,160,255,0.10) 0%, transparent 50%),
        radial-gradient(ellipse at 85% 80%, rgba(40,120,200,0.08) 0%, transparent 40%),
        linear-gradient(170deg, #05080f 0%, #060a14 50%, #040710 100%);
      color: #c8daf0;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }

    .av-header {
      background: rgba(255,255,255,0.03);
      backdrop-filter: blur(28px); -webkit-backdrop-filter: blur(28px);
      border-bottom: 1px solid rgba(255,255,255,0.08);
      padding: 14px 24px; display: flex; align-items: center; gap: 16px;
      position: relative; z-index: 10;
      box-shadow: 0 1px 0 rgba(255,255,255,0.05) inset;
    }
    .av-logo {
      width:42px; height:42px;
      border:1px solid rgba(160,210,255,0.45); border-radius:8px;
      display:flex; align-items:center; justify-content:center;
      font-size:18px; color:rgba(160,210,255,0.9);
      box-shadow:0 0 16px rgba(100,180,255,0.20);
    }
    .av-title { font-family:'Orbitron',monospace; font-size:20px; font-weight:700; color:#e8f2ff; letter-spacing:3px; }
    .av-sub { font-size:10px; color:rgba(150,185,230,0.38); letter-spacing:4px; text-transform:uppercase; }
    .av-spacer { flex:1; }
    .av-badge {
      font-family:'Orbitron',monospace; font-size:10px;
      color:rgba(150,200,255,0.65); border:1px solid rgba(150,200,255,0.18);
      border-radius:4px; padding:4px 10px; background:rgba(100,160,255,0.06);
    }
    .av-syncbtn {
      background:rgba(100,160,255,0.10); color:rgba(180,220,255,0.9);
      border:1px solid rgba(140,190,255,0.25); border-radius:6px;
      padding:8px 18px; font-family:'Orbitron',monospace; font-size:10px;
      font-weight:600; letter-spacing:1px; cursor:pointer; backdrop-filter:blur(8px);
    }

    .av-tabs {
      background:rgba(255,255,255,0.02); backdrop-filter:blur(16px); -webkit-backdrop-filter:blur(16px);
      border-bottom:1px solid rgba(255,255,255,0.06); padding:0 20px;
      display:flex; gap:0; overflow-x:auto; position:relative; z-index:10;
    }
    .av-tab {
      font-family:'Orbitron',monospace; font-size:10px; letter-spacing:1px; text-transform:uppercase;
      padding:13px 16px; background:none; border:none; border-bottom:1px solid transparent;
      color:rgba(150,185,230,0.28); cursor:pointer; white-space:nowrap; transition:all 0.2s;
    }
    .av-tab.active {
      color:rgba(200,230,255,0.9); border-bottom-color:rgba(160,210,255,0.5);
      background:linear-gradient(180deg,rgba(100,160,255,0.04) 0%,transparent 100%);
    }
    .av-tab:hover:not(.active) { color:rgba(190,220,255,0.55); }

    .av-body { display:flex; flex:1; min-height:0; position:relative; z-index:1; }

    .av-sidebar {
      width:300px; background:rgba(255,255,255,0.02);
      backdrop-filter:blur(20px); -webkit-backdrop-filter:blur(20px);
      border-right:1px solid rgba(255,255,255,0.05);
      padding:18px 14px; overflow-y:auto; display:flex; flex-direction:column; gap:14px;
    }
    .av-panel {
      background:rgba(255,255,255,0.03); backdrop-filter:blur(14px); -webkit-backdrop-filter:blur(14px);
      border:1px solid rgba(255,255,255,0.07); border-radius:12px; overflow:hidden;
    }
    .av-panel-hdr {
      background:rgba(255,255,255,0.03); border-bottom:1px solid rgba(255,255,255,0.05);
      padding:10px 14px; display:flex; align-items:center; gap:8px;
    }
    .av-panel-icon { color:rgba(150,200,255,0.7); font-size:14px; }
    .av-panel-title { font-family:'Orbitron',monospace; font-size:10px; font-weight:600; letter-spacing:1.5px; text-transform:uppercase; color:rgba(200,225,255,0.75); flex:1; }
    .av-panel-body { padding:14px; }
    .av-label { font-size:11px; font-weight:600; color:rgba(150,185,230,0.40); letter-spacing:1px; text-transform:uppercase; margin-bottom:6px; display:block; }
    .av-input {
      width:100%; background:rgba(255,255,255,0.04); border:1px solid rgba(255,255,255,0.08);
      border-radius:8px; color:#c8daf0; font-family:'Rajdhani',sans-serif; font-size:14px;
      padding:9px 12px; outline:none;
    }
    .av-input:focus { border-color:rgba(150,200,255,0.30); }
    .av-slider-row { display:flex; align-items:center; gap:10px; margin-top:6px; }
    .av-slider { flex:1; accent-color:rgba(140,190,255,0.8); }
    .av-slider-val { font-family:'Orbitron',monospace; font-size:12px; color:rgba(160,210,255,0.75); min-width:32px; text-align:right; }
    .av-searchbtn {
      width:100%; background:rgba(100,160,255,0.12); color:rgba(190,225,255,0.9);
      border:1px solid rgba(140,190,255,0.22); border-radius:8px; padding:12px;
      font-family:'Orbitron',monospace; font-size:11px; font-weight:700; letter-spacing:1.5px;
      cursor:pointer; margin-top:4px; transition:all 0.15s;
    }
    .av-searchbtn:hover { background:rgba(120,180,255,0.18); }

    .av-content { flex:1; padding:20px; overflow-y:auto; display:flex; flex-direction:column; gap:10px; }
    .av-summary {
      display:flex; align-items:center; gap:12px; padding:10px 16px;
      background:rgba(255,255,255,0.025); border:1px solid rgba(255,255,255,0.06);
      border-radius:10px; font-size:13px; color:rgba(160,195,240,0.55);
    }
    .av-summary strong { color:rgba(190,225,255,0.85); font-family:'Orbitron',monospace; font-size:12px; }

    .av-card {
      background:rgba(255,255,255,0.028); backdrop-filter:blur(16px); -webkit-backdrop-filter:blur(16px);
      border:1px solid rgba(255,255,255,0.07); border-radius:14px; overflow:hidden; transition:all 0.22s;
    }
    .av-card:hover {
      transform:translateY(-3px); background:rgba(255,255,255,0.042);
      border-color:rgba(160,210,255,0.22);
      box-shadow:0 12px 36px rgba(80,140,255,0.10), 0 2px 8px rgba(0,0,0,0.5);
    }
    .av-card-hdr { padding:13px 16px; display:flex; align-items:center; gap:10px; border-bottom:1px solid rgba(255,255,255,0.05); }
    .av-rating-wrap { display:flex; flex-direction:column; align-items:center; flex-shrink:0; }
    .av-rating { color:#fff; font-family:'Orbitron',monospace; font-size:14px; font-weight:700; border-radius:8px; padding:5px 11px; min-width:46px; text-align:center; }
    .av-eco-lbl { font-size:8px; color:rgba(255,255,255,0.45); font-family:'Orbitron',monospace; text-transform:uppercase; margin-top:2px; }
    .av-sys-name { font-family:'Orbitron',monospace; font-size:13px; color:rgba(215,232,255,0.95); font-weight:600; flex:1; }
    .av-dist { font-size:12px; color:rgba(155,188,230,0.45); }
    .av-card-body { padding:12px 16px; }
    .av-tags { display:flex; flex-wrap:wrap; gap:6px; margin-bottom:10px; }
    .av-tag { font-size:11px; padding:3px 10px; border-radius:20px; background:rgba(255,255,255,0.05); border:1px solid rgba(255,255,255,0.10); color:rgba(190,220,255,0.60); }
    .av-stat-row { display:flex; gap:20px; margin-top:8px; }
    .av-stat { display:flex; flex-direction:column; gap:2px; }
    .av-stat-lbl { font-size:10px; color:rgba(150,185,230,0.38); text-transform:uppercase; letter-spacing:1px; }
    .av-stat-val { font-size:13px; color:rgba(210,228,255,0.85); font-weight:600; }
    .av-card-footer { padding:10px 16px; border-top:1px solid rgba(255,255,255,0.05); display:flex; gap:8px; justify-content:flex-end; }
    .av-btn { font-size:11px; padding:6px 14px; border-radius:20px; border:1px solid rgba(255,255,255,0.08); background:rgba(255,255,255,0.04); color:rgba(180,215,255,0.55); cursor:pointer; font-family:'Rajdhani',sans-serif; font-weight:600; transition:all 0.15s; }
    .av-btn:hover { background:rgba(255,255,255,0.08); color:rgba(210,235,255,0.85); }
    .av-btn.primary { background:rgba(100,160,255,0.10); border-color:rgba(140,195,255,0.25); color:rgba(180,220,255,0.85); }
  `;

  const ECO: Record<string,{bg:string;glow:string}> = {
    'High Tech':   { bg:'linear-gradient(135deg,#0d7abf,#22d3ee)', glow:'rgba(0,180,240,0.45)' },
    'Industrial':  { bg:'linear-gradient(135deg,#8a5010,#c8820a)', glow:'rgba(180,120,0,0.45)'  },
    'Agriculture': { bg:'linear-gradient(135deg,#1a7038,#2aac60)', glow:'rgba(30,180,80,0.42)'  },
    'Military':    { bg:'linear-gradient(135deg,#7a1010,#c83030)', glow:'rgba(200,30,30,0.42)'  },
  };

  const systems = [
    { name:'Colonia Gateway', rating:94, economy:'High Tech',   dist:'22,000 ly', tags:['High Tech','Industrial'],  pop:'2.1B', slots:7, bodies:23, star:'F-class', sec:'High'   },
    { name:'Eravate',         rating:88, economy:'Industrial',  dist:'34.2 ly',   tags:['Industrial','Refinery'],   pop:'450M', slots:5, bodies:14, star:'G-class', sec:'Medium' },
    { name:'Lave',            rating:81, economy:'Agriculture', dist:'108.5 ly',  tags:['Agriculture','Tourism'],   pop:'1.2B', slots:6, bodies:18, star:'K-class', sec:'High'   },
    { name:'Alioth',          rating:76, economy:'Military',    dist:'82.6 ly',   tags:['Military','Service'],      pop:'8.4B', slots:4, bodies:11, star:'A-class', sec:'High'   },
  ];

  return (
    <div className="av-root">
      <style dangerouslySetInnerHTML={{ __html: css }} />
      <div className="av-header">
        <div className="av-logo">🎯</div>
        <div><div className="av-title">ED:FINDER</div><div className="av-sub">Advanced System Finder &amp; Optimizer</div></div>
        <div className="av-spacer" />
        <span style={{fontSize:12,color:'rgba(150,185,230,0.38)',marginRight:8}}>· Never synced yet</span>
        <button className="av-syncbtn">⟳ SYNC NOW</button>
        <span className="av-badge">v3.90</span>
      </div>
      <div className="av-tabs">
        {['🎯 SYSTEM FINDER','⚙️ OPTIMIZER','📊 ECONOMY','📌 PINNED','⚖️ COMPARE','👁 WATCHLIST','🗺️ ROUTE','🛸 FC PLANNER','🌐 MAP','✨ 3D MAP','🏗️ COLONIES'].map((t,i)=>(
          <button key={i} className={`av-tab${i===0?' active':''}`}>{t}</button>
        ))}
      </div>
      <div className="av-body">
        <div className="av-sidebar">
          <div className="av-panel">
            <div className="av-panel-hdr"><span className="av-panel-icon">📍</span><span className="av-panel-title">Reference System</span><span style={{fontSize:10,color:'rgba(150,185,230,0.30)'}}>▼</span></div>
            <div className="av-panel-body">
              <label className="av-label">System Name</label>
              <input className="av-input" defaultValue="Sol" />
              <div style={{marginTop:8,padding:'7px 11px',background:'rgba(100,160,255,0.07)',borderRadius:8,border:'1px solid rgba(140,195,255,0.18)',fontSize:13,color:'rgba(160,210,255,0.80)',display:'flex',alignItems:'center',gap:8}}><span>📍</span><span>Sol — 0, 0, 0</span></div>
            </div>
          </div>
          <div className="av-panel">
            <div className="av-panel-hdr"><span className="av-panel-icon">📡</span><span className="av-panel-title">Search Radius</span><span style={{fontSize:10,color:'rgba(150,185,230,0.30)'}}>▼</span></div>
            <div className="av-panel-body">
              {([['Max Distance (ly)',50],['Min Distance (ly)',0],['Results Per Page',50]] as [string,number][]).map(([lbl,val],i)=>(
                <div key={i} style={{marginBottom:i<2?12:0}}><label className="av-label">{lbl}</label><div className="av-slider-row"><input type="range" className="av-slider" defaultValue={val}/><span className="av-slider-val">{val}</span></div></div>
              ))}
            </div>
          </div>
          <div className="av-panel">
            <div className="av-panel-hdr"><span className="av-panel-icon">⭐</span><span className="av-panel-title">Rating Filter</span><span style={{fontSize:10,color:'rgba(150,185,230,0.30)'}}>▼</span></div>
            <div className="av-panel-body"><label className="av-label">Minimum Rating</label><div className="av-slider-row"><input type="range" className="av-slider" defaultValue={60}/><span className="av-slider-val">60</span></div></div>
          </div>
          <button className="av-searchbtn">🔍 SEARCH SYSTEMS</button>
        </div>
        <div className="av-content">
          <div className="av-summary"><span>Found <strong>247 SYSTEMS</strong></span><span>·</span><span>⏱ 843ms</span><div style={{flex:1}}/><button className="av-btn">👁 Watch All</button><button className="av-btn">📋 Copy Names</button></div>
          {systems.map((sys,i)=>{
            const b = ECO[sys.economy] ?? {bg:'linear-gradient(135deg,#334,#556)',glow:'rgba(100,120,160,0.4)'};
            return (
              <div className="av-card" key={i}>
                <div className="av-card-hdr">
                  <div className="av-rating-wrap"><span className="av-rating" style={{background:b.bg,boxShadow:`0 2px 14px ${b.glow}`}}>{sys.rating}</span><span className="av-eco-lbl">{sys.economy}</span></div>
                  <span className="av-sys-name">{sys.name}</span>
                  <span className="av-dist">📡 {sys.dist}</span>
                  <button style={{background:'none',border:'none',color:'rgba(150,185,230,0.30)',cursor:'pointer',fontSize:16}}>📌</button>
                </div>
                <div className="av-card-body">
                  <div className="av-tags">{sys.tags.map((t,j)=><span key={j} className="av-tag">{t}</span>)}<span className="av-tag">⭐ Landable</span><span className="av-tag">💰 {sys.pop}</span></div>
                  <div className="av-stat-row"><div className="av-stat"><span className="av-stat-lbl">Slots</span><span className="av-stat-val">{sys.slots}</span></div><div className="av-stat"><span className="av-stat-lbl">Bodies</span><span className="av-stat-val">{sys.bodies}</span></div><div className="av-stat"><span className="av-stat-lbl">Stars</span><span className="av-stat-val">{sys.star}</span></div><div className="av-stat"><span className="av-stat-lbl">Security</span><span className="av-stat-val">{sys.sec}</span></div></div>
                </div>
                <div className="av-card-footer"><button className="av-btn">👁 Watch</button><button className="av-btn">⚖️ Compare</button><button className="av-btn primary">📋 Briefing</button></div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
