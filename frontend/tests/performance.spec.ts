import { test, expect } from '@playwright/test';

test('ambient loop caps draws and cancels work while paused, hidden or disposed', async ({ page }) => {
  await page.route('**/__ambient_test', route => route.fulfill({ contentType: 'text/html', body: '<title>Loop test</title>' }));
  await page.goto('/__ambient_test');
  const report = await page.evaluate(async () => {
    const path = '/ambient-loop.js';
    const { createAmbientLoop } = await import(/* @vite-ignore */ path);
    const callbacks = new Map<number, FrameRequestCallback>();
    let id = 0, now = 0, hidden = false, reduced = false;
    const media = new EventTarget();
    Object.defineProperty(media, 'matches', { get: () => reduced });
    window.matchMedia = () => media as MediaQueryList;
    Object.defineProperty(document, 'hidden', { configurable: true, get: () => hidden });
    window.requestAnimationFrame = callback => { callbacks.set(++id, callback); return id; };
    window.cancelAnimationFrame = handle => { callbacks.delete(handle); };
    const advance = (frames: number) => {
      for (let i = 0; i < frames; i++) {
        now += 1000 / 60;
        const pending = [...callbacks.values()]; callbacks.clear();
        for (const callback of pending) callback(now);
      }
    };
    const draws: { dt: number; reduced: boolean }[] = [];
    const loop = createAmbientLoop((_now: number, dt: number, reduced: boolean) => draws.push({ dt, reduced }));
    advance(60);
    const fps = draws.length;
    loop.setPaused(true); advance(60);
    const pausedDraws = draws.length - fps, pausedCallbacks = callbacks.size;
    hidden = true; document.dispatchEvent(new Event('visibilitychange'));
    loop.setPaused(false); advance(60);
    const hiddenDraws = draws.length - fps, hiddenCallbacks = callbacks.size;
    hidden = false; document.dispatchEvent(new Event('visibilitychange')); advance(1);
    const resumeDelta = draws.at(-1)?.dt;
    reduced = true; media.dispatchEvent(new Event('change'));
    const beforeReduced = draws.length; advance(60);
    const reducedDraws = draws.length - beforeReduced, reducedCallbacks = callbacks.size;
    loop.setPaused(true); loop.setPaused(false); advance(60);
    const reducedResumeDraws = draws.length - beforeReduced;
    reduced = false; media.dispatchEvent(new Event('change')); advance(60);
    const restarted = draws.length > beforeReduced + 2;
    loop.dispose(); const beforeDispose = draws.length;
    loop.requestRender(); document.dispatchEvent(new Event('visibilitychange')); advance(60);
    return { fps, pausedDraws, pausedCallbacks, hiddenDraws, hiddenCallbacks, resumeDelta,
      reducedDraws, reducedCallbacks, reducedResumeDraws, restarted, disposedDraws: draws.length - beforeDispose, disposedCallbacks: callbacks.size };
  });
  expect(report).toEqual({ fps: 30, pausedDraws: 0, pausedCallbacks: 0, hiddenDraws: 0, hiddenCallbacks: 0,
    resumeDelta: 0, reducedDraws: 1, reducedCallbacks: 0, reducedResumeDraws: 2, restarted: true, disposedDraws: 0, disposedCallbacks: 0 });
});

test('landing bridge batches input, pauses outside the hero and unmounts in the workspace', async ({ page }) => {
  await page.route('**/api/health', route => route.fulfill({ json: { llm: { model: 'test' } } }));
  await page.route('**/api/capabilities', route => route.fulfill({ json: { targets: [] } }));
  await page.route('**/flow-wave/index.html?embed', route => route.fulfill({ contentType: 'text/html', body: `<script>
    window.updates = [];
    addEventListener('message', event => { if (event.data?.type === 'lever:flow-wave') window.updates.push(event.data); });
    parent.postMessage({ type: 'lever:flow-wave-ready' }, location.origin);
  </script>` }));
  await page.goto('/');
  const iframe = page.locator('iframe');
  await expect(iframe).toHaveCount(1);
  const scene = page.frames().find(frame => frame.url().includes('/flow-wave/'))!;
  const lastPause = () => scene.evaluate(() => (window as any).updates.filter((u: any) => typeof u.paused === 'boolean').at(-1)?.paused);
  await expect.poll(lastPause).toBe(false);
  await page.waitForTimeout(100);
  await scene.evaluate(() => { (window as any).updates = []; });
  await page.evaluate(() => {
    for (let i = 0; i < 100; i++) {
      dispatchEvent(new MouseEvent('mousemove', { clientX: i, clientY: i }));
      dispatchEvent(new Event('scroll'));
    }
  });
  await expect.poll(() => scene.evaluate(() => (window as any).updates.length)).toBe(1);
  expect(await scene.evaluate(() => (window as any).updates[0])).toMatchObject({ x: 99 / 1440 * 2 - 1, y: -(99 / 1000 * 2 - 1), scroll: 0 });
  await page.evaluate(() => scrollTo({ top: document.documentElement.scrollHeight, behavior: 'instant' }));
  await expect.poll(lastPause).toBe(true);
  await scene.evaluate(() => { (window as any).updates = []; });
  await page.evaluate(() => { dispatchEvent(new MouseEvent('mousemove')); dispatchEvent(new Event('scroll')); });
  await page.waitForTimeout(100);
  expect(await scene.evaluate(() => (window as any).updates.length)).toBe(0);
  await page.evaluate(() => scrollTo({ top: 0, behavior: 'instant' }));
  await expect.poll(lastPause).toBe(false);
  await page.evaluate(() => {
    Object.defineProperty(document, 'hidden', { configurable: true, value: true });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await expect.poll(lastPause).toBe(true);
  await page.evaluate(() => {
    Object.defineProperty(document, 'hidden', { configurable: true, value: false });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await expect.poll(lastPause).toBe(false);
  await page.getByRole('button', { name: 'Pause background animation' }).click();
  await expect(iframe).toHaveCount(0);
  await page.getByRole('button', { name: 'Enable background animation' }).click();
  await expect(iframe).toHaveCount(1);
  await page.getByRole('link', { name: 'Open builder', exact: true }).click();
  await expect(iframe).toHaveCount(0);
});

for (const sceneName of ['starfield', 'flow-wave']) {
  test(`${sceneName} renders at capped DPR without bloom and redraws after resize`, async ({ browser, baseURL }) => {
    const context = await browser.newContext({ baseURL, deviceScaleFactor: 2, viewport: { width: 800, height: 600 } });
    const page = await context.newPage();
    const errors: string[] = [], bloomRequests: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('console', message => { if (message.type() === 'error') errors.push(`${message.text()} (${message.location().url})`); });
    page.on('request', request => { if (request.url().includes('UnrealBloomPass')) bloomRequests.push(request.url()); });
    await page.goto(`/${sceneName}/index.html`);
    const canvas = page.locator('#scene');
    await expect.poll(() => canvas.evaluate((node: HTMLCanvasElement) => node.width)).toBe(1200);
    await expect(page.locator('#fallback')).toBeHidden();
    expect(await canvas.evaluate((node: HTMLCanvasElement) => node.getContext('webgl')?.getContextAttributes()?.antialias)).toBe(false);
    await page.waitForTimeout(1800);
    await page.screenshot({ path: `.qa/${sceneName}-optimized.png` });
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.setViewportSize({ width: 640, height: 480 });
    await expect.poll(() => canvas.evaluate((node: HTMLCanvasElement) => node.width)).toBe(960);
    await expect(page.locator('#fallback')).toBeHidden();
    expect(bloomRequests).toEqual([]);
    expect(errors).toEqual([]);
    await context.close();
  });
}

test('backend polling stops while hidden and refreshes on return', async ({ page }) => {
  let healthChecks = 0;
  await page.route('**/api/health', route => { healthChecks++; return route.fulfill({ json: { llm: { model: 'test' } } }); });
  await page.route('**/api/capabilities', route => route.fulfill({ json: { targets: [] } }));
  await page.clock.install();
  await page.goto('/build');
  await expect.poll(() => healthChecks).toBeGreaterThan(0);
  await page.evaluate(() => {
    Object.defineProperty(document, 'hidden', { configurable: true, value: true });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  const beforeHidden = healthChecks;
  await page.clock.runFor(90_000);
  expect(healthChecks).toBe(beforeHidden);
  await page.evaluate(() => {
    Object.defineProperty(document, 'hidden', { configurable: true, value: false });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await expect.poll(() => healthChecks).toBe(beforeHidden + 1);
  await page.clock.runFor(31_000);
  await expect.poll(() => healthChecks).toBe(beforeHidden + 2);
});
