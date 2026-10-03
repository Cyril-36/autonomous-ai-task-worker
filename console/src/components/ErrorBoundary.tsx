import { Component, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  message: string | null;
}

/** Keeps a rendering fault in one run from blanking the whole console. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { message: null };

  static getDerivedStateFromError(error: unknown): State {
    return { message: error instanceof Error ? error.message : "Unknown error" };
  }

  render() {
    if (this.state.message === null) return this.props.children;
    return (
      <section className="col-main">
        <div className="sheet sheet-pad stack" role="alert">
          <h2 className="sheet-title">This view hit an error</h2>
          <p className="muted">The run itself is unaffected; only the display failed. Reload to show it again.</p>
          <p className="mono muted" style={{ fontSize: 12 }}>{this.state.message}</p>
          <div className="actions">
            <button type="button" className="btn btn-primary" onClick={() => window.location.reload()}>Reload</button>
          </div>
        </div>
      </section>
    );
  }
}
