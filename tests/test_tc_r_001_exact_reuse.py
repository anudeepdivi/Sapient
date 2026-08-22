from harness.adapter import SponsorEnv
from harness.resolver import resolve_case
from tests.harness_base import HarnessTestCase


class TestTCR001(HarnessTestCase):
    def test_action_is_reuse_with_zero_delta(self):
        case = self.load_case("TC-R-001")
        results = resolve_case(case, SponsorEnv(self.env_root), self.state_dir)
        result, expected = results[0], case["expected"]
        self.assertEqual(result["status"], expected["status"])
        self.assertEqual(result["action"], expected["action"])
        self.assertEqual(result["standard_match"], expected["standard_match"])
        self.assertEqual(result["delta_count"], 0)
        self.assertFalse(result["generate_new_program"])

    def test_deprecated_and_draft_versions_never_selected(self):
        env = SponsorEnv(self.env_root)
        self.assertEqual(env.get_version("ADSL", "1.0")["status"], "deprecated")
        case = self.load_case("TC-R-001")
        result = resolve_case(case, env, self.state_dir)[0]
        self.assertEqual(result["version"], "2.0")
        self.assertNotEqual(result["standard_match"], "ADSL_v1.R")
