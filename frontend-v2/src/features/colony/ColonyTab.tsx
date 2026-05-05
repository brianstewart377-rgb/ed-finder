import { useState } from 'react';
import type { ColonyEntry, Phase, UseColony } from './useColony';
import { PHASE_META, PHASES } from './useColony';

export interface ColonyTabProps {
  colony: UseColony;
  onOpenDetail?: (id64: number) => void;
}

export function ColonyTab({ colony, onOpenDetail }: ColonyTabProps) {
  const [showAdd,    setShowAdd]    = useState(false);
  const [editingId,  setEditingId]  = useState<string | null>(null);
  const editingEntry = editingId
    ? colony.entries.find((e) => e.id === editingId) ?? null
    : null;

  return (
    <section data-testid="colony-tab" className="space-y-4">
      <header className="flex flex-wrap items-center gap-3">
        <h2 className="font-mono text-orange tracking-wider text-lg">🏗️ Colony Tracker</h2>
        <span className="font-mono text-xs text-text-dim">
          local-only — track your claimed systems
        </span>
        <span className="flex-1" />
        <button
          type="button"
          onClick={() => setShowAdd(true)}
          data-testid="colony-add-open"
          className="px-3 py-1 rounded bg-orange text-bg1 border border-orange font-mono text-[11px] hover:bg-orange-dk"
        >
          ➕ Track System
        </button>
        <button
          type="button"
          onClick={colony.exportCsv}
          disabled={colony.entries.length === 0}
          data-testid="colony-export"
          className="px-2 py-1 rounded bg-bg4 border border-border font-mono text-[11px] text-text-dim hover:text-orange hover:border-orange-dk disabled:opacity-40 disabled:cursor-not-allowed"
        >
          ⬇ Export CSV
        </button>
      </header>

      {/* Stats row */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 text-xs font-mono">
        <StatCard label="Tracked"  value={colony.counts.total} />
        {PHASES.map((p) => (
          <StatCard
            key={p}
            label={PHASE_META[p].label}
            value={colony.counts[p]}
            colour={PHASE_META[p].colour}
          />
        ))}
      </div>

      {/* List or empty state */}
      {colony.entries.length === 0 ? (
        <div className="text-center py-16 px-4 rounded border border-dashed border-border">
          <div className="text-3xl mb-2" aria-hidden>🏗️</div>
          <h3 className="font-mono text-orange text-sm mb-1">No systems tracked yet</h3>
          <p className="text-text-dim text-xs max-w-sm mx-auto">
            Click <span className="text-orange">➕ Track System</span> to add a colonisation project.
            Data lives in your browser — no server round-trip.
          </p>
        </div>
      ) : (
        <ul className="space-y-2">
          {colony.entries.map((e) => (
            <ColonyRow
              key={e.id}
              entry={e}
              onEdit={() => setEditingId(e.id)}
              onRemove={() => colony.remove(e.id)}
              onPhaseChange={(p) => colony.update(e.id, { phase: p })}
              onOpenDetail={e.id64 != null && onOpenDetail
                ? () => onOpenDetail(e.id64!)
                : undefined}
            />
          ))}
        </ul>
      )}

      {showAdd && (
        <ColonyFormModal
          mode="add"
          entry={null}
          onClose={() => setShowAdd(false)}
          onSave={(data) => { colony.add(data); setShowAdd(false); }}
        />
      )}

      {editingEntry && (
        <ColonyFormModal
          mode="edit"
          entry={editingEntry}
          onClose={() => setEditingId(null)}
          onSave={(data) => { colony.update(editingEntry.id, data); setEditingId(null); }}
        />
      )}
    </section>
  );
}

// ─── Subcomponents ────────────────────────────────────────────────────────

function StatCard({ label, value, colour }: {
  label: string; value: number; colour?: string;
}) {
  return (
    <div className="rounded p-2 border border-border bg-bg3/40">
      <div className="text-text-dim uppercase tracking-wider text-[10px]">{label}</div>
      <div
        className="tabular-nums font-bold text-lg"
        style={colour ? { color: colour } : undefined}
      >
        {value}
      </div>
    </div>
  );
}

function ColonyRow({
  entry, onEdit, onRemove, onPhaseChange, onOpenDetail,
}: {
  entry:        ColonyEntry;
  onEdit:       () => void;
  onRemove:     () => void;
  onPhaseChange: (p: Phase) => void;
  onOpenDetail?: () => void;
}) {
  const meta = PHASE_META[entry.phase];
  const progress = (entry.target_population && entry.current_population)
    ? Math.min(100, Math.round((entry.current_population / entry.target_population) * 100))
    : null;

  return (
    <li
      data-testid={`colony-row-${entry.id}`}
      className="rounded border border-border p-3 bg-bg3/30 grid grid-cols-[1fr_auto] gap-3"
    >
      <div className="min-w-0 space-y-1">
        <div className="flex items-center gap-2 flex-wrap">
          <span
            className="px-2 py-0.5 rounded text-[11px] font-mono border"
            style={{ borderColor: meta.colour, color: meta.colour, backgroundColor: `${meta.colour}22` }}
          >
            {meta.icon} {meta.label}
          </span>
          {onOpenDetail
            ? (
              <button
                type="button"
                onClick={onOpenDetail}
                className="font-mono text-orange font-bold hover:underline truncate"
              >
                {entry.name}
              </button>
            )
            : (
              <span className="font-mono text-orange font-bold truncate">{entry.name}</span>
            )
          }
          <span className="text-[10px] font-mono text-text-dim">
            claimed {new Date(entry.claimed_at).toLocaleDateString()}
          </span>
        </div>

        {progress !== null && entry.target_population && (
          <div className="space-y-0.5">
            <div className="flex items-center justify-between text-[10px] font-mono text-text-dim">
              <span>Population</span>
              <span className="tabular-nums">
                {(entry.current_population ?? 0).toLocaleString()} / {entry.target_population.toLocaleString()} ({progress}%)
              </span>
            </div>
            <div className="h-1.5 bg-bg4 rounded overflow-hidden">
              <div className="h-full" style={{ width: `${progress}%`, backgroundColor: meta.colour }} />
            </div>
          </div>
        )}

        {entry.notes && (
          <p className="text-[11px] text-text-dim italic leading-snug">{entry.notes}</p>
        )}
      </div>

      <div className="flex flex-col gap-1.5 text-[10px] font-mono">
        <select
          value={entry.phase}
          onChange={(e) => onPhaseChange(e.target.value as Phase)}
          data-testid={`colony-phase-${entry.id}`}
          className="bg-bg4 border border-border rounded px-1 py-0.5 text-text"
        >
          {PHASES.map((p) => (
            <option key={p} value={p}>{PHASE_META[p].icon} {PHASE_META[p].label}</option>
          ))}
        </select>
        <button
          type="button"
          onClick={onEdit}
          data-testid={`colony-edit-${entry.id}`}
          className="px-2 py-0.5 rounded bg-bg4 border border-border text-text-dim hover:text-orange hover:border-orange-dk"
        >
          ✎ Edit
        </button>
        <button
          type="button"
          onClick={() => { if (confirm(`Remove "${entry.name}" from tracker?`)) onRemove(); }}
          data-testid={`colony-remove-${entry.id}`}
          className="px-2 py-0.5 rounded bg-red/10 border border-red/40 text-red hover:bg-red/20"
        >
          ✕ Remove
        </button>
      </div>
    </li>
  );
}

function ColonyFormModal({
  mode, entry, onClose, onSave,
}: {
  mode:    'add' | 'edit';
  entry:   ColonyEntry | null;
  onClose: () => void;
  onSave:  (data: Omit<ColonyEntry, 'id' | 'claimed_at' | 'updated_at'>) => void;
}) {
  const [name,    setName]    = useState(entry?.name ?? '');
  const [phase,   setPhase]   = useState<Phase>(entry?.phase ?? 'planning');
  const [target,  setTarget]  = useState<string>(
    entry?.target_population != null ? String(entry.target_population) : ''
  );
  const [current, setCurrent] = useState<string>(
    entry?.current_population != null ? String(entry.current_population) : ''
  );
  const [notes,   setNotes]   = useState(entry?.notes ?? '');

  const submit = () => {
    if (!name.trim()) return;
    onSave({
      name:               name.trim(),
      phase,
      target_population:  target  ? parseInt(target,  10) : null,
      current_population: current ? parseInt(current, 10) : null,
      notes:              notes.trim(),
      id64:               entry?.id64 ?? null,
      x:                  entry?.x ?? null,
      y:                  entry?.y ?? null,
      z:                  entry?.z ?? null,
    });
  };

  return (
    <div
      className="fixed inset-0 z-30 flex items-center justify-center bg-bg1/80 backdrop-blur-sm px-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
    >
      <div
        className="w-full max-w-md rounded border border-border bg-bg2 p-5 space-y-3"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="font-mono text-orange tracking-wider text-sm">
          {mode === 'add' ? 'Track new system' : `Edit ${entry?.name}`}
        </h3>

        <Field label="System name *">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            data-testid="colony-form-name"
            placeholder="Enter system name…"
            className="w-full bg-bg4 border border-border rounded px-2 py-1 text-text font-mono text-xs"
            autoFocus
          />
        </Field>

        <Field label="Phase">
          <select
            value={phase}
            onChange={(e) => setPhase(e.target.value as Phase)}
            data-testid="colony-form-phase"
            className="w-full bg-bg4 border border-border rounded px-2 py-1 text-text font-mono text-xs"
          >
            {PHASES.map((p) => (
              <option key={p} value={p}>{PHASE_META[p].icon} {PHASE_META[p].label}</option>
            ))}
          </select>
        </Field>

        <div className="grid grid-cols-2 gap-2">
          <Field label="Target population">
            <input
              type="number"
              min={0}
              value={target}
              onChange={(e) => setTarget(e.target.value)}
              data-testid="colony-form-target"
              placeholder="e.g. 1000000"
              className="w-full bg-bg4 border border-border rounded px-2 py-1 text-text font-mono text-xs"
            />
          </Field>
          <Field label="Current population">
            <input
              type="number"
              min={0}
              value={current}
              onChange={(e) => setCurrent(e.target.value)}
              data-testid="colony-form-current"
              placeholder="optional"
              className="w-full bg-bg4 border border-border rounded px-2 py-1 text-text font-mono text-xs"
            />
          </Field>
        </div>

        <Field label="Notes">
          <textarea
            rows={2}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            data-testid="colony-form-notes"
            placeholder="Anything worth remembering…"
            className="w-full bg-bg4 border border-border rounded px-2 py-1 text-text font-mono text-xs resize-vertical"
          />
        </Field>

        <div className="flex justify-end gap-2 pt-1">
          <button
            type="button"
            onClick={onClose}
            className="px-3 py-1 rounded bg-bg4 border border-border font-mono text-xs text-text-dim hover:text-orange"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={submit}
            disabled={!name.trim()}
            data-testid="colony-form-save"
            className="px-3 py-1 rounded bg-orange text-bg1 border border-orange font-mono text-xs hover:bg-orange-dk disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {mode === 'add' ? '➕ Track' : '✓ Save'}
          </button>
        </div>
      </div>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="block font-mono text-[11px] text-text-dim uppercase tracking-wider mb-1">
        {label}
      </span>
      {children}
    </label>
  );
}
