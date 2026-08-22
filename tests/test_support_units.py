from harness.adapter import SponsorEnv
from harness.gates import run_checks
from harness.resolver import normalize_expr
from tests.harness_base import HarnessTestCase


class TestSupportUnits(HarnessTestCase):
    def test_normalize_expr_ignores_whitespace(self):
        self.assertEqual(
            normalize_expr('SAFFL == "Y" & SPECIALFL == "Y"'),
            normalize_expr('SAFFL=="Y"&SPECIALFL=="Y"'))

    def test_gate_subset_catches_bad_package_and_syntax(self):
        rules = SponsorEnv(self.env_root).get_validation_rules()
        result = run_checks("library(nosuchpkg)\nx <- \n", rules)
        self.assertFalse(result["passed"])
        self.assertTrue(any("nosuchpkg" in i for i in result["issues"]))
        clean = run_checks("library(dplyr)\nf <- function(x) x\n", rules)
        self.assertTrue(clean["passed"], clean["issues"])

    def test_adapter_status_filters_and_capability_listing(self):
        env = SponsorEnv(self.env_root)
        adsl = env.get_standard("ADSL")
        self.assertEqual(len(adsl["versions"]), 2)
        names = {c["name"] for c in env.list_capabilities()}
        self.assertIn("derive_teae", names)
        self.assertIn("dplyr", env.get_validation_rules()["packages_allowed"])
