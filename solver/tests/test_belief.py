import unittest

from spar_mpc.belief import aggregate, condition, predict, update


class BeliefTests(unittest.TestCase):
    def test_predict_uses_source_rows_and_preserves_zero_states(self):
        result = predict(
            {"healthy": 0.75, "fault": 0.25},
            {
                "healthy": {"healthy": 0.8, "fault": 0.2, "lost": 0.0},
                "fault": {"healthy": 0.4, "fault": 0.6},
            },
        )
        self.assertAlmostEqual(result["healthy"], 0.7)
        self.assertAlmostEqual(result["fault"], 0.3)
        self.assertEqual(result["lost"], 0.0)

    def test_full_model_can_be_used_with_sparse_prior(self):
        self.assertEqual(
            predict({"a": 1.0}, {"a": {"b": 1.0}, "b": {"a": 1.0}}),
            {"a": 0.0, "b": 1.0},
        )
        self.assertEqual(update({"a": 1.0}, {"a": 0.1, "b": 0.9}), {"a": 1.0})

    def test_update_matches_bayes_and_does_not_mutate(self):
        prior = {"a": 0.25, "b": 0.75, "impossible": 0.0}
        result = update(prior, {"a": 0.8, "b": 0.2, "impossible": 1.0})
        self.assertAlmostEqual(result["a"], 4 / 7)
        self.assertAlmostEqual(result["b"], 3 / 7)
        self.assertEqual(result["impossible"], 0.0)
        self.assertEqual(prior, {"a": 0.25, "b": 0.75, "impossible": 0.0})

    def test_simultaneous_observations_equal_sequential_updates(self):
        prior = {"a": 0.4, "b": 0.6}
        observations = [{"a": 0.8, "b": 0.3}, {"a": 0.2, "b": 0.7}]
        batch = condition(prior, observations)
        sequential = update(update(prior, observations[0]), observations[1])
        for state in prior:
            self.assertAlmostEqual(batch[state], sequential[state])

    def test_log_weights_avoid_likelihood_product_underflow(self):
        result = condition({"a": 0.25, "b": 0.75}, [{"a": 1e-100, "b": 1e-100}] * 20)
        self.assertAlmostEqual(result["a"], 0.25, places=12)
        self.assertAlmostEqual(result["b"], 0.75, places=12)

    def test_empty_batch_and_aggregation(self):
        prior = {"radio1": 0.2, "radio2": 0.3, "deployment": 0.5}
        self.assertEqual(condition(prior, []), prior)
        self.assertIsNot(condition(prior, []), prior)
        self.assertEqual(
            aggregate(prior, {"radio1": "wait", "radio2": "wait", "deployment": "deploy"}),
            {"wait": 0.5, "deploy": 0.5},
        )

    def test_impossible_evidence_is_an_error(self):
        for observations in ([{"a": 0.0, "b": 0.0}], [{"a": 1.0, "b": 0.0}, {"a": 0.0, "b": 1.0}]):
            with self.subTest(observations=observations), self.assertRaises(ValueError):
                condition({"a": 0.5, "b": 0.5}, observations)

    def test_invalid_probability_inputs_are_rejected(self):
        for invalid in (-0.1, 1.1, float("nan"), float("inf"), True, "1"):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                update({"a": 1.0}, {"a": invalid})
        for prior in ({}, {"a": 0.8}, {"a": -0.1, "b": 1.1}):
            with self.subTest(prior=prior), self.assertRaises(ValueError):
                condition(prior, [])

    def test_missing_entries_and_invalid_unused_rows_are_rejected(self):
        with self.assertRaises(ValueError):
            predict({"a": 1.0}, {"b": {"b": 1.0}})
        with self.assertRaises(ValueError):
            predict({"a": 1.0}, {"a": {"a": 1.0}, "b": {"b": 0.5}})
        with self.assertRaises(ValueError):
            update({"a": 1.0}, {"b": 1.0})
        with self.assertRaises(ValueError):
            aggregate({"a": 1.0}, {"b": "recover"})


if __name__ == "__main__":
    unittest.main()
