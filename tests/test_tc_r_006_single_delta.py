from harness.adapter import SponsorEnv
from harness.deltas import apply_deltas, materialize
from harness.resolver import resolve_case
from harness.r_executor import run_r_file
from tests.harness_base import HarnessTestCase


class TestTCR006(HarnessTestCase):
    def setUp(self):
        super().setUp()
        self.env = SponsorEnv(self.env_root)
        self.case = self.load_case("TC-R-006")
        self.result = resolve_case(self.case, self.env, self.state_dir)[0]

    def test_single_population_filter_delta_detected(self):
        expected = self.case["expected"]
        self.assertEqual(self.result["status"], expected["status"])
        self.assertEqual(self.result["action"], expected["action"])
        self.assertEqual(self.result["standard_match"], expected["standard_match"])
        self.assertEqual(self.result["delta_count"], 1)
        self.assertEqual(self.result["delta_types"], expected["delta_types"])
        delta = self.result["deltas"][0]
        self.assertEqual(delta["type"], "population_filter")
        self.assertEqual(delta["source_requirement"], "R-006")
        self.assertIn("standard_text", delta["evidence"])
        self.assertIn("requirement_text", delta["evidence"])
        self.assertEqual(delta["evidence"]["source_sections"], ["SAP §9.2"])

    def test_applied_copy_executes_under_rscript(self):
        rel = f"standards/adae/{self.result['standard_match']}"
        original = self.env.read_program(rel)
        self.assertEqual(original.count('filter(ae1, SAFFL == "Y")'), 1)
        modified = apply_deltas(original, self.result["deltas"])
        self.assertIn('SPECIALFL == "Y"', modified)
        path = materialize(self.env, rel, modified,
                           self.case["study_requirement"]["study_id"], self.state_dir)
        executed = run_r_file(path, cwd=self.env.root)
        self.assertTrue(executed["success"], executed["stderr"])

    def test_standard_program_not_modified_after_apply(self):
        rel = self.env.program_path(f"standards/adae/{self.result['standard_match']}")
        before = rel.read_bytes()
        modified = apply_deltas(rel.read_text(), self.result["deltas"])
        materialize(self.env, "standards/adae/ADAE_v2.R", modified,
                    self.case["study_requirement"]["study_id"], self.state_dir)
        self.assertEqual(rel.read_bytes(), before)
