import { useState } from 'react';

export function OptimiserErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  const [showDetails, setShowDetails] = useState(false);

  return (
    <div className="rounded border border-gold/40 bg-gold/10 px-3 py-3 font-mono text-xs text-gold">
      <div className="font-bold text-gold">
        Suggested Builds are temporarily unavailable. You can still edit your Build Plan manually or try again.
      </div>
      <button
        type="button"
        onClick={onRetry}
        className="mt-2 rounded border border-gold/50 px-2 py-1 text-[11px] font-bold uppercase tracking-[0.12em] hover:border-orange hover:text-orange"
      >
        Retry
      </button>
      <div className="mt-2 text-[11px] text-silver-dk">
        <button
          type="button"
          aria-expanded={showDetails}
          onClick={() => setShowDetails((value) => !value)}
          className="text-gold underline hover:text-orange"
        >
          {showDetails ? 'Hide technical details' : 'Show technical details'}
        </button>
        {showDetails && (
          <pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap rounded border border-border/60 bg-bg2/70 p-2 text-silver-dk">
            {message}
          </pre>
        )}
      </div>
    </div>
  );
}
