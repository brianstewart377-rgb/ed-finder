import { AlertTriangle } from 'lucide-react';
import type { SimulateBuildResponse } from '@/types/api';

export function CpSummary({ cp }: { cp: SimulateBuildResponse['cp'] }) {
  return (
    <div className="rounded-chunk-lg border border-border/70 bg-bg2/70 p-3">
      <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.18em] text-silver-dk">
        Construction points
      </div>
      <div className="grid grid-cols-4 gap-2">
        <CpCell label="Yellow" value={cp.yellow_cp_final} colour="#fbbf24" />
        <CpCell label="Green" value={cp.green_cp_final} colour="#4ade80" />
        <CpCell label="T2 ports" value={cp.t2_ports} colour="#c8ccd1" />
        <CpCell label="T3 ports" value={cp.t3_ports} colour="#7dd3fc" />
      </div>
      {cp.warnings.length > 0 && (
        <div className="mt-2 flex items-start gap-2 rounded border border-gold/30 bg-gold/5 px-2 py-1.5 text-[10px] font-mono text-gold">
          <AlertTriangle size={13} className="mt-0.5 shrink-0" />
          <span>{cp.warnings[0]}</span>
        </div>
      )}
    </div>
  );
}

function CpCell({ label, value, colour }: { label: string; value: number; colour: string }) {
  return (
    <div className="rounded border border-border/60 bg-bg3/60 p-2 text-center">
      <div className="font-mono text-[9px] uppercase tracking-[0.14em] text-silver-dk">{label}</div>
      <div className="font-mono text-sm font-bold tabular-nums" style={{ color: colour }}>
        {value > 0 ? `+${value}` : value}
      </div>
    </div>
  );
}
