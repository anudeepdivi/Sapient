from harness.adapter import SponsorEnv
from harness.capabilities import (
    CapabilityNotApproved, approve, implement, propose, register, validate,
)
from harness.resolver import resolve_case
from tests.harness_base import HarnessTestCase


class TestTCR013(HarnessTestCase):
    def setUp(self):
        super().setUp()
        self.env = SponsorEnv(self.env_root)
        self.case = self.load_case("TC-R-013")
        self.requirement = self.case["study_requirement"]["requirements"][0]

    def _flow_to_validation(self):
        resolve_case(self.case, self.env, self.state_dir)
        proposal = propose("derive_special_response_flag", self.requirement,
                           self.env, self.state_dir)
        proposal = implement(proposal, self.env, self.state_dir)
        return validate(proposal, self.env, self.state_dir)

    def test_generated_implementation_passes_testthat(self):
        proposal = self._flow_to_validation()
        self.assertEqual(proposal["status"], "awaiting_approval")

    def test_lifecycle_stops_at_awaiting_approval_without_registering(self):
        proposal = self._flow_to_validation()
        module = self.env.root / "modules" / "derive_special_response_flag.R"
        self.assertFalse(module.exists())
        names = {c["name"] for c in self.env.list_capabilities()}
        self.assertNotIn("derive_special_response_flag", names)

    def test_approval_permits_registration_into_sponsor_copy(self):
        proposal = self._flow_to_validation()
        proposal = approve(proposal, actor="qc_reviewer", state_dir=self.state_dir)
        proposal = register(proposal, self.env, self.state_dir)
        self.assertEqual(proposal["status"], "registered")
        module = self.env.root / "modules" / "derive_special_response_flag.R"
        self.assertTrue(module.exists())
        entry = next(c for c in self.env.list_capabilities()
                     if c["name"] == "derive_special_response_flag")
        self.assertEqual(entry["source"], "sapient-generated")

    def test_register_refused_without_approval(self):
        proposal = self._flow_to_validation()
        with self.assertRaises(CapabilityNotApproved):
            register(proposal, self.env, self.state_dir)
        self.assertFalse(
            (self.env.root / "modules" / "derive_special_response_flag.R").exists())

    def test_failed_validation_blocks_registration(self):
        from harness.capabilities import load_proposal
        proposal = self._flow_to_validation()
        impl_path = (self.state_dir / "proposals"
                     / proposal["implementation_file"])
        impl_path.write_text("library(nosuchpkg)\n")
        proposal = validate(load_proposal(self.state_dir,
                                          "derive_special_response_flag"),
                            self.env, self.state_dir)
        self.assertEqual(proposal["status"], "failed_validation")
        with self.assertRaises(CapabilityNotApproved):
            register(proposal, self.env, self.state_dir)
        self.assertFalse(
            (self.env.root / "modules" / "derive_special_response_flag.R").exists())
