import type { ReactNode } from 'react';
import { AlertTriangle, CheckCircle2, Edit3, Sparkles } from 'lucide-react';
import { Message } from './components';
import type { StartMode } from './types';

export function StartModes({
  mode,
  hasRecommendedBuild,
  loadingRecommended,
  onUseRecommended,
  onEditRecommended,
  onBlank,
}: {
  mode: StartMode;
  hasRecommendedBuild: boolean;
  loadingRecommended: boolean;
  onUseRecommended: () => void;
  onEditRecommended: () => void;
  onBlank: () => void;
}) {
  return (
    <div className="grid gap-2 md:grid-cols-3">
      <ModeButton
        active={mode === 'recommended'}
        disabled={!hasRecommendedBuild}
        icon={<Sparkles size={15} />}
        title="Use recommended build"
        body={hasRecommendedBuild ? 'Load ED-Finder\'s suggested plan and preview it directly.' : loadingRecommended ? 'Looking for a suggested plan...' : 'No suggested plan is available yet.'}
        onClick={onUseRecommended}
      />
      <ModeButton
        active={mode === 'edit_recommended'}
        disabled={!hasRecommendedBuild}
        icon={<Edit3 size={15} />}
        title="Edit selected recommended build"
        body="Start from the suggested plan, then adjust facilities, bodies, and order."
        onClick={onEditRecommended}
      />
      <ModeButton
        active={mode === 'blank_advanced'}
        icon={<AlertTriangle size={15} />}
        title="Start blank advanced simulation"
        body="Begin with an empty plan when you already know what you want to test."
        onClick={onBlank}
      />
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
}: {
  active: boolean;
  disabled?: boolean;
  icon: ReactNode;
  title: string;
  body: string;
  onClick: () => void;
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
          : 'border-border/70 bg-bg2/70 hover:border-orange/45 hover:bg-orange/5',
        disabled ? 'cursor-not-allowed opacity-50' : '',
      ].join(' ')}
    >
      <div className="flex items-center gap-2 font-mono text-[11px] font-bold uppercase tracking-[0.12em] text-orange">
        {icon}
        <span>{title}</span>
      </div>
      <p className="mt-1 text-[11px] leading-snug text-silver-dk">{body}</p>
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
        body: 'You are building from scratch. Add every facility yourself, then run the preview to check CP, economy order, and risks.',
        tone: 'warn' as const,
      }
    : mode === 'edit_recommended'
      ? {
          title: 'Recommended plan editor',
          body: 'A suggested build is loaded. Adjust the sequence or facilities before previewing the in-game outcome.',
          tone: 'info' as const,
        }
      : {
          title: hasRecommendedBuild ? 'Recommended build loaded' : 'Waiting for recommended build',
          body: hasRecommendedBuild
            ? 'Start here: this is the safest first view. Run the preview as-is, then edit if you want to experiment.'
            : 'ED-Finder will load a recommended plan here when buildability data is available.',
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
    : mode === 'edit_recommended'
      ? 'Editing recommendation'
      : hasRecommendedBuild ? 'Recommended plan' : 'Recommendation pending';
  return (
    <span className="inline-flex items-center gap-1.5 rounded-chunk-sm border border-orange/40 bg-orange/10 px-2.5 py-1 text-[10px] font-mono font-bold uppercase tracking-[0.12em] text-orange">
      <CheckCircle2 size={13} />
      {label}
    </span>
  );
}
