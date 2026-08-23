from harness.adapter import SponsorEnv
from harness.resolver import resolve_case
from tests.harness_base import HarnessTestCase


class TestTCR005(HarnessTestCase):
    def setUp(self):
        super().setUp()
        self.env = SponsorEnv(self.env_root)
        self.case = self.load_case("TC-R-005")

    def test_full_reuse_with_zero_deltas_and_zero_modifications(self):
        result = resolve_case(self.case, self.env, self.state_dir)[0]
        expected = self.case["expected"]
        self.assertTrue(expected["reuse"])
        self.assertEqual(result["action"], expected["action"])
        self.assertEqual(result["standard_match"], expected["standard_match"])
        self.assertEqual(result["delta_count"], expected["delta_count"])
        self.assertFalse(result["generate_new_program"])

    def test_no_program_is_modified_or_materialized(self):
        resolve_case(self.case, self.env, self.state_dir)[0]
        artifacts = self.state_dir / "artifacts"
        self.assertFalse(artifacts.exists())
        self.assertEqual(list(self.env_root.rglob("*_delta.R")), [])
