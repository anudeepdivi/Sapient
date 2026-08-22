from harness.adapter import SponsorEnv
from harness.deltas import apply_deltas
from harness.preservation import compare_programs, compute_metrics, run_preservation
from harness.resolver import resolve_case
from tests.harness_base import HarnessTestCase


class TestTCR008(HarnessTestCase):
    def setUp(self):
        super().setUp()
        self.env = SponsorEnv(self.env_root)
        self.case = self.load_case("TC-R-008")
        self.study_id = self.case["study_requirement"]["study_id"]
        self.keys = self.case["key_columns"]
        self.result = resolve_case(self.case, self.env, self.state_dir)[0]
        self.expected_removed = self.case["expected"]["removed_keys"]

    def _run_declared(self):
        return run_preservation(self.env, self.case["standard"], self.result["deltas"],
                                self.study_id, self.state_dir, key_cols=self.keys)

    def test_good_delta_fully_preserves_standard_behavior(self):
        run = self._run_declared()
        self.assertTrue(run["executed"])
        self.assertTrue(run["base_run"]["success"], run["base_run"]["stderr"])
        self.assertTrue(run["mod_run"]["success"], run["mod_run"]["stderr"])
        metrics = compute_metrics(run, self.expected_removed,
                                  self.case["expected"]["added_keys"])
        self.assertEqual(metrics["standard_preservation_rate"], 1.0)
        self.assertEqual(metrics["intended_change_recall"], 1.0)
        self.assertEqual(metrics["unintended_change_rate"], 0.0)
        self.assertTrue(metrics["schema_equal"])
        self.assertEqual(sorted(run["removed"]), sorted(self.expected_removed))
        self.assertEqual(run["preserved_count"],
                         self.case["expected"]["preserved_count"])
        # the standard itself is never mutated by any of this
        program = self.env.program_path(self.case["standard"])
        self.assertIn('filter(ae1, SAFFL == "Y")\n', program.read_text())

    def test_value_mutating_delta_executes_but_fails_preservation(self):
        rel = self.case["standard"]
        base_code = self.env.read_program(rel)
        good = apply_deltas(base_code, self.result["deltas"])
        bad = good.replace(
            'ae1 <- filter(ae1, SAFFL == "Y" & SPECIALFL == "Y")',
            'ae1 <- filter(ae1, SAFFL == "Y" & SPECIALFL == "Y")'
            ' %>% mutate(TRTEMFL = "Y")')
        self.assertNotEqual(bad, good)
        run = compare_programs(self.env, rel, base_code, bad,
                               self.study_id, self.state_dir, key_cols=self.keys)
        self.assertTrue(run["executed"])
        # executes, population change exactly right — and still fails preservation
        self.assertTrue(run["mod_run"]["success"])
        metrics = compute_metrics(run, self.expected_removed, [])
        self.assertEqual(metrics["standard_preservation_rate"], 0.0)
        self.assertEqual(metrics["intended_change_recall"], 1.0)
        self.assertGreater(metrics["unintended_change_rate"], 0.0)
        self.assertTrue(any("TRTEMFL" in d for d in run["cell_diffs"]))

    def test_over_restricted_delta_fails_intended_change(self):
        case = self.load_case("TC-R-008")
        case["study_requirement"]["requirements"][0]["population"] += ' & AESEV != "MILD"'
        result = resolve_case(case, self.env, self.state_dir)[0]
        run = run_preservation(self.env, self.case["standard"], result["deltas"],
                               self.study_id, self.state_dir, key_cols=self.keys)
        self.assertTrue(run["executed"])
        metrics = compute_metrics(run, self.expected_removed, [])
        self.assertEqual(metrics["standard_preservation_rate"], 1.0)
        self.assertEqual(metrics["intended_change_recall"], 0.0)
        self.assertNotEqual(sorted(run["removed"]), sorted(self.expected_removed))
