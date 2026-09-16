import unittest
from dataclasses import FrozenInstanceError

from spar_mpc.diagnosis import Diagnostic, value_diagnostic


class DiagnosisTests(unittest.TestCase):
    def test_perfect_information_switches_recovery_and_has_expected_gain(self):
        diagnostic = value_diagnostic(
            "listen",
            {"a": 0.5, "b": 0.5},
            {"a": {"a": 1.0}, "b": {"b": 1.0}},
            {"recover_a": {"a": 1.0, "b": 0.0}, "recover_b": {"a": 0.0, "b": 1.0}},
        )
        self.assertTrue(diagnostic.decision_relevant)
        self.assertAlmostEqual(diagnostic.gain, 0.5)
        self.assertEqual(dict(diagnostic.responses), {"a": "recover_a", "b": "recover_b"})

    def test_wait_response_and_recovery_cost(self):
        diagnostic = value_diagnostic(
            "listen",
            {"healthy": 0.5, "fault": 0.5},
            {"healthy": {"healthy": 1.0}, "fault": {"fault": 1.0}},
            {"repair": {"healthy": 0.0, "fault": 1.0}},
            recovery_cost=0.2,
        )
        self.assertEqual(diagnostic.responses["healthy"], None)
        self.assertEqual(diagnostic.responses["fault"], "repair")
        self.assertAlmostEqual(diagnostic.gain, 0.1)

    def test_rare_outcomes_count_in_gain_and_remain_in_responses(self):
        diagnostic = value_diagnostic(
            "listen",
            {"a": 0.499, "b": 0.499, "rare": 0.002},
            {state: {state: 1.0} for state in ("a", "b", "rare")},
            {
                f"repair_{state}": {other: float(state == other) for other in ("a", "b", "rare")}
                for state in ("a", "b", "rare")
            },
            min_outcome_probability=0.01,
        )
        self.assertTrue(diagnostic.decision_relevant)
        self.assertAlmostEqual(diagnostic.gain, 0.501)
        self.assertEqual(diagnostic.responses["rare"], "repair_rare")
        self.assertAlmostEqual(diagnostic.outcome_probabilities["rare"], 0.002)

    def test_rare_outcome_cannot_alone_pass_the_gate(self):
        diagnostic = value_diagnostic(
            "listen",
            {"a": 0.999, "b": 0.001},
            {"a": {"a": 1.0}, "b": {"b": 1.0}},
            {"repair_a": {"a": 1.0, "b": 0.0}, "repair_b": {"a": 0.0, "b": 1.0}},
        )
        self.assertFalse(diagnostic.decision_relevant)
        self.assertEqual(diagnostic.gain, 0.0)
        self.assertEqual(diagnostic.responses["b"], "repair_b")

    def test_gate_requires_cross_response_margin_on_both_outcomes(self):
        diagnostic = value_diagnostic(
            "listen",
            {"a": 0.5, "b": 0.5},
            {"a": {"a": 1.0}, "b": {"b": 1.0}},
            {"repair_a": {"a": 1.0, "b": 0.49}, "repair_b": {"a": 0.0, "b": 0.5}},
            min_margin=0.02,
        )
        self.assertEqual(dict(diagnostic.responses), {"a": "repair_a", "b": "repair_b"})
        self.assertFalse(diagnostic.decision_relevant)
        self.assertEqual(diagnostic.gain, 0.0)

    def test_information_without_a_decision_change_has_no_credit(self):
        diagnostic = value_diagnostic(
            "listen",
            {"a": 0.5, "b": 0.5},
            {"a": {"a": 1.0}, "b": {"b": 1.0}},
            {"repair": {"a": 1.0, "b": 1.0}},
        )
        self.assertFalse(diagnostic.decision_relevant)
        self.assertEqual(diagnostic.gain, 0.0)

    def test_ties_prefer_wait_then_stable_action_ids(self):
        wait = value_diagnostic(
            "listen", {"a": 1.0}, {"a": {"seen": 1.0}}, {"repair": {"a": 0.2}}, recovery_cost=0.2
        )
        self.assertIsNone(wait.responses["seen"])
        action = value_diagnostic(
            "listen",
            {"a": 1.0},
            {"a": {"seen": 1.0}},
            {"z_repair": {"a": 0.5}, "a_repair": {"a": 0.5}},
        )
        self.assertEqual(action.responses["seen"], "a_repair")

    def test_no_recoveries_and_impossible_outcomes(self):
        diagnostic = value_diagnostic(
            "listen",
            {"a": 1.0, "b": 0.0},
            {"a": {"seen": 1.0, "never": 0.0}, "b": {"other": 1.0}},
            {},
        )
        self.assertEqual(dict(diagnostic.responses), {"seen": None})
        self.assertEqual(dict(diagnostic.outcome_probabilities), {"seen": 1.0})
        self.assertEqual(diagnostic.gain, 0.0)
        self.assertFalse(diagnostic.decision_relevant)

    def test_constructor_snapshots_and_freezes_mappings(self):
        responses = {"seen": "repair"}
        probabilities = {"seen": 1.0}
        diagnostic = Diagnostic("listen", 0.1, responses, probabilities)
        responses["seen"] = None
        probabilities["seen"] = 0.0
        self.assertEqual(diagnostic.responses["seen"], "repair")
        self.assertEqual(diagnostic.outcome_probabilities["seen"], 1.0)
        with self.assertRaises(TypeError):
            diagnostic.responses["seen"] = None
        with self.assertRaises(FrozenInstanceError):
            diagnostic.gain = 2.0

    def test_invalid_inputs_are_rejected(self):
        with self.assertRaises(ValueError):
            Diagnostic("listen", float("nan"), {"seen": None}, {"seen": 1.0})
        with self.assertRaises(ValueError):
            Diagnostic("listen", 0.0, {"seen": None}, {"other": 1.0})
        with self.assertRaises(ValueError):
            Diagnostic("listen", 0.0, {"seen": None, "never": None}, {"seen": 1.0, "never": 0.0})
        cases = [
            ({"a": 0.9}, {"a": {"seen": 1.0}}, {}, {}),
            ({"a": 1.0}, {"a": {"seen": 0.9}}, {}, {}),
            ({"a": 1.0}, {"a": {"seen": 1.0}}, {"repair": {"b": 1.0}}, {}),
            ({"a": 1.0}, {"a": {"seen": 1.0}}, {"repair": {"a": float("inf")}}, {}),
            ({"a": 1.0}, {"a": {"seen": 1.0}}, {}, {"min_margin": -0.1}),
            ({"a": 1.0}, {"a": {"seen": 1.0}}, {}, {"min_outcome_probability": 1.1}),
            ({"a": 1.0}, {"a": {"seen": 1.0}}, {}, {"recovery_cost": float("nan")}),
        ]
        for prior, likelihoods, recoveries, options in cases:
            with self.subTest(
                prior=prior, likelihoods=likelihoods, recoveries=recoveries, options=options
            ):
                with self.assertRaises(ValueError):
                    value_diagnostic("listen", prior, likelihoods, recoveries, **options)


if __name__ == "__main__":
    unittest.main()
