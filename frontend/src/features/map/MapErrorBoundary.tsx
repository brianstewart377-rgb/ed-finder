import { Component, type ErrorInfo, type ReactNode } from 'react';

interface MapErrorBoundaryProps {
  children: ReactNode;
}

interface MapErrorBoundaryState {
  hasError: boolean;
}

export class MapErrorBoundary extends Component<MapErrorBoundaryProps, MapErrorBoundaryState> {
  state: MapErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError(): MapErrorBoundaryState {
    return { hasError: true };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('[ED:Finder] Map UI error caught by boundary:', error, errorInfo);
  }

  private handleRetry = () => {
    this.setState({ hasError: false });
  };

  render() {
    if (!this.state.hasError) return this.props.children;

    return (
      <section
        role="alert"
        aria-live="polite"
        data-testid="map-error-boundary"
        className="panel-thin flex min-h-[400px] flex-col items-center justify-center gap-3 px-6 py-10 text-center"
      >
        <p className="font-display text-orange text-sm tracking-[0.14em]">Map temporarily unavailable</p>
        <p className="max-w-md text-xs text-silver-dk">
          The map hit an unexpected rendering error. The rest of ED:FINDER is still available.
        </p>
        <button
          type="button"
          onClick={this.handleRetry}
          className="rounded border border-orange/60 bg-orange/15 px-3 py-2 font-mono text-xs text-orange transition-colors hover:bg-orange/25"
        >
          Retry map
        </button>
      </section>
    );
  }
}
