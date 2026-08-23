from harness.adapter import SponsorEnv
from harness.deltas import DeltaAnchorError, apply_deltas, materialize
from harness.resolver import resolve_case
from harness.r_executor import run_r_file
from tests.harness_base import HarnessTestCase


class TestTCR007(HarnessTestCase):
    def setUp(self):
        super().setUp()
        self.env = SponsorEnv(self.env_root)
        self.case = self.load_case("TC-R-007")

    def _resolve(self):
        return resolve_case(self.case, self.env, self.state_dir)[0]

    def test_exactly_three_deltas_of_the_required_types(self):
        result = self._resolve()
        expected = self.case["expected"]
        self.assertEqual(result["status"], expected["status"])
        self.assertEqual(result["action"], expected["action"])
        self.assertEqual(result["delta_count"], expected["delta_count"])
        self.assertEqual(sorted(result["delta_types"]),
                         sorted(expected["delta_types"]))

    def test_each_delta_carries_its_own_requirement_evidence(self):
        deltas = {d["type"]: d for d in self._resolve()["deltas"]}
        req = self.case["study_requirement"]["requirements"][0]
        self.assertEqual(deltas["population_filter"]["evidence"]["requirement_text"],
                         req["population"])
        self.assertEqual(deltas["derivation_change"]["evidence"]["requirement_text"],
                         req["derivation"])
        self.assertEqual(deltas["variable_addition"]["evidence"]["requirement_text"],
                         ", ".join(req["variables"]))
        for delta in deltas.values():
            self.assertEqual(delta["source_requirement"], "R-007")
            self.assertIn("SAP §8.2", delta["evidence"]["source_sections"])

    def test_applied_copy_contains_all_three_changes_and_standard_is_untouched(self):
        result = self._resolve()
        rel = f"standards/advs/{result['standard_match']}"
        base_code = self.env.read_program(rel)
        modified = apply_deltas(base_code, result["deltas"])
        req = self.case["study_requirement"]["requirements"][0]
        self.assertIn(f'filter(advs, {req["population"]})', modified)
        self.assertIn(f'mutate({req["derivation"]})', modified)
        self.assertIn(f'mutate({", ".join(req["variables"])}) %>% arrange', modified)
        self.assertEqual(self.env.read_program(rel), base_code)

    def test_modified_copy_executes_green(self):
        result = self._resolve()
        rel = f"standards/advs/{result['standard_match']}"
        modified = apply_deltas(self.env.read_program(rel), result["deltas"])
        path = materialize(self.env, rel, modified,
                           self.case["study_requirement"]["study_id"], self.state_dir)
        executed = run_r_file(path, cwd=self.env.root)
        self.assertTrue(executed["success"], executed["stderr"])
