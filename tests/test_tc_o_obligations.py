"""Requirements Slice 2 adversarial tests: SAP -> analysis obligations.

Each test maps 1:1 to an independently-authored ground-truth case in
tests/cases/TC-O-00*.yaml (authored by reading the fixture as a statistician
would, never from extractor output). Hermetic: no network, no model calls.
"""
import unittest
from pathlib import Path

import yaml

BASE_DIR = Path(__file__).resolve().parent.parent
FIXTURE = BASE_DIR / "sap_fixtures" / "SAP_FX002.md"
CASES = BASE_DIR / "tests" / "cases"

from harness.coverage import evaluate, requirement_representations
from harness.obligations import KINDS, extract_obligations
from harness.sap_extract import extract_requirements


def load_case(test_id):
    with open(CASES / f"{test_id}.yaml") as f:
        return yaml.safe_load(f)


class ObligationsTestCase(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        cls.text = FIXTURE.read_text()

    def _run(self, case, obligations=None, requirements=None):
        report = extract_obligations(self.text,
                                     section_ids=case["sections"])
        if obligations is None:
            obligations = report["obligations"]
        evaluation = evaluate(case["reference"], obligations,
                              requirements=requirements,
                              grounded_rate=report["grounded_rate"])
        return report, evaluation

    def _assert_expected(self, case, report, evaluation):
        expected = {(o["kind"], o["status"], o["subject_key"])
                    for o in case["expected"]["obligations"]}
        actual = {(o["kind"], o["status"], o["subject_key"])
                  for o in report["obligations"]}
        self.assertEqual(actual, expected)
        for name, value in case["expected"]["metrics"].items():
            self.assertEqual(
                evaluation["metrics"][name], value,
                f"{name}: got {evaluation['metrics'][name]}, want {value}")

    def test_tc_o_001_explicit_recovered_with_evidence(self):
        """Explicit obligations are recovered; every one carries section-
        contained verbatim-quote evidence."""
        case = load_case("TC-O-001")
        report, evaluation = self._run(case)
        self._assert_expected(case, report, evaluation)
        for obl in report["obligations"]:
            self.assertTrue(obl["evidence"])
            self.assertTrue(
                all(e["section_id"] == "2" for e in obl["evidence"]),
                obl)
        self.assertEqual(report["grounded_rate"], 1.0)

    def test_tc_o_002_multiple_obligations_in_one_paragraph(self):
        """A single dense paragraph yields five distinct explicit obligations
        plus one unresolved; each with its own sentence-level evidence."""
        case = load_case("TC-O-002")
        report, evaluation = self._run(case)
        self._assert_expected(case, report, evaluation)
        kinds = {o["kind"] for o in report["obligations"]}
        self.assertGreaterEqual(len(kinds), 4, kinds)
        for obl in report["obligations"]:
            self.assertTrue(
                all(e["section_id"] == "6.1" for e in obl["evidence"]), obl)

    def test_tc_o_003_inference_marked_inferred_with_basis(self):
        """Derived obligations carry status=inferred plus their declared
        basis; evaluated against an inferred-only scope, coverage holds but
        false-confidence is 1.0 BY DESIGN (visible, never hidden)."""
        case = load_case("TC-O-003")
        report = extract_obligations(self.text, section_ids=case["sections"])
        inferred = [o for o in report["obligations"]
                    if o["status"] == "inferred"]
        self.assertEqual(len(inferred), 2)
        for obl in inferred:
            self.assertIn("summary", obl["subject"])
            self.assertEqual(obl["inference"]["basis_id"],
                             "secondary_endpoint_output_v1")
            self.assertTrue(obl["inference"]["basis"])
        evaluation = evaluate(case["reference"], inferred,
                              grounded_rate=report["grounded_rate"])
        for name, value in case["expected"]["metrics"].items():
            self.assertEqual(evaluation["metrics"][name], value)

    def test_tc_o_004_conflicting_sections_escalate_not_adjudicate(self):
        """ANCOVA (6.1) vs MMRM amendment (6.3): one escalated conflict with
        both quoted values; NO explicit statistical_method survives; the
        material method obligation is blocked from downstream coverage."""
        case = load_case("TC-O-004")
        report, evaluation = self._run(case)
        expected = {(o["kind"], o["status"], o["subject_key"])
                    for o in case["expected"]["obligations"]}
        actual = {(o["kind"], o["status"], o["subject_key"])
                  for o in report["obligations"]}
        self.assertEqual(actual, expected)
        self.assertEqual(len(report["conflicts"]), 1)
        conflict = report["conflicts"][0]
        self.assertEqual(conflict["kind"], "statistical_method")
        self.assertEqual(conflict["anchor"], "primary")
        self.assertEqual(len(conflict["values"]), 2)
        quoted = {v["value"] for v in conflict["values"]}
        self.assertTrue(any("ANCOVA" in q for q in quoted))
        self.assertTrue(any("mixed model" in q for q in quoted))
        self.assertFalse(
            [o for o in report["obligations"]
             if o["kind"] == "statistical_method"
             and o["status"] == "explicit"])
        self.assertIn("statistical_method/primary analysis statistical method",
                      evaluation["outstanding"])

    def test_tc_o_005_indeterminate_statement_unresolved_satisfies_nothing(self):
        """"as appropriate" prose becomes an unresolved obligation that lands
        in the human queue and covers nothing."""
        case = load_case("TC-O-005")
        report = extract_obligations(self.text, section_ids=case["sections"])
        indeterminate = [o for o in report["obligations"]
                         if o["kind"] == "indeterminate"]
        self.assertEqual(len(indeterminate), 1)
        obl = indeterminate[0]
        self.assertEqual(obl["status"], "unresolved")
        self.assertEqual(obl["reason"], "indeterminate scope")
        self.assertEqual(obl["subject_key"],
                         "additional supportive analyses may be "
                         "performed as appropriate")
        evaluation = evaluate(case["reference"], indeterminate,
                              grounded_rate=report["grounded_rate"])
        self.assertNotIn(f"{obl['kind']}/{obl['subject_key']}",
                         evaluation["covered"])
        self.assertIn(f"{obl['kind']}/{obl['subject_key']}",
                      evaluation["outstanding"])
        for name, value in case["expected"]["metrics"].items():
            self.assertEqual(evaluation["metrics"][name], value)

    def test_tc_o_006_omitted_material_obligation_fails_coverage(self):
        """Plan built without section 6.2 must MISS the sensitivity-analysis
        obligation: named in `missing`, coverage recall depressed, conflict
        and indeterminate items outstanding for a human."""
        case = load_case("TC-O-006")
        report, evaluation = self._run(case)
        expected = {(o["kind"], o["status"], o["subject_key"])
                    for o in case["expected"]["obligations"]}
        actual = {(o["kind"], o["status"], o["subject_key"])
                  for o in report["obligations"]}
        self.assertEqual(actual, expected)
        self.assertEqual(len(report["conflicts"]), 1)
        self.assertEqual(
            evaluation["missing"],
            case["expected"]["missing"])
        self.assertEqual(
            evaluation["outstanding"],
            sorted(case["expected"]["outstanding"]))
        for name, value in case["expected"]["metrics"].items():
            self.assertEqual(
                evaluation["metrics"][name], value,
                f"{name}: got {evaluation['metrics'][name]}, want {value}")

    def test_tc_o_007_noise_text_creates_zero_obligations(self):
        """Background/bookkeeping prose (external listing numbers) creates no
        obligations, no conflicts, no inferences — the anti-confabulation
        control."""
        case = load_case("TC-O-007")
        report, evaluation = self._run(case)
        self.assertEqual(report["obligations"], [])
        self.assertEqual(report["conflicts"], [])
        self.assertEqual(report["counts"]["total"], 0)
        self.assertEqual(evaluation["missing"], [])
        for name, value in case["expected"]["metrics"].items():
            self.assertEqual(evaluation["metrics"][name], value)

    def test_kind_vocabulary_is_the_declared_nine(self):
        """The obligation vocabulary is exactly the nine declared concepts."""
        self.assertEqual(KINDS, {
            "endpoint", "population", "treatment_group", "parameter",
            "timepoint", "statistical_method", "subgroup",
            "sensitivity_analysis", "output_obligation"})


class CoverageMetricDefinitionsTest(unittest.TestCase):
    """Pin each metric formula (and its vacuous conventions) with toy sets,
    independently of any fixture."""

    def test_requirement_bridge_covers_parameter_explicitly(self):
        """A requirement carrying teae_definition represents the parameter
        obligation at EXPLICIT grade (no false-confidence penalty)."""
        reqs = [{"dataset": "ADAE",
                 "teae_definition": 'TRTEMFL = if_else(...)'}]
        self.assertEqual(requirement_representations(reqs),
                         {("parameter", "teae_definition")})
        evaluation = evaluate(
            [{"kind": "parameter", "subject": "TEAE definition",
              "subject_key": "teae_definition"}],
            [], requirements=reqs)
        self.assertEqual(evaluation["metrics"]["coverage_recall"], 1.0)
        self.assertEqual(evaluation["metrics"]["false_confidence_rate"], 0.0)

    def test_inferred_only_coverage_is_visible_false_confidence(self):
        evaluation = evaluate(
            [{"kind": "output_obligation", "subject": "x summary"}],
            [{"kind": "output_obligation", "status": "inferred",
              "subject": "x summary", "subject_key": "x summary",
              "reason": None}])
        self.assertEqual(evaluation["metrics"]["coverage_recall"], 1.0)
        self.assertEqual(evaluation["metrics"]["false_confidence_rate"], 1.0)

    def test_unresolved_never_covers_a_resolvable_reference_entry(self):
        evaluation = evaluate(
            [{"kind": "population", "subject": "safety population"}],
            [{"kind": "population", "status": "unresolved",
              "subject": "safety population",
              "subject_key": "safety population",
              "reason": "indeterminate scope"}])
        self.assertEqual(evaluation["metrics"]["coverage_recall"], 0.0)
        self.assertEqual(evaluation["missing"],
                         ["population/safety population"])
        self.assertEqual(evaluation["outstanding"], [])

    def test_vacuous_conventions(self):
        evaluation = evaluate([], [])
        self.assertEqual(evaluation["metrics"], {
            "obligation_recall": 1.0, "obligation_precision": 1.0,
            "grounded_rate": 1.0, "unsupported_inference_rate": 0.0,
            "unresolved_high_risk_rate": 0.0, "coverage_recall": 1.0,
            "false_confidence_rate": 0.0})

    def test_bridge_golden_from_real_extractor_output(self):
        """Golden composition: a requirement produced by extract_requirements
        on the fixture's labeled lines represents the parameter obligation
        through the bridge — pinning the extractor-key <-> bridge-key
        invariant that synthetic literals alone cannot pin."""
        report = extract_requirements(FIXTURE.read_text(),
                                      study_id="STUDY-FX002",
                                      section_ids=["8"])
        reqs = report["requirements"]
        self.assertEqual(len(reqs), 1)
        self.assertIn("teae_definition", reqs[0])
        evaluation = evaluate(
            [{"kind": "parameter", "subject": "TEAE definition",
              "subject_key": "teae_definition"}],
            [], requirements=reqs)
        self.assertEqual(evaluation["metrics"]["coverage_recall"], 1.0)
        self.assertEqual(evaluation["metrics"]["false_confidence_rate"], 0.0)
        self.assertIn("parameter/teae_definition", evaluation["covered"])


if __name__ == "__main__":
    unittest.main()
