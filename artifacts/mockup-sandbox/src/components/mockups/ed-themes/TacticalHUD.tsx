export function TacticalHUD() {
  const css = `
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;600;700&family=Rajdhani:wght@400;500;600&display=swap');

    .th-root {
      font-family: 'Rajdhani', sans-serif;
      background: #080b06;
      color: #c8c8a0;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
    }
    /* subtle hex grid bg */
    .th-root::before {
      content:'';
      position:fixed; inset:0; pointer-events:none; z-index:0;
      background-image:
        linear-gradient(rgba(120,140,60,0.04) 1px, transparent 1px),
        linear-gradient(90deg, rgba(120,140,60,0.04) 1px, transparent 1px);
      background-size: 32px 32px;
    }

    .th-header {
      background: #0c1008;
      border-bottom: 2px solid #4a6020;
      padding: 12px 24px; display: flex; align-items: center; gap: 16px;
      position: relative; z-index: 10;
      box-shadow: 0 4px 24px rgba(80,120,20,0.18);
    }
    .th-logo {
      width: 42px; height: 42px; border: 2px solid #6a8030; background: #111808;
      display: flex; align-items: center; justify-content: center;
      font-size: 18px; color: #a0c040;
      clip-path: polygon(50% 0%, 100% 25%, 100% 75%, 50% 100%, 0% 75%, 0% 25%);
      box-shadow: 0 0 16px rgba(100,160,30,0.3);
    }
    .th-title { font-family:'Orbitron',monospace; font-size:20px; font-weight:700; color:#c8e040; letter-spacing:3px; text-shadow:0 0 10px rgba(180,220,40,0.4); }
    .th-sub { font-size:10px; color:#405020; letter-spacing:3px; text-transform:uppercase; }
    .th-spacer { flex:1; }
    /* corner brackets decoration */
    .th-brackets {
      position:relative; padding: 4px 10px;
      font-family:'Orbitron',monospace; font-size:10px; color:#6a8030; letter-spacing:1px;
    }
    .th-brackets::before, .th-brackets::after {
      content:''; position:absolute; width:8px; height:8px;
    }
    .th-brackets::before { top:0; left:0; border-top:2px solid #6a8030; border-left:2px solid #6a8030; }
    .th-brackets::after { bottom:0; right:0; border-bottom:2px solid #6a8030; border-right:2px solid #6a8030; }
    .th-status { display:flex; align-items:center; gap:6px; font-size:11px; color:#506030; margin-right:8px; }
    .th-status-dot { width:7px; height:7px; background:#6a8030; border-radius:50%; box-shadow:0 0 6px rgba(100,160,30,0.6); }
    .th-syncbtn {
      background:#0c1808; color:#a0c040; border:2px solid #4a6020; padding:7px 16px;
      font-family:'Orbitron',monospace; font-size:10px; font-weight:600; letter-spacing:1px;
      cursor:pointer; text-transform:uppercase;
      clip-path: polygon(8px 0%, 100% 0%, calc(100% - 8px) 100%, 0% 100%);
    }
    .th-syncbtn:hover { background:#152200; border-color:#7a9a30; }

    .th-tabs {
      background:#0a0d07; border-bottom:1px solid #2a3a10; padding:0 20px;
      display:flex; gap:0; overflow-x:auto; position:relative; z-index:10;
    }
    .th-tab {
      font-family:'Orbitron',monospace; font-size:10px; letter-spacing:1px; text-transform:uppercase;
      padding:12px 14px; background:none; border:none; border-bottom:2px solid transparent;
      color:#304020; cursor:pointer; white-space:nowrap; transition:all 0.2s;
    }
    .th-tab.active { color:#c8e040; border-bottom-color:#8aaa30; background:#0f1a08; text-shadow:0 0 8px rgba(180,220,40,0.4); }
    .th-tab:hover:not(.active) { color:#809040; }

    .th-body { display:flex; flex:1; min-height:0; position:relative; z-index:1; }

    .th-sidebar {
      width:300px; background:#080b06; border-right:2px solid #2a3a10;
      padding:16px 14px; overflow-y:auto; display:flex; flex-direction:column; gap:12px;
    }
    .th-panel { border:1px solid #2a3a10; background:#0a0d07; }
    .th-panel-hdr {
      background:#0e1608; border-bottom:1px solid #2a3a10;
      padding:9px 12px; display:flex; align-items:center; gap:8px;
    }
    .th-panel-icon { color:#7aaa30; font-size:13px; }
    .th-panel-title { font-family:'Orbitron',monospace; font-size:10px; font-weight:600; letter-spacing:1.5px; text-transform:uppercase; color:#a0c040; flex:1; }
    .th-panel-body { padding:12px; }
    .th-label { font-size:10px; font-weight:600; color:#405020; letter-spacing:1px; text-transform:uppercase; margin-bottom:5px; display:block; }
    .th-input {
      width:100%; background:#080b06; border:1px solid #2a3a10;
      color:#c8c8a0; font-family:'Rajdhani',sans-serif; font-size:14px;
      padding:8px 10px; outline:none;
    }
    .th-input:focus { border-color:#6a8030; }
    .th-slider-row { display:flex; align-items:center; gap:10px; margin-top:5px; }
    .th-slider { flex:1; accent-color:#8aaa30; }
    .th-slider-val { font-family:'Orbitron',monospace; font-size:12px; color:#a0c040; min-width:32px; text-align:right; }
    .th-searchbtn {
      width:100%; background:#0e1e08; color:#c8e040; border:2px solid #5a7820; padding:11px;
      font-family:'Orbitron',monospace; font-size:11px; font-weight:700; letter-spacing:2px;
      cursor:pointer; text-transform:uppercase; clip-path:polygon(6px 0%,100% 0%,calc(100% - 6px) 100%,0% 100%);
      margin-top:4px;
    }
    .th-searchbtn:hover { background:#162e08; border-color:#8aaa30; }

    .th-content { flex:1; padding:16px; overflow-y:auto; display:flex; flex-direction:column; gap:10px; }
    .th-summary {
      display:flex; align-items:center; gap:12px; padding:8px 14px;
      background:#0a0d07; border:1px solid #2a3a10; border-left:3px solid #6a8030;
      font-size:13px; color:#506030;
    }
    .th-summary strong { color:#c8e040; font-family:'Orbitron',monospace; font-size:12px; }

    /* horizontal scan line on card hover */
    .th-card { border:1px solid #2a3a10; background:#0a0d07; position:relative; overflow:hidden; transition:all 0.18s; }
    .th-card::before { content:''; position:absolute; left:0; right:0; height:1px; background:rgba(180,220,40,0); top:50%; transition:all 0.18s; }
    .th-card:hover { border-color:#5a7a20; background:#0c1108; box-shadow:0 0 20px rgba(100,160,30,0.10); }
    .th-card:hover::before { background:rgba(180,220,40,0.05); }

    .th-card-hdr { padding:10px 14px; display:flex; align-items:center; gap:10px; border-bottom:1px solid #222e0c; }
    /* corner markers on card header */
    .th-corner-tl, .th-corner-br {
      position:absolute; width:10px; height:10px;
    }
    .th-corner-tl { top:0; left:0; border-top:2px solid #5a7820; border-left:2px solid #5a7820; }
    .th-corner-br { bottom:0; right:0; border-bottom:2px solid #5a7820; border-right:2px solid #5a7820; }
    .th-rating-wrap { display:flex; flex-direction:column; align-items:center; flex-shrink:0; }
    .th-rating {
      color:#fff; font-family:'Orbitron',monospace; font-size:13px; font-weight:700;
      padding:4px 10px; min-width:44px; text-align:center;
      clip-path:polygon(4px 0%,100% 0%,calc(100% - 4px) 100%,0% 100%);
    }
    .th-eco-lbl { font-size:8px; color:#405020; text-transform:uppercase; margin-top:3px; letter-spacing:0.5px; font-family:'Orbitron',monospace; }
    .th-sys-name { font-family:'Orbitron',monospace; font-size:13px; color:#c8c8a0; font-weight:600; flex:1; }
    .th-dist { font-size:11px; color:#405020; }
    .th-card-body { padding:10px 14px; }
    .th-tags { display:flex; flex-wrap:wrap; gap:5px; margin-bottom:8px; }
    .th-tag {
      font-size:11px; padding:2px 10px;
      background:#0a0d07; border:1px solid #2a3a10; color:#708040;
      clip-path:polygon(4px 0%,100% 0%,calc(100% - 4px) 100%,0% 100%);
    }
    .th-tag.amber { border-color:#604020; color:#c8a040; }
    .th-tag.red   { border-color:#602020; color:#c84040; }
    .th-stat-row { display:flex; gap:18px; margin-top:6px; }
    .th-stat { display:flex; flex-direction:column; gap:1px; }
    .th-stat-lbl { font-size:9px; color:#304020; text-transform:uppercase; letter-spacing:1px; }
    .th-stat-val { font-size:13px; color:#a0b060; font-weight:600; }
    .th-card-footer { padding:8px 14px; border-top:1px solid #222e0c; display:flex; gap:6px; justify-content:flex-end; }
    .th-btn {
      font-size:11px; padding:5px 14px; border:1px solid #2a3a10; background:#080b06;
      color:#506030; cursor:pointer; font-family:'Rajdhani',sans-serif; font-weight:600; transition:all 0.12s;
      clip-path:polygon(4px 0%,100% 0%,calc(100% - 4px) 100%,0% 100%);
    }
    .th-btn:hover { border-color:#6a8030; color:#90b040; }
    .th-btn.primary { border-color:#5a7820; color:#a0c040; background:#0c1608; }
  `;

  const ECO: Record<string,{bg:string;glow:string}> = {
    'High Tech':   { bg:'linear-gradient(135deg,#0a6090,#0e9acc)', glow:'rgba(0,150,200,0.5)' },
    'Industrial':  { bg:'linear-gradient(135deg,#804010,#c07018)', glow:'rgba(180,110,0,0.5)'  },
    'Agriculture': { bg:'linear-gradient(135deg,#205a20,#3a9a40)', glow:'rgba(40,160,60,0.5)'  },
    'Military':    { bg:'linear-gradient(135deg,#6a1010,#b03030)', glow:'rgba(180,30,30,0.5)'  },
  };

  const systems = [
    { name:'Colonia Gateway', rating:94, economy:'High Tech',   dist:'22,000 ly', tags:['High Tech','Industrial'],  tc:['','amber'], pop:'2.1B', slots:7, bodies:23, star:'F', sec:'HIGH'   },
    { name:'Eravate',         rating:88, economy:'Industrial',  dist:'34.2 ly',   tags:['Industrial','Refinery'],   tc:['amber','amber'], pop:'450M', slots:5, bodies:14, star:'G', sec:'MED'  },
    { name:'Lave',            rating:81, economy:'Agriculture', dist:'108.5 ly',  tags:['Agriculture','Tourism'],   tc:['',''],      pop:'1.2B', slots:6, bodies:18, star:'K', sec:'HIGH'  },
    { name:'Alioth',          rating:76, economy:'Military',    dist:'82.6 ly',   tags:['Military','Service'],      tc:['red',''],   pop:'8.4B', slots:4, bodies:11, star:'A', sec:'HIGH'  },
  ];

  return (
    <div className="th-root">
      <style dangerouslySetInnerHTML={{ __html: css }} />
      <div className="th-header">
        <div className="th-logo">◈</div>
        <div><div className="th-title">ED:FINDER</div><div className="th-sub">Advanced System Finder &amp; Optimizer</div></div>
        <div className="th-spacer" />
        <div className="th-status"><span className="th-status-dot"/>SYS READY</div>
        <button className="th-syncbtn">⟳ SYNC</button>
        <span className="th-brackets">v3.90</span>
      </div>
      <div className="th-tabs">
        {['◈ FINDER','OPTIM','ECON','PINNED','COMPARE','WATCH','ROUTE','FC PLAN','MAP','3D MAP','COLONY'].map((t,i)=>(
          <button key={i} className={`th-tab${i===0?' active':''}`}>{t}</button>
        ))}
      </div>
      <div className="th-body">
        <div className="th-sidebar">
          <div className="th-panel">
            <div className="th-panel-hdr"><span className="th-panel-icon">📍</span><span className="th-panel-title">Target System</span></div>
            <div className="th-panel-body">
              <label className="th-label">Designation</label>
              <input className="th-input" defaultValue="Sol" />
              <div style={{marginTop:8,padding:'6px 10px',background:'#080b06',border:'1px solid #2a3a10',fontSize:12,color:'#a0c040',clipPath:'polygon(4px 0%,100% 0%,calc(100% - 4px) 100%,0% 100%)'}}>◉ Sol — 0, 0, 0</div>
            </div>
          </div>
          <div className="th-panel">
            <div className="th-panel-hdr"><span className="th-panel-icon">📡</span><span className="th-panel-title">Scan Radius</span></div>
            <div className="th-panel-body">
              {([['Max Range (ly)',50],['Min Range (ly)',0],['Results Limit',50]] as [string,number][]).map(([lbl,val],i)=>(
                <div key={i} style={{marginBottom:i<2?10:0}}><label className="th-label">{lbl}</label><div className="th-slider-row"><input type="range" className="th-slider" defaultValue={val}/><span className="th-slider-val">{val}</span></div></div>
              ))}
            </div>
          </div>
          <div className="th-panel">
            <div className="th-panel-hdr"><span className="th-panel-icon">⭐</span><span className="th-panel-title">Rating Threshold</span></div>
            <div className="th-panel-body"><label className="th-label">Min Rating</label><div className="th-slider-row"><input type="range" className="th-slider" defaultValue={60}/><span className="th-slider-val">60</span></div></div>
          </div>
          <button className="th-searchbtn">▶ EXECUTE SCAN</button>
        </div>
        <div className="th-content">
          <div className="th-summary">
            <span style={{color:'#6a8030',marginRight:4}}>▶</span>
            <span>TARGETS ACQUIRED: <strong>247</strong></span>
            <span style={{color:'#304020'}}>// 843ms</span>
            <div style={{flex:1}}/>
            <button className="th-btn">WATCH ALL</button>
            <button className="th-btn">COPY LIST</button>
          </div>
          {systems.map((sys,i)=>{
            const b = ECO[sys.economy] ?? {bg:'#556',glow:'rgba(100,100,120,0.4)'};
            return (
              <div className="th-card" key={i}>
                <div style={{position:'relative'}}>
                  <span className="th-corner-tl"/>
                  <span className="th-corner-br"/>
                  <div className="th-card-hdr">
                    <div className="th-rating-wrap">
                      <span className="th-rating" style={{background:b.bg,boxShadow:`0 0 12px ${b.glow}`}}>{sys.rating}</span>
                      <span className="th-eco-lbl">{sys.economy}</span>
                    </div>
                    <span className="th-sys-name">{sys.name}</span>
                    <span className="th-dist">📡 {sys.dist}</span>
                    <button style={{background:'none',border:'none',color:'#304020',cursor:'pointer',fontSize:14}}>📌</button>
                  </div>
                </div>
                <div className="th-card-body">
                  <div className="th-tags">
                    {sys.tags.map((t,j)=><span key={j} className={`th-tag ${sys.tc[j]??''}`}>{t}</span>)}
                    <span className="th-tag">⭐ Landable</span>
                    <span className="th-tag amber">💰 {sys.pop}</span>
                  </div>
                  <div className="th-stat-row">
                    <div className="th-stat"><span className="th-stat-lbl">Slots</span><span className="th-stat-val">{sys.slots}</span></div>
                    <div className="th-stat"><span className="th-stat-lbl">Bodies</span><span className="th-stat-val">{sys.bodies}</span></div>
                    <div className="th-stat"><span className="th-stat-lbl">Star</span><span className="th-stat-val">{sys.star}</span></div>
                    <div className="th-stat"><span className="th-stat-lbl">Sec</span><span className="th-stat-val">{sys.sec}</span></div>
                  </div>
                </div>
                <div className="th-card-footer">
                  <button className="th-btn">WATCH</button>
                  <button className="th-btn">COMPARE</button>
                  <button className="th-btn primary">BRIEFING ▶</button>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
