# SPAR-MPC

Code and [project website](https://spar-mpc.github.io/) for *Fault-Aware Fleet
Recovery Scheduling with Service-Preserving Active Diagnosis*, by Carlo
Schreiber, Duncan Eddy, and Mykel J. Kochenderfer.

The [Python solver](solver/README.md) uses Gurobi to schedule fleet service,
diagnosis, and recovery. It includes a small robot-fleet example.

## Run the website

Use Node.js 22.12+ and npm.

```sh
npm ci
npm run dev
```

To build and test:

```sh
npx playwright install chromium
npm run build
npm test
```

GitHub Actions deploys `dist/` to GitHub Pages after successful pushes to `main`.

## Files

- `solver/`: Python package, example, and solver tests.
- `src/`: React website and Three.js globe. Publication links and results are in
  `src/data/site.ts`.
- `tests/`: desktop and mobile browser tests.

The globe is an illustration, separate from the paper's experiments. Local
reference PDFs are ignored by Git and excluded from the website build.

## Contributing and license

See [CONTRIBUTING.md](CONTRIBUTING.md) for bug reports, pull requests, and checks.
The code is released under the [MIT license](LICENSE). Dependencies and external
assets retain their own terms.

The page layout was inspired by [Nerfies](https://github.com/nerfies/nerfies.github.io).
Earth imagery and station sources are credited in
[public/textures/README.md](public/textures/README.md).
