import { test, expect } from '@playwright/test';

test('landing page renders the actual WebGL scene and navigates to the builder', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1 })).toContainText('Blockchain Code.');
  const scene = page.frameLocator('iframe');
  await expect.poll(async () => scene.locator('#scene').evaluate((canvas: HTMLCanvasElement) => canvas.width)).toBeGreaterThan(300);
  await expect(scene.locator('#fallback')).toBeHidden();
  await page.waitForTimeout(2200); // Allow the specified 1.4-second fade-in before visual capture.
  await page.screenshot({ path: '.qa/desktop-home.png' });
  await page.getByRole('link', { name: 'Get Started', exact: true }).click();
  await expect(page).toHaveURL(/#build$/);
  await expect(page.getByRole('heading', { name: 'Your next contract starts here.' })).toBeInViewport();
  expect(errors).toEqual([]);
});

test('builder validates input, preserves ecosystem and mode, and reports absent backend honestly', async ({ page }) => {
  await page.goto('/build');
  await page.getByRole('button', { name: 'Generate Smart Contract' }).click();
  await expect(page.getByRole('alert')).toContainText('Describe what');
  await page.getByRole('button', { name: /Solana Rust/ }).click();
  await page.getByRole('button', { name: 'No Lean Generation without the Lean verification path.' }).click();
  await page.getByLabel('What Would You Like to Build?').fill('Create a vault with owner-only withdrawals.');
  await page.getByRole('button', { name: /Ethereum Solidity/ }).click();
  await expect(page.getByLabel('What Would You Like to Build?')).toHaveValue('Create a vault with owner-only withdrawals.');
  await page.getByRole('button', { name: /Solana Rust/ }).click();
  await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
  await page.screenshot({ path: '.qa/desktop-builder.png', fullPage: true });
  await page.getByRole('button', { name: 'Generate Smart Contract' }).click();
  await expect(page.getByRole('alert')).toContainText('Backend not connected');
  await expect(page.locator('.detail-meta')).toContainText('Solana');
  await expect(page.locator('.detail-meta')).toContainText('no_lean');
  await expect(page.getByText('No source files yet', { exact: true })).toBeVisible();
  await page.getByRole('link', { name: 'Edit requirement' }).click();
  await expect(page.getByLabel('What Would You Like to Build?')).toHaveValue('Create a vault with owner-only withdrawals.');
  await expect(page.getByRole('button', { name: /Solana Rust/ })).toHaveAttribute('aria-pressed', 'true');
});

test('sample source supports search, download and ecosystem switching', async ({ page }) => {
  await page.goto('/preview/solidity');
  await expect(page.locator('.preview-notice')).toContainText('No code was generated or verified');
  await page.getByLabel('Search in code').fill('contract');
  await expect(page.locator('.code-line.highlighted').first()).toBeVisible();
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download source', exact: true }).click();
  expect((await downloadPromise).suggestedFilename()).toMatch(/\.sol$/);
  await page.getByRole('link', { name: 'Preview Solana' }).click();
  await expect(page.locator('.language-label')).toHaveText('rust');
  await page.getByRole('button', { name: 'Expand editor', exact: true }).click();
  await expect(page.locator('.code-workspace')).toHaveClass(/is-expanded/);
  await page.keyboard.press('Escape');
  await expect(page.locator('.code-workspace')).not.toHaveClass(/is-expanded/);
  await page.screenshot({ path: '.qa/source-workspace.png' });
});

test('mobile has no horizontal overflow and navigation works', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await page.screenshot({ path: '.qa/mobile-home.png', fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole('button', { name: 'Open menu' }).click();
  await page.getByRole('link', { name: 'Modes', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Choose Your Execution Mode' })).toBeInViewport();
  await expect(page.getByRole('button', { name: 'Open menu' })).toBeVisible();
  await page.goto('/build');
  await page.getByRole('button', { name: /Solana Rust/ }).click();
  await page.screenshot({ path: '.qa/mobile-builder.png', fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('HTTP adapter forwards the exact selections and consumes real streamed stages', async ({ page }) => {
  await page.goto('/build');
  let payload: unknown;
  await page.route('**/__test_generation', async route => {
    payload = route.request().postDataJSON();
    await route.fulfill({ contentType: 'application/x-ndjson', body: [
      JSON.stringify({ type: 'progress', stage: 'Code Generation' }),
      JSON.stringify({ type: 'result', result: { files: [{ path: 'lib.rs', language: 'rust', content: 'pub fn example() {}' }] } }),
    ].join('\n') });
  });
  const result = await page.evaluate(async () => {
    const path = '/src/lib/generation.ts'; const { createHttpAdapter } = await import(/* @vite-ignore */ path);
    const stages: string[] = [];
    const result = await createHttpAdapter('/__test_generation').generate({ name: 'Test', requirement: 'Test requirement', target: 'solana', mode: 'no_lean', maxIterations: 3, attackRounds: 3 }, { signal: new AbortController().signal, onProgress: (event: { stage: string }) => stages.push(event.stage) });
    return { result, stages };
  });
  expect(payload).toMatchObject({ target: 'solana', mode: 'no_lean', requirement: 'Test requirement' });
  expect(result.stages).toEqual(['Code Generation']);
  expect(result.result.files[0].language).toBe('rust');
});

test('HTTP adapter rejects wrong-ecosystem source and empty streams', async ({ page }) => {
  await page.goto('/build');
  await page.route('**/__test_bad', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify({ files: [{ path: 'wrong.sol', language: 'solidity', content: 'contract Wrong {}' }] }) }));
  await page.route('**/__test_empty', route => route.fulfill({ contentType: 'application/x-ndjson', body: '{"type":"progress","stage":"Requirement Analysis"}\n' }));
  const errors = await page.evaluate(async () => {
    const path = '/src/lib/generation.ts'; const { createHttpAdapter } = await import(/* @vite-ignore */ path);
    const errors = [];
    for (const endpoint of ['/__test_bad', '/__test_empty']) {
      try { await createHttpAdapter(endpoint).generate({ name: 'Test', requirement: 'Test', target: 'solana', mode: 'full', maxIterations: 3, attackRounds: 3 }, { signal: new AbortController().signal, onProgress: () => {} }); } catch (error) { errors.push((error as Error).message); }
    }
    return errors;
  });
  expect(errors[0]).toContain('does not match'); expect(errors[1]).toContain('without a result');
});
