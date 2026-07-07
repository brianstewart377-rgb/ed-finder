import { Component, type ErrorInfo, type ReactNode } from 'react';

interface ErrorBoundaryProps {
  children: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { hasError: false };

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('[ED:Finder] Critical UI error caught by boundary:', error, errorInfo);
  }

  render() {
    if (!this.state.hasError) return this.props.children;

    return (
      <main
        role="alert"
        aria-live="assertive"
        style={{
          minHeight: '100vh',
          display: 'grid',
          placeItems: 'center',
          padding: '2rem',
          background: 'radial-gradient(circle at 50% 0%, rgba(255, 122, 20, 0.18), transparent 34%), #05070a',
          color: '#f8fafc',
          fontFamily: 'system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
        }}
      >
        <section
          style={{
            width: 'min(100%, 34rem)',
            border: '1px solid rgba(255, 122, 20, 0.45)',
            borderRadius: '0.75rem',
            background: 'rgba(12, 16, 24, 0.94)',
            padding: '1.5rem',
            boxShadow: '0 24px 80px rgba(0, 0, 0, 0.45)',
          }}
        >
          <p
            style={{
              margin: 0,
              color: '#ff7a14',
              fontSize: '0.75rem',
              fontWeight: 800,
              letterSpacing: '0.16em',
              textTransform: 'uppercase',
            }}
          >
            ED:Finder UI Recovery
          </p>
          <h1 style={{ margin: '0.75rem 0 0', fontSize: '1.5rem', lineHeight: 1.2 }}>
            A critical UI error occurred
          </h1>
          <p style={{ margin: '0.75rem 0 0', color: '#d8dee9', lineHeight: 1.6 }}>
            Reload the application to clear the current UI state and reconnect to the planner.
          </p>
          <button
            type="button"
            onClick={() => window.location.reload()}
            style={{
              marginTop: '1.25rem',
              border: '1px solid rgba(255, 122, 20, 0.72)',
              borderRadius: '0.5rem',
              background: '#ff7a14',
              color: '#080a0e',
              cursor: 'pointer',
              fontWeight: 800,
              padding: '0.7rem 1rem',
            }}
          >
            Reload application
          </button>
        </section>
      </main>
    );
  }
}
