"""Two-stage SPAR scheduling with finite-outcome response certification."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations, product
from math import isfinite, prod
from time import monotonic

import gurobipy as gp
from gurobipy import GRB

from .diagnosis import Diagnostic
from .model import (
    Action,
    Commitments,
    PendingDiagnostic,
    Problem,
    feasible,
    incompatible,
    service_value,
)


class SolveError(RuntimeError):
    def __init__(self, stage: str, status: int, detail: str = "") -> None:
        self.stage = stage
        self.status = status
        super().__init__(
            f"{stage}: Gurobi status {status}; no certified plan returned. {detail}".strip()
        )


class CertificationLimit(RuntimeError):
    pass


@dataclass(frozen=True)
class SolverOptions:
    time_limit: float = 60.0
    threads: int = 1
    seed: int = 0
    feasibility_tolerance: float = 1e-8
    max_outcome_combinations: int = 100_000
    log: bool = False

    def __post_init__(self) -> None:
        if not isfinite(self.time_limit) or self.time_limit <= 0:
            raise ValueError("time_limit must be finite and positive")
        if (
            not isfinite(self.feasibility_tolerance)
            or not 1e-9 <= self.feasibility_tolerance <= 1e-6
        ):
            raise ValueError("feasibility_tolerance must lie in [1e-9, 1e-6]")
        for name, minimum, maximum in (
            ("threads", 1, 1024),
            ("seed", 0, 2_000_000_000),
            ("max_outcome_combinations", 1, 2_000_000_000),
        ):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not minimum <= value <= maximum
            ):
                raise ValueError(f"{name} must be an integer in [{minimum}, {maximum}]")


@dataclass(frozen=True)
class StageStats:
    stage: str
    status: int
    objective: float
    bound: float
    gap: float
    runtime: float
    certification_cuts: int


@dataclass(frozen=True)
class Plan:
    selected: tuple[Action, ...]
    anchor: tuple[Action, ...]
    credited: tuple[Diagnostic, ...]
    service: float
    anchor_service: float
    information: float
    commitments: Commitments
    next_feedback: float | None
    stats: tuple[StageStats, ...]


class _Scheduler:
    def __init__(self, problem: Problem, options: SolverOptions, model: gp.Model) -> None:
        self.problem = problem
        self.options = options
        self.model = model
        self.deadline = monotonic() + options.time_limit
        self.actions = {a.id: a for a in problem.actions}
        self.fixed = {a.id for a in problem.commitments.fixed}
        self.stats: list[StageStats] = []
        self.required: dict[str, set[str]] = {}
        self.z: dict[str, gp.Var] = {}
        self.diagnostics = {d.action_id: d for d in problem.diagnostics}

        model.Params.OutputFlag = int(options.log)
        model.Params.Threads = options.threads
        model.Params.Seed = options.seed
        model.Params.MIPGap = 0
        model.Params.MIPGapAbs = 0
        model.Params.FeasibilityTol = options.feasibility_tolerance
        model.Params.IntFeasTol = 1e-9
        self.x = {
            key: model.addVar(vtype=GRB.BINARY, name=f"select[{j}]")
            for j, key in enumerate(self.actions)
        }
        self.prefix = {
            key: model.addVar(vtype=GRB.BINARY, name=f"commit[{j}]")
            for j, key in enumerate(self.actions)
        }
        self._schedule_constraints()
        self._prefix_constraints()
        self.service = self._service_expression()

    def _schedule_constraints(self) -> None:
        actions, model = self.problem.actions, self.model
        for key in sorted(self.fixed):
            model.addConstr(self.x[key] == 1)
        for first, second in combinations(actions, 2):
            if incompatible(first, second):
                model.addConstr(self.x[first.id] + self.x[second.id] <= 1)
        for resource, capacity in self.problem.capacities.items():
            relevant = [a for a in actions if a.demands.get(resource, 0) > 0]
            seen = set()
            for time in sorted({a.start for a in relevant}):
                active = tuple(a.id for a in relevant if a.start <= time < a.end)
                if active in seen:
                    continue
                seen.add(active)
                model.addConstr(
                    gp.quicksum(self.actions[key].demands[resource] * self.x[key] for key in active)
                    <= capacity
                )

    def _prefix_constraints(self) -> None:
        # A selected action is committed now iff it starts before any selected feedback.
        for action in self.problem.actions:
            p, x = self.prefix[action.id], self.x[action.id]
            self.model.addConstr(p <= x)
            if action.start >= self.problem.feedback_boundary:
                self.model.addConstr(p == 0)
                continue
            blockers = [self.x[a.id] for a in self.problem.actions if a.feedback <= action.start]
            for blocker in blockers:
                self.model.addConstr(p + blocker <= 1)
            self.model.addConstr(p >= x - gp.quicksum(blockers))

    def _service_expression(self) -> gp.LinExpr:
        terms = []
        scale = self.problem.scenario_count * sum(self.problem.priorities.values())
        for i, (asset, priority) in enumerate(sorted(self.problem.priorities.items())):
            actions = [a for a in self.problem.actions if a.asset == asset]
            for scenario in range(self.problem.scenario_count):
                value = self.model.addVar(lb=0, ub=1, name=f"service[{i},{scenario}]")
                self.model.addConstr(
                    value
                    <= gp.quicksum(
                        self.problem.service[a.id][scenario] * self.x[a.id] for a in actions
                    )
                )
                terms.append(priority / scale * value)
        return gp.quicksum(terms)

    def _ids(self, variables: dict[str, gp.Var]) -> set[str]:
        return {key for key, variable in variables.items() if variable.X > 0.5}

    def _committed_ids(self, credited: set[str]) -> set[str]:
        ids = self.fixed | self._ids(self.prefix)
        for key in credited:
            ids.update(self.required[key])
        return ids

    def _response_choices(self, credited: set[str]) -> list[tuple[str | None, ...]]:
        choices = [
            tuple(dict.fromkeys(a.id if a is not None else None for a in d.responses.values()))
            for d in self.problem.commitments.pending
        ]
        for key in sorted(credited):
            diagnostic = self.diagnostics[key]
            choices.append(
                tuple(
                    dict.fromkeys(
                        response
                        for outcome, response in diagnostic.responses.items()
                        if diagnostic.outcome_probabilities[outcome] > 0
                    )
                )
            )
        return choices

    def _certified(self, credited: set[str]) -> bool:
        committed = self._committed_ids(credited)
        if not feasible(
            (self.actions[key] for key in committed),
            self.problem.capacities,
            self.options.feasibility_tolerance,
        ):
            return False
        choices = self._response_choices(credited)
        count = prod(len(branches) for branches in choices)
        if count > self.options.max_outcome_combinations:
            raise CertificationLimit(
                f"{count} joint response combinations exceed the configured limit "
                f"of {self.options.max_outcome_combinations}; no plan was certified"
            )
        for responses in product(*choices):
            if monotonic() >= self.deadline:
                raise SolveError("response certification", GRB.TIME_LIMIT)
            ids = committed | {key for key in responses if key is not None}
            if not feasible(
                (self.actions[key] for key in ids),
                self.problem.capacities,
                self.options.feasibility_tolerance,
            ):
                return False
        return True

    def optimize(self, stage: str, objective: gp.LinExpr, sense: int) -> None:
        self.model.setObjective(objective, sense)
        runtime, cuts = 0.0, 0
        while True:
            remaining = self.deadline - monotonic()
            if remaining <= 0:
                raise SolveError(stage, GRB.TIME_LIMIT)
            self.model.Params.TimeLimit = remaining
            self.model.optimize()
            runtime += self.model.Runtime
            if self.model.Status != GRB.OPTIMAL:
                raise SolveError(
                    stage,
                    self.model.Status,
                    "Optimality is required for strict service preservation.",
                )
            credited = self._ids(self.z)
            if self._certified(credited):
                break
            # Feasibility is monotone under adding committed actions or promises.
            # Exclude this combination, allowing either the prefix or credits to change.
            witness = [self.prefix[key] for key in sorted(self._ids(self.prefix) - self.fixed)]
            witness.extend(self.z[key] for key in sorted(credited))
            self.model.addConstr(gp.quicksum(witness) <= len(witness) - 1)
            cuts += 1
        self.stats.append(
            StageStats(
                stage,
                self.model.Status,
                self.model.ObjVal,
                self.model.ObjBound,
                self.model.MIPGap,
                runtime,
                cuts,
            )
        )

    def add_information_stage(self, anchor: set[str]) -> gp.LinExpr:
        locked_assets = set(self.problem.blocked_assets)
        locked_assets.update(d.asset for d in self.problem.commitments.pending)
        locked_assets.update(
            self.actions[key].asset for key in self.fixed if self.actions[key].kind == "recover"
        )
        for key, diagnostic in self.diagnostics.items():
            action = self.actions[key]
            if self.problem.required_anchor is None:
                required = {a for a in anchor if self.actions[a].start < action.feedback}
            else:
                required = set(self.problem.required_anchor.get(key, ()))
                if required - anchor:
                    raise ValueError(
                        f"required_anchor[{key!r}] contains actions outside the service anchor"
                    )
            self.required[key] = required
            enabled = (
                diagnostic.decision_relevant
                and diagnostic.gain > 0
                and action.asset not in locked_assets
            )
            credit = self.model.addVar(
                vtype=GRB.BINARY, ub=int(enabled), name=f"credit[{len(self.z)}]"
            )
            self.z[key] = credit
            self.model.addConstr(credit <= self.prefix[key])
            for action_id in sorted(required):
                self.model.addConstr(self.x[action_id] >= credit)
        for asset in self.problem.priorities:
            self.model.addConstr(
                gp.quicksum(self.z[key] for key in self.z if self.actions[key].asset == asset) <= 1
            )
        q = sum(self.problem.priorities.values())
        return gp.quicksum(
            self.problem.priorities[self.actions[key].asset]
            / q
            * self.diagnostics[key].gain
            * credit
            for key, credit in self.z.items()
        )

    def plan(self, anchor: set[str], anchor_value: float, *, use_anchor: bool = False) -> Plan:
        selected = anchor if use_anchor else self._ids(self.x)
        credited = set() if use_anchor else self._ids(self.z)
        boundary = min(
            [self.problem.feedback_boundary] + [self.actions[key].feedback for key in selected]
        )
        committed = self.fixed | {key for key in selected if self.actions[key].start < boundary}
        for key in credited:
            committed.update(self.required[key])
        pending = list(self.problem.commitments.pending)
        for key in sorted(credited):
            action, diagnostic = self.actions[key], self.diagnostics[key]
            pending.append(
                PendingDiagnostic(
                    key,
                    action.asset,
                    action.feedback,
                    {
                        outcome: self.actions[response] if response is not None else None
                        for outcome, response in diagnostic.responses.items()
                        if diagnostic.outcome_probabilities[outcome] > 0
                    },
                )
            )
        value = service_value(self.problem, selected)
        tolerance = 10 * self.options.feasibility_tolerance
        if abs(value - anchor_value) > tolerance:
            raise SolveError(
                "solution verification", GRB.NUMERIC, "Decoded service differs from the anchor."
            )
        if not self.fixed <= selected or not feasible(
            (self.actions[key] for key in selected),
            self.problem.capacities,
            self.options.feasibility_tolerance,
        ):
            raise SolveError(
                "solution verification", GRB.NUMERIC, "Decoded schedule violates a constraint."
            )

        def ordered(ids: set[str]) -> tuple[Action, ...]:
            return tuple(sorted((self.actions[key] for key in ids), key=lambda a: (a.start, a.id)))

        return Plan(
            selected=ordered(selected),
            anchor=ordered(anchor),
            credited=tuple(self.diagnostics[key] for key in sorted(credited)),
            service=value,
            anchor_service=anchor_value,
            information=sum(
                self.problem.priorities[self.actions[key].asset] * self.diagnostics[key].gain
                for key in credited
            )
            / sum(self.problem.priorities.values()),
            commitments=Commitments(ordered(committed), tuple(pending)),
            next_feedback=boundary if isfinite(boundary) else None,
            stats=tuple(self.stats),
        )

    def run(self) -> Plan:
        self.optimize("service", self.service, GRB.MAXIMIZE)
        anchor_value = service_value(self.problem, self._ids(self.x))
        # Equality retains the sampled optimum; this is not a service-loss budget.
        self.model.addConstr(self.service == anchor_value, name="preserve_service")
        action_count = gp.quicksum(self.x.values())
        self.optimize("service tie-break", action_count, GRB.MINIMIZE)
        anchor = self._ids(self.x)
        if not self.diagnostics:
            return self.plan(anchor, anchor_value)
        information = self.add_information_stage(anchor)
        self.optimize("information", information, GRB.MAXIMIZE)
        if not self._ids(self.z):
            return self.plan(anchor, anchor_value, use_anchor=True)
        self.model.addConstr(information == self.model.ObjVal, name="preserve_information")
        self.optimize("information tie-break", action_count, GRB.MINIMIZE)
        return self.plan(anchor, anchor_value)


def solve(
    problem: Problem, options: SolverOptions | None = None, *, env: gp.Env | None = None
) -> Plan:
    """Return a service-optimal schedule and jointly feasible diagnostic promises.

    Candidates and scenario columns remain fixed across both stages. Supply an
    existing Gurobi environment to reuse a license/session across replanning calls.
    The caller owns that environment; models created here are always disposed.
    """
    options = options or SolverOptions()
    if not problem.actions:
        return Plan((), (), (), 0.0, 0.0, 0.0, problem.commitments, problem.next_feedback, ())
    if env is None:
        with gp.Env(empty=True) as owned_env:
            owned_env.setParam("OutputFlag", int(options.log))
            owned_env.start()
            return solve(problem, options, env=owned_env)
    with gp.Model("spar-mpc", env=env) as model:
        return _Scheduler(problem, options, model).run()
