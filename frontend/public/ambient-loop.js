/** A single, visibility-aware render loop for decorative scenes. */
export function createAmbientLoop(draw, { paused = false } = {}) {
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
  const frameInterval = 1000 / 30;
  let frame = 0, lastDraw = null, disposed = false;

  function stop() {
    cancelAnimationFrame(frame);
    frame = 0;
    lastDraw = null;
  }

  function render(now) {
    frame = 0;
    if (disposed || paused || document.hidden) return;
    const elapsed = lastDraw === null ? 0 : now - lastDraw;
    // Small tolerance accounts for rAF timestamp jitter at 60 Hz.
    if (lastDraw !== null && elapsed < frameInterval - 0.5) {
      frame = requestAnimationFrame(render);
      return;
    }
    lastDraw = now;
    draw(now, reducedMotion.matches ? 0 : Math.min(elapsed / 1000, 0.05), reducedMotion.matches);
    if (!reducedMotion.matches) frame = requestAnimationFrame(render);
  }

  function requestRender() {
    stop();
    if (!disposed && !paused && !document.hidden) frame = requestAnimationFrame(render);
  }

  document.addEventListener('visibilitychange', requestRender);
  reducedMotion.addEventListener('change', requestRender);
  requestRender();
  return {
    requestRender,
    setPaused(value) {
      if (paused === value) return;
      paused = value;
      requestRender();
    },
    dispose() {
      disposed = true;
      stop();
      document.removeEventListener('visibilitychange', requestRender);
      reducedMotion.removeEventListener('change', requestRender);
    },
  };
}
