from harness.adapter import SponsorEnv
from harness.resolver import resolve_case
from tests.harness_base import HarnessTestCase


class TestTCR002(HarnessTestCase):
    def setUp(self):
        super().setUp()
        self.env = SponsorEnv(self.env_root)
        self.case = self.load_case("TC-R-002")

    def _resolve(self):
        return {r["requirement_id"]: r
                for r in resolve_case(self.case, self.env, self.state_dir)}

    def test_declared_attribute_selects_the_matching_standard(self):
        results = self._resolve()
        for rid, exp in self.case["expected"]["by_requirement"].items():
            result = results[rid]
            self.assertEqual(result["status"], self.case["expected"]["status"])
            self.assertEqual(result["action"], self.case["expected"]["action"])
            self.assertEqual(result["standard_match"], exp["standard_match"])
            self.assertEqual(result["delta_count"], exp["delta_count"])

    def test_selection_follows_attributes_not_filename_or_recency(self):
        results = self._resolve()
        self.assertNotEqual(results["R-002A"]["standard_match"],
                            results["R-002B"]["standard_match"])
        for r in results.values():
            self.assertEqual(r["version"], "1.0")

    def test_no_discriminating_attribute_escalates_instead_of_guessing(self):
        req = {"requirement_id": "R-002C", "type": "adam_dataset", "dataset": "ADEFF",
               "population": 'SAFFL == "Y"', "capabilities": [],
               "source_sections": ["SAP §10.9"]}
        result = __import__("harness.resolver", fromlist=["resolve"]).resolve(
            req, self.env, self.state_dir)
        self.assertEqual(result["status"], "WAITING_FOR_HUMAN")
        self.assertEqual(result["reason"], "STANDARD_SELECTION_AMBIGUITY")
        self.assertEqual(sorted(result["candidates"]),
                         ["ADEFF_exploratory_v1.R", "ADEFF_primary_v1.R",
                          "ADEFF_sensitivity_v1.R"])
