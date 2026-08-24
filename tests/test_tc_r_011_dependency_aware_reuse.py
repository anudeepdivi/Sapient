from pathlib import Path

import yaml

from harness.adapter import SponsorEnv
from harness.dependencies import impact, path_metrics
from harness.modification_scope import modification_scope
from harness.preservation import compare_programs
from harness.resolver import resolve_case
from harness.r_executor import run_r_file
from harness.views import apply_module_deltas, materialize_view
from tests.harness_base import HarnessTestCase


class TestTCR011(HarnessTestCase):
    def setUp(self):
        super().setUp()
        self.env = SponsorEnv(self.env_root)
        self.case = self.load_case("TC-R-011")
        self.std_rel = self.case["standard"]
        self.study_id = self.case["study_requirement"]["study_id"]
        self.base = self.env.read_program(self.std_rel)
        result = resolve_case(self.case, self.env, self.state_dir)[0]
        exp = self.case["expected"]
        self.assertEqual(result["action"], exp["action"])
        self.assertEqual(result["delta_types"], exp["delta_types"])
        self.deltas = result["deltas"]

    def audit_modules(self, view_dir, should_touch):
        registry = sorted({"modules/" + c["file"]
                           for c in self.env.list_capabilities()}
                          | {"modules/metadata.yaml"})
        baseline = {rel: (self.env.program_path(rel)).read_bytes()
                    for rel in registry}

        def current_bytes(rel):
            path = Path(view_dir) / rel
            return path.read_bytes() if path.exists() else None

        touched = sorted(rel for rel in registry
                         if current_bytes(rel) != baseline[rel])
        should_touch = sorted(should_touch)
        should_reuse = sorted(set(registry) - set(should_touch))
        return {
            "touched": touched,
            "module_reuse_accuracy":
                len(set(should_reuse) - set(touched)) / len(should_reuse),
            "unnecessary_module_modification_rate":
                len(set(touched) - set(should_touch)) / len(registry),
            "required_module_modification_recall":
                len(set(touched) & set(should_touch)) / len(should_touch),
        }

    def apply_to_view(self, extra=None):
        view_dir = materialize_view(self.env, self.state_dir, self.study_id)
        touched = list(apply_module_deltas(view_dir, self.deltas))
        if extra:
            extra(view_dir)
            touched += extra.files
        return view_dir, sorted(touched)

    def verify_adae(self, view_dir):
        exp = self.case["expected"]
        compare = compare_programs(self.env, self.std_rel, self.base,
                                   self.base, self.study_id, self.state_dir,
                                   mod_cwd=str(view_dir))
        teae_base = self.env.read_program("modules/teae.R")
        teae_mod = (Path(view_dir) / "modules/teae.R").read_text()
        scope = modification_scope(teae_base, teae_mod, self.deltas,
                                   executed=compare.get("executed", False))
        self.assertTrue(compare["executed"])
        self.assertEqual(compare["cell_diffs"], exp["adae_cell_diffs"])
        return {"compare": compare, "scope": scope}

    def verify_adsl_preserved(self, view_dir):
        adsl_base = self.env.read_program("standards/adsl/ADSL_v2.R")
        compare = compare_programs(self.env, "standards/adsl/ADSL_v2.R",
                                   adsl_base, adsl_base, self.study_id,
                                   self.state_dir, key_cols=["USUBJID"],
                                   mod_cwd=str(view_dir))
        self.assertTrue(compare["executed"])
        return compare

    def check_unaffected_bytes(self, view_dir, impacted):
        for dataset in impacted["unaffected"]:
            std = self.env.get_standard(dataset)
            approved = [v for v in std["versions"] if v["status"] == "approved"]
            for v in approved:
                rel = f"standards/{dataset.lower()}/{v['file']}"
                self.assertEqual(
                    (Path(view_dir) / rel).read_bytes(),
                    self.env.program_path(rel).read_bytes(),
                    f"unaffected standard {rel} changed")

    def test_impact_map_from_declarations(self):
        exp = self.case["expected"]

        impacted = impact(self.env, ["modules/teae.R"])
        self.assertEqual(impacted["affected"], exp["impacted"]["affected"])
        self.assertEqual(impacted["preserve"], exp["impacted"]["preserve"])
        self.assertEqual(impacted["unaffected"], exp["impacted"]["unaffected"])
        self.assertEqual(impacted["unmatched_changed_modules"], [])

        # an ADSL-module change flips ADSL from preserve to affected AND — by
        # reverse closure over the declared edge — its dependent ADAE as well;
        # blast radius is bidirectional
        upstream = impact(self.env, ["modules/treatment.R"])
        self.assertEqual(upstream["affected"], ["ADAE", "ADSL"])
        self.assertNotIn("ADSL", upstream["preserve"])

        # a module no standard declares leaves everything unaffected — but is
        # surfaced, never silently scored as a vacuous all-clean map
        orphan = impact(self.env, ["modules/response.R"])
        self.assertEqual(orphan["affected"], [])
        self.assertEqual(orphan["unmatched_changed_modules"],
                         ["modules/response.R"])
        self.assertEqual(sorted(orphan["unaffected"]),
                         sorted(exp["impacted"]["unaffected"] + ["ADAE", "ADSL"]))

        # vacuous requirements score clean, not zero
        empty = path_metrics({"affected": [], "preserve": []})
        self.assertEqual(empty,
                         {"validation_precision": 1.0, "validation_recall": 1.0,
                          "preservation_recall": 1.0, "preservation_accuracy": 1.0})

        # a dangling depends_on entry is surfaced loudly, never silently dropped
        meta_path = self.env_root / "standards/adae/metadata.yaml"
        meta = yaml.safe_load(meta_path.read_text())
        meta["depends_on_standards"] = ["ADSL", "ADRS"]
        meta_path.write_text(yaml.dump(meta, sort_keys=False))
        dangling = impact(SponsorEnv(self.env_root), ["modules/teae.R"])
        self.assertEqual(dangling["unknown_dependencies"], ["ADRS"])
        self.assertEqual(dangling["preserve"], ["ADSL"])

    def test_good_changes_only_the_necessary_dependency_path(self):
        exp = self.case["expected"]
        view_dir, touched = self.apply_to_view()
        impacted = impact(self.env, touched)

        self.assertEqual(impacted["affected"], exp["impacted"]["affected"])
        self.assertEqual(impacted["preserve"], exp["impacted"]["preserve"])
        self.assertEqual(touched, exp["modify_modules"])
        self.check_unaffected_bytes(view_dir, impacted)

        adae = self.verify_adae(view_dir)
        self.assertTrue(adae["scope"]["modification_scope_accuracy"])

        # the declared dependency: byte-identical program AND output frame
        self.assertEqual((Path(view_dir) / "standards/adsl/ADSL_v2.R").read_text(),
                         self.env.read_program("standards/adsl/ADSL_v2.R"))
        adsl = self.verify_adsl_preserved(view_dir)
        self.assertTrue(adsl["preserved_identical"])
        self.assertEqual(adsl["cell_diffs"], exp["adsl_cell_diffs"])
        self.assertTrue(adsl["total_compared_cells"] > 0)

        audit = self.audit_modules(view_dir, exp["modify_modules"])
        metrics = path_metrics(impacted,
                               revalidated=["ADAE"],
                               preserved_verified=["ADSL"],
                               preserved_identical=["ADSL"])
        self.assertAlmostEqual(metrics["validation_precision"],
                               exp["good"]["validation_precision"])
        self.assertAlmostEqual(metrics["validation_recall"],
                               exp["good"]["validation_recall"])
        self.assertAlmostEqual(metrics["preservation_recall"],
                               exp["good"]["preservation_recall"])
        self.assertAlmostEqual(metrics["preservation_accuracy"],
                               exp["good"]["preservation_accuracy"])
        self.assertAlmostEqual(audit["module_reuse_accuracy"],
                               exp["good"]["module_reuse_accuracy"])
        self.assertAlmostEqual(audit["unnecessary_module_modification_rate"],
                               exp["good"]["unnecessary_module_modification_rate"])

    def test_adsl_output_contract_saves_the_expected_frame(self):
        rds = self.state_dir / "adsl_frame.rds"
        run = run_r_file(self.env.program_path("standards/adsl/ADSL_v2.R"),
                         cwd=self.env.root,
                         env={"SAPIENT_STD_OUTPUT": str(rds)})
        self.assertTrue(run["success"], run["stderr"])
        probe = self.state_dir / "probe.r"
        probe.write_text(f'd <- readRDS("{rds}")\n'
                         'cat("NROW", nrow(d), "\\n")\n'
                         'cat("IDS", paste(d$USUBJID, collapse=","), "\\n")\n')
        out = run_r_file(probe)
        self.assertIn(f"NROW {self.case['expected']['adsl_subjects']}",
                      out["stdout"])
        self.assertIn("IDS S001,S002,S003,S005,S006", out["stdout"])

    def test_bad_a_scope_creep_expands_required_work(self):
        exp = self.case["expected"]
        BAD_TREATMENT = '''derive_treatment <- function(data) {
  out <- data
  out$TRT01P <- as.character(out$ARM)
  out
}
'''
        BAD_DATES = '''derive_study_day <- function(data) {
  out <- data
  out$STUDYDAY <- as.integer(difftime(out$TRTEDT, out$TRTSDT,
                                       units = "days")) + 1L
  out
}
'''

        def regenerate_unrelated(view_dir):
            regenerate_unrelated.files = ["modules/treatment.R",
                                          "modules/dates.R"]
            (view_dir / "modules/treatment.R").write_text(BAD_TREATMENT)
            (view_dir / "modules/dates.R").write_text(BAD_DATES)

        regenerate_unrelated.files = []
        view_dir, actual_touched = self.apply_to_view(regenerate_unrelated)

        # executes green; ADAE behavior identical to GOOD (unsourced modules)
        self.verify_adae(view_dir)

        # but the ACTUAL change set drags ADSL into the affected set: required
        # work that was never done
        impacted_actual = impact(self.env, actual_touched)
        self.assertIn("ADSL", impacted_actual["affected"])
        self.assertNotIn("ADSL", impacted_actual["preserve"])
        metrics = path_metrics(impacted_actual, revalidated=["ADAE"])
        self.assertLess(metrics["validation_recall"],
                        exp["bad_a"]["validation_recall_lt"])

        audit = self.audit_modules(view_dir, exp["modify_modules"])
        self.assertGreater(audit["unnecessary_module_modification_rate"],
                           exp["bad_a"]["unnecessary_module_modification_rate_gt"])
        self.assertLess(audit["module_reuse_accuracy"],
                        exp["bad_a"]["module_reuse_accuracy_lt"])

    def test_bad_b_skipped_dependency_verification_caught_only_by_coverage(self):
        exp = self.case["expected"]
        view_dir, touched = self.apply_to_view()
        impacted = impact(self.env, touched)

        # full ADAE revalidation passes every behavioral oracle...
        adae = self.verify_adae(view_dir)
        self.assertTrue(adae["scope"]["modification_scope_accuracy"])
        audit = self.audit_modules(view_dir, exp["modify_modules"])
        self.assertEqual(audit["unnecessary_module_modification_rate"], 0.0)

        # ...but the declared dependency was never proven preserved
        metrics = path_metrics(impacted,
                               revalidated=["ADAE"],
                               preserved_verified=[],
                               preserved_identical=[])
        self.assertAlmostEqual(metrics["preservation_recall"],
                               exp["bad_b"]["preservation_recall"])
        self.assertAlmostEqual(metrics["preservation_accuracy"],
                               exp["bad_b"]["preservation_recall"])
        # while precision/recall over the affected set alone stay perfect —
        # only the dependency layer sees the gap
        self.assertAlmostEqual(metrics["validation_precision"], 1.0)
        self.assertAlmostEqual(metrics["validation_recall"], 1.0)

    def test_missing_dependency_declaration_is_auditable_not_silent(self):
        # negative control: strip the fixture's ONLY standard-level edge.
        # The map must shrink to exactly what the degraded declarations
        # support and expose its basis — never claim a completeness the
        # metadata no longer backs.
        meta_path = self.env_root / "standards/adae/metadata.yaml"
        meta = yaml.safe_load(meta_path.read_text())
        del meta["depends_on_standards"]
        meta_path.write_text(yaml.dump(meta, sort_keys=False))
        degraded = impact(SponsorEnv(self.env_root), ["modules/teae.R"])

        self.assertEqual(degraded["affected"], ["ADAE"])
        self.assertEqual(degraded["preserve"], [])
        # the basis is inspectable: ADAE carries no outgoing edge, so the
        # empty preserve set is traceable to the missing declaration
        self.assertEqual(degraded["edges"], {})

        # the scorer manufactures no obligations either: with nothing
        # declared, nothing is demanded — the residual risk (a MISSING
        # declaration is undetectable from metadata alone) is pinned here
        # in executable form rather than hidden behind a perfect score
        metrics = path_metrics(degraded, revalidated=["ADAE"])
        self.assertEqual(metrics["validation_recall"], 1.0)
        self.assertEqual(metrics["preservation_recall"], 1.0)

    def test_resolver_and_views_untouched_by_dependency_layer(self):
        # the TEAE delta itself is unchanged from TC-R-010: same single
        # module_behavior targeting the same file — dependencies add an
        # obligation layer, they do not alter resolution
        self.assertEqual(len(self.deltas), 1)
        self.assertEqual(self.deltas[0]["type"], "module_behavior")
        self.assertEqual(self.deltas[0]["target_file"], "modules/teae.R")
        view_dir, _ = self.apply_to_view()
        self.assertEqual((Path(view_dir) / self.std_rel).read_text(), self.base)
