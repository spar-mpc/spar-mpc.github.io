# Contributing

Bug reports, fixes, and examples are welcome. Open an
[issue](https://github.com/spar-mpc/spar-mpc.github.io/issues) or submit a pull
request with a short description of the change and how you checked it.

For solver bugs, include a small reproducible problem, the expected result, and
your Python and Gurobi versions. For website bugs, include the browser and steps
to reproduce the issue.

## Solver changes

Follow the [solver setup](solver/README.md), then run these from the repository root:

```sh
python -m pytest solver/tests
python -m ruff check solver
python -m ruff format --check solver
```

Add a regression test when changing scheduling behavior. For small cases, a
hand-computed or exhaustive solution is useful for checking the MILP. Explain
any changes to the objective, constraints, or commitment rules in the pull request.
Keep fleet-specific models in examples or adapters.

## Website changes

Use Node.js 22.12+ and npm:

```sh
npm ci
npx playwright install chromium
npm run build
npm test
```

Check visible changes at desktop and mobile widths. Keep generated files, local
environments, and reference manuscripts out of commits. Documentation-only
changes need a check of the text, links, and commands; they do not need new tests.

Contributions use the repository's [MIT license](LICENSE).
