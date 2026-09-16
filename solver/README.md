# SPAR-MPC solver

A Python and Gurobi implementation of service-preserving active diagnosis for
fleets. The application supplies fixed-time candidate actions, joint sampled
service outcomes, and diagnostic observation models. The solver selects actions,
values recovery decisions, and retains commitments across replanning epochs.

This package is independent of the research website and has no satellite,
orbital-propagation, or simulation dependencies.

## Install and run

Use Python 3.11 or later and a Gurobi installation/license that supports your
problem size. `gurobipy` is installed as a package dependency; Gurobi's licensing
terms apply separately. See Gurobi's [Python installation guide](https://support.gurobi.com/hc/en-us/articles/360044290292-How-do-I-install-Gurobi-for-Python)
and [Python API reference](https://docs.gurobi.com/projects/optimizer/en/current/reference/python/overview.html).

From the repository root:

```sh
python -m pip install -e './solver[dev]'
python solver/examples/fleet.py --outcome drive
python solver/examples/fleet.py --outcome sensor
python -m pytest solver/tests
```

The example uses two ground robots sharing a radio. Diagnosing robot A can lead
to a drive reset or waiting; robot B has a routine upload. It prints the original
service schedule, the service-preserving diagnostic schedule, and a replan after
the supplied observation. Its two joint scenarios and all numeric values are
illustrative, not paper experiment results.

## Inputs

Import the public API from `spar_mpc`:

- `Action` describes an asset, action kind (`routine`, `diagnose`, or `recover`),
  start, end, feedback time, resource demands, and optional incompatibility
  groups. Actions are nonpreemptive. Use one consistent time unit and clock.
- `Problem` combines actions, positive asset priorities, resource capacities,
  sampled service rows, diagnostics, and retained `Commitments`.
- Each `service[action_id]` row contains one bounded credit per **joint**
  scenario. Every action has a row, including zeros for diagnostics. Column
  identities must agree across all actions; preserve relevant correlations
  between assets and competing actions when generating scenarios.
- `value_diagnostic` takes a class prior predicted to diagnostic feedback, a
  class-to-outcome likelihood table, and timely same-asset recovery rewards.
  It returns local expected value of information and a stored outcome-to-action
  map, including waiting. The recovery-attempt cost affects this local decision
  value; it does not change the sampled service objective.

The application generates candidate times and scenario credits. The solver
does not optimize arbitrary action start times, infer transition laws, or sample
the fleet's latent state. Different physical responses should have distinct
identifiers; use shared groups to declare mutually exclusive alternatives.
Same-asset actions are incompatible when their start-to-feedback intervals
overlap. Resource demands apply during half-open execution intervals
`[start, end)`, so a resource can be reused exactly at an action's end.

The pure helpers `predict`, `update`, `condition`, and `aggregate` propagate and
condition finite beliefs using supplied kernels. Impossible evidence raises an
error rather than adding probability floors. Aggregating modes into intervention
classes is appropriate only when the retained distinctions support the recovery
decisions being valued.

## Optimization and certificates

`solve(problem, options=SolverOptions(), env=None)` returns a `Plan`. Its
`anchor` maximizes average service, with each asset's contribution capped at one
in each scenario and normalized by asset priorities. The information stage
preserves that sampled service value while maximizing weighted local diagnostic
value. Deterministic tie-breaking prefers fewer actions.

Credited diagnostics must change the preferred response for sufficiently likely
outcomes, start before the next feedback, and preserve required service-anchor
actions. At most one diagnostic is credited per asset. Every combination of
possible stored responses is checked jointly against commitments, resource
capacity, and incompatibilities; rare outcomes remain part of this feasibility
check. Unobserved pending diagnostics from earlier solves retain their promises.

By default, `Problem.required_anchor=None` conservatively protects every
service-anchor action starting before each diagnostic's feedback. An explicit
mapping `{diagnostic_id: (anchor_action_id, ...)}` declares the required subset;
the solver verifies that those actions belong to the computed anchor.
`required_anchor={}` declares no additional anchor commitments and permits early
schedule replacements that still preserve sampled service and pass joint
response feasibility. The application must choose this subset according to its
execution requirements; existing fixed commitments always remain binding.

`Plan.selected` is the current schedule; `Plan.commitments` contains the actions
and response promises that must survive replanning. The plan also reports
`service`, `anchor_service`, `information`, `next_feedback`, and solver `stats`.
Future selected actions outside the committed prefix may change after feedback.

The model preserves combined **current sampled** service with an equality and no
intentional service-loss budget. The decoded solution is accepted only when its
service differs from the anchor by at most `10 * feasibility_tolerance`: `1e-7`
with the default `1e-8` setting. This numerical acceptance check does not
establish separate routine/recovery guarantees, calibrated beliefs, or realized
mission performance. The information objective sums local decision values; it
is not an exact fleet-wide value-of-information calculation.

## Replanning

Keep the returned commitments. When observations arrive, bind the stored
responses before the next solve:

```python
commitments = plan.commitments.resolve(
    {"inspect-A": "drive"},
    completed=("inspect-A",),
)
```

The returned commitments fix the previously promised recovery action for that
outcome, or resolve an explicit wait. Include every unfinished fixed action and
every possible pending response, with unchanged identifiers and definitions, in
the next `Problem`. Rebuild the remaining candidates and conditional service
scenarios from the updated belief. Do not drop an outstanding promise because a
new horizon was generated.

Report a command in `completed` when its declared feedback arrives, releasing its
fixed scheduling reservation. The autonomous recovery may still be running:
the application separately retains that physical pending state and its age
until actual completion or failure. Command acknowledgement is not restoration.
Set `Problem.blocked_assets=frozenset({"A"})` to withhold fresh diagnostic credit
while A's physical recovery remains pending, then remove A when appropriate.
Keeping an old command fixed past its feedback would incorrectly retain an old
replanning boundary. Pending diagnostics and fixed recovery commands already
block fresh credit for their assets; unrelated observations retain their promises.

## Limits and failures

`SolverOptions` controls the total solve time, seed, thread count, numerical
tolerance, logging, and maximum number of outcome combinations. The default
configuration uses one Gurobi thread, seed zero, a 60-second total budget, and a
100,000-combination certification limit.

Malformed inputs raise validation errors. A solve that cannot establish the
required optimum raises `SolveError`; it is not silently presented as an
optimal service guarantee. `CertificationLimit` means the explicit joint-outcome
check exceeded its configured limit. For large diagnostic alphabets or many
simultaneous diagnostics, this enumeration can be the main computational cost.

The package's tests cover the optimization and belief contracts on small
problems. Application adapters remain responsible for realistic action windows,
transition and observation models, scenario construction, and execution.
This standalone implementation does not reproduce the paper's experiment suite.

The formulation follows Sections II–III of the local reference manuscript,
*SPAR-MPC: Fault-Aware Fleet Recovery Scheduling with Service-Preserving Active
Diagnosis*, by Carlo Schreiber, Duncan Eddy, and Mykel J. Kochenderfer. The
reference PDF is not distributed with this package.
