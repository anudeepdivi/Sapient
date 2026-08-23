from harness.adapter import SponsorEnv
from harness.resolver import resolve_case
from tests.harness_base import HarnessTestCase


class TestTCR004(HarnessTestCase):
    def setUp(self):
        super().setUp()
        self.env = SponsorEnv(self.env_root)
        self.case = self.load_case("TC-R-004")

    def test_existing_standard_does_not_fully_satisfy_and_delta_is_required(self):
        result = resolve_case(self.case, self.env, self.state_dir)[0]
        expected = self.case["expected"]
        # standard_exists: a match was found against an approved standard
        self.assertTrue(result.get("standard_match"))
        # fully_satisfies: FALSE — at least one explicit delta stands between
        # the standard and the requirement
        self.assertGreaterEqual(result["delta_count"], 1)
        # delta_required: TRUE
        self.assertEqual(result["action"], expected["action"])
        self.assertEqual(sorted(result["delta_types"]),
                         sorted(expected["delta_types"]))

    def test_delta_targets_the_population_only(self):
        result = resolve_case(self.case, self.env, self.state_dir)[0]
        self.assertEqual(len(result["deltas"]), 1)
        delta = result["deltas"][0]
        self.assertEqual(delta["type"], "population_filter")
        self.assertIn('AESER == "Y"', delta["replacement"])
