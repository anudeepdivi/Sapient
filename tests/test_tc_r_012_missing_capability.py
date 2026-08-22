import json

from harness.adapter import SponsorEnv
from harness.resolver import resolve_case
from tests.harness_base import HarnessTestCase


class TestTCR012(HarnessTestCase):
    def setUp(self):
        super().setUp()
        self.env = SponsorEnv(self.env_root)
        self.case = self.load_case("TC-R-012")
        self.result = resolve_case(self.case, self.env, self.state_dir)[0]

    def test_missing_capability_returns_create_proposal(self):
        expected = self.case["expected"]
        self.assertEqual(self.result["status"], expected["status"])
        self.assertEqual(self.result["action"], expected["action"])

    def test_similarly_named_function_is_not_reused(self):
        names = {c["name"] for c in self.env.list_capabilities()}
        self.assertIn("derive_best_response_flag", names)
        self.assertEqual(self.result["missing_capabilities"],
                         ["derive_special_response_flag"])
        self.assertNotIn("standard_match", self.result)

    def test_resolve_generates_nothing(self):
        result_text = json.dumps(self.result, default=str)
        self.assertNotIn(".R", result_text.replace("CREATE_PROPOSAL", ""))
        self.assertFalse((self.state_dir / "proposals").exists())
        self.assertFalse((self.state_dir / "artifacts").exists())
