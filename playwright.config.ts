import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests', timeout: 45_000, workers: 1, reporter: 'list',
  outputDir: '.qa/test-results',
  use: { baseURL: 'http://127.0.0.1:5173', channel: 'chrome', headless: true, viewport: { width: 1440, height: 1000 }, launchOptions: { args: ['--enable-webgl', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'] } },
  webServer: { command: 'npm run dev', url: 'http://127.0.0.1:5173', reuseExistingServer: true },
});
