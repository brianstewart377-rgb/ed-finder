import { Play } from 'lucide-react';
import type { ComponentProps, ReactNode } from 'react';
import { PreviewResultSection } from './PreviewResultSection';

export function PreviewWorkspaceView({
  canRun,
  running,
  onRunPreview,
  roleContext,
  ...previewProps
}: ComponentProps<typeof PreviewResultSection> & {
  canRun: boolean;
  running: boolean;
  onRunPreview: () => void;
  roleContext?: ReactNode;
}) {
  const previewState = running
    ? 'Preview running'
    : !previewProps.result
      ? 'Preview not run'
      : previewProps.isResultStale
        ? 'Preview stale'
        : 'Preview current';

  return (
    <div className="space-y-3" data-testid="preview-workspace-view">
      <section className="rounded-chunk-lg border border-orange/25 bg-orange/5 px-3 py-2">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="font-mono">
            <div className="text-[10px] uppercase tracking-[0.16em] text-orange">Preview control</div>
            <p className="mt-0.5 text-[11px] leading-snug text-silver-dk">
              <span className="font-bold text-orange">{previewState}</span>
              <span className="ml-2">Preview runs only when you click Run Preview.</span>
            </p>
          </div>
          <button
            type="button"
            onClick={onRunPreview}
            disabled={!canRun}
            className="inline-flex items-center gap-2 rounded-chunk-sm border border-orange/50 bg-orange/15 px-3 py-2 text-xs font-mono font-bold text-orange hover:bg-orange/25 disabled:cursor-not-allowed disabled:opacity-45"
          >
            <Play size={14} />
            {running ? 'Running' : 'Run Preview'}
          </button>
        </div>
      </section>
      {roleContext}
      <PreviewResultSection {...previewProps} />
    </div>
  );
}
