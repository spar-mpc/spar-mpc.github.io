"""Two robots sharing a radio, with one observation-conditioned repair.

Run from the repository root after installing ``./solver``:
    python solver/examples/fleet.py --outcome drive
    python solver/examples/fleet.py --outcome sensor

All probabilities, times, and service credits are synthetic.
"""

from __future__ import annotations

import argparse

from spar_mpc import Action, Problem, solve, update, value_diagnostic


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--outcome", choices=("drive", "sensor"), default="drive")
    outcome = parser.parse_args().outcome

    # Absolute time in minutes. The radio is shared by both robots; a drive
    # reset also occupies the one technician. Endpoint-touching jobs can fit.
    inspect = Action("inspect-A", "A", "diagnose", 0, 1, 1, {"radio": 1})
    reset = Action("reset-A", "A", "recover", 2, 3, 3, {"radio": 1, "technician": 1})
    upload = Action("upload-B", "B", "routine", 1, 2, 2, {"radio": 1})
    capacities = {"radio": 1, "technician": 1}
    priorities = {"A": 1, "B": 1}

    # Two equally weighted JOINT scenarios. The same scenario column is used
    # for every action: here A's fault and B's achievable service are correlated.
    # A sensor fault does not benefit from a drive reset, so its response is wait.
    scenario_faults = ("drive", "sensor")
    service = {
        inspect.id: (0.0, 0.0),
        reset.id: (1.0, 0.0),
        upload.id: (1.0, 0.4),
    }
    prior = {"drive": 0.5, "sensor": 0.5}
    likelihoods = {
        "drive": {"drive": 1.0, "sensor": 0.0},
        "sensor": {"drive": 0.0, "sensor": 1.0},
    }
    diagnostic = value_diagnostic(
        action_id=inspect.id,
        prior=prior,
        likelihoods=likelihoods,
        recoveries={reset.id: {"drive": 1.0, "sensor": 0.0}},
        recovery_cost=0.2,
    )
    problem = Problem(
        actions=(inspect, reset, upload),
        priorities=priorities,
        capacities=capacities,
        service=service,
        diagnostics=(diagnostic,),
    )
    plan = solve(problem)

    print("Service anchor:", ", ".join(action.id for action in plan.anchor))
    print("SPAR-MPC plan:", ", ".join(action.id for action in plan.selected))
    print(f"Sampled service: {plan.anchor_service:.3f} -> {plan.service:.3f}")
    print(f"Weighted diagnostic value: {plan.information:.3f}")
    for credited in plan.credited:
        for observation, response in credited.responses.items():
            print(f"  {observation}: {response or 'wait'}")

    # The observation is supplied by the application. Bind the response stored
    # BEFORE observing it, release the completed diagnostic, and preserve all
    # outstanding promises/fixed jobs in the next solve.
    commitments = plan.commitments.resolve({inspect.id: outcome}, completed=(inspect.id,))
    posterior = update(prior, {state: row[outcome] for state, row in likelihoods.items()})

    # With this perfect diagnostic, conditioning the joint scenario set means
    # retaining only the matching column. For a noisy channel an application
    # would instead update its joint belief and resample conditional scenarios.
    matching = [i for i, fault in enumerate(scenario_faults) if fault == outcome]
    next_service = {
        action.id: tuple(service[action.id][i] for i in matching) for action in (reset, upload)
    }
    replanned = solve(
        Problem(
            actions=(reset, upload),
            priorities=priorities,
            capacities=capacities,
            service=next_service,
            commitments=commitments,
        )
    )
    print(f"Observed: {outcome}")
    print("Updated class belief:", dict(posterior))
    print("Replanned actions:", ", ".join(action.id for action in replanned.selected))
    print("A reset command is not a claim that recovery has completed.")


if __name__ == "__main__":
    main()
