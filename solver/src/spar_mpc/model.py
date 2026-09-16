"""Fixed-time actions, sampled service, and retained controller commitments."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from math import fsum, isfinite
from types import MappingProxyType
from typing import Literal

from .diagnosis import Diagnostic


def _name(value: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError("identifiers must be nonempty strings")


@dataclass(frozen=True)
class Action:
    id: str
    asset: str
    kind: Literal["routine", "diagnose", "recover"]
    start: float
    end: float
    feedback: float
    demands: Mapping[str, float] = field(default_factory=dict)
    groups: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _name(self.id)
        _name(self.asset)
        if self.kind not in {"routine", "diagnose", "recover"}:
            raise ValueError(f"unknown action kind: {self.kind}")
        if not all(isfinite(t) for t in (self.start, self.end, self.feedback)):
            raise ValueError("action times must be finite")
        if not self.start < self.end <= self.feedback:
            raise ValueError("actions require start < end <= feedback")
        demands = dict(self.demands)
        for resource, demand in demands.items():
            _name(resource)
            if not isfinite(demand) or demand < 0:
                raise ValueError("resource demands must be finite and nonnegative")
        groups = tuple(self.groups)
        for group in groups:
            _name(group)
        object.__setattr__(self, "demands", MappingProxyType(demands))
        object.__setattr__(self, "groups", tuple(dict.fromkeys(groups)))


def incompatible(a: Action, b: Action) -> bool:
    if a.id == b.id:
        return False
    same_asset_overlap = a.asset == b.asset and a.start < b.feedback and b.start < a.feedback
    return same_asset_overlap or bool(set(a.groups).intersection(b.groups))


@dataclass(frozen=True)
class PendingDiagnostic:
    """A response promise waiting for this diagnostic's own observation."""

    id: str
    asset: str
    feedback: float
    responses: Mapping[str, Action | None]

    def __post_init__(self) -> None:
        _name(self.id)
        _name(self.asset)
        if not isfinite(self.feedback) or not self.responses:
            raise ValueError("pending diagnostics need finite feedback and possible outcomes")
        for outcome, response in self.responses.items():
            _name(outcome)
            if response is not None and (
                response.asset != self.asset
                or response.kind != "recover"
                or response.start < self.feedback
            ):
                raise ValueError("responses must recover the same asset after feedback")
        object.__setattr__(self, "responses", MappingProxyType(dict(self.responses)))


@dataclass(frozen=True)
class Commitments:
    fixed: tuple[Action, ...] = ()
    pending: tuple[PendingDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        fixed, pending = tuple(self.fixed), tuple(self.pending)
        if len({a.id for a in fixed}) != len(fixed):
            raise ValueError("fixed action identifiers must be unique")
        if len({d.id for d in pending}) != len(pending):
            raise ValueError("pending diagnostic identifiers must be unique")
        if len({d.asset for d in pending}) != len(pending):
            raise ValueError("only one pending diagnostic is allowed per asset")
        object.__setattr__(self, "fixed", fixed)
        object.__setattr__(self, "pending", pending)

    def resolve(self, outcomes: Mapping[str, str], *, completed: Iterable[str] = ()) -> Commitments:
        """Bind observed responses and release actions explicitly reported complete.

        Report an action complete only after its feedback. A recovery response
        stays fixed, and its asset stays locked against fresh diagnostic credit,
        until it is included in a later ``completed`` batch.
        This releases the command reservation, not the physical recovery state.
        """
        pending_by_id = {d.id: d for d in self.pending}
        unknown = set(outcomes) - pending_by_id.keys()
        if unknown:
            raise ValueError(f"unknown diagnostic feedback: {sorted(unknown)}")
        fixed = {a.id: a for a in self.fixed}
        completed = set(completed)
        if completed - fixed.keys():
            raise ValueError("completed actions must already be fixed")
        for action_id in completed:
            del fixed[action_id]
        remaining = []
        for diagnostic in self.pending:
            if diagnostic.id not in outcomes:
                remaining.append(diagnostic)
                continue
            outcome = outcomes[diagnostic.id]
            if outcome not in diagnostic.responses:
                raise ValueError(f"unknown outcome {outcome!r} for {diagnostic.id}")
            response = diagnostic.responses[outcome]
            if response is not None:
                if response.id in fixed and fixed[response.id] != response:
                    raise ValueError(f"response action changed: {response.id}")
                fixed[response.id] = response
        return Commitments(tuple(fixed.values()), tuple(remaining))


@dataclass(frozen=True)
class Problem:
    actions: tuple[Action, ...]
    priorities: Mapping[str, float]
    capacities: Mapping[str, float]
    service: Mapping[str, tuple[float, ...]]
    diagnostics: tuple[Diagnostic, ...] = ()
    commitments: Commitments = field(default_factory=Commitments)
    next_feedback: float | None = None
    required_anchor: Mapping[str, tuple[str, ...]] | None = None
    blocked_assets: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        actions = tuple(sorted(self.actions, key=lambda a: a.id))
        by_id = {a.id: a for a in actions}
        if len(by_id) != len(actions):
            raise ValueError("action identifiers must be unique")
        priorities, capacities = dict(self.priorities), dict(self.capacities)
        assets = {a.asset for a in actions}
        if set(priorities) != assets:
            raise ValueError("priorities must cover exactly the assets with candidate actions")
        if any(not isfinite(q) or q <= 0 for q in priorities.values()):
            raise ValueError("priorities must be finite and positive")
        if not isfinite(sum(priorities.values())):
            raise ValueError("total priority must be finite")
        blocked_assets = frozenset(self.blocked_assets)
        for asset in blocked_assets:
            _name(asset)
        for resource, capacity in capacities.items():
            _name(resource)
            if not isfinite(capacity) or capacity < 0:
                raise ValueError("capacities must be finite and nonnegative")
        for action in actions:
            if set(action.demands) - capacities.keys():
                raise ValueError(f"unknown resource in action {action.id}")
        service = {key: tuple(values) for key, values in self.service.items()}
        if set(service) != by_id.keys():
            raise ValueError("service must contain a scenario row for every action")
        lengths = {len(row) for row in service.values()}
        if actions and (len(lengths) != 1 or 0 in lengths):
            raise ValueError("service rows must share a nonzero scenario count")
        for action_id, row in service.items():
            if any(not isfinite(c) or not 0 <= c <= 1 for c in row):
                raise ValueError("service credits must be finite and in [0, 1]")
            if by_id[action_id].kind == "diagnose" and any(row):
                raise ValueError("diagnostics cannot receive direct service credit")
        for action in self.commitments.fixed:
            if by_id.get(action.id) != action:
                raise ValueError(f"missing or changed fixed action: {action.id}")
        for pending in self.commitments.pending:
            if pending.asset not in assets:
                raise ValueError("pending diagnostic asset has no candidate actions")
            for response in pending.responses.values():
                if response is not None and by_id.get(response.id) != response:
                    raise ValueError(f"missing or changed promised response: {response.id}")
        diagnostics = tuple(sorted(self.diagnostics, key=lambda d: d.action_id))
        if len({d.action_id for d in diagnostics}) != len(diagnostics):
            raise ValueError("diagnostic identifiers must be unique")
        for diagnostic in diagnostics:
            action = by_id.get(diagnostic.action_id)
            if action is None or action.kind != "diagnose":
                raise ValueError("diagnostic values must refer to diagnostic actions")
            responses = []
            for response_id in set(diagnostic.responses.values()) - {None}:
                response = by_id.get(response_id)
                if response is None or response.kind != "recover" or response.asset != action.asset:
                    raise ValueError("diagnostic responses must be same-asset recovery candidates")
                if response.start < action.feedback:
                    raise ValueError("a response cannot start before diagnostic feedback")
                responses.append(response)
            for i, first in enumerate(responses):
                for second in responses[i + 1 :]:
                    if not incompatible(first, second):
                        raise ValueError("alternative responses must be mutually exclusive")
        if self.next_feedback is not None and not isfinite(self.next_feedback):
            raise ValueError("next_feedback must be finite when supplied")
        if self.required_anchor is not None:
            required = {key: tuple(ids) for key, ids in self.required_anchor.items()}
            if set(required) - {d.action_id for d in diagnostics}:
                raise ValueError("required_anchor keys must name valued diagnostics")
            for ids in required.values():
                if set(ids) - by_id.keys():
                    raise ValueError("required_anchor refers to an unknown action")
            object.__setattr__(self, "required_anchor", MappingProxyType(required))
        object.__setattr__(self, "actions", actions)
        object.__setattr__(self, "priorities", MappingProxyType(priorities))
        object.__setattr__(self, "capacities", MappingProxyType(capacities))
        object.__setattr__(self, "service", MappingProxyType(service))
        object.__setattr__(self, "diagnostics", diagnostics)
        object.__setattr__(self, "blocked_assets", blocked_assets)

    @property
    def scenario_count(self) -> int:
        return len(next(iter(self.service.values()))) if self.service else 0

    @property
    def feedback_boundary(self) -> float:
        times = [d.feedback for d in self.commitments.pending]
        if self.next_feedback is not None:
            times.append(self.next_feedback)
        return min(times, default=float("inf"))


def service_value(problem: Problem, selected: Iterable[str]) -> float:
    """Evaluate capped sampled service independently of the MILP variables."""
    ids = set(selected)
    by_id = {a.id: a for a in problem.actions}
    if ids - by_id.keys():
        raise ValueError("unknown selected action")
    if not problem.actions:
        return 0.0
    totals = []
    for asset, priority in problem.priorities.items():
        rows = [problem.service[key] for key in sorted(ids) if by_id[key].asset == asset]
        totals.append(
            priority
            * fsum(min(1.0, fsum(row[s] for row in rows)) for s in range(problem.scenario_count))
        )
    return fsum(totals) / (problem.scenario_count * fsum(problem.priorities.values()))


def feasible(
    actions: Iterable[Action], capacities: Mapping[str, float], tolerance: float = 1e-9
) -> bool:
    """Check a union of actions; an action shared by two promises counts once."""
    unique = {}
    if not isfinite(tolerance) or tolerance < 0:
        raise ValueError("tolerance must be finite and nonnegative")
    for action in actions:
        if set(action.demands) - capacities.keys():
            raise ValueError(f"unknown resource in action {action.id}")
        if action.id in unique and unique[action.id] != action:
            raise ValueError(f"conflicting definitions of action {action.id}")
        unique[action.id] = action
    actions = tuple(unique.values())
    for i, first in enumerate(actions):
        if any(incompatible(first, second) for second in actions[i + 1 :]):
            return False
    for resource, capacity in capacities.items():
        relevant = [a for a in actions if a.demands.get(resource, 0) > 0]
        for time in {a.start for a in relevant}:
            demand = sum(a.demands[resource] for a in relevant if a.start <= time < a.end)
            if demand > capacity + tolerance:
                return False
    return True
