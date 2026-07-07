import type { SimulateBuildResponse } from '@/types/api';
import { Chip } from '../components';
import { titleCase } from '../utils/formatters';
import { serviceTone } from '../utils/toneHelpers';

export function PortServicePanel({
  states,
  ledger,
}: {
  states: SimulateBuildResponse['port_service_states'];
  ledger: SimulateBuildResponse['service_unlock_ledger'];
}) {
  if ((!states || states.length === 0) && (!ledger || ledger.length === 0)) return null;
  return (
    <div className="rounded-chunk-lg border border-green/25 bg-green/5 p-3">
      <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.18em] text-green">
        Port Service Graph
      </div>
      {states && states.length > 0 ? (
        <div className="space-y-3">
          {states.map((state) => {
            const active = Object.values(state.active_services ?? {});
            const locked = Object.values(state.locked_services ?? {});
            const unknown = Object.values(state.unknown_services ?? {});
            return (
              <div key={`${state.local_body_id ?? 'system'}-${state.port_id}`} className="rounded border border-border/60 bg-bg3/45 px-2 py-2">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div>
                    <div className="font-mono text-[11px] text-silver">{state.port_name}</div>
                    <div className="mt-0.5 font-mono text-[10px] text-silver-dk">
                      {state.body_name || (state.local_body_id ? `Body ${state.local_body_id}` : 'System-wide')} · {titleCase(state.location_type)} · {titleCase(state.effective_role)}
                    </div>
                  </div>
                  <div className="flex flex-wrap justify-end gap-1.5 font-mono text-[10px]">
                    <Chip tone="good">{active.length} active</Chip>
                    <Chip tone={locked.length > 0 ? 'warn' : 'default'}>{locked.length} locked</Chip>
                    <Chip>{unknown.length} unknown</Chip>
                  </div>
                </div>
                <ServiceEntryGroup title="Active services" entries={active.slice(0, 4)} tone="good" />
                <ServiceEntryGroup title="Locked services" entries={locked.slice(0, 4)} tone="warn" />
                <ServiceEntryGroup title="Unknown" entries={unknown.slice(0, 3)} tone="default" />
                {[...(state.warnings ?? []), ...(state.recommendations ?? [])].slice(0, 2).map((item) => (
                  <div key={item} className="mt-2 rounded border border-gold/30 bg-gold/5 px-2 py-1 font-mono text-[10px] leading-snug text-gold">
                    {item}
                  </div>
                ))}
              </div>
            );
          })}
        </div>
      ) : (
        <div className="rounded border border-border/60 bg-bg3/45 px-2 py-2 font-mono text-[10px] text-silver-dk">
          No Main Ports are present yet, so there are no per-port service states.
        </div>
      )}
      {ledger && ledger.length > 0 && (
        <details className="mt-3 rounded border border-border/60 bg-bg2/55 px-2 py-2">
          <summary className="cursor-pointer font-mono text-[10px] uppercase tracking-[0.14em] text-silver">
            Service Unlock Ledger
          </summary>
          <div className="mt-2 space-y-1.5">
            {ledger.slice(0, 14).map((entry) => (
              <div key={`${entry.target_port_id}-${entry.service}-${entry.status}-${entry.unlock_type}-${entry.source_id ?? 'none'}`} className="rounded border border-border/50 bg-bg3/45 px-2 py-1.5">
                <div className="grid gap-1 font-mono text-[10px] text-silver-dk sm:grid-cols-[92px_72px_minmax(0,1fr)_minmax(0,1fr)]">
                  <span className={serviceTone(entry.status)}>{titleCase(entry.status)}</span>
                  <span>{titleCase(entry.unlock_type)}</span>
                  <span className="truncate"><span className="text-silver">Service:</span> {titleCase(entry.service)}</span>
                  <span className="truncate"><span className="text-silver">Target:</span> {entry.target_port_name}</span>
                </div>
                <div className="mt-1 font-mono text-[10px] leading-snug text-silver-dk">
                  <span className="text-silver">{titleCase(entry.confidence)}:</span> {entry.reason}
                </div>
                {entry.caveats.slice(0, 1).map((caveat) => (
                  <div key={caveat} className="mt-1 font-mono text-[10px] leading-snug text-gold">{caveat}</div>
                ))}
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}

function ServiceEntryGroup({
  title,
  entries,
  tone,
}: {
  title: string;
  entries: SimulateBuildResponse['service_unlock_ledger'];
  tone: 'good' | 'warn' | 'default';
}) {
  if (!entries || entries.length === 0) return null;
  const titleClass = tone === 'good' ? 'text-green' : tone === 'warn' ? 'text-gold' : 'text-silver-dk';
  return (
    <div className="mt-2 space-y-1">
      <div className={`font-mono text-[9px] uppercase tracking-[0.14em] ${titleClass}`}>{title}</div>
      {entries.map((entry) => (
        <div key={`${entry.service}-${entry.status}-${entry.source_id ?? 'none'}`} className="rounded border border-border/50 bg-bg2/45 px-2 py-1 font-mono text-[10px] text-silver-dk">
          <span className="text-silver">{titleCase(entry.service)}</span>
          {entry.source_name && <span> · {entry.source_name}</span>}
          <span> · {titleCase(entry.unlock_type)}</span>
          {entry.requirements.length > 0 && <div className="mt-0.5 text-gold">{entry.requirements[0]}</div>}
          {entry.caveats.length > 0 && <div className="mt-0.5 text-gold">{entry.caveats[0]}</div>}
        </div>
      ))}
    </div>
  );
}
