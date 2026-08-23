from harness.adapter import SponsorEnv
from harness.resolver import resolve_case
from tests.harness_base import HarnessTestCase


class TestTCR003(HarnessTestCase):
    def setUp(self):
        super().setUp()
        self.env = SponsorEnv(self.env_root)
        self.case = self.load_case("TC-R-003")

    def test_only_the_approved_version_is_selected(self):
        result = resolve_case(self.case, self.env, self.state_dir)[0]
        expected = self.case["expected"]
        self.assertEqual(result["status"], expected["status"])
        self.assertEqual(result["action"], expected["action"])
        self.assertEqual(result["standard_match"], expected["standard_match"])
        self.assertEqual(result["version"], expected["version"])

    def test_draft_and_deprecated_are_never_candidates(self):
        result = resolve_case(self.case, self.env, self.state_dir)[0]
        self.assertNotEqual(result["standard_match"], "ADVS_v4.R")
        self.assertNotEqual(result["standard_match"], "ADVS_v6.R")
        # the newest version is the draft — recency must not have won
        self.assertNotEqual(result.get("version"), "6.0")
