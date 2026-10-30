import { Component } from 'react';
import type { ErrorInfo, ReactNode } from 'react';
export class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch(error: Error, info: ErrorInfo) { console.error('LeVer interface error', error, info); }
  render() { return this.state.failed ? <div className="empty-state"><h1>Something went wrong.</h1><p>Reload to restore your saved workspace.</p><button className="button primary" onClick={() => location.reload()}>Reload workspace</button></div> : this.props.children; }
}
