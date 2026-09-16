# SPAR-MPC

Python and Gurobi solver for fleet scheduling with active diagnosis. It first
maximizes sampled service, then adds decision-relevant diagnostics while
preserving that value.

## Installation

Requires Python 3.11+ and a Gurobi license suitable for your problem size.
From the repository root:

```sh
python -m venv .venv
source .venv/bin/activate
python -m pip install -e './solver[dev]'
```

The package installs `gurobipy`. See the official
[Gurobi installation guide](https://support.gurobi.com/hc/en-us/articles/360044290292-How-do-I-install-Gurobi-for-Python)
for environment and license setup.

## Example

```sh
python solver/examples/fleet.py --outcome drive
python solver/examples/fleet.py --outcome sensor
```

Two robots share a radio. A diagnostic determines whether one robot needs a
drive reset or should wait. The example prints the service anchor, the diagnostic
schedule, and the next plan after observing either outcome.

## Usage

Build a `Problem` from fixed-time `Action` candidates, resource capacities,
priorities, and joint service scenarios. Use `value_diagnostic` to value an
observation model and its available recovery responses, then call:

```python
from spar_mpc import solve

plan = solve(problem)
print(plan.selected)
print(plan.service, plan.anchor_service)
```

Retain `plan.commitments` when replanning. The
[complete example](examples/fleet.py) shows construction and observation handling;
the [model reference](docs/model.md) describes the inputs, guarantees, and
commitment lifecycle. Public types and functions are exported from `spar_mpc`.

## Tests

From the repository root:

```sh
python -m pytest solver/tests
python -m ruff check solver
```

## Contributing and license

See [CONTRIBUTING.md](../CONTRIBUTING.md) for development and pull requests.
The solver is released under the [MIT License](LICENSE). Gurobi is licensed
separately.
