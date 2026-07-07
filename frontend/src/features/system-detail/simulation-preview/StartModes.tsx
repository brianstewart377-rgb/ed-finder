import type { ReactNode } from 'react';
import { AlertTriangle, CheckCircle2, Sparkles, Wand2 } from 'lucide-react';
import { Message } from './components';
import type { StartMode } from './types';

export function StartModes({
  mode,
  hasRecommendedBuild,
  loadingRecommended,
  onUseRecommended,
  onBlank,
  onShowSuggestedBuilds,
}: {
  mode: StartMode;
  hasRecommendedBuild: boolean;
  loadingRecommended: boolean;
  onUseRecommended: () => void;
  onBlank: () => void;
  onShowSuggestedBuilds?: () => void;
}) {
  return (
    <div className="space-y-2">
      <div>
        <h5 className="font-mono text-[10px] uppercase tracking-[0.18em] text-silver">How do you want to start?</h5>
        <p className="mt-1 text-[11px] text-silver-dk">
          Start with Suggested Builds if you are unsure, copy one to the Build Plan, tweak it, then run Preview.
        </p>
      </div>
      <div className="grid gap-2 md:grid-cols-3">
        <ModeButton
          active={false}
          icon={<Wand2 size={15} />}
          title="Show Suggested Builds"
          body="Jump to the Suggested Builds section below, where you can generate possible build plans when you are ready."
          onClick={onShowSuggestedBuilds ?? (() => undefined)}
          primary
        />
        <ModeButton
          active={mode === 'recommended'}
          disabled={!hasRecommendedBuild}
          icon={<Sparkles size={15} />}
          title="Use recommended baseline"
          body={hasRecommendedBuild ? 'Start from a simple recommended plan, then tweak it before running Preview.' : loadingRecommended ? 'Looking for a recommended baseline...' : 'No recommended baseline is available yet.'}
          onClick={onUseRecommended}
        />
        <ModeButton
          active={mode === 'blank_advanced'}
          icon={<AlertTriangle size={15} />}
          title="Start blank"
          body="Begin with an empty plan when you already know what you want to test."
          onClick={onBlank}
          secondary
        />
      </div>
    </div>
  );
}

function ModeButton({
  active,
  disabled,
  icon,
  title,
  body,
  onClick,
  primary,
  secondary,
}: {
  active: boolean;
  disabled?: boolean;
  icon: ReactNode;
  title: string;
  body: string;
  onClick: () => void;
  primary?: boolean;
  secondary?: boolean;
}) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={[
        'rounded-chunk-lg border p-3 text-left transition-colors',
        active
          ? 'border-orange/65 bg-orange/12 shadow-brand-glow'
          : primary
            ? 'border-cyan/45 bg-cyan/10 hover:border-cyan/70 hover:bg-cyan/15'
          : secondary
            ? 'border-border/60 bg-bg2/45 hover:border-gold/45 hover:bg-gold/5'
            : 'border-border/70 bg-bg2/70 hover:border-orange/45 hover:bg-orange/5',
        disabled ? 'cursor-not-allowed opacity-50' : '',
      ].join(' ')}
    >
      <div className={[
        'flex items-center gap-2 font-mono text-[11px] font-bold uppercase tracking-[0.12em]',
        primary ? 'text-cyan' : 'text-orange',
      ].join(' ')}>
        {icon}
        <span>{title}</span>
      </div>
      <p className="mt-1 text-[11px] leading-snug text-silver-dk">{body}</p>
      {secondary && (
        <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.12em] text-gold">Advanced manual control</p>
      )}
    </button>
  );
}

export function ModeIntro({
  mode,
  hasRecommendedBuild,
}: {
  mode: StartMode;
  hasRecommendedBuild: boolean;
}) {
  const copy = mode === 'blank_advanced'
    ? {
        title: 'Advanced blank plan',
        body: 'You are building from scratch. Add every facility yourself, then run Preview to check CP, economy order, and risks.',
        tone: 'warn' as const,
      }
    : mode === 'optimiser_candidate'
      ? {
          title: 'Suggested build copied',
          body: 'A suggested build is loaded into the editable Build Plan. Adjust facilities or run Preview when ready.',
          tone: 'info' as const,
        }
    : mode === 'edit_recommended'
      ? {
          title: 'Recommended plan editor',
          body: 'A recommended plan is loaded into the editable Build Plan. Adjust the sequence or facilities before running Preview.',
          tone: 'info' as const,
        }
      : {
          title: hasRecommendedBuild ? 'Recommended baseline loaded' : 'Waiting for recommended baseline',
          body: hasRecommendedBuild
            ? 'Use this as a simple baseline. You can still compare Suggested Builds, edit the Build Plan, then run Preview.'
            : 'ED-Finder will load a recommended baseline here when buildability data is available.',
          tone: hasRecommendedBuild ? 'good' as const : 'info' as const,
        };

  return <Message title={copy.title} tone={copy.tone} items={[copy.body]} />;
}

export function PlanBadge({
  mode,
  hasRecommendedBuild,
}: {
  mode: StartMode;
  hasRecommendedBuild: boolean;
}) {
  const label = mode === 'blank_advanced'
    ? 'Advanced blank'
    : mode === 'optimiser_candidate'
      ? 'Suggested build'
      : mode === 'edit_recommended'
        ? 'Editing recommendation'
        : hasRecommendedBuild ? 'Recommended baseline' : 'Baseline pending';
  return (
    <span className="inline-flex items-center gap-1.5 rounded-chunk-sm border border-orange/40 bg-orange/10 px-2.5 py-1 text-[10px] font-mono font-bold uppercase tracking-[0.12em] text-orange">
      <CheckCircle2 size={13} />
      {label}
    </span>
  );
}
