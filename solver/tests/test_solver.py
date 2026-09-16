"""Independent scheduling oracles and adversarial diagnostic certificates."""

from itertools import combinations, product
from math import fsum
from random import Random

import gurobipy as gp
import pytest

from spar_mpc import (
    Action,
    CertificationLimit,
    Commitments,
    Diagnostic,
    PendingDiagnostic,
    Problem,
    SolveError,
    SolverOptions,
    solve,
)


@pytest.fixture(scope="module")
def gurobi_env():
    """One quiet licensed environment, with models disposed by the solver."""
    with gp.Env(empty=True) as env:
        env.setParam("OutputFlag", 0)
        env.start()
        yield env


def action(
    name,
    asset=None,
    *,
    start=0,
    end=1,
    feedback=None,
    kind="routine",
    demands=None,
    groups=(),
):
    return Action(
        name,
        asset or name,
        kind,
        start,
        end,
        end if feedback is None else feedback,
        {"station": 1} if demands is None else demands,
        groups,
    )


def problem(
    *actions,
    credits=None,
    priorities=None,
    capacities=None,
    diagnostics=(),
    commitments=None,
    next_feedback=None,
    required_anchor=None,
    blocked_assets=frozenset(),
):
    credits = credits or {}
    scenario_count = len(next(iter(credits.values()))) if credits else 1
    return Problem(
        actions=tuple(actions),
        priorities=priorities or {a.asset: 1 for a in actions},
        capacities={"station": 1} if capacities is None else capacities,
        service={a.id: tuple(credits.get(a.id, (0,) * scenario_count)) for a in actions},
        diagnostics=tuple(diagnostics),
        commitments=commitments or Commitments(),
        next_feedback=next_feedback,
        required_anchor=required_anchor,
        blocked_assets=blocked_assets,
    )


def diagnostic(name, response, *, gain=0.5, probability=0.5, relevant=True):
    return Diagnostic(
        action_id=name,
        gain=gain,
        responses={"fault": response, "healthy": None},
        outcome_probabilities={"fault": probability, "healthy": 1 - probability},
        decision_relevant=relevant,
    )


def optimize(instance, env, **options):
    return solve(instance, options=SolverOptions(time_limit=20, **options), env=env)


def ids(actions):
    return frozenset(a.id for a in actions)


def oracle_feasible(selected, capacities):
    """No production feasibility helpers: enumerate event times and pairs."""
    for left, right in combinations(selected, 2):
        if set(left.groups) & set(right.groups):
            return False
        if left.asset == right.asset:
            earlier, later = sorted((left, right), key=lambda a: a.start)
            if later.start < earlier.feedback:
                return False
    event_times = {a.start for a in selected}
    for time in event_times:
        for resource, capacity in capacities.items():
            used = fsum(a.demands.get(resource, 0) for a in selected if a.start <= time < a.end)
            if used > capacity + 1e-12:
                return False
    return True


def oracle_service(instance, selected):
    total = 0.0
    for asset, priority in instance.priorities.items():
        for scenario in range(instance.scenario_count):
            credit = fsum(instance.service[a.id][scenario] for a in selected if a.asset == asset)
            total += priority * min(1.0, credit)
    return total / (instance.scenario_count * fsum(instance.priorities.values()))


def service_oracle(instance):
    """Enumerate every binary schedule, then minimize count among optima."""
    assert not instance.commitments.pending
    required = ids(instance.commitments.fixed)
    best_value, best_count, best_schedules = -1.0, float("inf"), set()
    for count in range(len(instance.actions) + 1):
        for selected in combinations(instance.actions, count):
            selected_ids = ids(selected)
            if not required <= selected_ids or not oracle_feasible(selected, instance.capacities):
                continue
            value = oracle_service(instance, selected)
            if value > best_value + 1e-10:
                best_value, best_count, best_schedules = value, count, {selected_ids}
            elif abs(value - best_value) <= 1e-10:
                if count < best_count:
                    best_count, best_schedules = count, {selected_ids}
                elif count == best_count:
                    best_schedules.add(selected_ids)
    return best_value, best_schedules


def information_oracle(instance):
    """Enumerate (selected, credited) and every response branch independently."""
    assert not instance.commitments.pending
    anchor_value, anchors = service_oracle(instance)
    assert len(anchors) == 1, "This fixture must have one minimum-cardinality anchor."
    anchor = next(iter(anchors))
    by_id = {a.id: a for a in instance.actions}
    best_gain, best_count, best_pairs = -1.0, float("inf"), set()
    for count in range(len(instance.actions) + 1):
        for selected in combinations(instance.actions, count):
            selected_ids = ids(selected)
            if not ids(instance.commitments.fixed) <= selected_ids:
                continue
            if not oracle_feasible(selected, instance.capacities):
                continue
            if abs(oracle_service(instance, selected) - anchor_value) > 1e-10:
                continue
            boundary = min(
                [a.feedback for a in selected]
                + [instance.next_feedback if instance.next_feedback is not None else float("inf")]
            )
            possible = [
                d
                for d in instance.diagnostics
                if d.action_id in selected_ids
                and d.decision_relevant
                and d.gain > 0
                and by_id[d.action_id].start < boundary
            ]
            for credited_count in range(len(possible) + 1):
                for credited in combinations(possible, credited_count):
                    credited_assets = [by_id[d.action_id].asset for d in credited]
                    if len(set(credited_assets)) != len(credited_assets):
                        continue
                    committed_ids = ids(instance.commitments.fixed) | frozenset(
                        a.id for a in selected if a.start < boundary
                    )
                    for value in credited:
                        if instance.required_anchor is None:
                            committed_ids |= frozenset(
                                key
                                for key in anchor
                                if by_id[key].start < by_id[value.action_id].feedback
                            )
                        else:
                            committed_ids |= frozenset(
                                instance.required_anchor.get(value.action_id, ())
                            )
                    if not committed_ids <= selected_ids:
                        continue
                    response_sets = [
                        set(d.responses[o] for o, p in d.outcome_probabilities.items() if p > 0)
                        for d in credited
                    ]
                    if not all(
                        oracle_feasible(
                            [by_id[key] for key in committed_ids | (set(branch) - {None})],
                            instance.capacities,
                        )
                        for branch in product(*response_sets)
                    ):
                        continue
                    gain = fsum(
                        instance.priorities[by_id[d.action_id].asset] * d.gain for d in credited
                    ) / fsum(instance.priorities.values())
                    pair = (selected_ids, frozenset(d.action_id for d in credited))
                    if gain > best_gain + 1e-10:
                        best_gain, best_count, best_pairs = gain, count, {pair}
                    elif abs(gain - best_gain) <= 1e-10:
                        if count < best_count:
                            best_count, best_pairs = count, {pair}
                        elif count == best_count:
                            best_pairs.add(pair)
    return best_gain, best_pairs


@pytest.mark.parametrize("seed", range(8))
def test_service_milp_matches_exhaustive_subset_oracle(seed, gurobi_env):
    rng = Random(seed)
    candidates = []
    credits = {}
    for index in range(8):
        start = rng.randrange(5)
        end = start + rng.choice((1, 2))
        candidate = action(
            f"job-{index}",
            f"asset-{index % 3}",
            start=start,
            end=end,
            feedback=end + rng.choice((0, 1)),
            kind=rng.choice(("routine", "recover")),
            demands={"station": 1, "operator": rng.choice((0.5, 1))},
            groups=(f"choice-{rng.randrange(2)}",) if rng.random() < 0.25 else (),
        )
        candidates.append(candidate)
        credits[candidate.id] = tuple(rng.choice((0, 0.25, 0.5, 0.75, 1)) for _ in range(3))
    instance = problem(
        *candidates,
        credits=credits,
        priorities={"asset-0": 1, "asset-1": 2, "asset-2": 4},
        capacities={"station": 2, "operator": 1},
        commitments=Commitments(fixed=(candidates[0],)) if seed % 2 else None,
    )
    best_value, best_schedules = service_oracle(instance)
    plan = optimize(instance, gurobi_env)

    assert plan.anchor_service == pytest.approx(best_value, abs=1e-9)
    assert plan.service == pytest.approx(best_value, abs=1e-9)
    assert ids(plan.anchor) in best_schedules
    assert plan.selected == plan.anchor
    assert not plan.credited
    assert oracle_feasible(plan.selected, instance.capacities)


def test_caps_apply_per_asset_per_scenario_before_averaging(gurobi_env):
    first = action("first", "A", start=0, end=1)
    redundant = action("redundant", "A", start=1, end=2)
    different = action("different", "B", start=1, end=2)
    instance = problem(
        first,
        redundant,
        different,
        credits={"first": (1, 0), "redundant": (1, 0), "different": (0.55, 0.55)},
        priorities={"A": 2, "B": 1},
    )
    plan = optimize(instance, gurobi_env)
    assert ids(plan.selected) == {"first", "different"}
    assert plan.service == pytest.approx((2 * 0.5 + 0.55) / 3)


def test_anchor_uses_fewest_actions_among_service_optima(gurobi_env):
    single = action("single", "A", start=0, end=2)
    first = action("split-first", "A", start=0, end=1)
    second = action("split-second", "A", start=1, end=2)
    unused = action("zero-credit", "B", start=3, end=4)
    plan = optimize(
        problem(
            single,
            first,
            second,
            unused,
            credits={"single": (1,), "split-first": (0.5,), "split-second": (0.5,)},
        ),
        gurobi_env,
    )
    assert ids(plan.anchor) == {"single"}
    assert plan.selected == plan.anchor


def test_resource_intervals_are_half_open_and_release_before_feedback(gurobi_env):
    first = action("first", "A", start=0, end=1, feedback=3)
    touching = action("touching", "B", start=1, end=2)
    plan = optimize(
        problem(first, touching, credits={"first": (1,), "touching": (1,)}),
        gurobi_env,
    )
    assert ids(plan.selected) == {"first", "touching"}
    assert plan.service == 1


def test_same_asset_waits_until_feedback_not_only_execution_end(gurobi_env):
    first = action("first", "A", start=0, end=1, feedback=2)
    early = action("early", "A", start=1, end=2)
    ready = action("ready", "A", start=2, end=3)
    plan = optimize(
        problem(
            first,
            early,
            ready,
            credits={"first": (0.4,), "early": (0.6,), "ready": (0.6,)},
            commitments=Commitments(fixed=(first,)),
        ),
        gurobi_env,
    )
    assert ids(plan.selected) == {"first", "ready"}
    assert plan.service == 1


def test_exclusion_groups_apply_even_without_time_overlap(gurobi_env):
    high = action("high", "A", start=0, end=1, groups=("intervention",))
    low = action("low", "B", start=2, end=3, groups=("intervention",))
    plan = optimize(problem(high, low, credits={"high": (1,), "low": (0.4,)}), gurobi_env)
    assert ids(plan.selected) == {"high"}


def test_commitment_retained_despite_better_conflicting_candidate(gurobi_env):
    fixed = action("fixed", "A")
    better = action("better", "B")
    plan = optimize(
        problem(
            fixed,
            better,
            credits={"fixed": (0.2,), "better": (1,)},
            commitments=Commitments(fixed=(fixed,)),
        ),
        gurobi_env,
    )
    assert ids(plan.selected) == {"fixed"}
    assert "fixed" in ids(plan.commitments.fixed)


def test_infeasible_fixed_commitments_raise_instead_of_dropping_actions(gurobi_env):
    first, second = action("first", "A"), action("second", "B")
    instance = problem(first, second, commitments=Commitments(fixed=(first, second)))
    with pytest.raises(SolveError) as error:
        optimize(instance, gurobi_env)
    assert error.value.status == gp.GRB.INFEASIBLE


def diagnostic_fixture(*, gain=0.5, relevant=True, next_feedback=None, start=0):
    probe = action("probe", "A", kind="diagnose", start=start, end=start + 0.1, feedback=2)
    response = action("response", "A", kind="recover", start=3, end=4)
    routine = action("routine", "B", start=5, end=6)
    value = diagnostic("probe", "response", gain=gain, relevant=relevant)
    return problem(
        probe,
        response,
        routine,
        credits={"routine": (1,)},
        diagnostics=(value,),
        next_feedback=next_feedback,
    )


def test_positive_diagnostic_preserves_service_and_records_response_promise(gurobi_env):
    instance = diagnostic_fixture()
    plan = optimize(instance, gurobi_env)
    assert ids(plan.anchor) == {"routine"}
    assert ids(plan.selected) == {"probe", "routine"}
    assert [d.action_id for d in plan.credited] == ["probe"]
    assert plan.service == plan.anchor_service == 0.5
    assert plan.information == pytest.approx(0.25)
    assert plan.next_feedback == 2
    assert ids(plan.commitments.fixed) == {"probe"}
    assert len(plan.commitments.pending) == 1
    promise = plan.commitments.pending[0]
    assert promise.id == "probe"
    assert promise.responses["fault"].id == "response"
    assert promise.responses["healthy"] is None


@pytest.mark.parametrize("gain,relevant", [(0, True), (1, False)])
def test_no_positive_eligible_credit_retains_exact_anchor(gain, relevant, gurobi_env):
    plan = optimize(diagnostic_fixture(gain=gain, relevant=relevant), gurobi_env)
    assert plan.selected == plan.anchor
    assert not plan.credited
    assert not plan.commitments.pending
    assert plan.information == 0


def test_information_cannot_trade_away_any_service(gurobi_env):
    probe = action("probe", "A", kind="diagnose")
    response = action("response", "A", kind="recover", start=2, end=3)
    service = action("service", "B", groups=("alternative",))
    later = action("later", "B", start=4, end=5, groups=("alternative",))
    instance = problem(
        probe,
        response,
        service,
        later,
        credits={"service": (1,), "later": (1 - 1e-4,)},
        diagnostics=(diagnostic("probe", "response", gain=100),),
        required_anchor={},
    )
    plan = optimize(instance, gurobi_env)
    assert ids(plan.anchor) == {"service"}
    assert plan.selected == plan.anchor
    assert plan.service == plan.anchor_service == 0.5
    assert not plan.credited


def test_equal_combined_service_allows_replacing_nonrequired_anchor(gurobi_env):
    anchor = action("anchor", "A", groups=("A-or-B", "A-or-C"))
    replacement_b = action("replacement-B", "B", start=1, end=2, groups=("A-or-B",))
    replacement_c = action("replacement-C", "C", start=2, end=3, groups=("A-or-C",))
    probe = action("probe", "D", kind="diagnose", feedback=1)
    response = action("response", "D", kind="recover", start=3, end=4)
    instance = problem(
        anchor,
        replacement_b,
        replacement_c,
        probe,
        response,
        credits={"anchor": (1,), "replacement-B": (1,), "replacement-C": (1,)},
        priorities={"A": 2, "B": 1, "C": 1, "D": 1},
        diagnostics=(diagnostic("probe", "response"),),
        required_anchor={},
    )
    plan = optimize(instance, gurobi_env)
    assert ids(plan.anchor) == {"anchor"}
    assert ids(plan.selected) == {"probe", "replacement-B", "replacement-C"}
    assert [d.action_id for d in plan.credited] == ["probe"]
    assert plan.service == plan.anchor_service == pytest.approx(0.4)


def test_explicit_required_anchor_prevents_its_replacement(gurobi_env):
    anchor = action("anchor", "A", groups=("A-or-B", "A-or-C"))
    replacement_b = action("replacement-B", "B", start=1, end=2, groups=("A-or-B",))
    replacement_c = action("replacement-C", "C", start=2, end=3, groups=("A-or-C",))
    probe = action("probe", "D", kind="diagnose")
    response = action("response", "D", kind="recover", start=3, end=4)
    instance = problem(
        anchor,
        replacement_b,
        replacement_c,
        probe,
        response,
        credits={"anchor": (1,), "replacement-B": (1,), "replacement-C": (1,)},
        priorities={"A": 2, "B": 1, "C": 1, "D": 1},
        diagnostics=(diagnostic("probe", "response"),),
        required_anchor={"probe": ("anchor",)},
    )
    plan = optimize(instance, gurobi_env)
    assert ids(plan.anchor) == {"anchor"}
    assert plan.selected == plan.anchor
    assert not plan.credited


@pytest.mark.parametrize("start,allowed", [(0.75, True), (1.0, False), (1.25, False)])
def test_diagnostic_start_must_strictly_precede_next_feedback(start, allowed, gurobi_env):
    plan = optimize(diagnostic_fixture(start=start, next_feedback=1), gurobi_env)
    assert bool(plan.credited) is allowed
    if allowed:
        assert "probe" in ids(plan.commitments.fixed)
        assert plan.next_feedback == 1
    else:
        assert plan.selected == plan.anchor


@pytest.mark.parametrize("conflict", ["capacity", "exclusion"])
def test_joint_outcome_conflict_prevents_individually_feasible_diagnostics(conflict, gurobi_env):
    probes = [
        action(f"probe-{a}", a, kind="diagnose", end=0.2, feedback=1, demands={})
        for a in ("A", "B")
    ]
    responses = [
        action(
            f"response-{asset}",
            asset,
            kind="recover",
            start=2 + (index if conflict == "exclusion" else 0),
            end=3 + (index if conflict == "exclusion" else 0),
            groups=("choose-one",) if conflict == "exclusion" else (),
        )
        for index, asset in enumerate(("A", "B"))
    ]
    routine = action("routine", "C", start=4, end=5)
    values = (
        diagnostic("probe-A", "response-A", gain=0.6),
        diagnostic("probe-B", "response-B", gain=0.4),
    )
    for value in values:
        alone = optimize(
            problem(*probes, *responses, routine, credits={"routine": (1,)}, diagnostics=(value,)),
            gurobi_env,
        )
        assert [d.action_id for d in alone.credited] == [value.action_id]
    joint = optimize(
        problem(*probes, *responses, routine, credits={"routine": (1,)}, diagnostics=values),
        gurobi_env,
    )
    assert [d.action_id for d in joint.credited] == ["probe-A"]
    assert joint.service == joint.anchor_service == pytest.approx(1 / 3)


def test_information_optimum_matches_full_schedule_and_outcome_oracle(gurobi_env):
    probes = [
        action(f"probe-{asset}", asset, kind="diagnose", end=0.2, feedback=1, demands={})
        for asset in ("A", "B", "C")
    ]
    responses = [
        action("response-A", "A", kind="recover", start=2, end=3),
        action("response-B", "B", kind="recover", start=2, end=3),
        action("response-C", "C", kind="recover", start=3, end=4),
    ]
    routine = action("routine", "D", start=5, end=6)
    instance = problem(
        *probes,
        *responses,
        routine,
        credits={"routine": (1,)},
        priorities={"A": 1, "B": 2, "C": 3, "D": 1},
        diagnostics=tuple(
            diagnostic(f"probe-{asset}", f"response-{asset}", gain=gain)
            for asset, gain in (("A", 0.9), ("B", 0.6), ("C", 0.2))
        ),
    )
    best_gain, best_pairs = information_oracle(instance)
    plan = optimize(instance, gurobi_env)
    credited = frozenset(d.action_id for d in plan.credited)
    assert (ids(plan.selected), credited) in best_pairs
    assert credited == {"probe-B", "probe-C"}
    assert plan.information == pytest.approx(best_gain)
    assert plan.service == plan.anchor_service == pytest.approx(1 / 7)
    assert len(plan.commitments.pending) == 2


def test_response_can_replace_uncommitted_post_feedback_anchor(gurobi_env):
    probe = action("probe", "A", kind="diagnose", end=0.2, feedback=1)
    response_a = action("response-A", "A", kind="recover", start=2, end=3)
    response_b = action("response-B", "A", kind="recover", start=2, end=3)
    value = Diagnostic(
        "probe",
        0.2,
        {"mode-A": "response-A", "mode-B": "response-B"},
        {"mode-A": 0.5, "mode-B": 0.5},
    )
    plan = optimize(
        problem(
            probe,
            response_a,
            response_b,
            credits={"response-A": (0.6,), "response-B": (0.4,)},
            diagnostics=(value,),
        ),
        gurobi_env,
    )
    assert ids(plan.anchor) == {"response-A"}
    assert ids(plan.selected) == {"probe", "response-A"}
    assert ids(plan.commitments.fixed) == {"probe"}
    assert plan.commitments.pending[0].responses == {
        "mode-A": response_a,
        "mode-B": response_b,
    }
    after_feedback = plan.commitments.resolve({"probe": "mode-B"}, completed=("probe",))
    assert ids(after_feedback.fixed) == {"response-B"}
    assert not after_feedback.pending


def test_at_most_one_diagnostic_per_asset_is_credited(gurobi_env):
    first = action("first", "A", kind="diagnose", start=0, end=0.1, feedback=0.2)
    second = action("second", "A", kind="diagnose", start=0.3, end=0.4, feedback=0.5)
    response = action("response", "A", kind="recover", start=1, end=2)
    plan = optimize(
        problem(
            first,
            second,
            response,
            diagnostics=(
                diagnostic("first", "response", gain=0.3),
                diagnostic("second", "response", gain=0.5),
            ),
        ),
        gurobi_env,
    )
    assert [d.action_id for d in plan.credited] == ["second"]
    assert len(plan.commitments.pending) == 1


def test_rare_outcome_still_requires_feasible_response(gurobi_env):
    probe = action("probe", "A", kind="diagnose", end=0.2, feedback=1, demands={})
    response = action("response", "A", kind="recover", start=2, end=3)
    fixed = action("fixed", "B", start=2, end=3)
    plan = optimize(
        problem(
            probe,
            response,
            fixed,
            credits={"fixed": (1,)},
            diagnostics=(diagnostic("probe", "response", probability=1e-6),),
            commitments=Commitments(fixed=(fixed,)),
        ),
        gurobi_env,
    )
    assert not plan.credited
    assert plan.selected == plan.anchor


def test_pending_and_fixed_identical_response_is_counted_once(gurobi_env):
    response = action("response", "A", kind="recover", start=2, end=3)
    routine = action("routine", "B", start=4, end=5)
    promise = PendingDiagnostic("old-probe", "A", 1, {"fault": response, "healthy": None})
    retained = Commitments(fixed=(response,), pending=(promise,))
    plan = optimize(
        problem(
            response,
            routine,
            credits={"response": (0.5,), "routine": (1,)},
            commitments=retained,
        ),
        gurobi_env,
    )
    assert ids(plan.selected) == {"response", "routine"}
    assert plan.commitments.pending == (promise,)
    assert ids(plan.commitments.fixed) == {"response"}


def test_pending_response_blocks_conflicting_early_commitment(gurobi_env):
    response = action("response", "A", kind="recover", start=2, end=3)
    long = action("long", "B", start=0, end=3, feedback=3)
    safe = action("safe", "B", start=0, end=0.5)
    promise = PendingDiagnostic("old-probe", "A", 1, {"fault": response, "healthy": None})
    plan = optimize(
        problem(
            response,
            long,
            safe,
            credits={"long": (1,), "safe": (0.4,)},
            commitments=Commitments(pending=(promise,)),
        ),
        gurobi_env,
    )
    assert ids(plan.selected) == {"safe"}
    assert plan.service == pytest.approx(0.2)
    assert plan.commitments.pending == (promise,)


def test_new_response_is_certified_jointly_with_pending_response(gurobi_env):
    old_response = action("old-response", "A", kind="recover", start=2, end=3)
    pending = PendingDiagnostic("old-probe", "A", 1, {"fault": old_response, "healthy": None})
    probe = action("new-probe", "B", kind="diagnose", end=0.2, feedback=1)
    response = action("new-response", "B", kind="recover", start=2, end=3)
    plan = optimize(
        problem(
            old_response,
            probe,
            response,
            diagnostics=(diagnostic("new-probe", "new-response"),),
            commitments=Commitments(pending=(pending,)),
        ),
        gurobi_env,
    )
    assert not plan.credited
    assert plan.commitments.pending == (pending,)


@pytest.mark.parametrize("required,credited", [(None, False), ({}, True)])
def test_required_anchor_outside_prefix_participates_in_response_certificate(
    required, credited, gurobi_env
):
    early = action("early", "A", start=0, end=1, demands={})
    anchor = action("later-anchor", "B", start=1.5, end=3)
    probe = action("probe", "C", kind="diagnose", end=0.2, feedback=2, demands={})
    response = action("response", "C", kind="recover", start=2, end=3)
    plan = optimize(
        problem(
            early,
            anchor,
            probe,
            response,
            credits={"early": (1,), "later-anchor": (1,)},
            diagnostics=(diagnostic("probe", "response"),),
            required_anchor=required,
        ),
        gurobi_env,
    )
    assert ids(plan.anchor) == {"early", "later-anchor"}
    assert bool(plan.credited) is credited
    assert plan.service == plan.anchor_service == pytest.approx(2 / 3)
    assert plan.next_feedback == 1


def test_pending_and_unfinished_recovery_both_block_fresh_credit(gurobi_env):
    probe = action("new-probe", "A", kind="diagnose", end=0.1, feedback=1, demands={})
    fresh_response = action("new-response", "A", kind="recover", start=1, end=1.5)
    old_response = action("old-response", "A", kind="recover", start=3, end=4)
    value = diagnostic("new-probe", "new-response")
    pending = PendingDiagnostic("old-probe", "A", 2, {"fault": old_response, "healthy": None})
    awaiting_feedback = Commitments(pending=(pending,))
    awaiting_completion = awaiting_feedback.resolve({"old-probe": "fault"})
    for retained in (awaiting_feedback, awaiting_completion):
        plan = optimize(
            problem(
                probe, fresh_response, old_response, diagnostics=(value,), commitments=retained
            ),
            gurobi_env,
        )
        assert not plan.credited
    released = awaiting_completion.resolve({}, completed=("old-response",))
    plan = optimize(
        problem(probe, fresh_response, old_response, diagnostics=(value,), commitments=released),
        gurobi_env,
    )
    assert [d.action_id for d in plan.credited] == ["new-probe"]


def test_external_recovery_lock_blocks_only_its_own_assets_credit(gurobi_env):
    probe_a = action("probe-A", "A", kind="diagnose", end=0.2, feedback=1, demands={})
    probe_b = action("probe-B", "B", kind="diagnose", end=0.2, feedback=1, demands={})
    response_a = action("response-A", "A", kind="recover", start=2, end=3)
    response_b = action("response-B", "B", kind="recover", start=3, end=4)
    routine_a = action("routine-A", "A", start=5, end=6)
    instance = problem(
        probe_a,
        probe_b,
        response_a,
        response_b,
        routine_a,
        credits={"routine-A": (1,)},
        diagnostics=(
            diagnostic("probe-A", "response-A", gain=0.8),
            diagnostic("probe-B", "response-B", gain=0.3),
        ),
        blocked_assets=frozenset({"A"}),
    )
    plan = optimize(instance, gurobi_env)
    assert [d.action_id for d in plan.credited] == ["probe-B"]
    assert "routine-A" in ids(plan.selected)
    assert plan.service == plan.anchor_service == 0.5


def test_resolving_feedback_retains_other_promises_and_fixed_actions():
    fixed = action("fixed", "C", start=0, end=1)
    response_a = action("response-A", "A", kind="recover", start=2, end=3)
    response_b = action("response-B", "B", kind="recover", start=3, end=4)
    promise_a = PendingDiagnostic("probe-A", "A", 1, {"fault": response_a, "healthy": None})
    promise_b = PendingDiagnostic("probe-B", "B", 2, {"fault": response_b, "healthy": None})
    original = Commitments(fixed=(fixed,), pending=(promise_a, promise_b))
    partial = original.resolve({"probe-A": "fault"})
    assert ids(partial.fixed) == {"fixed", "response-A"}
    assert partial.pending == (promise_b,)
    finished = partial.resolve({"probe-B": "healthy"}, completed=("fixed",))
    assert ids(finished.fixed) == {"response-A"}
    assert not finished.pending
    assert original.fixed == (fixed,)
    assert original.pending == (promise_a, promise_b)


def test_outcome_budget_raises_instead_of_silently_omitting_branches(gurobi_env):
    response = action("response", "A", kind="recover", start=2, end=3)
    promise = PendingDiagnostic("old-probe", "A", 1, {"fault": response, "healthy": None})
    instance = problem(response, commitments=Commitments(pending=(promise,)))
    with pytest.raises(CertificationLimit):
        optimize(instance, gurobi_env, max_outcome_combinations=1)


def test_equivalent_outcomes_share_one_response_branch(gurobi_env):
    probe = action("probe", "A", kind="diagnose", end=0.2, feedback=1)
    response = action("response", "A", kind="recover", start=2, end=3)
    value = Diagnostic(
        "probe",
        0.2,
        {"fault-1": "response", "fault-2": "response", "healthy": None},
        {"fault-1": 0.2, "fault-2": 0.3, "healthy": 0.5},
    )
    plan = optimize(
        problem(probe, response, diagnostics=(value,)),
        gurobi_env,
        max_outcome_combinations=2,
    )
    assert [d.action_id for d in plan.credited] == ["probe"]
    assert set(plan.commitments.pending[0].responses) == {"fault-1", "fault-2", "healthy"}


def test_missing_or_changed_retained_actions_are_rejected():
    fixed = action("fixed", "A")
    other = action("other", "A", start=2, end=3)
    with pytest.raises(ValueError, match="missing or changed fixed"):
        problem(other, commitments=Commitments(fixed=(fixed,)))
    changed = action("fixed", "A", end=1.1)
    with pytest.raises(ValueError, match="missing or changed fixed"):
        problem(changed, commitments=Commitments(fixed=(fixed,)))
    response = action("response", "A", kind="recover", start=3, end=4)
    pending = PendingDiagnostic("probe", "A", 2, {"fault": response, "healthy": None})
    with pytest.raises(ValueError, match="missing or changed promised response"):
        problem(other, commitments=Commitments(pending=(pending,)))
    changed_response = action("response", "A", kind="recover", start=3, end=4.1)
    with pytest.raises(ValueError, match="missing or changed promised response"):
        problem(changed_response, commitments=Commitments(pending=(pending,)))


def test_empty_problem_returns_wait_until_known_feedback(gurobi_env):
    plan = optimize(problem(next_feedback=4.5), gurobi_env)
    assert not plan.selected
    assert not plan.anchor
    assert not plan.credited
    assert plan.service == plan.anchor_service == plan.information == 0
    assert plan.next_feedback == 4.5
    assert not plan.stats


def test_exhausted_time_limit_raises_without_returning_partial_plan(gurobi_env):
    instance = problem(action("routine"), credits={"routine": (1,)})
    with pytest.raises(SolveError) as error:
        solve(instance, options=SolverOptions(time_limit=1e-12), env=gurobi_env)
    assert error.value.status == gp.GRB.TIME_LIMIT
