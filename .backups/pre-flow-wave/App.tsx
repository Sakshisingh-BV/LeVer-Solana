import { useEffect, useState } from 'react';
import { Link, Route, Routes, useNavigate } from 'react-router-dom';
import { ArrowRight, Bell, X } from 'lucide-react';
import { AppShell } from './components/AppShell';
import { ErrorBoundary } from './components/ErrorBoundary';
import { useRuns } from './hooks/useRuns';
import { usePreference } from './hooks/usePreference';
import { previewRun } from './data/preview';
import NewRunPage from './pages/NewRunPage';
import RunDetailPage from './pages/RunDetailPage';
import RunHistoryPage from './pages/RunHistoryPage';
import PropertiesPage from './pages/PropertiesPage';
import { DocumentationPage, SettingsPage } from './pages/WorkspacePages';
import type { RunInput } from './types/run';

export default function App() {
  const { runs, startRun, cancelRun, storageWarning } = useRuns();
  const [toast, setToast] = useState('');
  const [ambient, setAmbient] = usePreference('lever.ambient', true);
  const navigate = useNavigate();
  useEffect(() => { if (!toast) return; const timer = window.setTimeout(() => setToast(''), 4500); return () => window.clearTimeout(timer); }, [toast]);
  function createRun(input: RunInput) {
    try { const id = startRun(input); navigate('/runs/' + id); } catch (error) { setToast(error instanceof Error ? error.message : 'Could not start this analysis.'); }
  }
  const detailProps = { runs, onCancel: cancelRun, onRetry: createRun, notify: setToast };
  return <>
    <AppShell ambient={ambient} onToggleAmbient={() => setAmbient(!ambient)}>
      {storageWarning && <div className="inline-notice">Browser storage is unavailable or full. Keep this tab open to preserve your session.</div>}
      <ErrorBoundary><Routes>
        <Route path="/" element={<NewRunPage onRun={createRun} notify={setToast} />} />
        <Route path="/runs" element={<RunHistoryPage runs={runs} />} />
        <Route path="/contracts" element={<RunHistoryPage runs={runs} contractsOnly />} />
        <Route path="/runs/:id" element={<RunDetailPage {...detailProps} />} />
        <Route path="/preview/solidity" element={<RunDetailPage key="preview-solidity" {...detailProps} preview={previewRun('solidity')} />} />
        <Route path="/preview/solana" element={<RunDetailPage key="preview-solana" {...detailProps} preview={previewRun('solana')} />} />
        <Route path="/properties" element={<PropertiesPage />} />
        <Route path="/docs" element={<DocumentationPage />} />
        <Route path="/settings" element={<SettingsPage ambient={ambient} setAmbient={setAmbient} />} />
        <Route path="*" element={<div className="empty-state"><h1>That page isn't here.</h1><Link className="button primary" to="/">Back to the studio<ArrowRight size={16} /></Link></div>} />
      </Routes></ErrorBoundary>
    </AppShell>
    {toast && <div className="toast" role="status"><Bell size={16} /><span>{toast}</span><button className="icon-button" aria-label="Dismiss notification" onClick={() => setToast('')}><X size={15} /></button></div>}
  </>;
}
