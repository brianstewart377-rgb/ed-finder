export function OptimiserErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="rounded border border-gold/40 bg-gold/10 px-3 py-2 font-mono text-xs text-gold">
      Optimiser candidates are unavailable: {message}
      <button type="button" onClick={onRetry} className="ml-2 underline hover:text-orange">
        retry
      </button>
    </div>
  );
}
