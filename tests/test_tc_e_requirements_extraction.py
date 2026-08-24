import json

from harness.adapter import SponsorEnv
from harness.resolver import resolve_case
from harness.sap_extract import extract_requirements
from tests.harness_base import BASE_DIR, HarnessTestCase

DOC = (BASE_DIR / "sap_fixtures" / "SAP_FX001.md").read_text()


def _comparable(resolution):
    """Strip the known representational differences between an engine-run
    requirement and a hand-authored one: the engine's own requirement_id and
    its verbatim-quote delta evidence (hand truth cites 'SAP §9.3'; the
    engine cites the fixture section id '9.3')."""
    out = {k: v for k, v in resolution.items() if k != "requirement_id"}
    if "deltas" in out:
        out["deltas"] = [{k: v for k, v in d.items()
                          if k not in ("evidence", "source_requirement")}
                         for d in out["deltas"]]
    return out


class TestTCERequirementsExtraction(HarnessTestCase):
    def setUp(self):
        super().setUp()
        self.env = SponsorEnv(self.env_root)

    def extract(self, name):
        case = self.load_case(name)
        report = extract_requirements(DOC, study_id="STUDY-FX001",
                                      section_ids=case["sections"],
                                      env=self.env)
        return case, report

    def assert_resolution(self, resolution, expected):
        for key, value in expected.items():
            self.assertEqual(resolution[key], value)

    def test_tc_e_001_explicit_requirement_golden_linkage(self):
        exp = self.load_case("TC-E-001")["expected"]
        report = extract_requirements(DOC, study_id="STUDY-FX001",
                                      section_ids=["9.3"], env=self.env)

        self.assertEqual(len(report["requirements"]),
                         exp["requirement_count"])
        self.assertEqual(report["conflicts"], [])
        want = exp["requirement"]
        req = report["requirements"][0]
        self.assertEqual(req["requirement_id"], "REQ-001")
        self.assertEqual(req["type"], want["type"])
        self.assertEqual(req["dataset"], want["dataset"])
        self.assertEqual(req["capabilities"], want["capabilities"])
        self.assertEqual(req["teae_definition"], want["teae_definition"])
        self.assertEqual(req["source_sections"], want["source_sections"])
        self.assertEqual(req["extraction"]["status"],
                         want["extraction_status"])
        self.assertEqual(req["extraction"]["method"],
                         want["extraction_method"])
        evidence = req["extraction"]["evidence"]
        self.assertEqual([e["field"] for e in evidence],
                         [want["evidence_field"]])

        # golden linkage: identical harness resolution to the hand-authored
        # TC-R-011 requirement, after stripping only the documented
        # representational differences
        hand_case = self.load_case(
            exp["golden_linkage"]["hand_authored_case"])
        engine_res = resolve_case(report["case"], self.env, self.state_dir)[0]
        hand_res = resolve_case(hand_case, self.env, self.state_dir)[0]
        self.assertEqual(_comparable(engine_res), _comparable(hand_res))
        self.assertEqual(engine_res["action"],
                         exp["golden_linkage"]["resolution_action"])
        self.assertEqual(engine_res["standard_match"],
                         exp["golden_linkage"]["resolution_standard"])

    def test_tc_e_002_multiple_requirements_one_extraction_run(self):
        exp = self.load_case("TC-E-002")["expected"]
        _, report = self.extract("TC-E-002")

        self.assertEqual(len(report["requirements"]),
                         exp["requirement_count"])
        self.assertEqual(report["conflicts"], [])
        self.assertEqual([r["requirement_id"] for r in report["requirements"]],
                         ["REQ-001", "REQ-002"])
        results = resolve_case(report["case"], self.env, self.state_dir)
        for req, res, want in zip(report["requirements"], results,
                                  exp["requirements"]):
            self.assertEqual(req["dataset"], want["dataset"])
            if "population" in want:
                self.assertEqual(req["population"], want["population"])
            else:
                self.assertNotIn("population", req)
            if "teae_definition" in want:
                self.assertEqual(req["teae_definition"],
                                 want["teae_definition"])
            self.assert_resolution(res, want["resolution"])

    def test_tc_e_003_missing_operationalization_recorded_not_invented(self):
        exp = self.load_case("TC-E-003")["expected"]
        _, report = self.extract("TC-E-003")

        self.assertEqual(len(report["requirements"]),
                         exp["requirement_count"])
        self.assertEqual(report["conflicts"], [])
        req = report["requirements"][0]
        self.assertEqual(req["dataset"], exp["dataset"])
        self.assertEqual(("population" in req), exp["has_population_field"])
        gaps = req["extraction"]["gaps"]
        self.assertEqual(len(gaps), exp["gap_count"])
        self.assertEqual(gaps[0]["field"], exp["gap_field"])
        self.assertEqual(gaps[0]["section_id"], exp["gap_section_id"])
        # nothing invented anywhere in the emitted requirement
        blob = json.dumps(req)
        for forbidden in exp["forbidden_anywhere_in_requirement"]:
            self.assertNotIn(forbidden, blob)
        # documented downstream behavior of the unconstrained-but-flagged
        # requirement: reuse proceeds, the gap is visible upstream
        res = resolve_case(report["case"], self.env, self.state_dir)[0]
        self.assert_resolution(res, exp["resolution"])

    def test_tc_e_004_conflicting_values_never_silently_resolved(self):
        exp = self.load_case("TC-E-004")["expected"]
        _, report = self.extract("TC-E-004")

        self.assertEqual(len(report["requirements"]),
                         exp["requirement_count"])
        self.assertEqual(len(report["conflicts"]), exp["conflict_count"])
        conflict = report["conflicts"][0]
        self.assertEqual(conflict["dataset"], exp["conflict_dataset"])
        self.assertEqual(conflict["field"], exp["conflict_field"])
        self.assertEqual(len(conflict["values"]),
                         exp["conflict_value_count"])
        for fragment in exp["conflict_value_contains"]:
            matches = [v for v in conflict["values"] if fragment in v["value"]]
            self.assertEqual(len(matches), 1,
                             f"expected exactly one {fragment!r} value")
        self.assertEqual(sorted(v["section_id"] for v in conflict["values"]),
                         exp["conflict_sections"])
        # nothing silently reaches the resolver
        self.assertEqual(report["case"]["study_requirement"]["requirements"],
                         [])

    def test_tc_e_005_novel_capability_reaches_resolver_unharmed(self):
        exp = self.load_case("TC-E-005")["expected"]
        _, report = self.extract("TC-E-005")

        req = report["requirements"][0]
        self.assertEqual(len(report["requirements"]),
                         exp["requirement_count"])
        self.assertEqual(req["dataset"], exp["dataset"])
        self.assertEqual(req["capabilities"], exp["capabilities"])
        self.assertEqual(req["extraction"]["unverified_datasets"],
                         exp["unverified_datasets"])
        self.assertEqual(req["extraction"]["unverified_capabilities"],
                         exp["unverified_capabilities"])
        self.assertNotIn(exp["decoy_not_substituted"],
                         req["capabilities"])
        res = resolve_case(report["case"], self.env, self.state_dir)[0]
        self.assertEqual(res["status"], exp["resolution"]["status"])
        self.assertEqual(res["action"], exp["resolution"]["action"])
        self.assertEqual(res["missing_capabilities"],
                         exp["resolution"]["missing_capabilities"])

    def test_tc_e_006_negative_space_yields_nothing(self):
        exp = self.load_case("TC-E-006")["expected"]
        _, report = self.extract("TC-E-006")

        self.assertEqual(report["sections_scanned"],
                         self.load_case("TC-E-006")["sections"])
        self.assertEqual(len(report["requirements"]),
                         exp["requirement_count"])
        self.assertEqual(len(report["conflicts"]), exp["conflict_count"])
        self.assertEqual(len(report["gaps"]), exp["gap_count"])
