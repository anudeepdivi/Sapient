from harness.adapter import SponsorEnv
from harness.decisions import pending_decisions, resolve_decision
from harness.resolver import resolve_case
from tests.harness_base import HarnessTestCase


class TestTCR017(HarnessTestCase):
    def setUp(self):
        super().setUp()
        self.env = SponsorEnv(self.env_root)
        self.case = self.load_case("TC-R-017")

    def _resolve(self):
        return resolve_case(self.case, self.env, self.state_dir)[0]

    def test_two_equally_plausible_standards_escalate(self):
        result = self._resolve()
        expected = self.case["expected"]
        self.assertEqual(result["status"], expected["status"])
        self.assertEqual(result["reason"], expected["reason"])
        self.assertEqual(sorted(result["candidates"]),
                         ["ADTTE_cardio_v1.R", "ADTTE_oncology_v1.R"])
        self.assertNotIn("standard_match", result)

    def test_decision_request_carries_required_fields(self):
        decision = self._resolve()["decision"]
        for field in ("question", "evidence", "possible_interpretations",
                      "recommendation", "confidence", "downstream_impact"):
            self.assertIn(field, decision)
        self.assertIn("oncology", decision["possible_interpretations"][0])
        self.assertIn("cardiology", decision["possible_interpretations"][1])
        pending = pending_decisions(self.state_dir)
        self.assertEqual(len(pending), 1)

    def test_resolved_decision_not_asked_again(self):
        first = self._resolve()
        decision_id = first["decision"]["decision_id"]
        resolve_decision(decision_id,
                         choice="standards/adtte/ADTTE_oncology_v1.R",
                         actor="statistician", state_dir=self.state_dir)
        second = self._resolve()
        self.assertEqual(second["decision"]["decision_id"], decision_id)
        self.assertTrue(second["decision"]["asked_again"])
        decisions = list((self.state_dir / "decisions").glob("D-*.yaml"))
        self.assertEqual(len(decisions), 1)
