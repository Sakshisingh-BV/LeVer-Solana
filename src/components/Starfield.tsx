import { useEffect, useRef } from 'react';

/** The supplied, standalone Three.js scene stays outside React's render cycle. */
export function Starfield({ enabled, paused }: { enabled: boolean; paused: boolean }) {
  const ref = useRef<HTMLIFrameElement>(null);
  useEffect(() => {
    if (!enabled) return;
    const send = (data: Record<string, unknown>) => ref.current?.contentWindow?.postMessage({ type: 'lever:starfield', ...data }, location.origin);
    const scroll = () => send({ scroll: window.scrollY / Math.max(1, document.documentElement.scrollHeight - innerHeight) });
    const pointer = (event: MouseEvent) => send({ x: event.clientX / innerWidth * 2 - 1, y: -(event.clientY / innerHeight * 2 - 1) });
    const leave = (event: MouseEvent) => { if (!event.relatedTarget) send({ active: false }); };
    const ready = (event: MessageEvent) => {
      if (event.origin === location.origin && event.source === ref.current?.contentWindow && event.data?.type === 'lever:starfield-ready') { send({ paused }); scroll(); }
    };
    send({ paused }); scroll();
    window.addEventListener('mousemove', pointer, { passive: true });
    window.addEventListener('mouseout', leave);
    window.addEventListener('scroll', scroll, { passive: true });
    window.addEventListener('message', ready);
    return () => { window.removeEventListener('mousemove', pointer); window.removeEventListener('mouseout', leave); window.removeEventListener('scroll', scroll); window.removeEventListener('message', ready); };
  }, [enabled, paused]);
  return <div className="ambient-background" aria-hidden="true">{enabled && <iframe ref={ref} src="/starfield/index.html?embed" title="Decorative starfield" tabIndex={-1} />}</div>;
}
