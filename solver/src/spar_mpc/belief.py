"""Finite-state belief operations for supplied transition and observation models.

These helpers do not infer dynamics or independence. ``condition`` assumes its
observations are conditionally independent given the state. Model mappings may
include extra states, but must cover every state in the supplied prior.
"""

from collections.abc import Mapping, Sequence
from math import exp, fsum, isclose, isfinite, log
from numbers import Real


def _number(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite number")
    value = float(value)
    if not isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    return value


def _identifier(value: str, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a nonempty string")
    return value


def _probabilities(values: Mapping[str, float], name: str) -> dict[str, float]:
    """Copy and validate probability-valued entries, without requiring sum one."""
    if not isinstance(values, Mapping):
        raise ValueError(f"{name} must be a mapping")
    result = {}
    for key, value in values.items():
        _identifier(key, f"{name} key")
        probability = _number(value, f"{name}[{key!r}]")
        if not 0.0 <= probability <= 1.0:
            raise ValueError(f"{name}[{key!r}] must be between zero and one")
        result[key] = probability
    return result


def _distribution(values: Mapping[str, float], name: str) -> dict[str, float]:
    result = _probabilities(values, name)
    total = fsum(result.values())
    if not result or not isclose(total, 1.0, rel_tol=0.0, abs_tol=1e-12):
        raise ValueError(f"{name} must sum to one")
    return {key: value / total for key, value in result.items()}


def _covers(values: Mapping, states: Mapping, name: str) -> None:
    missing = states.keys() - values.keys()
    if missing:
        raise ValueError(f"{name} is missing states: {', '.join(sorted(missing))}")


def predict(
    prior: Mapping[str, float],
    transition: Mapping[str, Mapping[str, float]],
) -> dict[str, float]:
    """Propagate a prior through a row-stochastic transition kernel.

    ``transition[source][destination]`` is the conditional transition
    probability. Sparse destination rows are allowed; omitted entries are zero.
    All supplied rows are validated, including rows outside the prior's support.
    """
    belief = _distribution(prior, "prior")
    if not isinstance(transition, Mapping):
        raise ValueError("transition must be a mapping")
    rows = {}
    for state, row in transition.items():
        _identifier(state, "transition state")
        rows[state] = _distribution(row, f"transition[{state!r}]")
    _covers(rows, belief, "transition")
    destinations = dict.fromkeys(state for row in rows.values() for state in row)
    result = {
        destination: fsum(
            probability * rows[state].get(destination, 0.0) for state, probability in belief.items()
        )
        for destination in destinations
    }
    return _distribution(result, "predicted belief")


def update(prior: Mapping[str, float], likelihood: Mapping[str, float]) -> dict[str, float]:
    """Condition on one observation; reject evidence with zero probability."""
    return condition(prior, [likelihood])


def condition(
    prior: Mapping[str, float],
    observations: Sequence[Mapping[str, float]],
) -> dict[str, float]:
    """Condition on simultaneous conditionally independent observations.

    Each mapping supplies P(observation | state), not a distribution over states.
    Log weights avoid underflow from multiplying many small likelihoods. Exact
    prior and likelihood zeros remain impossible. An empty batch copies the prior.
    """
    belief = _distribution(prior, "prior")
    if not isinstance(observations, Sequence) or isinstance(observations, (str, bytes)):
        raise ValueError("observations must be a sequence of likelihood mappings")
    likelihoods = []
    for index, observation in enumerate(observations):
        values = _probabilities(observation, f"observations[{index}]")
        _covers(values, belief, f"observations[{index}]")
        likelihoods.append(values)
    if not likelihoods:
        return belief
    weights = {}
    for state, probability in belief.items():
        factors = [probability, *(values[state] for values in likelihoods)]
        weights[state] = fsum(log(value) for value in factors) if all(factors) else -float("inf")
    largest = max(weights.values())
    if not isfinite(largest):
        raise ValueError("observation has zero probability under the prior")
    scaled = {state: exp(value - largest) for state, value in weights.items()}
    total = fsum(scaled.values())
    return {state: value / total for state, value in scaled.items()}


def aggregate(prior: Mapping[str, float], classes: Mapping[str, str]) -> dict[str, float]:
    """Aggregate a state belief into caller-supplied intervention classes."""
    belief = _distribution(prior, "prior")
    if not isinstance(classes, Mapping):
        raise ValueError("classes must be a mapping")
    for state, intervention_class in classes.items():
        _identifier(state, "class state")
        _identifier(intervention_class, "intervention class")
    _covers(classes, belief, "classes")
    grouped: dict[str, list[float]] = {}
    for state, probability in belief.items():
        grouped.setdefault(classes[state], []).append(probability)
    return {intervention_class: fsum(values) for intervention_class, values in grouped.items()}
