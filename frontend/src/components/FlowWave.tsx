import { useEffect, useRef } from 'react';

/** The exact standalone scene runs independently from React's render cycle. */
export function FlowWave({ enabled }: { enabled: boolean }) {
  const ref = useRef<HTMLIFrameElement>(null);
  useEffect(() => {
    if (!enabled) return;
    const send = (data: Record<string, unknown>) => ref.current?.contentWindow?.postMessage({ type: 'lever:flow-wave', ...data }, location.origin);
    const scroll = () => send({ scroll: window.scrollY / Math.max(1, document.documentElement.scrollHeight - innerHeight), paused: window.scrollY > innerHeight * 1.4 });
    const pointer = (event: MouseEvent) => send({ x: event.clientX / innerWidth * 2 - 1, y: -(event.clientY / innerHeight * 2 - 1) });
    const leave = (event: MouseEvent) => { if (!event.relatedTarget) send({ active: false }); };
    const ready = (event: MessageEvent) => { if (event.origin === location.origin && event.source === ref.current?.contentWindow && event.data?.type === 'lever:flow-wave-ready') scroll(); };
    window.addEventListener('mousemove', pointer, { passive: true }); window.addEventListener('mouseout', leave); window.addEventListener('scroll', scroll, { passive: true }); window.addEventListener('message', ready);
    return () => { window.removeEventListener('mousemove', pointer); window.removeEventListener('mouseout', leave); window.removeEventListener('scroll', scroll); window.removeEventListener('message', ready); };
  }, [enabled]);
  return <div className="flow-background" aria-hidden="true">{enabled && <iframe ref={ref} src="/flow-wave/index.html?embed" title="Decorative Flow Wave animation" tabIndex={-1}/>}</div>;
}
