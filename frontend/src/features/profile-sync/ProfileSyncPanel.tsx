import { useState } from 'react';
import { useProfileSync, type UseProfileSync } from '@/features/profile-sync/useProfileSync';

export function ProfileSyncPanel() {
  const sync = useProfileSync();
  const [draft, setDraft] = useState(sync.syncKey);

  return (
    <section className="panel p-5 space-y-3">
      <h3 className="font-display text-orange text-xs uppercase tracking-[0.18em]">
        6. Profile sync
      </h3>
      <p className="text-silver-dk text-[11px] leading-snug">
        Cross-device sync for your <strong className="text-orange-lt">Pinned</strong>,
        <strong className="text-orange-lt"> Compare</strong>,
        <strong className="text-orange-lt"> FC route</strong>, and
        <strong className="text-orange-lt"> Colony tracker</strong>.
        The sync key IS the credential — pick a hard-to-guess string and
        share it across your devices. Last-write-wins; no auto-merge.
      </p>

      <div className="flex flex-wrap items-center gap-2">
        <input
          type="text"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="16+ chars, [A-Za-z0-9_-]"
          data-testid="sync-key-input"
          className="flex-1 min-w-[260px]"
          autoComplete="off"
        />
        <button
          type="button"
          onClick={() => sync.setSyncKey(draft.trim())}
          disabled={draft.trim().length < 16 || draft.trim() === sync.syncKey}
          data-testid="sync-key-save"
          className="btn-primary text-[11px] py-1.5 px-3 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Save key
        </button>
        <button
          type="button"
          onClick={() => setDraft(sync.generateKey())}
          data-testid="sync-key-generate"
          className="btn-metal text-[11px] py-1.5 px-3"
          title="Generate a 24-char random key"
        >
          🎲 Generate
        </button>
      </div>

      <SyncStateToast state={sync.state} onDismiss={sync.resetState} />

      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => void sync.pull()}
          disabled={!sync.hasKey || sync.state.kind === 'busy'}
          data-testid="sync-pull"
          className="text-[11px] py-1.5 px-3 rounded-chunk-sm border border-cyan/50 bg-cyan/15 text-cyan font-mono hover:bg-cyan/25 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          ⬇ Pull from cloud
        </button>
        <button
          type="button"
          onClick={() => void sync.push()}
          disabled={!sync.hasKey || sync.state.kind === 'busy'}
          data-testid="sync-push"
          className="btn-primary text-[11px] py-1.5 px-3 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          ⬆ Push to cloud
        </button>
        <span className="flex-1" />
        {sync.lastPushAt && (
          <span className="font-mono text-[10px] text-silver-dk">
            last push: {new Date(sync.lastPushAt).toLocaleString()}
          </span>
        )}
        <span
          data-testid="sync-key-status"
          className={[
            'font-mono text-[10px] uppercase tracking-wider',
            sync.hasKey ? 'text-green' : 'text-silver-dk',
          ].join(' ')}
        >
          {sync.hasKey ? '● Key set' : '○ No key'}
        </span>
      </div>

      {!sync.hasKey && (
        <p className="text-[10px] text-silver-dk font-mono">
          A key is needed before push/pull. Click Generate then Save.
        </p>
      )}
    </section>
  );
}

function SyncStateToast({
  state,
  onDismiss,
}: { state: UseProfileSync['state']; onDismiss: () => void }) {
  if (state.kind === 'idle' || state.kind === 'busy') return null;
  const ok = state.kind === 'ok';
  return (
    <div
      data-testid="sync-toast"
      className={[
        'rounded-chunk-sm border p-2.5 font-mono text-xs flex items-center gap-2',
        ok ? 'border-green/50 text-green' : 'border-red/50 text-red',
      ].join(' ')}
      style={{ background: ok ? 'rgba(74,222,128,0.10)' : 'rgba(248,113,113,0.10)' }}
    >
      <span>{ok ? '✓' : '✕'}</span>
      <span className="font-bold">{state.what}:</span>
      <span>
        {ok
          ? `${state.bytes != null ? `${state.bytes.toLocaleString()} bytes · ` : ''}saved at ${new Date(state.updated_at).toLocaleString()}`
          : state.message}
      </span>
      <button
        type="button"
        onClick={onDismiss}
        className="ml-auto opacity-70 hover:opacity-100"
        aria-label="Dismiss"
      >
        ✕
      </button>
    </div>
  );
}
