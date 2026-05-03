export function SolidFlat() {
  const css = `
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;600;700&family=Inter:wght@400;500;600&display=swap');

    .sf-root {
      font-family: 'Inter', sans-serif;
      background: #0e1118;
      color: #c8d4e8;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }

    .sf-header {
      background: #161c28;
      border-bottom: 1px solid #252e40;
      padding: 14px 24px; display: flex; align-items: center; gap: 16px;
      position: relative; z-index: 10;
    }
    .sf-logo {
      width:42px; height:42px; background:#ff7a20; border-radius:10px;
      display:flex; align-items:center; justify-content:center;
      font-size:20px; color:#fff; font-weight:700;
    }
    .sf-title { font-family:'Orbitron',monospace; font-size:18px; font-weight:700; color:#f0f4ff; letter-spacing:2px; }
    .sf-sub { font-size:11px; color:#5a6a88; letter-spacing:1px; }
    .sf-spacer { flex:1; }
    .sf-badge {
      font-family:'Orbitron',monospace; font-size:10px; color:#7a8aaa;
      border:1px solid #252e40; border-radius:6px; padding:4px 10px; background:#161c28;
    }
    .sf-syncbtn {
      background:#ff7a20; color:#fff; border:none; border-radius:8px;
      padding:8px 18px; font-size:13px; font-weight:600; cursor:pointer; letter-spacing:0.5px;
    }
    .sf-syncbtn:hover { background:#ff8f3a; }

    .sf-tabs {
      background:#161c28; border-bottom:1px solid #252e40; padding:0 20px;
      display:flex; gap:0; overflow-x:auto; position:relative; z-index:10;
    }
    .sf-tab {
      font-size:12px; font-weight:500; padding:13px 16px; background:none; border:none;
      border-bottom:2px solid transparent; color:#4a5a78; cursor:pointer; white-space:nowrap; transition:all 0.15s;
    }
    .sf-tab.active { color:#f0f4ff; border-bottom-color:#ff7a20; background:rgba(255,122,32,0.06); }
    .sf-tab:hover:not(.active) { color:#8a9ab8; }

    .sf-body { display:flex; flex:1; min-height:0; }

    .sf-sidebar {
      width:300px; background:#131820; border-right:1px solid #1e2738;
      padding:16px 14px; overflow-y:auto; display:flex; flex-direction:column; gap:12px;
    }
    .sf-panel { background:#161c28; border:1px solid #1e2738; border-radius:12px; overflow:hidden; }
    .sf-panel-hdr {
      background:#1a2234; border-bottom:1px solid #1e2738;
      padding:10px 14px; display:flex; align-items:center; gap:8px;
    }
    .sf-panel-icon { font-size:14px; }
    .sf-panel-title { font-size:12px; font-weight:600; color:#8a9ab8; letter-spacing:0.5px; flex:1; }
    .sf-panel-body { padding:14px; }
    .sf-label { font-size:11px; font-weight:600; color:#4a5a78; letter-spacing:0.5px; text-transform:uppercase; margin-bottom:6px; display:block; }
    .sf-input {
      width:100%; background:#0e1118; border:1px solid #1e2738; border-radius:8px;
      color:#c8d4e8; font-family:'Inter',sans-serif; font-size:14px; padding:9px 12px; outline:none;
    }
    .sf-input:focus { border-color:#ff7a20; }
    .sf-slider-row { display:flex; align-items:center; gap:10px; margin-top:6px; }
    .sf-slider { flex:1; accent-color:#ff7a20; }
    .sf-slider-val { font-size:13px; font-weight:600; color:#ff7a20; min-width:32px; text-align:right; }
    .sf-searchbtn {
      width:100%; background:#ff7a20; color:#fff; border:none; border-radius:10px;
      padding:12px; font-size:13px; font-weight:700; cursor:pointer; letter-spacing:0.5px; margin-top:4px;
    }
    .sf-searchbtn:hover { background:#ff8f3a; }

    .sf-content { flex:1; padding:20px; overflow-y:auto; display:flex; flex-direction:column; gap:10px; }
    .sf-summary {
      display:flex; align-items:center; gap:12px; padding:10px 16px;
      background:#161c28; border:1px solid #1e2738; border-radius:10px;
      font-size:13px; color:#4a5a78;
    }
    .sf-summary strong { color:#f0f4ff; font-weight:700; }

    .sf-card { background:#161c28; border:1px solid #1e2738; border-radius:14px; overflow:hidden; transition:all 0.18s; }
    .sf-card:hover { border-color:#2e3e58; background:#1a2030; box-shadow:0 8px 32px rgba(0,0,0,0.4); }
    /* left accent bar coloured by economy */
    .sf-card-inner { display:flex; }
    .sf-accent-bar { width:4px; flex-shrink:0; }
    .sf-card-right { flex:1; min-width:0; }
    .sf-card-hdr { padding:12px 16px; display:flex; align-items:center; gap:10px; border-bottom:1px solid #1e2738; }
    .sf-rating-wrap { display:flex; flex-direction:column; align-items:center; flex-shrink:0; }
    .sf-rating { color:#fff; font-family:'Orbitron',monospace; font-size:14px; font-weight:700; border-radius:8px; padding:5px 11px; min-width:46px; text-align:center; }
    .sf-eco-lbl { font-size:9px; color:rgba(255,255,255,0.55); font-family:'Orbitron',monospace; text-transform:uppercase; margin-top:2px; }
    .sf-sys-name { font-size:14px; font-weight:600; color:#e8f0ff; flex:1; }
    .sf-dist { font-size:12px; color:#4a5a78; }
    .sf-card-body { padding:10px 16px; }
    .sf-tags { display:flex; flex-wrap:wrap; gap:5px; margin-bottom:8px; }
    .sf-tag { font-size:11px; padding:3px 10px; border-radius:20px; background:#1e2738; color:#6a7a98; font-weight:500; }
    .sf-stat-row { display:flex; gap:20px; }
    .sf-stat { display:flex; flex-direction:column; gap:1px; }
    .sf-stat-lbl { font-size:10px; color:#3a4a68; text-transform:uppercase; letter-spacing:0.5px; font-weight:500; }
    .sf-stat-val { font-size:13px; color:#a0b0cc; font-weight:600; }
    .sf-card-footer { padding:10px 16px; border-top:1px solid #1e2738; display:flex; gap:8px; justify-content:flex-end; }
    .sf-btn { font-size:12px; padding:6px 14px; border-radius:8px; border:1px solid #1e2738; background:#1a2030; color:#5a6a88; cursor:pointer; font-weight:500; transition:all 0.12s; }
    .sf-btn:hover { background:#222c3e; color:#8a9ab8; border-color:#2e3e58; }
    .sf-btn.primary { background:#ff7a20; border-color:#ff7a20; color:#fff; }
    .sf-btn.primary:hover { background:#ff8f3a; }
  `;

  const ECO: Record<string,{bg:string;bar:string}> = {
    'High Tech':   { bg:'#0d7abf', bar:'#0d7abf' },
    'Industrial':  { bg:'#c06010', bar:'#f59e0b' },
    'Agriculture': { bg:'#1a7a38', bar:'#34d399' },
    'Military':    { bg:'#8a1010', bar:'#ef4444' },
    'Tourism':     { bg:'#9a1a6a', bar:'#f472b6' },
    'Extraction':  { bg:'#8a7010', bar:'#fbbf24' },
    'Colony':      { bg:'#4a1a9a', bar:'#a855f7' },
    'Service':     { bg:'#0e7a7a', bar:'#2dd4bf' },
  };

  const systems = [
    { name:'Colonia Gateway', rating:94, economy:'High Tech',   dist:'22,000 ly', tags:['High Tech','Industrial','Landable'],  pop:'2.1B', slots:7, bodies:23, star:'F-class', sec:'High'   },
    { name:'Eravate',         rating:88, economy:'Industrial',  dist:'34.2 ly',   tags:['Industrial','Refinery','Landable'],   pop:'450M', slots:5, bodies:14, star:'G-class', sec:'Medium' },
    { name:'Lave',            rating:81, economy:'Agriculture', dist:'108.5 ly',  tags:['Agriculture','Tourism','Landable'],   pop:'1.2B', slots:6, bodies:18, star:'K-class', sec:'High'   },
    { name:'Alioth',          rating:76, economy:'Military',    dist:'82.6 ly',   tags:['Military','Service','Landable'],      pop:'8.4B', slots:4, bodies:11, star:'A-class', sec:'High'   },
  ];

  return (
    <div className="sf-root">
      <style dangerouslySetInnerHTML={{ __html: css }} />
      <div className="sf-header">
        <div className="sf-logo">🎯</div>
        <div><div className="sf-title">ED:FINDER</div><div className="sf-sub">Advanced System Finder &amp; Optimizer</div></div>
        <div className="sf-spacer" />
        <span style={{fontSize:12,color:'#3a4a68',marginRight:8}}>Never synced</span>
        <button className="sf-syncbtn">⟳ Sync Now</button>
        <span className="sf-badge">v3.90</span>
      </div>
      <div className="sf-tabs">
        {['🎯 System Finder','⚙️ Optimizer','📊 Economy','📌 Pinned','⚖️ Compare','👁 Watchlist','🗺️ Route','🛸 FC Planner','🌐 Map','✨ 3D Map','🏗️ Colonies'].map((t,i)=>(
          <button key={i} className={`sf-tab${i===0?' active':''}`}>{t}</button>
        ))}
      </div>
      <div className="sf-body">
        <div className="sf-sidebar">
          <div className="sf-panel">
            <div className="sf-panel-hdr"><span className="sf-panel-icon">📍</span><span className="sf-panel-title">Reference System</span><span style={{color:'#3a4a68'}}>▼</span></div>
            <div className="sf-panel-body">
              <label className="sf-label">System Name</label>
              <input className="sf-input" defaultValue="Sol" />
              <div style={{marginTop:8,padding:'8px 12px',background:'rgba(255,122,32,0.08)',borderRadius:8,border:'1px solid rgba(255,122,32,0.2)',fontSize:13,color:'#ff9a50',display:'flex',alignItems:'center',gap:8}}>📍 Sol — 0, 0, 0</div>
            </div>
          </div>
          <div className="sf-panel">
            <div className="sf-panel-hdr"><span className="sf-panel-icon">📡</span><span className="sf-panel-title">Search Radius</span><span style={{color:'#3a4a68'}}>▼</span></div>
            <div className="sf-panel-body">
              {([['Max Distance (ly)',50],['Min Distance (ly)',0],['Results Per Page',50]] as [string,number][]).map(([lbl,val],i)=>(
                <div key={i} style={{marginBottom:i<2?12:0}}><label className="sf-label">{lbl}</label><div className="sf-slider-row"><input type="range" className="sf-slider" defaultValue={val}/><span className="sf-slider-val">{val}</span></div></div>
              ))}
            </div>
          </div>
          <div className="sf-panel">
            <div className="sf-panel-hdr"><span className="sf-panel-icon">⭐</span><span className="sf-panel-title">Rating Filter</span><span style={{color:'#3a4a68'}}>▼</span></div>
            <div className="sf-panel-body"><label className="sf-label">Minimum Rating</label><div className="sf-slider-row"><input type="range" className="sf-slider" defaultValue={60}/><span className="sf-slider-val">60</span></div></div>
          </div>
          <button className="sf-searchbtn">🔍 Search Systems</button>
        </div>
        <div className="sf-content">
          <div className="sf-summary"><span>Found <strong>247 systems</strong></span><span>·</span><span style={{color:'#3a4a68'}}>843ms</span><div style={{flex:1}}/><button className="sf-btn">👁 Watch All</button><button className="sf-btn">📋 Copy Names</button></div>
          {systems.map((sys,i)=>{
            const b = ECO[sys.economy] ?? {bg:'#556',bar:'#778'};
            return (
              <div className="sf-card" key={i}>
                <div className="sf-card-inner">
                  <div className="sf-accent-bar" style={{background:b.bar}}/>
                  <div className="sf-card-right">
                    <div className="sf-card-hdr">
                      <div className="sf-rating-wrap">
                        <span className="sf-rating" style={{background:b.bg}}>{sys.rating}</span>
                        <span className="sf-eco-lbl">{sys.economy}</span>
                      </div>
                      <span className="sf-sys-name">{sys.name}</span>
                      <span className="sf-dist">📡 {sys.dist}</span>
                      <button style={{background:'none',border:'none',color:'#3a4a68',cursor:'pointer',fontSize:16}}>📌</button>
                    </div>
                    <div className="sf-card-body">
                      <div className="sf-tags">{sys.tags.map((t,j)=><span key={j} className="sf-tag">{t}</span>)}<span className="sf-tag">💰 {sys.pop}</span></div>
                      <div className="sf-stat-row">
                        <div className="sf-stat"><span className="sf-stat-lbl">Slots</span><span className="sf-stat-val">{sys.slots}</span></div>
                        <div className="sf-stat"><span className="sf-stat-lbl">Bodies</span><span className="sf-stat-val">{sys.bodies}</span></div>
                        <div className="sf-stat"><span className="sf-stat-lbl">Stars</span><span className="sf-stat-val">{sys.star}</span></div>
                        <div className="sf-stat"><span className="sf-stat-lbl">Security</span><span className="sf-stat-val">{sys.sec}</span></div>
                      </div>
                    </div>
                    <div className="sf-card-footer">
                      <button className="sf-btn">👁 Watch</button>
                      <button className="sf-btn">⚖️ Compare</button>
                      <button className="sf-btn primary">📋 Briefing</button>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
