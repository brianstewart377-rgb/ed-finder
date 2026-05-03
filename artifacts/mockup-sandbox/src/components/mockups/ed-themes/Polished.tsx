export function Polished() {
  const css = `
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;600;700&family=Rajdhani:wght@400;500;600&display=swap');
    .p-root { font-family:'Rajdhani',sans-serif; background:#0a0c0f; color:#d0d8e8; min-height:100vh; display:flex; flex-direction:column; }
    .p-header { background:linear-gradient(135deg,#0d1117 0%,#1e0e02 50%,#0d1117 100%); border-bottom:1px solid rgba(255,106,0,0.3); padding:14px 24px; display:flex; align-items:center; gap:16px; box-shadow:0 4px 32px rgba(255,106,0,0.15); }
    .p-logo { width:42px;height:42px;border:2px solid #ff6a00;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:18px;color:#ff6a00;box-shadow:0 0 18px rgba(255,106,0,0.45); }
    .p-title { font-family:'Orbitron',monospace;font-size:20px;font-weight:700;color:#fff;letter-spacing:2px; }
    .p-sub { font-size:10px;color:#7a8fa0;letter-spacing:3px;text-transform:uppercase; }
    .p-spacer { flex:1; }
    .p-badge { font-family:'Orbitron',monospace;font-size:10px;color:#ff6a00;border:1px solid rgba(255,106,0,0.5);border-radius:6px;padding:4px 10px;background:rgba(255,106,0,0.08); }
    .p-syncbtn { background:linear-gradient(135deg,#ff6a00,#c44d00);color:#fff;border:none;border-radius:8px;padding:8px 18px;font-family:'Orbitron',monospace;font-size:10px;font-weight:600;letter-spacing:1px;cursor:pointer;box-shadow:0 2px 12px rgba(255,106,0,0.4); }
    .p-tabs { background:#111418;border-bottom:1px solid #1e2530;padding:0 20px;display:flex;gap:2px;overflow-x:auto; }
    .p-tab { font-family:'Orbitron',monospace;font-size:10px;letter-spacing:1px;text-transform:uppercase;padding:13px 18px;background:none;border:none;border-bottom:3px solid transparent;color:#7a8fa0;cursor:pointer;white-space:nowrap; }
    .p-tab.active { color:#ff6a00;border-bottom-color:#ff6a00;background:linear-gradient(180deg,rgba(255,106,0,0.05) 0%,transparent 100%); }
    .p-tab:hover:not(.active) { color:#d0d8e8;border-bottom-color:#2a3040; }
    .p-body { display:flex;flex:1;min-height:0; }
    .p-sidebar { width:300px;background:#111418;border-right:1px solid #1e2530;padding:18px 14px;overflow-y:auto;display:flex;flex-direction:column;gap:14px; }
    .p-panel { background:#181c22;border:1px solid #1e2530;border-radius:12px;overflow:hidden;box-shadow:0 2px 8px rgba(0,0,0,0.3); }
    .p-panel-hdr { background:linear-gradient(90deg,#20262e 0%,#181c22 100%);border-bottom:1px solid #1e2530;padding:10px 14px;display:flex;align-items:center;gap:8px;border-radius:12px 12px 0 0; }
    .p-panel-icon { color:#ff6a00;font-size:14px; }
    .p-panel-title { font-family:'Orbitron',monospace;font-size:10px;font-weight:600;letter-spacing:1.5px;text-transform:uppercase;color:#fff;flex:1; }
    .p-panel-body { padding:14px; }
    .p-label { font-size:11px;font-weight:600;color:#7a8fa0;letter-spacing:1px;text-transform:uppercase;margin-bottom:6px;display:block; }
    .p-input { width:100%;background:#0d1117;border:1px solid #1e2530;border-radius:8px;color:#d0d8e8;font-family:'Rajdhani',sans-serif;font-size:14px;padding:9px 12px;outline:none; }
    .p-slider-row { display:flex;align-items:center;gap:10px;margin-top:6px; }
    .p-slider { flex:1;accent-color:#ff6a00; }
    .p-slider-val { font-family:'Orbitron',monospace;font-size:12px;color:#ff6a00;min-width:32px;text-align:right; }
    .p-searchbtn { width:100%;background:linear-gradient(135deg,#ff6a00,#c44d00);color:#fff;border:none;border-radius:10px;padding:12px;font-family:'Orbitron',monospace;font-size:11px;font-weight:700;letter-spacing:1.5px;cursor:pointer;margin-top:8px;box-shadow:0 4px 18px rgba(255,106,0,0.35);transition:transform 0.15s; }
    .p-content { flex:1;padding:20px;overflow-y:auto;display:flex;flex-direction:column;gap:12px; }
    .p-summary { display:flex;align-items:center;gap:12px;padding:10px 16px;background:#111418;border:1px solid #1e2530;border-radius:10px;font-size:13px;color:#7a8fa0; }
    .p-summary strong { color:#ff6a00;font-family:'Orbitron',monospace;font-size:12px; }
    .p-card { background:#111418;border:1px solid #1e2530;border-radius:14px;overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.4);transition:transform 0.2s,box-shadow 0.2s; }
    .p-card:hover { transform:translateY(-3px);box-shadow:0 8px 28px rgba(255,106,0,0.15),0 2px 8px rgba(0,0,0,0.5);border-color:rgba(255,106,0,0.3); }
    .p-card-hdr { padding:12px 16px;display:flex;align-items:center;gap:10px;border-bottom:1px solid #1e2530; }
    .p-rating { background:linear-gradient(135deg,#ff6a00,#ff9133);color:#fff;font-family:'Orbitron',monospace;font-size:14px;font-weight:700;border-radius:8px;padding:4px 10px; }
    .p-sys-name { font-family:'Orbitron',monospace;font-size:13px;color:#fff;font-weight:600;flex:1; }
    .p-dist { font-size:12px;color:#7a8fa0; }
    .p-card-body { padding:12px 16px; }
    .p-tags { display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px; }
    .p-tag { font-size:11px;padding:3px 9px;border-radius:20px;background:rgba(255,106,0,0.1);border:1px solid rgba(255,106,0,0.25);color:#ff9133; }
    .p-tag.blue { background:rgba(77,166,255,0.1);border-color:rgba(77,166,255,0.25);color:#4da6ff; }
    .p-tag.green { background:rgba(61,220,132,0.1);border-color:rgba(61,220,132,0.25);color:#3ddc84; }
    .p-stat-row { display:flex;gap:16px;margin-top:8px; }
    .p-stat { display:flex;flex-direction:column;gap:2px; }
    .p-stat-lbl { font-size:10px;color:#7a8fa0;text-transform:uppercase;letter-spacing:1px; }
    .p-stat-val { font-size:13px;color:#d0d8e8;font-weight:600; }
    .p-card-footer { padding:10px 16px;border-top:1px solid #1e2530;display:flex;gap:8px;justify-content:flex-end; }
    .p-btn { font-size:11px;padding:6px 14px;border-radius:8px;border:1px solid #1e2530;background:#181c22;color:#d0d8e8;cursor:pointer;font-family:'Rajdhani',sans-serif;font-weight:600;letter-spacing:0.5px; }
    .p-btn.primary { background:rgba(255,106,0,0.15);border-color:rgba(255,106,0,0.4);color:#ff9133; }
  `;
  return (
    <div className="p-root">
      <style dangerouslySetInnerHTML={{ __html: css }} />
      <div className="p-header">
        <div className="p-logo">🎯</div>
        <div>
          <div className="p-title">ED:FINDER</div>
          <div className="p-sub">Advanced System Finder & Optimizer</div>
        </div>
        <div className="p-spacer" />
        <span style={{fontSize:12,color:'#9baabb',marginRight:8}}>· Never synced yet</span>
        <button className="p-syncbtn">⟳ SYNC NOW</button>
        <span className="p-badge">v3.90</span>
      </div>

      <div className="p-tabs">
        {['🎯 SYSTEM FINDER','⚙️ OPTIMIZER','📊 ECONOMY','📌 PINNED','⚖️ COMPARE','👁 WATCHLIST','🗺️ ROUTE','🛸 FC PLANNER','🌐 MAP','✨ 3D MAP','🏗️ COLONIES'].map((t,i) => (
          <button key={i} className={`p-tab ${i===0?'active':''}`}>{t}</button>
        ))}
      </div>

      <div className="p-body">
        <div className="p-sidebar">
          <div className="p-panel">
            <div className="p-panel-hdr">
              <span className="p-panel-icon">📍</span>
              <span className="p-panel-title">Reference System</span>
              <span style={{fontSize:10,color:'#7a8fa0'}}>▼</span>
            </div>
            <div className="p-panel-body">
              <label className="p-label">System Name</label>
              <input className="p-input" defaultValue="Sol" />
              <div style={{marginTop:8,padding:'6px 10px',background:'rgba(255,106,0,0.06)',borderRadius:8,border:'1px solid rgba(255,106,0,0.2)',fontSize:13,color:'#ff9133',display:'flex',alignItems:'center',gap:8}}>
                <span>📍</span> <span>Sol — 0, 0, 0</span>
              </div>
            </div>
          </div>

          <div className="p-panel">
            <div className="p-panel-hdr">
              <span className="p-panel-icon">📡</span>
              <span className="p-panel-title">Search Radius</span>
              <span style={{fontSize:10,color:'#7a8fa0'}}>▼</span>
            </div>
            <div className="p-panel-body">
              <label className="p-label">Max Distance (ly)</label>
              <div className="p-slider-row">
                <input type="range" className="p-slider" min={10} max={500} defaultValue={50} />
                <span className="p-slider-val">50</span>
              </div>
              <label className="p-label" style={{marginTop:12}}>Min Distance (ly)</label>
              <div className="p-slider-row">
                <input type="range" className="p-slider" min={0} max={50} defaultValue={0} />
                <span className="p-slider-val">0</span>
              </div>
              <label className="p-label" style={{marginTop:12}}>Results Per Page</label>
              <div className="p-slider-row">
                <input type="range" className="p-slider" min={10} max={100} defaultValue={50} />
                <span className="p-slider-val">50</span>
              </div>
            </div>
          </div>

          <div className="p-panel">
            <div className="p-panel-hdr">
              <span className="p-panel-icon">⭐</span>
              <span className="p-panel-title">Rating Filter</span>
              <span style={{fontSize:10,color:'#7a8fa0'}}>▼</span>
            </div>
            <div className="p-panel-body">
              <label className="p-label">Minimum Rating</label>
              <div className="p-slider-row">
                <input type="range" className="p-slider" min={0} max={100} defaultValue={60} />
                <span className="p-slider-val">60</span>
              </div>
            </div>
          </div>

          <button className="p-searchbtn">🔍 SEARCH SYSTEMS</button>
        </div>

        <div className="p-content">
          <div className="p-summary">
            <span>Found <strong>247 SYSTEMS</strong></span>
            <span>·</span>
            <span>⏱ 843ms</span>
            <div style={{flex:1}} />
            <button className="p-btn">👁 Watch All</button>
            <button className="p-btn">📋 Copy Names</button>
          </div>

          {[
            {name:'Colonia Gateway',rating:94,dist:'22,000.4 ly',tags:['High Tech','Industrial'],color:'#ff6a00',pop:'2.1B',slots:7,bodies:23},
            {name:'Eravate',rating:88,dist:'34.2 ly',tags:['Agriculture','Refinery'],color:'#ffd700',pop:'450M',slots:5,bodies:14},
            {name:'Lave',rating:81,dist:'108.5 ly',tags:['Agriculture'],color:'#3ddc84',pop:'1.2B',slots:6,bodies:18},
          ].map((sys,i) => (
            <div className="p-card" key={i}>
              <div className="p-card-hdr">
                <span className="p-rating" style={{background:`linear-gradient(135deg,${sys.color},${sys.color}aa)`}}>{sys.rating}</span>
                <span className="p-sys-name">{sys.name}</span>
                <span className="p-dist">📡 {sys.dist}</span>
                <button style={{background:'none',border:'none',color:'#7a8fa0',cursor:'pointer',fontSize:16}}>📌</button>
              </div>
              <div className="p-card-body">
                <div className="p-tags">
                  {sys.tags.map((t,j) => <span key={j} className={`p-tag ${j===1?'blue':j===2?'green':''}`}>{t}</span>)}
                  <span className="p-tag green">⭐ Landable</span>
                  <span className="p-tag">💰 {sys.pop}</span>
                </div>
                <div className="p-stat-row">
                  <div className="p-stat"><span className="p-stat-lbl">Slots</span><span className="p-stat-val">{sys.slots}</span></div>
                  <div className="p-stat"><span className="p-stat-lbl">Bodies</span><span className="p-stat-val">{sys.bodies}</span></div>
                  <div className="p-stat"><span className="p-stat-lbl">Stars</span><span className="p-stat-val">F-class</span></div>
                  <div className="p-stat"><span className="p-stat-lbl">Security</span><span className="p-stat-val">High</span></div>
                </div>
              </div>
              <div className="p-card-footer">
                <button className="p-btn">👁 Watch</button>
                <button className="p-btn">⚖️ Compare</button>
                <button className="p-btn primary">📋 Briefing</button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
