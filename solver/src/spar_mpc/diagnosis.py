"""One-step diagnostic values and fixed recovery-or-wait response maps.

The prior is supplied at diagnostic feedback time. Recovery values must already
account for success, compatibility, and timeliness; these helpers do not infer
fault transitions, recovery clocks, or action feasibility. Distinct responses
used by the relevance gate are assumed mutually exclusive by the caller. The
scheduler must separately certify their timing and joint resource feasibility.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from itertools import combinations
from math import fsum
from types import MappingProxyType

from .belief import _covers, _distribution, _identifier, _number, _probabilities, update


@dataclass(frozen=True)
class Diagnostic:
    """A diagnostic's value and immutable, outcome-specific response promises.

    Outcome maps contain all possible outcomes, with strictly positive
    probabilities summing to one. ``None`` denotes waiting. Map contents are
    copied on construction, so subsequent caller mutations cannot alter a plan.
    """

    action_id: str
    gain: float
    responses: Mapping[str, str | None]
    outcome_probabilities: Mapping[str, float]
    decision_relevant: bool = True

    def __post_init__(self) -> None:
        _identifier(self.action_id, "action_id")
        gain = _number(self.gain, "gain")
        if gain < 0:
            raise ValueError("gain must be nonnegative")
        if not isinstance(self.decision_relevant, bool):
            raise ValueError("decision_relevant must be a boolean")
        probabilities = _distribution(self.outcome_probabilities, "outcome_probabilities")
        if any(probability == 0 for probability in probabilities.values()):
            raise ValueError("omit zero-probability outcomes from a Diagnostic")
        if not isinstance(self.responses, Mapping):
            raise ValueError("responses must be a mapping")
        responses = dict(self.responses)
        if responses.keys() != probabilities.keys():
            raise ValueError("responses and outcome_probabilities must have the same outcomes")
        for response in responses.values():
            if response is not None:
                _identifier(response, "response action")
        object.__setattr__(self, "gain", gain)
        object.__setattr__(self, "responses", MappingProxyType(responses))
        object.__setattr__(self, "outcome_probabilities", MappingProxyType(probabilities))


def value_diagnostic(
    action_id: str,
    prior: Mapping[str, float],
    likelihoods: Mapping[str, Mapping[str, float]],
    recoveries: Mapping[str, Mapping[str, float]],
    recovery_cost: float = 0.02,
    min_outcome_probability: float = 0.01,
    min_margin: float = 1e-6,
) -> Diagnostic:
    """Compute gated expected value of sample information (paper Eq. 9).

    ``likelihoods[class][outcome]`` is a row-stochastic observation model;
    omitted outcomes in a row have probability zero. ``recoveries[action][class]``
    supplies recovery values in [0, 1]. Waiting has value zero; each recovery's
    expected value is reduced by ``recovery_cost``. Exact ties prefer waiting,
    then lexicographically ordered action IDs.

    The gate requires two outcomes with probability at least the threshold,
    different best responses, and each response beating the other's response by
    at least ``min_margin`` under its own posterior. Every positive-probability
    outcome contributes to EVSI and retains a response, even below the threshold.
    A failed gate sets the returned gain to zero.
    """
    _identifier(action_id, "action_id")
    belief = _distribution(prior, "prior")
    recovery_cost = _number(recovery_cost, "recovery_cost")
    min_margin = _number(min_margin, "min_margin")
    min_outcome_probability = _number(min_outcome_probability, "min_outcome_probability")
    if recovery_cost < 0 or min_margin < 0:
        raise ValueError("recovery_cost and min_margin must be nonnegative")
    if not 0 <= min_outcome_probability <= 1:
        raise ValueError("min_outcome_probability must be between zero and one")
    if not isinstance(likelihoods, Mapping) or not isinstance(recoveries, Mapping):
        raise ValueError("likelihoods and recoveries must be mappings")
    rows = {}
    for intervention_class, row in likelihoods.items():
        _identifier(intervention_class, "likelihood class")
        rows[intervention_class] = _distribution(row, f"likelihoods[{intervention_class!r}]")
    _covers(rows, belief, "likelihoods")
    rewards = {}
    for response, values in recoveries.items():
        _identifier(response, "recovery action")
        rewards[response] = _probabilities(values, f"recoveries[{response!r}]")
        _covers(rewards[response], belief, f"recoveries[{response!r}]")

    def scores(distribution: Mapping[str, float]) -> dict[str | None, float]:
        result: dict[str | None, float] = {None: 0.0}
        for response in sorted(rewards):
            result[response] = (
                fsum(
                    probability * rewards[response][intervention_class]
                    for intervention_class, probability in distribution.items()
                )
                - recovery_cost
            )
        return result

    outcomes = sorted({outcome for row in rows.values() for outcome in row})
    probabilities = {}
    responses = {}
    posterior_scores = {}
    for outcome in outcomes:
        likelihood = {state: rows[state].get(outcome, 0.0) for state in belief}
        probability = fsum(belief[state] * likelihood[state] for state in belief)
        if probability == 0:
            continue
        values = scores(update(belief, likelihood))
        probabilities[outcome] = probability
        # Dict insertion order implements wait-first, stable-ID tie-breaking.
        responses[outcome] = max(values, key=values.__getitem__)
        posterior_scores[outcome] = values

    likely = [
        outcome
        for outcome in outcomes
        if probabilities.get(outcome, 0) > 0 and probabilities[outcome] >= min_outcome_probability
    ]
    relevant = False
    for first, second in combinations(likely, 2):
        first_response, second_response = responses[first], responses[second]
        if first_response == second_response:
            continue
        first_advantage = (
            posterior_scores[first][first_response] - posterior_scores[first][second_response]
        )
        second_advantage = (
            posterior_scores[second][second_response] - posterior_scores[second][first_response]
        )
        if first_advantage >= min_margin and second_advantage >= min_margin:
            relevant = True
            break
    gain = (
        max(
            0.0,
            fsum(
                probability * posterior_scores[outcome][responses[outcome]]
                for outcome, probability in probabilities.items()
            )
            - max(scores(belief).values()),
        )
        if relevant
        else 0.0
    )
    return Diagnostic(action_id, gain, responses, probabilities, relevant)
