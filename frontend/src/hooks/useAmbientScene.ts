import { useEffect, useRef } from 'react';

type SceneUpdate = { x?: number; y?: number; active?: boolean };

/** Batch input events, and suspend the iframe when its visible region leaves view. */
export function useAmbientScene(enabled: boolean, type: string, paused = false, visibilitySelector?: string) {
  const ref = useRef<HTMLIFrameElement>(null);
  useEffect(() => {
    const iframe = ref.current;
    if (!enabled || !iframe) return;
    let frame = 0;
    let inView = false;
    let latest: SceneUpdate = {};
    const inactive = () => paused || document.hidden || !inView;
    const send = (data: Record<string, unknown>) => iframe.contentWindow?.postMessage({ type, ...data }, location.origin);
    const flush = () => {
      frame = 0;
      if (inactive()) return;
      send({ ...latest, scroll: window.scrollY / Math.max(1, document.documentElement.scrollHeight - innerHeight) });
      latest = {};
    };
    const queue = () => { if (!inactive() && !frame) frame = requestAnimationFrame(flush); };
    const syncVisibility = () => {
      cancelAnimationFrame(frame);
      frame = 0;
      // Control messages must not wait for rAF, which stops in hidden tabs.
      send({ paused: inactive(), active: false });
      latest = {};
      queue();
    };
    const pointer = (event: MouseEvent) => {
      if (inactive()) return;
      latest = { x: event.clientX / innerWidth * 2 - 1, y: -(event.clientY / innerHeight * 2 - 1), active: true };
      queue();
    };
    const leave = (event: MouseEvent) => { if (!event.relatedTarget) { latest = { active: false }; queue(); } };
    const ready = (event: MessageEvent) => {
      if (event.origin === location.origin && event.source === iframe.contentWindow && event.data?.type === `${type}-ready`) syncVisibility();
    };
    // FlowWave is fixed, so observe the hero it decorates instead of the iframe.
    const region = (visibilitySelector && document.querySelector(visibilitySelector)) || iframe;
    const observer = new IntersectionObserver(([entry]) => {
      inView = entry.isIntersecting;
      syncVisibility();
    });
    observer.observe(region);
    syncVisibility();
    window.addEventListener('mousemove', pointer, { passive: true });
    window.addEventListener('mouseout', leave);
    window.addEventListener('scroll', queue, { passive: true });
    window.addEventListener('resize', queue);
    window.addEventListener('message', ready);
    document.addEventListener('visibilitychange', syncVisibility);
    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      send({ paused: true, active: false });
      window.removeEventListener('mousemove', pointer);
      window.removeEventListener('mouseout', leave);
      window.removeEventListener('scroll', queue);
      window.removeEventListener('resize', queue);
      window.removeEventListener('message', ready);
      document.removeEventListener('visibilitychange', syncVisibility);
    };
  }, [enabled, type, paused, visibilitySelector]);
  return ref;
}
