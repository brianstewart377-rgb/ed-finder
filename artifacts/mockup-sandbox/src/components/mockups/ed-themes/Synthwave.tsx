export function Synthwave() {
  const css = `
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;600;700&family=Rajdhani:wght@400;500;600&display=swap');

    .sw-root {
      font-family: 'Rajdhani', sans-serif;
      background:
        radial-gradient(ellipse at 50% 0%,  rgba(200,0,180,0.25) 0%, transparent 50%),
        radial-gradient(ellipse at 0%  80%, rgba(0,180,240,0.20) 0%, transparent 45%),
        radial-gradient(ellipse at 100% 60%,rgba(120,0,240,0.20) 0%, transparent 40%),
        linear-gradient(180deg, #0a0015 0%, #08001a 50%, #05000f 100%);
      color: #f0e0ff;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }
    /* grid floor */
    .sw-root::before {
      content:'';
      position:fixed; inset:0; pointer-events:none; z-index:0;
      background-image:
        linear-gradient(rgba(255,0,200,0.04) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255,0,200,0.04) 1px, transparent 1px);
      background-size: 40px 40px;
    }

    .sw-header {
      background: rgba(80,0,120,0.18);
      backdrop-filter: blur(22px); -webkit-backdrop-filter: blur(22px);
      border-bottom: 1px solid rgba(255,0,200,0.35);
      padding: 14px 24px; display: flex; align-items: center; gap: 16px;
      position: relative; z-index: 10;
      box-shadow: 0 4px 40px rgba(220,0,180,0.18), 0 0 80px rgba(0,180,255,0.06), 0 1px 0 rgba(255,100,220,0.08) inset;
    }
    .sw-logo {
      width:42px; height:42px;
      border:2px solid rgba(255,0,220,0.8); border-radius:6px;
      display:flex; align-items:center; justify-content:center;
      font-size:18px; color:#ff44dd;
      box-shadow:0 0 24px rgba(255,0,220,0.6), inset 0 0 16px rgba(255,0,220,0.08),
                 0 0 0 1px rgba(0,220,255,0.15);
    }
    .sw-title {
      font-family:'Orbitron',monospace; font-size:20px; font-weight:700; letter-spacing:2px;
      background: linear-gradient(90deg, #ff44dd 0%, #00e5ff 100%);
      -webkit-background-clip:text; -webkit-text-fill-color:transparent; background-clip:text;
      filter: drop-shadow(0 0 8px rgba(255,0,220,0.6));
    }
    .sw-sub { font-size:10px; color:rgba(220,160,255,0.45); letter-spacing:3px; text-transform:uppercase; }
    .sw-spacer { flex:1; }
    .sw-badge {
      font-family:'Orbitron',monospace; font-size:10px; color:#ff44dd;
      border:1px solid rgba(255,0,220,0.45); border-radius:4px; padding:4px 10px;
      background:rgba(200,0,180,0.10); backdrop-filter:blur(8px);
      box-shadow:0 0 10px rgba(255,0,220,0.2);
    }
    .sw-syncbtn {
      background:linear-gradient(135deg,rgba(220,0,180,0.85),rgba(0,160,240,0.65));
      color:#fff; border:1px solid rgba(255,0,220,0.5); border-radius:6px;
      padding:8px 18px; font-family:'Orbitron',monospace; font-size:10px;
      font-weight:600; letter-spacing:1px; cursor:pointer;
      box-shadow:0 2px 20px rgba(220,0,180,0.4), 0 0 40px rgba(0,200,255,0.08);
    }

    .sw-tabs {
      background:rgba(60,0,100,0.10); backdrop-filter:blur(14px); -webkit-backdrop-filter:blur(14px);
      border-bottom:1px solid rgba(255,0,200,0.18); padding:0 20px;
      display:flex; gap:2px; overflow-x:auto; position:relative; z-index:10;
    }
    .sw-tab {
      font-family:'Orbitron',monospace; font-size:10px; letter-spacing:1px; text-transform:uppercase;
      padding:13px 16px; background:none; border:none; border-bottom:2px solid transparent;
      color:rgba(220,160,255,0.35); cursor:pointer; white-space:nowrap; transition:all 0.2s;
    }
    .sw-tab.active {
      color:#ff44dd; border-bottom-color:#ff00cc;
      background:linear-gradient(180deg,rgba(220,0,180,0.09) 0%,transparent 100%);
      text-shadow:0 0 12px rgba(255,0,220,0.7);
    }
    .sw-tab:hover:not(.active) { color:rgba(240,200,255,0.7); }

    .sw-body { display:flex; flex:1; min-height:0; position:relative; z-index:1; }

    .sw-sidebar {
      width:300px; background:rgba(60,0,100,0.08);
      backdrop-filter:blur(18px); -webkit-backdrop-filter:blur(18px);
      border-right:1px solid rgba(255,0,200,0.12);
      padding:18px 14px; overflow-y:auto; display:flex; flex-direction:column; gap:14px;
    }
    .sw-panel {
      background:rgba(100,0,160,0.10); backdrop-filter:blur(14px); -webkit-backdrop-filter:blur(14px);
      border:1px solid rgba(255,0,200,0.18); border-radius:10px; overflow:hidden;
    }
    .sw-panel-hdr {
      background:rgba(100,0,160,0.12); border-bottom:1px solid rgba(255,0,200,0.12);
      padding:10px 14px; display:flex; align-items:center; gap:8px;
    }
    .sw-panel-icon { color:#ff44dd; font-size:14px; filter:drop-shadow(0 0 6px rgba(255,0,220,0.7)); }
    .sw-panel-title { font-family:'Orbitron',monospace; font-size:10px; font-weight:600; letter-spacing:1.5px; text-transform:uppercase; color:rgba(240,200,255,0.88); flex:1; }
    .sw-panel-body { padding:14px; }
    .sw-label { font-size:11px; font-weight:600; color:rgba(220,160,255,0.50); letter-spacing:1px; text-transform:uppercase; margin-bottom:6px; display:block; }
    .sw-input {
      width:100%; background:rgba(80,0,140,0.12); border:1px solid rgba(255,0,200,0.22);
      border-radius:6px; color:#f0e0ff; font-family:'Rajdhani',sans-serif; font-size:14px;
      padding:9px 12px; outline:none; backdrop-filter:blur(8px);
    }
    .sw-input:focus { border-color:rgba(255,0,220,0.55); box-shadow:0 0 14px rgba(220,0,180,0.22); }
    .sw-slider-row { display:flex; align-items:center; gap:10px; margin-top:6px; }
    .sw-slider { flex:1; accent-color:#ff00cc; }
    .sw-slider-val { font-family:'Orbitron',monospace; font-size:12px; color:#ff44dd; min-width:32px; text-align:right; text-shadow:0 0 8px rgba(255,0,220,0.55); }
    .sw-searchbtn {
      width:100%; background:linear-gradient(135deg,rgba(220,0,180,0.82),rgba(0,160,240,0.60));
      color:#fff; border:1px solid rgba(255,0,220,0.45); border-radius:8px; padding:12px;
      font-family:'Orbitron',monospace; font-size:11px; font-weight:700; letter-spacing:1.5px;
      cursor:pointer; box-shadow:0 4px 24px rgba(220,0,180,0.35); margin-top:4px;
    }

    .sw-content { flex:1; padding:20px; overflow-y:auto; display:flex; flex-direction:column; gap:12px; }
    .sw-summary {
      display:flex; align-items:center; gap:12px; padding:10px 16px;
      background:rgba(80,0,130,0.10); backdrop-filter:blur(10px);
      border:1px solid rgba(255,0,200,0.15); border-radius:10px;
      font-size:13px; color:rgba(220,160,255,0.60);
    }
    .sw-summary strong { color:#ff44dd; font-family:'Orbitron',monospace; font-size:12px; text-shadow:0 0 8px rgba(255,0,220,0.55); }

    .sw-card {
      background:rgba(80,0,130,0.09); backdrop-filter:blur(16px); -webkit-backdrop-filter:blur(16px);
      border:1px solid rgba(255,0,200,0.14); border-radius:14px; overflow:hidden; transition:all 0.22s;
    }
    .sw-card:hover {
      transform:translateY(-4px); background:rgba(100,0,160,0.14);
      border-color:rgba(255,0,220,0.40);
      box-shadow:0 14px 44px rgba(220,0,180,0.18), 0 0 60px rgba(0,200,255,0.06), 0 2px 8px rgba(0,0,0,0.6);
    }
    .sw-card-hdr { padding:13px 16px; display:flex; align-items:center; gap:10px; border-bottom:1px solid rgba(255,0,200,0.10); }
    .sw-rating-wrap { display:flex; flex-direction:column; align-items:center; flex-shrink:0; }
    .sw-rating { color:#fff; font-family:'Orbitron',monospace; font-size:14px; font-weight:700; border-radius:6px; padding:5px 11px; min-width:46px; text-align:center; }
    .sw-eco-lbl { font-size:8px; color:rgba(255,255,255,0.52); font-family:'Orbitron',monospace; text-transform:uppercase; margin-top:2px; }
    .sw-sys-name { font-family:'Orbitron',monospace; font-size:13px; color:rgba(240,215,255,0.96); font-weight:600; flex:1; }
    .sw-dist { font-size:12px; color:rgba(220,160,255,0.48); }
    .sw-card-body { padding:12px 16px; }
    .sw-tags { display:flex; flex-wrap:wrap; gap:6px; margin-bottom:10px; }
    .sw-tag      { font-size:11px; padding:3px 10px; border-radius:4px; background:rgba(200,0,180,0.12); border:1px solid rgba(255,0,220,0.30); color:#ff44dd; }
    .sw-tag.cyan { background:rgba(0,200,240,0.10); border-color:rgba(0,200,240,0.30); color:#00e5ff; }
    .sw-tag.grn  { background:rgba(0,240,160,0.09); border-color:rgba(0,240,160,0.28); color:#00f0a0; }
    .sw-tag.ylw  { background:rgba(255,220,0,0.09); border-color:rgba(255,220,0,0.26); color:#ffe000; }
    .sw-stat-row { display:flex; gap:20px; margin-top:8px; }
    .sw-stat { display:flex; flex-direction:column; gap:2px; }
    .sw-stat-lbl { font-size:10px; color:rgba(200,140,240,0.45); text-transform:uppercase; letter-spacing:1px; }
    .sw-stat-val { font-size:13px; color:rgba(235,210,255,0.88); font-weight:600; }
    .sw-card-footer { padding:10px 16px; border-top:1px solid rgba(255,0,200,0.09); display:flex; gap:8px; justify-content:flex-end; }
    .sw-btn { font-size:11px; padding:6px 14px; border-radius:6px; border:1px solid rgba(255,0,200,0.18); background:rgba(100,0,160,0.10); color:rgba(220,160,255,0.65); cursor:pointer; font-family:'Rajdhani',sans-serif; font-weight:600; transition:all 0.15s; }
    .sw-btn:hover { background:rgba(180,0,160,0.18); color:rgba(255,200,255,0.9); }
    .sw-btn.primary { background:rgba(200,0,180,0.20); border-color:rgba(255,0,220,0.44); color:#ff44dd; }
  `;

  const ECO: Record<string,{bg:string;glow:string}> = {
    'High Tech':   { bg:'linear-gradient(135deg,#0d7abf,#00e5ff)', glow:'rgba(0,200,255,0.55)' },
    'Industrial':  { bg:'linear-gradient(135deg,#c47010,#ffe000)', glow:'rgba(240,200,0,0.50)'  },
    'Agriculture': { bg:'linear-gradient(135deg,#0a8a40,#00f0a0)', glow:'rgba(0,220,130,0.48)'  },
    'Military':    { bg:'linear-gradient(135deg,#cc0020,#ff4060)', glow:'rgba(255,20,60,0.50)'  },
  };

  const systems = [
    { name:'Colonia Gateway', rating:94, economy:'High Tech',   dist:'22,000 ly', tags:['High Tech','Industrial'],  tc:['cyan','ylw'], pop:'2.1B', slots:7, bodies:23, star:'F-class', sec:'High'   },
    { name:'Eravate',         rating:88, economy:'Industrial',  dist:'34.2 ly',   tags:['Industrial','Refinery'],   tc:['ylw',''],     pop:'450M', slots:5, bodies:14, star:'G-class', sec:'Medium' },
    { name:'Lave',            rating:81, economy:'Agriculture', dist:'108.5 ly',  tags:['Agriculture','Tourism'],   tc:['grn',''],     pop:'1.2B', slots:6, bodies:18, star:'K-class', sec:'High'   },
    { name:'Alioth',          rating:76, economy:'Military',    dist:'82.6 ly',   tags:['Military','Service'],      tc:['','cyan'],    pop:'8.4B', slots:4, bodies:11, star:'A-class', sec:'High'   },
  ];

  return (
    <div className="sw-root">
      <style dangerouslySetInnerHTML={{ __html: css }} />
      <div className="sw-header">
        <div className="sw-logo">🎯</div>
        <div><div className="sw-title">ED:FINDER</div><div className="sw-sub">Advanced System Finder &amp; Optimizer</div></div>
        <div className="sw-spacer" />
        <span style={{fontSize:12,color:'rgba(220,160,255,0.40)',marginRight:8}}>· Never synced yet</span>
        <button className="sw-syncbtn">⟳ SYNC NOW</button>
        <span className="sw-badge">v3.90</span>
      </div>
      <div className="sw-tabs">
        {['🎯 SYSTEM FINDER','⚙️ OPTIMIZER','📊 ECONOMY','📌 PINNED','⚖️ COMPARE','👁 WATCHLIST','🗺️ ROUTE','🛸 FC PLANNER','🌐 MAP','✨ 3D MAP','🏗️ COLONIES'].map((t,i)=>(
          <button key={i} className={`sw-tab${i===0?' active':''}`}>{t}</button>
        ))}
      </div>
      <div className="sw-body">
        <div className="sw-sidebar">
          <div className="sw-panel">
            <div className="sw-panel-hdr"><span className="sw-panel-icon">📍</span><span className="sw-panel-title">Reference System</span><span style={{fontSize:10,color:'rgba(220,150,255,0.34)'}}>▼</span></div>
            <div className="sw-panel-body">
              <label className="sw-label">System Name</label>
              <input className="sw-input" defaultValue="Sol" />
              <div style={{marginTop:8,padding:'7px 11px',background:'rgba(180,0,160,0.10)',borderRadius:6,border:'1px solid rgba(255,0,220,0.24)',fontSize:13,color:'#ff44dd',display:'flex',alignItems:'center',gap:8}}><span>📍</span><span>Sol — 0, 0, 0</span></div>
            </div>
          </div>
          <div className="sw-panel">
            <div className="sw-panel-hdr"><span className="sw-panel-icon">📡</span><span className="sw-panel-title">Search Radius</span><span style={{fontSize:10,color:'rgba(220,150,255,0.34)'}}>▼</span></div>
            <div className="sw-panel-body">
              {([['Max Distance (ly)',50],['Min Distance (ly)',0],['Results Per Page',50]] as [string,number][]).map(([lbl,val],i)=>(
                <div key={i} style={{marginBottom:i<2?12:0}}><label className="sw-label">{lbl}</label><div className="sw-slider-row"><input type="range" className="sw-slider" defaultValue={val}/><span className="sw-slider-val">{val}</span></div></div>
              ))}
            </div>
          </div>
          <div className="sw-panel">
            <div className="sw-panel-hdr"><span className="sw-panel-icon">⭐</span><span className="sw-panel-title">Rating Filter</span><span style={{fontSize:10,color:'rgba(220,150,255,0.34)'}}>▼</span></div>
            <div className="sw-panel-body"><label className="sw-label">Minimum Rating</label><div className="sw-slider-row"><input type="range" className="sw-slider" defaultValue={60}/><span className="sw-slider-val">60</span></div></div>
          </div>
          <button className="sw-searchbtn">🔍 SEARCH SYSTEMS</button>
        </div>
        <div className="sw-content">
          <div className="sw-summary"><span>Found <strong>247 SYSTEMS</strong></span><span>·</span><span>⏱ 843ms</span><div style={{flex:1}}/><button className="sw-btn">👁 Watch All</button><button className="sw-btn">📋 Copy Names</button></div>
          {systems.map((sys,i)=>{
            const b = ECO[sys.economy] ?? {bg:'linear-gradient(135deg,#555,#888)',glow:'rgba(120,120,120,0.4)'};
            return (
              <div className="sw-card" key={i}>
                <div className="sw-card-hdr">
                  <div className="sw-rating-wrap"><span className="sw-rating" style={{background:b.bg,boxShadow:`0 2px 16px ${b.glow}`}}>{sys.rating}</span><span className="sw-eco-lbl">{sys.economy}</span></div>
                  <span className="sw-sys-name">{sys.name}</span>
                  <span className="sw-dist">📡 {sys.dist}</span>
                  <button style={{background:'none',border:'none',color:'rgba(220,150,255,0.38)',cursor:'pointer',fontSize:16}}>📌</button>
                </div>
                <div className="sw-card-body">
                  <div className="sw-tags">{sys.tags.map((t,j)=><span key={j} className={`sw-tag ${sys.tc[j]??''}`}>{t}</span>)}<span className="sw-tag grn">⭐ Landable</span><span className="sw-tag ylw">💰 {sys.pop}</span></div>
                  <div className="sw-stat-row"><div className="sw-stat"><span className="sw-stat-lbl">Slots</span><span className="sw-stat-val">{sys.slots}</span></div><div className="sw-stat"><span className="sw-stat-lbl">Bodies</span><span className="sw-stat-val">{sys.bodies}</span></div><div className="sw-stat"><span className="sw-stat-lbl">Stars</span><span className="sw-stat-val">{sys.star}</span></div><div className="sw-stat"><span className="sw-stat-lbl">Security</span><span className="sw-stat-val">{sys.sec}</span></div></div>
                </div>
                <div className="sw-card-footer"><button className="sw-btn">👁 Watch</button><button className="sw-btn">⚖️ Compare</button><button className="sw-btn primary">📋 Briefing</button></div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
