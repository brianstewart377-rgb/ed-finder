export function TerminalGreen() {
  const css = `
    @import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Orbitron:wght@400;600;700&display=swap');

    .tg-root {
      font-family: 'Share Tech Mono', monospace;
      background: #000d00;
      color: #00e040;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      position: relative;
    }
    /* CRT scanlines */
    .tg-root::before {
      content: '';
      position: fixed; inset: 0; pointer-events: none; z-index: 999;
      background: repeating-linear-gradient(
        0deg,
        transparent,
        transparent 2px,
        rgba(0,0,0,0.18) 2px,
        rgba(0,0,0,0.18) 4px
      );
    }
    /* phosphor glow flicker */
    .tg-root::after {
      content: '';
      position: fixed; inset: 0; pointer-events: none; z-index: 998;
      background: radial-gradient(ellipse at 50% 50%, rgba(0,60,0,0.12) 0%, rgba(0,0,0,0.35) 100%);
    }

    .tg-header {
      background: #001400;
      border-bottom: 2px solid #00e040;
      padding: 12px 24px; display: flex; align-items: center; gap: 16px;
      position: relative; z-index: 10;
      box-shadow: 0 0 20px rgba(0,200,60,0.25), inset 0 -1px 0 rgba(0,200,60,0.15);
    }
    .tg-logo {
      width: 42px; height: 42px;
      border: 2px solid #00e040;
      display: flex; align-items: center; justify-content: center;
      font-size: 18px; color: #00e040;
      box-shadow: 0 0 14px rgba(0,200,60,0.5), inset 0 0 10px rgba(0,200,60,0.08);
    }
    .tg-title {
      font-family: 'Share Tech Mono', monospace; font-size: 20px; font-weight: 400;
      color: #00ff50; letter-spacing: 3px;
      text-shadow: 0 0 12px rgba(0,240,80,0.8), 0 0 24px rgba(0,200,60,0.4);
    }
    .tg-sub { font-size: 10px; color: #006820; letter-spacing: 2px; text-transform: uppercase; }
    .tg-cursor { display: inline-block; width: 8px; height: 14px; background: #00ff50; animation: tg-blink 1.1s step-end infinite; vertical-align: bottom; margin-left: 3px; }
    @keyframes tg-blink { 0%,100%{opacity:1} 50%{opacity:0} }
    .tg-spacer { flex: 1; }
    .tg-badge {
      font-size: 10px; color: #00a030; border: 1px solid #004820; padding: 4px 10px;
      background: #001400; letter-spacing: 1px;
    }
    .tg-syncbtn {
      background: #001a00; color: #00e040; border: 1px solid #00e040; padding: 8px 18px;
      font-family: 'Share Tech Mono', monospace; font-size: 11px; letter-spacing: 1px;
      cursor: pointer; box-shadow: 0 0 10px rgba(0,200,60,0.25); text-transform: uppercase;
    }
    .tg-syncbtn:hover { background: #002800; box-shadow: 0 0 18px rgba(0,200,60,0.4); }

    .tg-tabs {
      background: #000d00; border-bottom: 1px solid #003010; padding: 0 20px;
      display: flex; gap: 0; overflow-x: auto; position: relative; z-index: 10;
    }
    .tg-tab {
      font-family: 'Share Tech Mono', monospace; font-size: 10px; letter-spacing: 1px;
      padding: 11px 14px; background: none; border: none; border-bottom: 2px solid transparent;
      color: #005520; cursor: pointer; white-space: nowrap; text-transform: uppercase; transition: all 0.15s;
    }
    .tg-tab.active { color: #00ff50; border-bottom-color: #00e040; background: #001000; text-shadow: 0 0 8px rgba(0,240,80,0.7); }
    .tg-tab:hover:not(.active) { color: #00c040; }

    .tg-body { display: flex; flex: 1; min-height: 0; position: relative; z-index: 1; }

    .tg-sidebar {
      width: 300px; background: #000d00; border-right: 1px solid #003010;
      padding: 16px 14px; overflow-y: auto; display: flex; flex-direction: column; gap: 12px;
    }
    .tg-panel { border: 1px solid #003a10; background: #000d00; }
    .tg-panel-hdr {
      background: #001400; border-bottom: 1px solid #003010;
      padding: 8px 12px; display: flex; align-items: center; gap: 8px;
    }
    .tg-panel-icon { color: #00c040; font-size: 12px; }
    .tg-panel-title { font-size: 10px; color: #00a030; letter-spacing: 1.5px; text-transform: uppercase; flex: 1; }
    .tg-panel-body { padding: 12px; }
    .tg-label { font-size: 10px; color: #005520; letter-spacing: 1px; text-transform: uppercase; margin-bottom: 5px; display: block; }
    .tg-input {
      width: 100%; background: #000d00; border: 1px solid #003a10;
      color: #00e040; font-family: 'Share Tech Mono', monospace; font-size: 13px;
      padding: 8px 10px; outline: none;
    }
    .tg-input:focus { border-color: #00e040; box-shadow: 0 0 8px rgba(0,180,60,0.2); }
    .tg-slider-row { display: flex; align-items: center; gap: 10px; margin-top: 5px; }
    .tg-slider { flex: 1; accent-color: #00e040; }
    .tg-slider-val { font-size: 12px; color: #00e040; min-width: 32px; text-align: right; text-shadow: 0 0 6px rgba(0,200,60,0.5); }
    .tg-searchbtn {
      width: 100%; background: #002000; color: #00ff50; border: 1px solid #00e040;
      padding: 11px; font-family: 'Share Tech Mono', monospace; font-size: 11px;
      text-transform: uppercase; letter-spacing: 2px; cursor: pointer;
      box-shadow: 0 0 14px rgba(0,200,60,0.22); margin-top: 4px;
    }
    .tg-searchbtn:hover { background: #003000; box-shadow: 0 0 22px rgba(0,200,60,0.38); }

    .tg-content { flex: 1; padding: 16px; overflow-y: auto; display: flex; flex-direction: column; gap: 10px; }
    .tg-summary {
      display: flex; align-items: center; gap: 12px; padding: 8px 14px;
      background: #001400; border: 1px solid #003010;
      font-size: 12px; color: #006820;
    }
    .tg-summary strong { color: #00e040; text-shadow: 0 0 6px rgba(0,200,60,0.45); }

    .tg-card { border: 1px solid #003010; background: #000d00; transition: all 0.15s; }
    .tg-card:hover { border-color: #00a030; box-shadow: 0 0 16px rgba(0,180,60,0.12); background: #001200; }
    .tg-card-hdr { padding: 10px 14px; display: flex; align-items: center; gap: 10px; border-bottom: 1px solid #002a0c; }
    .tg-rating-wrap { display: flex; flex-direction: column; align-items: center; flex-shrink: 0; }
    .tg-rating {
      color: #000d00; font-family: 'Share Tech Mono', monospace; font-size: 13px; font-weight: 400;
      padding: 4px 10px; min-width: 44px; text-align: center;
    }
    .tg-eco-lbl { font-size: 8px; color: #005520; text-transform: uppercase; margin-top: 2px; letter-spacing: 0.5px; }
    .tg-sys-name { font-size: 13px; color: #00e040; flex: 1; text-shadow: 0 0 6px rgba(0,200,60,0.35); }
    .tg-dist { font-size: 11px; color: #005520; }
    .tg-card-body { padding: 10px 14px; }
    .tg-tags { display: flex; flex-wrap: wrap; gap: 5px; margin-bottom: 8px; }
    .tg-tag { font-size: 10px; padding: 2px 8px; background: #001400; border: 1px solid #003a10; color: #009030; }
    .tg-stat-row { display: flex; gap: 18px; }
    .tg-stat { display: flex; flex-direction: column; gap: 1px; }
    .tg-stat-lbl { font-size: 9px; color: #005020; text-transform: uppercase; letter-spacing: 1px; }
    .tg-stat-val { font-size: 12px; color: #00c040; }
    .tg-card-footer { padding: 8px 14px; border-top: 1px solid #002a0c; display: flex; gap: 6px; justify-content: flex-end; }
    .tg-btn { font-size: 10px; padding: 5px 12px; border: 1px solid #003a10; background: #001400; color: #006820; cursor: pointer; font-family: 'Share Tech Mono', monospace; transition: all 0.12s; }
    .tg-btn:hover { border-color: #00a030; color: #00c040; }
    .tg-btn.primary { border-color: #00c040; color: #00e040; background: #001c00; }
  `;

  const ECO: Record<string,{bg:string;color:string}> = {
    'High Tech':   { bg:'#22d3ee', color:'#001a20' },
    'Industrial':  { bg:'#f59e0b', color:'#1a0d00' },
    'Agriculture': { bg:'#34d399', color:'#001a0d' },
    'Military':    { bg:'#ef4444', color:'#1a0000' },
  };

  const systems = [
    { name:'Colonia Gateway', rating:94, economy:'High Tech',   dist:'22,000 ly', tags:['High Tech','Industrial'],  pop:'2.1B', slots:7, bodies:23, star:'F', sec:'High'   },
    { name:'Eravate',         rating:88, economy:'Industrial',  dist:'34.2 ly',   tags:['Industrial','Refinery'],   pop:'450M', slots:5, bodies:14, star:'G', sec:'Medium' },
    { name:'Lave',            rating:81, economy:'Agriculture', dist:'108.5 ly',  tags:['Agriculture','Tourism'],   pop:'1.2B', slots:6, bodies:18, star:'K', sec:'High'   },
    { name:'Alioth',          rating:76, economy:'Military',    dist:'82.6 ly',   tags:['Military','Service'],      pop:'8.4B', slots:4, bodies:11, star:'A', sec:'High'   },
  ];

  return (
    <div className="tg-root">
      <style dangerouslySetInnerHTML={{ __html: css }} />
      <div className="tg-header">
        <div className="tg-logo">⬡</div>
        <div><div className="tg-title">ED:FINDER<span className="tg-cursor"/></div><div className="tg-sub">// Advanced System Finder &amp; Optimizer</div></div>
        <div className="tg-spacer" />
        <span style={{fontSize:11,color:'#004018',marginRight:8}}>SYS: IDLE</span>
        <button className="tg-syncbtn">[ ⟳ SYNC ]</button>
        <span className="tg-badge">v3.90</span>
      </div>
      <div className="tg-tabs">
        {['> FINDER','OPTIM','ECON','PINNED','COMPARE','WATCH','ROUTE','FC','MAP','3D','COLONY'].map((t,i)=>(
          <button key={i} className={`tg-tab${i===0?' active':''}`}>{t}</button>
        ))}
      </div>
      <div className="tg-body">
        <div className="tg-sidebar">
          <div className="tg-panel">
            <div className="tg-panel-hdr"><span className="tg-panel-icon">$</span><span className="tg-panel-title">ref_system</span></div>
            <div className="tg-panel-body">
              <label className="tg-label">system_name:</label>
              <input className="tg-input" defaultValue="Sol" />
              <div style={{marginTop:8,padding:'6px 10px',background:'#001400',border:'1px solid #003a10',fontSize:12,color:'#00c040'}}>📍 Sol &gt; 0, 0, 0</div>
            </div>
          </div>
          <div className="tg-panel">
            <div className="tg-panel-hdr"><span className="tg-panel-icon">~</span><span className="tg-panel-title">search_radius</span></div>
            <div className="tg-panel-body">
              {([['max_dist_ly',50],['min_dist_ly',0],['results_pp',50]] as [string,number][]).map(([lbl,val],i)=>(
                <div key={i} style={{marginBottom:i<2?10:0}}><label className="tg-label">{lbl}:</label><div className="tg-slider-row"><input type="range" className="tg-slider" defaultValue={val}/><span className="tg-slider-val">{val}</span></div></div>
              ))}
            </div>
          </div>
          <div className="tg-panel">
            <div className="tg-panel-hdr"><span className="tg-panel-icon">#</span><span className="tg-panel-title">rating_filter</span></div>
            <div className="tg-panel-body"><label className="tg-label">min_rating:</label><div className="tg-slider-row"><input type="range" className="tg-slider" defaultValue={60}/><span className="tg-slider-val">60</span></div></div>
          </div>
          <button className="tg-searchbtn">[ execute_search() ]</button>
        </div>
        <div className="tg-content">
          <div className="tg-summary">
            <span style={{color:'#006820'}}>&gt;</span>
            <span>query returned <strong>247 results</strong></span>
            <span style={{color:'#004010'}}>// 843ms</span>
            <div style={{flex:1}}/>
            <button className="tg-btn">WATCH_ALL</button>
            <button className="tg-btn">COPY_NAMES</button>
          </div>
          {systems.map((sys,i)=>{
            const b = ECO[sys.economy] ?? {bg:'#888',color:'#000'};
            return (
              <div className="tg-card" key={i}>
                <div className="tg-card-hdr">
                  <div className="tg-rating-wrap">
                    <span className="tg-rating" style={{background:b.bg,color:b.color,boxShadow:`0 0 10px ${b.bg}88`}}>{sys.rating}</span>
                    <span className="tg-eco-lbl">{sys.economy}</span>
                  </div>
                  <span className="tg-sys-name">{sys.name}</span>
                  <span className="tg-dist">{sys.dist}</span>
                  <button style={{background:'none',border:'none',color:'#004010',cursor:'pointer',fontSize:14}}>📌</button>
                </div>
                <div className="tg-card-body">
                  <div className="tg-tags">
                    {sys.tags.map((t,j)=><span key={j} className="tg-tag">{t}</span>)}
                    <span className="tg-tag">landable:true</span>
                    <span className="tg-tag">pop:{sys.pop}</span>
                  </div>
                  <div className="tg-stat-row">
                    <div className="tg-stat"><span className="tg-stat-lbl">slots</span><span className="tg-stat-val">{sys.slots}</span></div>
                    <div className="tg-stat"><span className="tg-stat-lbl">bodies</span><span className="tg-stat-val">{sys.bodies}</span></div>
                    <div className="tg-stat"><span className="tg-stat-lbl">star</span><span className="tg-stat-val">{sys.star}</span></div>
                    <div className="tg-stat"><span className="tg-stat-lbl">sec</span><span className="tg-stat-val">{sys.sec}</span></div>
                  </div>
                </div>
                <div className="tg-card-footer">
                  <button className="tg-btn">WATCH</button>
                  <button className="tg-btn">COMPARE</button>
                  <button className="tg-btn primary">BRIEFING</button>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
