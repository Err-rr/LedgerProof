# LedgerProof web

Next.js 14 App Router dashboard for the reconciliation API in `../api/`. No
mock data anywhere in this app -- every figure comes from a real run through
the real FastAPI backend.

## Local development

```bash
npm install
cp .env.example .env.local   # point LEDGERPROOF_API_BASE_URL at a running api/
npm run dev
```

`LEDGERPROOF_API_BASE_URL` is server-only (never `NEXT_PUBLIC_`) -- the
browser never talks to the API directly, only to this app's own route
handlers (`app/api/**`), which proxy to it server-side.

To develop against the real API without Neon/S3/Anthropic credentials, run
the backend's in-memory dev server from the repo root:

```bash
python scripts/dev_api_server.py --port 8000
```

This is the real `api/main.py` FastAPI app -- real routers, real
`core.passes` matching engine on whatever you actually upload -- with only
the database and object storage swapped for in-memory fakes. Restarting it
forgets every run, on purpose.

## Architecture notes

- **Server components by default.** Screens 02-04 fetch directly from the
  API server-side (`lib/api-client.ts`). Only screen 01 (upload + polling)
  and the interactive parts of screen 03 (filters, row expand, approve/reject)
  are client components.
- **No component library.** Everything is hand-rolled against the tokens in
  `app/tokens.css`; Tailwind (`tailwind.config.ts`) just maps utility classes
  onto those CSS custom properties.
- **Screen 01's "progress" is honest, not simulated.** `POST /runs` runs all
  four matching passes synchronously in one request -- there is no mid-run
  status to poll. The upload screen shows a real elapsed timer, not a fake
  per-pass animation; what each pass actually did (matches, exceptions,
  timing) is real data shown on the summary screen once the run completes
  (`RunSummary.stages`, added to the API specifically for this).
- **Screen 04 required one new backend endpoint** (`GET /runs/{id}/match-records`)
  that didn't exist before this screen was built -- there was previously no
  way to read match_records at all. Also added: `POST /exceptions/{id}/propose`
  (generates the resolution agent's hypothesis on demand; never writes
  anything -- a human still has to call `/resolve` with `approved: true`).

## Deploying to AWS Amplify

1. Connect this repository to an Amplify Hosting app.
2. Set the app's monorepo root to `web/` (Amplify's build settings ->
   "App settings" -> monorepo). `amplify.yml` in this directory is the build
   spec Amplify picks up automatically.
3. In Amplify's environment variables, set `LEDGERPROOF_API_BASE_URL` to the
   deployed API Gateway URL from `deploy/deploy.sh` (see the repo root
   README). Never commit this value.
4. Amplify detects the Next.js SSR output automatically (this app uses
   route handlers and dynamic server-rendered pages, so it deploys as an
   SSR compute app, not a static export).

## Known dependency notes

- Pinned to the latest Next.js **14.x** patch (14.2.35) rather than the
  version originally scaffolded with, which had unpatched CVEs on the npm
  registry; staying on the 14.x line per the brief rather than jumping to
  Next 16.
- `xlsx` (used client-side only, for the row-count preview on screen 01) is
  installed from SheetJS's own CDN tarball rather than the npm registry --
  the npm-published build has known unpatched CVEs; SheetJS's own fixed
  builds are only distributed that way. Low real risk here regardless: it
  only ever parses a file the same user is uploading, for an informational
  preview -- the actual parse that matters happens server-side in
  `api/reconcile.py`.
- `npm audit` still reports advisories against `next` (largely fixed in
  14.2.35 but the tool reports the full historical CVE range for the
  package) and against `postcss` (a transitive, build-time-only dependency
  bundled by Next.js itself, not by anything in this app). Both would clear
  with `next@16`, which is out of scope for a "Next.js 14" app.
