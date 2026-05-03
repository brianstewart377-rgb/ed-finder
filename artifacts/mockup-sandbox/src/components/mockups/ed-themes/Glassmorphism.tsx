export function Glassmorphism() {
  const css = `
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;600;700&family=Rajdhani:wght@400;500;600&display=swap');
    .g-root { font-family:'Rajdhani',sans-serif; background:radial-gradient(ellipse at 20% 20%, #1a0a2e 0%, #060812 50%, #000508 100%); color:#e0eaff; min-height:100vh; display:flex; flex-direction:column; }
    .g-root::before { content:''; position:fixed; inset:0; background:url("data:image/svg+xml,%3Csvg width='100' height='100' xmlns='http://www.w3.org/2000/svg'%3E%3Ccircle cx='2' cy='2' r='1' fill='white' opacity='0.15'/%3E%3Ccircle cx='50' cy='30' r='0.8' fill='white' opacity='0.1'/%3E%3Ccircle cx='80' cy='70' r='1.2' fill='white' opacity='0.12'/%3E%3Ccircle cx='20' cy='80' r='0.6' fill='white' opacity='0.08'/%3E%3C/svg%3E"); pointer-events:none; z-index:0; }
    .g-header { background:rgba(255,255,255,0.04); backdrop-filter:blur(20px); -webkit-backdrop-filter:blur(20px); border-bottom:1px solid rgba(255,140,0,0.25); padding:14px 24px; display:flex; align-items:center; gap:16px; position:relative; z-index:10; box-shadow:0 4px 32px rgba(0,0,0,0.5); }
    .g-logo { width:42px;height:42px;border:1.5px solid rgba(255,140,0,0.7);border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:18px;color:#ff8c00;box-shadow:0 0 20px rgba(255,140,0,0.4),inset 0 0 20px rgba(255,140,0,0.05); }
    .g-title { font-family:'Orbitron',monospace;font-size:20px;font-weight:700;color:#fff;letter-spacing:2px;text-shadow:0 0 20px rgba(255,140,0,0.4); }
    .g-sub { font-size:10px;color:rgba(200,220,255,0.5);letter-spacing:3px;text-transform:uppercase; }
    .g-spacer { flex:1; }
    .g-badge { font-family:'Orbitron',monospace;font-size:10px;color:#ff8c00;border:1px solid rgba(255,140,0,0.4);border-radius:6px;padding:4px 10px;background:rgba(255,140,0,0.08);backdrop-filter:blur(8px); }
    .g-syncbtn { background:linear-gradient(135deg,rgba(255,140,0,0.8),rgba(200,80,0,0.8));color:#fff;border:1px solid rgba(255,140,0,0.5);border-radius:10px;padding:8px 18px;font-family:'Orbitron',monospace;font-size:10px;font-weight:600;letter-spacing:1px;cursor:pointer;backdrop-filter:blur(8px);box-shadow:0 2px 16px rgba(255,140,0,0.3); }
    .g-tabs { background:rgba(255,255,255,0.025); backdrop-filter:blur(12px); border-bottom:1px solid rgba(255,255,255,0.06); padding:0 20px; display:flex; gap:2px; overflow-x:auto; position:relative; z-index:10; }
    .g-tab { font-family:'Orbitron',monospace;font-size:10px;letter-spacing:1px;text-transform:uppercase;padding:13px 16px;background:none;border:none;border-bottom:2px solid transparent;color:rgba(180,200,255,0.45);cursor:pointer;white-space:nowrap;transition:all 0.2s; }
    .g-tab.active { color:#ff8c00;border-bottom-color:#ff8c00;text-shadow:0 0 10px rgba(255,140,0,0.6); }
    .g-tab:hover:not(.active) { color:rgba(220,235,255,0.8); }
    .g-body { display:flex;flex:1;min-height:0;position:relative;z-index:1; }
    .g-sidebar { width:300px;background:rgba(255,255,255,0.03);backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);border-right:1px solid rgba(255,255,255,0.07);padding:18px 14px;overflow-y:auto;display:flex;flex-direction:column;gap:14px; }
    .g-panel { background:rgba(255,255,255,0.04);backdrop-filter:blur(12px);border:1px solid rgba(255,255,255,0.09);border-radius:16px;overflow:hidden; }
    .g-panel-hdr { background:rgba(255,255,255,0.04);border-bottom:1px solid rgba(255,255,255,0.06);padding:10px 14px;display:flex;align-items:center;gap:8px; }
    .g-panel-icon { color:#ff8c00;font-size:14px;filter:drop-shadow(0 0 6px rgba(255,140,0,0.6)); }
    .g-panel-title { font-family:'Orbitron',monospace;font-size:10px;font-weight:600;letter-spacing:1.5px;text-transform:uppercase;color:rgba(220,235,255,0.9);flex:1; }
    .g-panel-body { padding:14px; }
    .g-label { font-size:11px;font-weight:600;color:rgba(180,200,255,0.5);letter-spacing:1px;text-transform:uppercase;margin-bottom:6px;display:block; }
    .g-input { width:100%;background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);border-radius:10px;color:#e0eaff;font-family:'Rajdhani',sans-serif;font-size:14px;padding:9px 12px;outline:none;backdrop-filter:blur(8px); }
    .g-input:focus { border-color:rgba(255,140,0,0.5);box-shadow:0 0 12px rgba(255,140,0,0.15); }
    .g-slider { width:100%;accent-color:#ff8c00;margin-top:6px; }
    .g-slider-row { display:flex;align-items:center;gap:10px; }
    .g-slider-val { font-family:'Orbitron',monospace;font-size:12px;color:#ff8c00;min-width:32px;text-align:right;text-shadow:0 0 8px rgba(255,140,0,0.5); }
    .g-searchbtn { width:100%;background:linear-gradient(135deg,rgba(255,140,0,0.75),rgba(200,80,0,0.75));color:#fff;border:1px solid rgba(255,140,0,0.5);border-radius:12px;padding:12px;font-family:'Orbitron',monospace;font-size:11px;font-weight:700;letter-spacing:1.5px;cursor:pointer;margin-top:8px;backdrop-filter:blur(8px);box-shadow:0 4px 24px rgba(255,140,0,0.25); }
    .g-content { flex:1;padding:20px;overflow-y:auto;display:flex;flex-direction:column;gap:12px; }
    .g-summary { display:flex;align-items:center;gap:12px;padding:10px 16px;background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.08);border-radius:12px;font-size:13px;color:rgba(180,200,255,0.6);backdrop-filter:blur(8px); }
    .g-summary strong { color:#ff8c00;font-family:'Orbitron',monospace;font-size:12px;text-shadow:0 0 8px rgba(255,140,0,0.5); }
    .g-card { background:rgba(255,255,255,0.04);backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);border:1px solid rgba(255,255,255,0.08);border-radius:18px;overflow:hidden;transition:all 0.2s; }
    .g-card:hover { transform:translateY(-4px);background:rgba(255,255,255,0.06);border-color:rgba(255,140,0,0.3);box-shadow:0 12px 40px rgba(255,140,0,0.1),0 4px 12px rgba(0,0,0,0.5); }
    .g-card-hdr { padding:12px 16px;display:flex;align-items:center;gap:10px;border-bottom:1px solid rgba(255,255,255,0.06); }
    .g-rating { color:#fff;font-family:'Orbitron',monospace;font-size:14px;font-weight:700;border-radius:10px;padding:5px 11px;border:1px solid;min-width:46px;text-align:center; }
    .g-sys-name { font-family:'Orbitron',monospace;font-size:13px;color:rgba(225,235,255,0.95);font-weight:600;flex:1; }
    .g-dist { font-size:12px;color:rgba(180,200,255,0.5); }
    .g-card-body { padding:12px 16px; }
    .g-tags { display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px; }
    .g-tag { font-size:11px;padding:3px 10px;border-radius:20px;background:rgba(255,255,255,0.06);border:1px solid rgba(255,255,255,0.12);color:rgba(200,220,255,0.7); }
    .g-tag.orange { background:rgba(255,140,0,0.1);border-color:rgba(255,140,0,0.3);color:#ff9933; }
    .g-tag.green { background:rgba(61,220,132,0.1);border-color:rgba(61,220,132,0.25);color:#3ddc84; }
    .g-stat-row { display:flex;gap:20px;margin-top:8px; }
    .g-stat { display:flex;flex-direction:column;gap:2px; }
    .g-stat-lbl { font-size:10px;color:rgba(160,180,220,0.5);text-transform:uppercase;letter-spacing:1px; }
    .g-stat-val { font-size:13px;color:rgba(220,235,255,0.85);font-weight:600; }
    .g-card-footer { padding:10px 16px;border-top:1px solid rgba(255,255,255,0.06);display:flex;gap:8px;justify-content:flex-end; }
    .g-btn { font-size:11px;padding:6px 14px;border-radius:10px;border:1px solid rgba(255,255,255,0.1);background:rgba(255,255,255,0.05);color:rgba(200,220,255,0.7);cursor:pointer;font-family:'Rajdhani',sans-serif;font-weight:600;backdrop-filter:blur(8px); }
    .g-btn.primary { background:rgba(255,140,0,0.12);border-color:rgba(255,140,0,0.35);color:#ff9933; }
  `;

  const systems = [
    {name:'Colonia Gateway',rating:94,ratingColor:'rgba(255,140,0,0.8)',borderColor:'rgba(255,140,0,0.5)',dist:'22,000 ly',tags:['High Tech','Industrial'],pop:'2.1B',slots:7,bodies:23},
    {name:'Eravate',rating:88,ratingColor:'rgba(255,215,0,0.8)',borderColor:'rgba(255,215,0,0.5)',dist:'34.2 ly',tags:['Agriculture','Refinery'],pop:'450M',slots:5,bodies:14},
    {name:'Lave',rating:81,ratingColor:'rgba(61,220,132,0.8)',borderColor:'rgba(61,220,132,0.5)',dist:'108.5 ly',tags:['Agriculture'],pop:'1.2B',slots:6,bodies:18},
  ];

  return (
    <div className="g-root">
      <style dangerouslySetInnerHTML={{ __html: css }} />
      <div className="g-header">
        <div className="g-logo">🎯</div>
        <div>
          <div className="g-title">ED:FINDER</div>
          <div className="g-sub">Advanced System Finder & Optimizer</div>
        </div>
        <div className="g-spacer" />
        <span style={{fontSize:12,color:'rgba(180,200,255,0.45)',marginRight:8}}>· Never synced yet</span>
        <button className="g-syncbtn">⟳ SYNC NOW</button>
        <span className="g-badge">v3.90</span>
      </div>

      <div className="g-tabs">
        {['🎯 SYSTEM FINDER','⚙️ OPTIMIZER','📊 ECONOMY','📌 PINNED','⚖️ COMPARE','👁 WATCHLIST','🗺️ ROUTE','🛸 FC PLANNER','🌐 MAP','✨ 3D MAP'].map((t,i) => (
          <button key={i} className={`g-tab ${i===0?'active':''}`}>{t}</button>
        ))}
      </div>

      <div className="g-body">
        <div className="g-sidebar">
          {[
            {icon:'📍',title:'Reference System', children: (
              <div>
                <label className="g-label">System Name</label>
                <input className="g-input" defaultValue="Sol" />
                <div style={{marginTop:8,padding:'7px 11px',background:'rgba(255,140,0,0.07)',borderRadius:10,border:'1px solid rgba(255,140,0,0.2)',fontSize:13,color:'#ff9933',display:'flex',alignItems:'center',gap:8}}>
                  <span>📍</span><span>Sol — 0, 0, 0</span>
                </div>
              </div>
            )},
            {icon:'📡',title:'Search Radius', children: (
              <div>
                {[['Max Distance (ly)',50],['Min Distance (ly)',0],['Results Per Page',50]].map(([lbl,val],i) => (
                  <div key={i} style={{marginBottom:i<2?12:0}}>
                    <label className="g-label">{lbl}</label>
                    <div className="g-slider-row">
                      <input type="range" className="g-slider" defaultValue={val as number} style={{flex:1}} />
                      <span className="g-slider-val">{val}</span>
                    </div>
                  </div>
                ))}
              </div>
            )},
          ].map((p,i) => (
            <div className="g-panel" key={i}>
              <div className="g-panel-hdr">
                <span className="g-panel-icon">{p.icon}</span>
                <span className="g-panel-title">{p.title}</span>
                <span style={{fontSize:10,color:'rgba(180,200,255,0.35)'}}>▼</span>
              </div>
              <div className="g-panel-body">{p.children}</div>
            </div>
          ))}
          <button className="g-searchbtn">🔍 SEARCH SYSTEMS</button>
        </div>

        <div className="g-content">
          <div className="g-summary">
            <span>Found <strong>247 SYSTEMS</strong></span>
            <span>·</span><span>⏱ 843ms</span>
            <div style={{flex:1}} />
            <button className="g-btn">👁 Watch All</button>
            <button className="g-btn">📋 Copy Names</button>
          </div>

          {systems.map((sys,i) => (
            <div className="g-card" key={i}>
              <div className="g-card-hdr">
                <span className="g-rating" style={{background:sys.ratingColor,borderColor:sys.borderColor,boxShadow:`0 0 16px ${sys.ratingColor}88`}}>{sys.rating}</span>
                <span className="g-sys-name">{sys.name}</span>
                <span className="g-dist">📡 {sys.dist}</span>
                <button style={{background:'none',border:'none',color:'rgba(180,200,255,0.4)',cursor:'pointer',fontSize:16}}>📌</button>
              </div>
              <div className="g-card-body">
                <div className="g-tags">
                  {sys.tags.map((t,j) => <span key={j} className={`g-tag ${j===0?'orange':''}`}>{t}</span>)}
                  <span className="g-tag green">⭐ Landable</span>
                  <span className="g-tag">💰 {sys.pop}</span>
                </div>
                <div className="g-stat-row">
                  <div className="g-stat"><span className="g-stat-lbl">Slots</span><span className="g-stat-val">{sys.slots}</span></div>
                  <div className="g-stat"><span className="g-stat-lbl">Bodies</span><span className="g-stat-val">{sys.bodies}</span></div>
                  <div className="g-stat"><span className="g-stat-lbl">Stars</span><span className="g-stat-val">F-class</span></div>
                  <div className="g-stat"><span className="g-stat-lbl">Security</span><span className="g-stat-val">High</span></div>
                </div>
              </div>
              <div className="g-card-footer">
                <button className="g-btn">👁 Watch</button>
                <button className="g-btn">⚖️ Compare</button>
                <button className="g-btn primary">📋 Briefing</button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
