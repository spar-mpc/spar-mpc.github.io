# Model reference

The formulation follows Sections II–III of *Fault-Aware Fleet Recovery
Scheduling with Service-Preserving Active Diagnosis*, by Carlo Schreiber, Duncan
Eddy, and Mykel J. Kochenderfer. The package provides the generic scheduling
model; the paper's application adapter and experiments are separate.

## Actions and scenarios

`Action` specifies an asset, kind (`routine`, `diagnose`, or `recover`), start,
end, feedback time, resource demands, and optional incompatibility groups.
Candidate times are fixed inputs; the solver chooses actions rather than start
times. Use one consistent time unit and clock, with `start < end <= feedback`.

Resource use is nonpreemptive over `[start, end)`. Actions touching at an
execution endpoint can share a resource. Same-asset actions are incompatible
when their start-to-feedback intervals overlap; a shared group also makes
actions mutually exclusive, regardless of timing.

`Problem.service[action_id]` contains credits in `[0, 1]` for equally weighted
joint scenarios. Every action needs a row, including zeros for diagnostics.
All rows share the same scenario columns. Generate each column jointly so that
correlations between assets and alternative actions are retained. The caller
supplies candidate generation, transition models, and scenario sampling.

For each asset and scenario, selected service contributions add and are capped
at one. The service objective averages these credits over scenarios, weighted
by positive asset priorities and normalized by their sum.

## Diagnosis

`value_diagnostic` takes a class prior predicted to diagnostic feedback, a
class-to-outcome likelihood table, and timely same-asset recovery rewards.
It computes expected improvement in the best immediate recovery-or-wait decision
and stores the chosen response for each possible outcome. Waiting has value
zero; `recovery_cost` is subtracted from each recovery's expected reward. This
cost affects diagnostic valuation, not the sampled service objective.

The decision-relevance gate requires two sufficiently likely outcomes to favor
different responses by the specified margin. Every positive-probability outcome
still contributes to value and joint feasibility, including rare outcomes below
the gate's probability threshold. At most one diagnostic is credited per asset.
Credited diagnostics start before the next feedback and are committed for execution.

The information objective sums weighted local values. Joint feasibility checks
cover every combination of stored responses against resource capacities,
incompatibilities, and commitments. This includes promises retained from earlier
solves; it does not turn the local objective into exact fleet-wide information
value.

`predict`, `update`, `condition`, and `aggregate` operate on finite beliefs.
Impossible evidence raises an error; probability floors are not added.
Intervention classes must retain the distinctions needed for recovery decisions.

## Service preservation

`solve(problem, options=SolverOptions(), env=None)` returns a `Plan`. Its
`anchor` maximizes sampled service, with a tie-break favoring fewer actions.
The information stage preserves this value and maximizes diagnostic value.
It returns the anchor if no diagnostic receives positive credit.

The model uses service equality with no intentional loss budget. After decoding
the selected actions, the solver checks that service differs from the anchor by
at most `10 * feasibility_tolerance`: `1e-7` under the default `1e-8` setting.
This concerns the combined current sampled objective, not separate routine and
recovery totals or realized performance.

`Problem.required_anchor` controls additional service-anchor commitments:

- `None` (default): protect every anchor action starting before each diagnostic's
  feedback.
- `{diagnostic_id: (anchor_action_id, ...)}`: protect the declared subset. The
  solver checks membership in the computed anchor.
- `{}`: no additional anchor commitments; early replacements are allowed if
  service preservation and joint response feasibility still hold.

Choose the subset according to the application's execution requirements.
Existing fixed commitments always remain binding.

## Replanning and recovery

`Plan.selected` includes future actions that may change after feedback.
`Plan.commitments` contains the fixed actions and stored response promises that
must survive replanning. The plan also reports `service`, `anchor_service`,
`information`, `next_feedback`, and per-stage `stats`.

When diagnostic feedback arrives, bind its previously stored response:

```python
commitments = plan.commitments.resolve(
    {"inspect-A": "drive"},
    completed=("inspect-A",),
)
```

Pass these commitments to the next `Problem`. Include every unfinished fixed
action and every possible pending response with unchanged identifiers and
definitions. Update the belief and conditional service scenarios; unrelated
observations leave existing promises intact.

Report a command in `completed` when its declared feedback arrives, releasing
its scheduling reservation. Autonomous recovery may continue afterward. The
application retains that physical pending state and its age until completion or
failure; acknowledgement alone is not restoration. Use
`Problem.blocked_assets=frozenset({"A"})` to withhold new diagnostic credit during
that period, then remove A when appropriate. Keeping an old command fixed past
its feedback would retain an obsolete replanning boundary. Pending diagnostics
and fixed recovery commands already block new credit for their assets.

## Solver limits

`SolverOptions` defaults to one Gurobi thread, seed zero, a 60-second total solve
budget, and at most 100,000 outcome combinations. Enumeration can dominate the
cost when many diagnostics or outcomes are present. Pass an existing `gurobipy.Env`
to `solve` to reuse a Gurobi session; the caller retains ownership of that environment.

Malformed inputs raise validation errors. `SolveError` means the required
optimum or solution verification was not established; no certified plan is
returned. `CertificationLimit` means joint-outcome enumeration exceeded the
configured cap. See the [Gurobi Python API reference](https://docs.gurobi.com/projects/optimizer/en/current/reference/python/overview.html)
for optimizer and environment configuration.
