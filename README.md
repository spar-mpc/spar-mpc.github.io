# SPAR-MPC research website

Static React, TypeScript, and Vite page for **Fault-Aware Fleet Recovery Scheduling
with Service-Preserving Active Diagnosis**, by Carlo Schreiber, Duncan Eddy, and
Mykel J. Kochenderfer, Stanford University. No backend, API, or solver is required.

## Development

Use Node.js **22.12+** (or **20.19+**) and npm.

```sh
npm ci
npm run dev
```

Build and preview the production site with `npm run build` and `npm run preview`.

## GitHub Pages

Push to `main` and choose **GitHub Actions** under **Settings → Pages → Build and
deployment**. `.github/workflows/pages.yml` builds and tests pull requests and
pushes to `main`; successful pushes deploy `dist/`.

The repository `spar-mpc/spar-mpc.github.io` serves at
`https://spar-mpc.github.io/`. Relative asset paths (`base: './'`) and anchor
navigation also support project Pages URLs without server routing.

## 3D globe

`src/data/globeDemo.ts` defines the deterministic model; `src/demos/OrbitScene.ts`
renders it with Three.js, and `src/demos/FleetDemo.tsx` manages visibility and accessible scene state.
Eight satellites orbit a photographic NASA Earth, with station dots
at KSAT's Svalbard, Tromsø, and Troll sites. Contact eligibility follows geometric
elevation above each station's horizon. The illustration assigns at most one
satellite per station and one station per satellite. Gray links represent routine
service, blue links diagnosis, and red links recovery commands.

The animation runs automatically while visible and suspends offscreen or in a
hidden tab. Reduced motion keeps the satellites and contact signals still.
Drag or touch the globe, or use arrow keys on its focused canvas, to rotate the
view. Station dots have no on-globe name labels. A subtle legend identifies
routine, diagnosis, and recovery contacts.

If WebGL is unavailable, an SVG schematic shows the same contacts and follows
the same automatic-animation and reduced-motion behavior.

Station coordinates come from USGS, NASA, and the Brahe dataset. They locate
approximate sites on a sphere; the illustration does not reproduce KSAT's
operational capacity or schedules. Orbits, timing, and action assignments are
synthetic, separate from the paper experiments. A recovery contact represents a
command to an autonomous procedure, not proof of completed recovery.

The local 2048 × 1024 NASA Earth texture is `public/textures/earth-day.jpg`
(348 KiB). Lighting and satellite appearance are set in
`src/demos/OrbitScene.ts`. Texture credits, usage terms, geographic orientation,
and station-coordinate sources are recorded in
[public/textures/README.md](public/textures/README.md).

`src/App.tsx` contains the manuscript's full abstract and the page layout.
`src/components/Optimization.tsx` explains the scheduling and diagnosis idea in
one paragraph. The presentation follows the
[Nerfies research website](https://github.com/nerfies/nerfies.github.io), with
custom React components and CSS. `src/data/site.ts` stores the publication
URLs, citation, and Table I results for SPAR-MPC and four baselines. The results
chart toggles between deadline-weighted completion and lethal recovery. Styles
are in `src/styles/`; reusable page components are in `src/components/`.

## Publication resources

Set arXiv and research-code URLs in `src/data/site.ts`.
The header shows arXiv, Code, and BibTeX tags; unconfigured resource tags are
inactive. The citation is visible with a copy button. The **Website source** link
points to this repository.

**`SPAR_MPC-17.pdf` is local reference material only.** `/SPAR_MPC*.pdf` is ignored
by Git and is absent from `public/` and the build. To publish an approved
manuscript later, add `public/paper.pdf` and set its URL to
`${import.meta.env.BASE_URL}paper.pdf`.

## Verification

```sh
npx playwright install chromium
npm run build
npm test
```

An existing Chrome installation can be used with
`PLAYWRIGHT_CHANNEL=chrome npm test`. Browser checks are in `tests/`.
