export function AmberNoir() {
  const css = `
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;600;700&family=Rajdhani:wght@400;500;600&display=swap');

    .an-root {
      font-family: 'Rajdhani', sans-serif;
      background:
        radial-gradient(ellipse at 30% 0%,  rgba(120,70,0,0.28) 0%, transparent 55%),
        radial-gradient(ellipse at 80% 90%, rgba(80,40,0,0.20)  0%, transparent 50%),
        linear-gradient(170deg, #060402 0%, #0c0803 50%, #070502 100%);
      color: #e8d9b8;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }
    .an-root::before {
      content:'';
      position:fixed; inset:0; pointer-events:none; z-index:0;
      background-image:
        radial-gradient(1px 1px at 12% 22%, rgba(255,200,80,0.12) 0%, transparent 100%),
        radial-gradient(1px 1px at 55% 48%, rgba(255,200,80,0.08) 0%, transparent 100%),
        radial-gradient(1px 1px at 78% 14%, rgba(255,200,80,0.10) 0%, transparent 100%),
        radial-gradient(1px 1px at 33% 79%, rgba(255,200,80,0.07) 0%, transparent 100%),
        radial-gradient(1px 1px at 90% 63%, rgba(255,200,80,0.09) 0%, transparent 100%);
    }

    .an-header {
      background: rgba(100,55,0,0.14);
      backdrop-filter: blur(22px); -webkit-backdrop-filter: blur(22px);
      border-bottom: 1px solid rgba(200,140,0,0.30);
      padding: 14px 24px; display: flex; align-items: center; gap: 16px;
      position: relative; z-index: 10;
      box-shadow: 0 4px 32px rgba(160,90,0,0.18), 0 1px 0 rgba(255,210,80,0.06) inset;
    }
    .an-logo {
      width:42px; height:42px;
      border:1.5px solid rgba(210,160,0,0.75); border-radius:8px;
      display:flex; align-items:center; justify-content:center;
      font-size:18px; color:#d4a017;
      box-shadow:0 0 20px rgba(200,140,0,0.45), inset 0 0 12px rgba(180,120,0,0.10);
    }
    .an-title {
      font-family:'Orbitron',monospace; font-size:20px; font-weight:700;
      color:#f0d060; letter-spacing:2px;
      text-shadow: 0 0 20px rgba(220,170,0,0.5);
    }
    .an-sub { font-size:10px; color:rgba(200,170,100,0.45); letter-spacing:3px; text-transform:uppercase; }
    .an-spacer { flex:1; }
    .an-badge {
      font-family:'Orbitron',monospace; font-size:10px;
      color:#c8900a; border:1px solid rgba(200,140,0,0.45); border-radius:4px;
      padding:4px 10px; background:rgba(160,100,0,0.12); backdrop-filter:blur(8px);
    }
    .an-syncbtn {
      background:linear-gradient(135deg,rgba(180,110,0,0.85),rgba(100,55,0,0.85));
      color:#f0d060; border:1px solid rgba(200,140,0,0.5); border-radius:6px;
      padding:8px 18px; font-family:'Orbitron',monospace; font-size:10px;
      font-weight:600; letter-spacing:1px; cursor:pointer;
      box-shadow:0 2px 16px rgba(180,110,0,0.35); backdrop-filter:blur(8px);
    }

    .an-tabs {
      background:rgba(80,40,0,0.08); backdrop-filter:blur(14px); -webkit-backdrop-filter:blur(14px);
      border-bottom:1px solid rgba(200,140,0,0.15); padding:0 20px;
      display:flex; gap:2px; overflow-x:auto; position:relative; z-index:10;
    }
    .an-tab {
      font-family:'Orbitron',monospace; font-size:10px; letter-spacing:1px; text-transform:uppercase;
      padding:13px 16px; background:none; border:none; border-bottom:2px solid transparent;
      color:rgba(200,160,80,0.38); cursor:pointer; white-space:nowrap; transition:all 0.2s;
    }
    .an-tab.active {
      color:#d4a017; border-bottom-color:#b8860b;
      background:linear-gradient(180deg,rgba(180,110,0,0.09) 0%,transparent 100%);
      text-shadow:0 0 10px rgba(200,150,0,0.55);
    }
    .an-tab:hover:not(.active) { color:rgba(230,190,100,0.7); }

    .an-body { display:flex; flex:1; min-height:0; position:relative; z-index:1; }

    .an-sidebar {
      width:300px; background:rgba(80,40,0,0.07);
      backdrop-filter:blur(18px); -webkit-backdrop-filter:blur(18px);
      border-right:1px solid rgba(200,140,0,0.12);
      padding:18px 14px; overflow-y:auto; display:flex; flex-direction:column; gap:14px;
    }
    .an-panel {
      background:rgba(120,65,0,0.09); backdrop-filter:blur(14px); -webkit-backdrop-filter:blur(14px);
      border:1px solid rgba(200,140,0,0.18); border-radius:10px; overflow:hidden;
    }
    .an-panel-hdr {
      background:rgba(120,70,0,0.12); border-bottom:1px solid rgba(200,140,0,0.13);
      padding:10px 14px; display:flex; align-items:center; gap:8px;
    }
    .an-panel-icon { color:#c8900a; font-size:14px; filter:drop-shadow(0 0 5px rgba(200,140,0,0.6)); }
    .an-panel-title { font-family:'Orbitron',monospace; font-size:10px; font-weight:600; letter-spacing:1.5px; text-transform:uppercase; color:rgba(230,195,100,0.88); flex:1; }
    .an-panel-body { padding:14px; }
    .an-label { font-size:11px; font-weight:600; color:rgba(200,160,80,0.52); letter-spacing:1px; text-transform:uppercase; margin-bottom:6px; display:block; }
    .an-input {
      width:100%; background:rgba(100,55,0,0.12); border:1px solid rgba(200,140,0,0.22);
      border-radius:6px; color:#e8d0a0; font-family:'Rajdhani',sans-serif; font-size:14px;
      padding:9px 12px; outline:none; backdrop-filter:blur(8px);
    }
    .an-input:focus { border-color:rgba(210,155,0,0.5); box-shadow:0 0 12px rgba(180,120,0,0.18); }
    .an-slider-row { display:flex; align-items:center; gap:10px; margin-top:6px; }
    .an-slider { flex:1; accent-color:#b8860b; }
    .an-slider-val { font-family:'Orbitron',monospace; font-size:12px; color:#c8900a; min-width:32px; text-align:right; text-shadow:0 0 8px rgba(180,120,0,0.5); }
    .an-searchbtn {
      width:100%; background:linear-gradient(135deg,rgba(180,110,0,0.82),rgba(100,55,0,0.82));
      color:#f0d060; border:1px solid rgba(200,140,0,0.45); border-radius:8px; padding:12px;
      font-family:'Orbitron',monospace; font-size:11px; font-weight:700; letter-spacing:1.5px;
      cursor:pointer; backdrop-filter:blur(8px); box-shadow:0 4px 22px rgba(160,100,0,0.32); margin-top:4px;
    }

    .an-content { flex:1; padding:20px; overflow-y:auto; display:flex; flex-direction:column; gap:12px; }
    .an-summary {
      display:flex; align-items:center; gap:12px; padding:10px 16px;
      background:rgba(100,55,0,0.08); backdrop-filter:blur(10px);
      border:1px solid rgba(200,140,0,0.14); border-radius:10px;
      font-size:13px; color:rgba(200,160,80,0.62);
    }
    .an-summary strong { color:#c8900a; font-family:'Orbitron',monospace; font-size:12px; text-shadow:0 0 8px rgba(180,120,0,0.5); }

    .an-card {
      background:rgba(100,55,0,0.08); backdrop-filter:blur(16px); -webkit-backdrop-filter:blur(16px);
      border:1px solid rgba(200,140,0,0.15); border-radius:14px; overflow:hidden; transition:all 0.22s;
    }
    .an-card:hover {
      transform:translateY(-4px); background:rgba(120,68,0,0.13);
      border-color:rgba(210,155,0,0.38);
      box-shadow:0 14px 40px rgba(160,100,0,0.18), 0 2px 8px rgba(0,0,0,0.5);
    }
    .an-card-hdr { padding:13px 16px; display:flex; align-items:center; gap:10px; border-bottom:1px solid rgba(200,140,0,0.1); }
    .an-rating-wrap { display:flex; flex-direction:column; align-items:center; flex-shrink:0; }
    .an-rating { color:#fff; font-family:'Orbitron',monospace; font-size:14px; font-weight:700; border-radius:6px; padding:5px 11px; min-width:46px; text-align:center; }
    .an-eco-lbl { font-size:8px; color:rgba(255,255,255,0.55); font-family:'Orbitron',monospace; text-transform:uppercase; margin-top:2px; }
    .an-sys-name { font-family:'Orbitron',monospace; font-size:13px; color:rgba(235,210,155,0.96); font-weight:600; flex:1; }
    .an-dist { font-size:12px; color:rgba(200,160,80,0.5); }
    .an-card-body { padding:12px 16px; }
    .an-tags { display:flex; flex-wrap:wrap; gap:6px; margin-bottom:10px; }
    .an-tag { font-size:11px; padding:3px 10px; border-radius:4px; background:rgba(160,100,0,0.12); border:1px solid rgba(200,140,0,0.28); color:#c8900a; }
    .an-tag.g { background:rgba(40,160,80,0.10); border-color:rgba(40,160,80,0.28); color:#4ade80; }
    .an-tag.b { background:rgba(40,120,200,0.10); border-color:rgba(40,120,200,0.28); color:#60a5fa; }
    .an-stat-row { display:flex; gap:20px; margin-top:8px; }
    .an-stat { display:flex; flex-direction:column; gap:2px; }
    .an-stat-lbl { font-size:10px; color:rgba(190,150,70,0.48); text-transform:uppercase; letter-spacing:1px; }
    .an-stat-val { font-size:13px; color:rgba(230,205,145,0.88); font-weight:600; }
    .an-card-footer { padding:10px 16px; border-top:1px solid rgba(200,140,0,0.09); display:flex; gap:8px; justify-content:flex-end; }
    .an-btn { font-size:11px; padding:6px 14px; border-radius:6px; border:1px solid rgba(200,140,0,0.18); background:rgba(120,68,0,0.09); color:rgba(210,170,80,0.65); cursor:pointer; font-family:'Rajdhani',sans-serif; font-weight:600; transition:all 0.15s; }
    .an-btn:hover { background:rgba(160,100,0,0.18); color:rgba(240,200,100,0.9); }
    .an-btn.primary { background:rgba(180,110,0,0.20); border-color:rgba(210,155,0,0.42); color:#c8900a; }
  `;

  const ECO: Record<string,{bg:string;glow:string}> = {
    'High Tech':  { bg:'linear-gradient(135deg,#0d7abf,#22d3ee)', glow:'rgba(0,180,240,0.55)' },
    'Industrial': { bg:'linear-gradient(135deg,#b06010,#f59e0b)', glow:'rgba(220,140,0,0.55)' },
    'Agriculture':{ bg:'linear-gradient(135deg,#1a7a38,#34d399)', glow:'rgba(40,200,110,0.50)' },
    'Military':   { bg:'linear-gradient(135deg,#8a1010,#ef4444)', glow:'rgba(220,30,30,0.50)' },
  };

  const systems = [
    { name:'Colonia Gateway', rating:94, economy:'High Tech',   dist:'22,000 ly', tags:['High Tech','Industrial'],  tc:['b',''],  pop:'2.1B', slots:7,  bodies:23, star:'F-class', sec:'High'   },
    { name:'Eravate',         rating:88, economy:'Industrial',  dist:'34.2 ly',   tags:['Industrial','Refinery'],   tc:['',''],   pop:'450M', slots:5,  bodies:14, star:'G-class', sec:'Medium' },
    { name:'Lave',            rating:81, economy:'Agriculture', dist:'108.5 ly',  tags:['Agriculture','Tourism'],   tc:['g',''],  pop:'1.2B', slots:6,  bodies:18, star:'K-class', sec:'High'   },
    { name:'Alioth',          rating:76, economy:'Military',    dist:'82.6 ly',   tags:['Military','Service'],      tc:['',''],   pop:'8.4B', slots:4,  bodies:11, star:'A-class', sec:'High'   },
  ];

  return (
    <div className="an-root">
      <style dangerouslySetInnerHTML={{ __html: css }} />
      <div className="an-header">
        <div className="an-logo">🎯</div>
        <div><div className="an-title">ED:FINDER</div><div className="an-sub">Advanced System Finder &amp; Optimizer</div></div>
        <div className="an-spacer" />
        <span style={{fontSize:12,color:'rgba(200,160,80,0.42)',marginRight:8}}>· Never synced yet</span>
        <button className="an-syncbtn">⟳ SYNC NOW</button>
        <span className="an-badge">v3.90</span>
      </div>
      <div className="an-tabs">
        {['🎯 SYSTEM FINDER','⚙️ OPTIMIZER','📊 ECONOMY','📌 PINNED','⚖️ COMPARE','👁 WATCHLIST','🗺️ ROUTE','🛸 FC PLANNER','🌐 MAP','✨ 3D MAP','🏗️ COLONIES'].map((t,i)=>(
          <button key={i} className={`an-tab${i===0?' active':''}`}>{t}</button>
        ))}
      </div>
      <div className="an-body">
        <div className="an-sidebar">
          <div className="an-panel">
            <div className="an-panel-hdr"><span className="an-panel-icon">📍</span><span className="an-panel-title">Reference System</span><span style={{fontSize:10,color:'rgba(200,150,70,0.36)'}}>▼</span></div>
            <div className="an-panel-body">
              <label className="an-label">System Name</label>
              <input className="an-input" defaultValue="Sol" />
              <div style={{marginTop:8,padding:'7px 11px',background:'rgba(160,100,0,0.10)',borderRadius:6,border:'1px solid rgba(200,140,0,0.24)',fontSize:13,color:'#c8900a',display:'flex',alignItems:'center',gap:8}}><span>📍</span><span>Sol — 0, 0, 0</span></div>
            </div>
          </div>
          <div className="an-panel">
            <div className="an-panel-hdr"><span className="an-panel-icon">📡</span><span className="an-panel-title">Search Radius</span><span style={{fontSize:10,color:'rgba(200,150,70,0.36)'}}>▼</span></div>
            <div className="an-panel-body">
              {([['Max Distance (ly)',50],['Min Distance (ly)',0],['Results Per Page',50]] as [string,number][]).map(([lbl,val],i)=>(
                <div key={i} style={{marginBottom:i<2?12:0}}><label className="an-label">{lbl}</label><div className="an-slider-row"><input type="range" className="an-slider" defaultValue={val}/><span className="an-slider-val">{val}</span></div></div>
              ))}
            </div>
          </div>
          <div className="an-panel">
            <div className="an-panel-hdr"><span className="an-panel-icon">⭐</span><span className="an-panel-title">Rating Filter</span><span style={{fontSize:10,color:'rgba(200,150,70,0.36)'}}>▼</span></div>
            <div className="an-panel-body"><label className="an-label">Minimum Rating</label><div className="an-slider-row"><input type="range" className="an-slider" defaultValue={60}/><span className="an-slider-val">60</span></div></div>
          </div>
          <button className="an-searchbtn">🔍 SEARCH SYSTEMS</button>
        </div>
        <div className="an-content">
          <div className="an-summary"><span>Found <strong>247 SYSTEMS</strong></span><span>·</span><span>⏱ 843ms</span><div style={{flex:1}}/><button className="an-btn">👁 Watch All</button><button className="an-btn">📋 Copy Names</button></div>
          {systems.map((sys,i)=>{
            const b = ECO[sys.economy] ?? {bg:'linear-gradient(135deg,#555,#888)',glow:'rgba(120,120,120,0.4)'};
            return (
              <div className="an-card" key={i}>
                <div className="an-card-hdr">
                  <div className="an-rating-wrap"><span className="an-rating" style={{background:b.bg,boxShadow:`0 2px 14px ${b.glow}`}}>{sys.rating}</span><span className="an-eco-lbl">{sys.economy}</span></div>
                  <span className="an-sys-name">{sys.name}</span>
                  <span className="an-dist">📡 {sys.dist}</span>
                  <button style={{background:'none',border:'none',color:'rgba(200,150,70,0.4)',cursor:'pointer',fontSize:16}}>📌</button>
                </div>
                <div className="an-card-body">
                  <div className="an-tags">{sys.tags.map((t,j)=><span key={j} className={`an-tag ${sys.tc[j]??''}`}>{t}</span>)}<span className="an-tag g">⭐ Landable</span><span className="an-tag">💰 {sys.pop}</span></div>
                  <div className="an-stat-row"><div className="an-stat"><span className="an-stat-lbl">Slots</span><span className="an-stat-val">{sys.slots}</span></div><div className="an-stat"><span className="an-stat-lbl">Bodies</span><span className="an-stat-val">{sys.bodies}</span></div><div className="an-stat"><span className="an-stat-lbl">Stars</span><span className="an-stat-val">{sys.star}</span></div><div className="an-stat"><span className="an-stat-lbl">Security</span><span className="an-stat-val">{sys.sec}</span></div></div>
                </div>
                <div className="an-card-footer"><button className="an-btn">👁 Watch</button><button className="an-btn">⚖️ Compare</button><button className="an-btn primary">📋 Briefing</button></div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
