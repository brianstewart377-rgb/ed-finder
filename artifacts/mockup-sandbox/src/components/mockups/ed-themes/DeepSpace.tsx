export function DeepSpace() {
  const css = `
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;600;700&family=Rajdhani:wght@400;500;600&display=swap');
    .d-root { font-family:'Rajdhani',sans-serif; background:linear-gradient(160deg,#05080f 0%,#080c1a 40%,#050a14 100%); color:#c8d8f0; min-height:100vh; display:flex; flex-direction:column; }
    .d-header { background:linear-gradient(90deg,#080d1c,#0d1528,#080d1c); border-bottom:1px solid rgba(100,160,255,0.2); padding:14px 24px; display:flex; align-items:center; gap:16px; box-shadow:0 2px 24px rgba(60,100,255,0.12); }
    .d-logo { width:42px;height:42px;border:1.5px solid rgba(120,180,255,0.6);border-radius:12px;display:flex;align-items:center;justify-content:center;font-size:18px;color:#78b4ff;box-shadow:0 0 16px rgba(80,130,255,0.3),inset 0 0 12px rgba(80,130,255,0.08); }
    .d-title { font-family:'Orbitron',monospace;font-size:20px;font-weight:700;background:linear-gradient(90deg,#78b4ff,#b899ff);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text;letter-spacing:2px; }
    .d-sub { font-size:10px;color:rgba(150,180,230,0.45);letter-spacing:3px;text-transform:uppercase; }
    .d-spacer { flex:1; }
    .d-badge { font-family:'Orbitron',monospace;font-size:10px;color:#78b4ff;border:1px solid rgba(100,160,255,0.3);border-radius:20px;padding:4px 12px;background:rgba(80,130,255,0.08); }
    .d-syncbtn { background:linear-gradient(135deg,#3a6fd8,#6b3ed8);color:#fff;border:none;border-radius:20px;padding:8px 20px;font-family:'Orbitron',monospace;font-size:10px;font-weight:600;letter-spacing:1px;cursor:pointer;box-shadow:0 2px 16px rgba(80,100,255,0.35); }
    .d-tabs { background:#080d1c;border-bottom:1px solid rgba(100,160,255,0.12);padding:0 20px;display:flex;gap:0;overflow-x:auto; }
    .d-tab { font-family:'Orbitron',monospace;font-size:10px;letter-spacing:1px;text-transform:uppercase;padding:11px 16px;background:none;border:none;border-bottom:2px solid transparent;color:rgba(140,170,220,0.4);cursor:pointer;white-space:nowrap;transition:all 0.2s; }
    .d-tab.active { color:#78b4ff;border-bottom-color:#78b4ff;background:linear-gradient(180deg,rgba(80,130,255,0.07) 0%,transparent 100%); }
    .d-tab:hover:not(.active) { color:rgba(180,210,255,0.75); }
    .d-body { display:flex;flex:1;min-height:0; }
    .d-sidebar { width:300px;background:rgba(8,13,28,0.8);border-right:1px solid rgba(100,160,255,0.1);padding:18px 14px;overflow-y:auto;display:flex;flex-direction:column;gap:12px; }
    .d-panel { background:linear-gradient(145deg,rgba(15,22,45,0.9),rgba(10,16,32,0.95));border:1px solid rgba(100,160,255,0.12);border-radius:14px;overflow:hidden; }
    .d-panel-hdr { background:rgba(80,130,255,0.05);border-bottom:1px solid rgba(100,160,255,0.1);padding:10px 14px;display:flex;align-items:center;gap:8px; }
    .d-panel-icon { color:#78b4ff;font-size:14px; }
    .d-panel-title { font-family:'Orbitron',monospace;font-size:10px;font-weight:600;letter-spacing:1.5px;text-transform:uppercase;color:rgba(180,210,255,0.85);flex:1; }
    .d-panel-body { padding:14px; }
    .d-label { font-size:11px;font-weight:600;color:rgba(120,160,220,0.55);letter-spacing:1px;text-transform:uppercase;margin-bottom:6px;display:block; }
    .d-input { width:100%;background:rgba(10,20,50,0.8);border:1px solid rgba(100,160,255,0.15);border-radius:10px;color:#c8d8f0;font-family:'Rajdhani',sans-serif;font-size:14px;padding:9px 12px;outline:none; }
    .d-input:focus { border-color:rgba(100,160,255,0.45);box-shadow:0 0 12px rgba(80,130,255,0.15); }
    .d-slider { width:100%;accent-color:#78b4ff;margin:6px 0; }
    .d-slider-row { display:flex;align-items:center;gap:10px; }
    .d-slider-val { font-family:'Orbitron',monospace;font-size:12px;color:#78b4ff;min-width:32px;text-align:right; }
    .d-searchbtn { width:100%;background:linear-gradient(135deg,#3a6fd8,#6b3ed8);color:#fff;border:none;border-radius:24px;padding:12px;font-family:'Orbitron',monospace;font-size:11px;font-weight:700;letter-spacing:1.5px;cursor:pointer;margin-top:6px;box-shadow:0 4px 20px rgba(80,100,255,0.4); }
    .d-content { flex:1;padding:20px;overflow-y:auto;display:flex;flex-direction:column;gap:12px; }
    .d-summary { display:flex;align-items:center;gap:12px;padding:10px 16px;background:rgba(15,22,45,0.7);border:1px solid rgba(100,160,255,0.12);border-radius:12px;font-size:13px;color:rgba(140,170,220,0.6); }
    .d-summary strong { color:#78b4ff;font-family:'Orbitron',monospace;font-size:12px; }
    .d-card { background:linear-gradient(145deg,rgba(13,20,44,0.9),rgba(9,15,33,0.95));border:1px solid rgba(100,160,255,0.1);border-radius:16px;overflow:hidden;transition:all 0.25s; }
    .d-card:hover { transform:translateY(-4px);border-color:rgba(100,160,255,0.3);box-shadow:0 12px 36px rgba(60,100,255,0.18),0 0 60px rgba(100,130,255,0.04); }
    .d-card-hdr { padding:13px 16px;display:flex;align-items:center;gap:10px;border-bottom:1px solid rgba(100,160,255,0.08); }
    .d-rating { color:#fff;font-family:'Orbitron',monospace;font-size:14px;font-weight:700;border-radius:10px;padding:5px 11px;min-width:46px;text-align:center; }
    .d-sys-name { font-family:'Orbitron',monospace;font-size:13px;color:rgba(200,225,255,0.95);font-weight:600;flex:1; }
    .d-dist { font-size:12px;color:rgba(140,170,220,0.5); }
    .d-card-body { padding:12px 16px; }
    .d-tags { display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px; }
    .d-tag { font-size:11px;padding:3px 10px;border-radius:20px; }
    .d-tag-blue { background:rgba(80,140,255,0.12);border:1px solid rgba(80,140,255,0.3);color:#78b4ff; }
    .d-tag-purple { background:rgba(160,100,255,0.12);border:1px solid rgba(160,100,255,0.3);color:#b899ff; }
    .d-tag-cyan { background:rgba(34,211,238,0.1);border:1px solid rgba(34,211,238,0.25);color:#22d3ee; }
    .d-tag-green { background:rgba(52,211,153,0.1);border:1px solid rgba(52,211,153,0.25);color:#34d399; }
    .d-stat-row { display:flex;gap:20px;margin-top:8px; }
    .d-stat { display:flex;flex-direction:column;gap:2px; }
    .d-stat-lbl { font-size:10px;color:rgba(120,160,220,0.45);text-transform:uppercase;letter-spacing:1px; }
    .d-stat-val { font-size:13px;color:rgba(200,225,255,0.85);font-weight:600; }
    .d-card-footer { padding:10px 16px;border-top:1px solid rgba(100,160,255,0.07);display:flex;gap:8px;justify-content:flex-end; }
    .d-btn { font-size:11px;padding:6px 14px;border-radius:20px;border:1px solid rgba(100,160,255,0.15);background:rgba(80,120,255,0.06);color:rgba(180,210,255,0.65);cursor:pointer;font-family:'Rajdhani',sans-serif;font-weight:600; }
    .d-btn.primary { background:linear-gradient(135deg,rgba(80,120,255,0.25),rgba(120,80,255,0.25));border-color:rgba(100,160,255,0.4);color:#78b4ff; }
  `;

  const systems = [
    {name:'Colonia Gateway',rating:94,bg:'linear-gradient(135deg,#3a6fd8,#6b3ed8)',dist:'22,000 ly',tag1:'High Tech',tag2:'Industrial',pop:'2.1B',slots:7,bodies:23},
    {name:'Eravate',rating:88,bg:'linear-gradient(135deg,#1e88c9,#0e5a9a)',dist:'34.2 ly',tag1:'Agriculture',tag2:'Refinery',pop:'450M',slots:5,bodies:14},
    {name:'Lave',rating:81,bg:'linear-gradient(135deg,#1a8a6a,#136050)',dist:'108.5 ly',tag1:'Agriculture',tag2:'Tourism',pop:'1.2B',slots:6,bodies:18},
  ];

  return (
    <div className="d-root">
      <style dangerouslySetInnerHTML={{ __html: css }} />
      <div className="d-header">
        <div className="d-logo">🎯</div>
        <div>
          <div className="d-title">ED:FINDER</div>
          <div className="d-sub">Advanced System Finder & Optimizer</div>
        </div>
        <div className="d-spacer" />
        <span style={{fontSize:12,color:'rgba(140,170,220,0.4)',marginRight:8}}>· Never synced yet</span>
        <button className="d-syncbtn">⟳ SYNC NOW</button>
        <span className="d-badge">v3.90</span>
      </div>

      <div className="d-tabs">
        {['🎯 SYSTEM FINDER','⚙️ OPTIMIZER','📊 ECONOMY','📌 PINNED','⚖️ COMPARE','👁 WATCHLIST','🗺️ ROUTE','🛸 FC PLANNER','🌐 MAP','✨ 3D MAP'].map((t,i) => (
          <button key={i} className={`d-tab ${i===0?'active':''}`}>{t}</button>
        ))}
      </div>

      <div className="d-body">
        <div className="d-sidebar">
          <div className="d-panel">
            <div className="d-panel-hdr">
              <span className="d-panel-icon">📍</span>
              <span className="d-panel-title">Reference System</span>
              <span style={{fontSize:10,color:'rgba(120,160,220,0.4)'}}>▼</span>
            </div>
            <div className="d-panel-body">
              <label className="d-label">System Name</label>
              <input className="d-input" defaultValue="Sol" />
              <div style={{marginTop:8,padding:'7px 12px',background:'rgba(80,130,255,0.08)',borderRadius:10,border:'1px solid rgba(100,160,255,0.2)',fontSize:13,color:'#78b4ff',display:'flex',alignItems:'center',gap:8}}>
                <span>📍</span><span>Sol — 0, 0, 0</span>
              </div>
            </div>
          </div>

          <div className="d-panel">
            <div className="d-panel-hdr">
              <span className="d-panel-icon">📡</span>
              <span className="d-panel-title">Search Radius</span>
              <span style={{fontSize:10,color:'rgba(120,160,220,0.4)'}}>▼</span>
            </div>
            <div className="d-panel-body">
              {[['Max Distance (ly)',50],['Min Distance (ly)',0],['Results Per Page',50]].map(([lbl,val],i) => (
                <div key={i} style={{marginBottom:i<2?12:0}}>
                  <label className="d-label">{lbl}</label>
                  <div className="d-slider-row">
                    <input type="range" className="d-slider" defaultValue={val as number} style={{flex:1}} />
                    <span className="d-slider-val">{val}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="d-panel">
            <div className="d-panel-hdr">
              <span className="d-panel-icon">⭐</span>
              <span className="d-panel-title">Rating Filter</span>
              <span style={{fontSize:10,color:'rgba(120,160,220,0.4)'}}>▼</span>
            </div>
            <div className="d-panel-body">
              <label className="d-label">Minimum Rating</label>
              <div className="d-slider-row">
                <input type="range" className="d-slider" defaultValue={60} style={{flex:1}} />
                <span className="d-slider-val">60</span>
              </div>
            </div>
          </div>

          <button className="d-searchbtn">🔍 SEARCH SYSTEMS</button>
        </div>

        <div className="d-content">
          <div className="d-summary">
            <span>Found <strong>247 SYSTEMS</strong></span>
            <span>·</span><span>⏱ 843ms</span>
            <div style={{flex:1}} />
            <button className="d-btn">👁 Watch All</button>
            <button className="d-btn">📋 Copy Names</button>
          </div>

          {systems.map((sys,i) => (
            <div className="d-card" key={i}>
              <div className="d-card-hdr">
                <span className="d-rating" style={{background:sys.bg,boxShadow:'0 2px 12px rgba(80,100,255,0.4)'}}>{sys.rating}</span>
                <span className="d-sys-name">{sys.name}</span>
                <span className="d-dist">📡 {sys.dist}</span>
                <button style={{background:'none',border:'none',color:'rgba(120,160,220,0.4)',cursor:'pointer',fontSize:16}}>📌</button>
              </div>
              <div className="d-card-body">
                <div className="d-tags">
                  <span className="d-tag d-tag-blue">{sys.tag1}</span>
                  <span className="d-tag d-tag-purple">{sys.tag2}</span>
                  <span className="d-tag d-tag-cyan">⭐ Landable</span>
                  <span className="d-tag d-tag-green">💰 {sys.pop}</span>
                </div>
                <div className="d-stat-row">
                  <div className="d-stat"><span className="d-stat-lbl">Slots</span><span className="d-stat-val">{sys.slots}</span></div>
                  <div className="d-stat"><span className="d-stat-lbl">Bodies</span><span className="d-stat-val">{sys.bodies}</span></div>
                  <div className="d-stat"><span className="d-stat-lbl">Stars</span><span className="d-stat-val">F-class</span></div>
                  <div className="d-stat"><span className="d-stat-lbl">Security</span><span className="d-stat-val">High</span></div>
                </div>
              </div>
              <div className="d-card-footer">
                <button className="d-btn">👁 Watch</button>
                <button className="d-btn">⚖️ Compare</button>
                <button className="d-btn primary">📋 Briefing</button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
