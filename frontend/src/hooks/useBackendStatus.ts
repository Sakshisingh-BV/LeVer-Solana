import { useEffect, useState } from 'react';
import { fetchBackendStatus } from '../lib/generation';
import type { BackendStatus } from '../types/run';

const initial: BackendStatus = { state: 'checking', targets: [] };

/** Live backend availability, polled through the central API layer. */
export function useBackendStatus(intervalMs = 30_000): BackendStatus {
  const [status, setStatus] = useState<BackendStatus>(initial);
  useEffect(() => {
    let cancelled = false;
    let controller: AbortController | null = null;
    let timer: number | undefined;
    function stop() {
      window.clearTimeout(timer);
      controller?.abort();
      controller = null;
    }
    async function check() {
      if (cancelled || document.hidden || controller) return;
      const request = new AbortController();
      controller = request;
      try {
        const next = await fetchBackendStatus(request.signal);
        if (!cancelled && !request.signal.aborted) setStatus(next);
      } catch (error) {
        if (cancelled || request.signal.aborted) return;
        setStatus({ state: 'offline', targets: [], error: error instanceof Error ? error.message : 'Backend unreachable.', checkedAt: new Date().toISOString() });
      } finally {
        if (controller === request) {
          controller = null;
          if (!cancelled && !document.hidden) timer = window.setTimeout(check, intervalMs);
        }
      }
    }
    const onVisibility = () => { if (document.hidden) stop(); else void check(); };
    void check();
    document.addEventListener('visibilitychange', onVisibility);
    return () => { cancelled = true; stop(); document.removeEventListener('visibilitychange', onVisibility); };
  }, [intervalMs]);
  return status;
}
