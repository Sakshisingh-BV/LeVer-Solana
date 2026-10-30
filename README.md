# LeVer frontend

React + TypeScript + Vite. Charcoal and mint landing page, Ethereum/Solana builder,
existing source viewer, and the supplied procedural Flow Wave scene.

Run `npm install`, then `npm run dev`. Open http://127.0.0.1:5173.
Use `npm run build` for the production build and `npm run preview` to inspect it.

- `/`: landing page and unified builder.
- `/build`: focused contract builder.
- `/runs`: locally saved generation requests.
- `/preview/solidity` and `/preview/solana`: explicitly labeled sample output.
- `/flow-wave/index.html`: standalone, self-contained scene. Three.js r143 loads
  from unpkg using an importmap; internet access is required for those modules.

## Generation integration

The repository contains Python CLI pipelines, but no connected HTTP generation
service. The frontend therefore shows a clear connection error and saves the
requirement when no service is configured. It never simulates pipeline progress.

Set `VITE_GENERATION_URL` in `.env.local` to an actual HTTP bridge URL and restart
Vite. This is an explicit frontend integration contract, not a claim that the
existing Python CLI exposes this endpoint. `/api` can be proxied to port 8000 by
the included Vite development config. Production needs its own proxy or CORS.

The bridge receives a JSON `RunInput` from `src/types/run.ts`: `name`,
`requirement`, `target` (`solidity` or `solana`), `mode` (`lean`, `no_lean`,
`full`), `maxIterations`, and `attackRounds`. The bridge must map UI `lean` to
CLI `lean_only`; no CLI behavior has been changed. Other modes remain unchanged.
Mode descriptions are centralized in `src/data/modes.ts`.

Return `application/json` with a `GenerationResult` defined in `src/types/run.ts`,
or `application/x-ndjson` with newline-delimited events:

```json
{"type":"progress","stage":"Requirement Analysis"}
{"type":"progress","stage":"Code Generation","log":{"level":"info","message":"Source generated"}}
{"type":"result","result":{"files":[{"path":"Contract.sol","language":"solidity","content":"..."}]}}
```

Only send stages when the backend actually enters them. Use `type: "error"`
with `message` for stream errors. Verification checks, issues, logs and summaries
are optional; absent evidence is displayed as absent. Requests time out after
two minutes; stopping the browser request does not guarantee backend cancellation.
Do not place LLM API keys in frontend environment variables.

## Animation

`public/flow-wave/index.html` contains the supplied seven shaders verbatim, fixed
constants, `SphereGeometry(4.2, 200, 600)`, three composers, 300 motes, scroll dive
and pointer repulsion. `?embed` hides the 620vh scroll host and accepts same-origin
scroll/pointer messages from React. The standalone page retains its own scroll.
Reduced motion renders a still frame; background tabs and offscreen embeds pause.
The header motion toggle is persistent. WebGL/CDN failures fall back to a gradient.

The previous main layout files were copied to `.backups/pre-flow-wave` before
replacement. The old standalone starfield remains under `public/starfield`.

## Validation

`npm test` runs the six Playwright browser checks in installed Google Chrome.
The checks cover the WebGL scene, navigation, mobile layout, selections, request
validation, source download, and the configurable HTTP bridge. Bridge tests use
intercepted responses; they do not establish that the real Python service works.
Screenshots and test output are stored under `.qa/`.
