from pathlib import Path

from harness.adapter import SponsorEnv
from harness.deltas import apply_deltas
from harness.modification_scope import modification_scope
from harness.preservation import compare_programs
from harness.resolver import resolve_case
from harness.r_executor import run_r_file
from harness.views import apply_module_deltas, materialize_view
from tests.harness_base import HarnessTestCase

# BAD-A: behavior-preserving reimplementations of two modules ADAE_v2 never
# sources. Regenerating them changes nothing downstream — which is exactly
# why only the module-touch audit can catch the unnecessary modification.
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

# BAD-B: the targeted module fully rewritten instead of minimally delta'd.
# Produces frames identical to the sanctioned application (passes preservation
# and the touch audit — teae.R is legitimately touched), so only module-grain
# scope attribution condemns it.
BAD_TEAE = '''derive_teae <- function(ae, trt_start) {
  flags <- rep(NA_character_, nrow(ae))
  idx <- which(ae$AESTDT >= trt_start & ae$AESTDT <= trt_start + 7)
  flags[idx] <- "Y"
  ae %>% mutate(TRTEMFL = flags)
}
'''


class TestTCR010(HarnessTestCase):
    def setUp(self):
        super().setUp()
        self.env = SponsorEnv(self.env_root)
        self.case = self.load_case("TC-R-010")
        self.std_rel = self.case["standard"]
        self.study_id = self.case["study_requirement"]["study_id"]
        self.base = self.env.read_program(self.std_rel)
        result = resolve_case(self.case, self.env, self.state_dir)[0]
        exp = self.case["expected"]
        self.assertEqual(result["action"], exp["action"])
        self.assertEqual(result["standard_match"], exp["standard_match"])
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
            "registry": registry,
            "touched": touched,
            "module_reuse_accuracy":
                len(set(should_reuse) - set(touched)) / len(should_reuse),
            "unnecessary_module_modification_rate":
                len(set(touched) - set(should_touch)) / len(registry),
            "required_module_modification_recall":
                len(set(touched) & set(should_touch)) / len(should_touch),
        }

    def run_scenario(self, extra=None):
        view_dir = materialize_view(self.env, self.state_dir, self.study_id)
        touched = apply_module_deltas(view_dir, self.deltas)
        if extra:
            extra(view_dir)
        compare = compare_programs(self.env, self.std_rel, self.base,
                                   self.base, self.study_id, self.state_dir,
                                   mod_cwd=str(view_dir))
        teae_base = self.env.read_program("modules/teae.R")
        teae_mod = (Path(view_dir) / "modules/teae.R").read_text()
        scope = modification_scope(teae_base, teae_mod, self.deltas,
                                   executed=compare.get("executed", False))
        return {"view": view_dir, "touched_by_deltas": touched,
                "compare": compare, "scope": scope}

    def test_good_minimal_module_delta(self):
        exp = self.case["expected"]
        run = self.run_scenario()

        self.assertTrue(run["compare"]["executed"])
        self.assertTrue(run["compare"]["schema_equal"])
        self.assertEqual(run["compare"]["removed"], [])
        self.assertEqual(run["compare"]["added"], [])
        self.assertEqual(run["compare"]["cell_diffs"], exp["cell_diffs"])
        # flag-value semantics: the changed cell IS the declared intent
        self.assertFalse(run["compare"]["preserved_identical"])

        self.assertEqual(run["touched_by_deltas"], exp["modify_modules"])
        audit = self.audit_modules(run["view"], exp["modify_modules"])
        self.assertEqual(audit["touched"], exp["modify_modules"])
        self.assertAlmostEqual(
            audit["module_reuse_accuracy"],
            exp["good"]["module_reuse_accuracy"])
        self.assertAlmostEqual(
            audit["unnecessary_module_modification_rate"],
            exp["good"]["unnecessary_module_modification_rate"])
        self.assertAlmostEqual(
            audit["required_module_modification_recall"],
            exp["good"]["required_module_modification_recall"])

        self.assertTrue(run["scope"]["applied_as_declared"])
        self.assertTrue(run["scope"]["modification_scope_accuracy"])
        # the standard program itself stays byte-identical; the delta lives
        # entirely in the module layer
        self.assertEqual((Path(run["view"]) / self.std_rel).read_text(),
                         self.base)

    def test_bad_a_unrelated_module_regeneration_caught_only_by_audit(self):
        exp = self.case["expected"]

        def regenerate_unrelated(view_dir):
            (view_dir / "modules/treatment.R").write_text(BAD_TREATMENT)
            (view_dir / "modules/dates.R").write_text(BAD_DATES)

        run = self.run_scenario(regenerate_unrelated)

        # executes green; behavior identical to GOOD because neither module
        # is sourced by ADAE_v2
        self.assertTrue(run["compare"]["executed"])
        self.assertEqual(run["compare"]["removed"], [])
        self.assertEqual(run["compare"]["added"], [])
        self.assertEqual(run["compare"]["cell_diffs"],
                         self.case["expected"]["cell_diffs"])

        # the targeted-module change itself is still minimal and authorized
        self.assertTrue(run["scope"]["modification_scope_accuracy"])

        # ONLY the touch audit sees the damage
        audit = self.audit_modules(run["view"], exp["modify_modules"])
        self.assertIn("modules/treatment.R", audit["touched"])
        self.assertIn("modules/dates.R", audit["touched"])
        self.assertGreater(
            audit["unnecessary_module_modification_rate"],
            exp["bad_a"]["unnecessary_module_modification_rate_gt"])
        self.assertLess(audit["module_reuse_accuracy"], 1.0)

    def test_bad_a_rewrites_are_behavior_preserving(self):
        # prove detection is NOT due to breakage: each rewritten module yields
        # output identical to its original on a probe frame
        view_dir = materialize_view(self.env, self.state_dir, self.study_id)
        apply_module_deltas(view_dir, self.deltas)
        (view_dir / "modules/treatment.R").write_text(BAD_TREATMENT)
        (view_dir / "modules/dates.R").write_text(BAD_DATES)
        probe = f'''
library(dplyr)
df_trt <- data.frame(ARM = c("A", "B", "A"), x = 1:3)
source("{self.env.program_path("modules/treatment.R")}")
a1 <- derive_treatment(df_trt)
source("{view_dir / 'modules/treatment.R'}")
a2 <- derive_treatment(df_trt)
stopifnot(identical(a1, a2))
df_day <- data.frame(TRTSDT = as.Date(c("2024-01-05", "2024-02-01")),
                     TRTEDT = as.Date(c("2024-01-12", "2024-02-08")))
source("{self.env.program_path("modules/dates.R")}")
d1 <- derive_study_day(df_day)
source("{view_dir / 'modules/dates.R'}")
d2 <- derive_study_day(df_day)
stopifnot(identical(d1, d2))
cat("EQUIVALENT OK\\n")
'''
        probe_path = self.state_dir / "probe_equivalence.R"
        probe_path.write_text(probe)
        run = run_r_file(probe_path)
        self.assertTrue(run["success"], run["stderr"])
        self.assertIn("EQUIVALENT OK", run["stdout"])

    def test_bad_b_full_module_rewrite_caught_only_by_scope(self):
        exp = self.case["expected"]

        def rewrite_teae(view_dir):
            (view_dir / "modules/teae.R").write_text(BAD_TEAE)

        run = self.run_scenario(rewrite_teae)

        # executes green and produces exactly the GOOD frame: behavioral
        # oracles are blind to the rewrite
        self.assertTrue(run["compare"]["executed"])
        self.assertEqual(run["compare"]["cell_diffs"], exp["cell_diffs"])
        self.assertEqual(run["compare"]["removed"], [])
        self.assertEqual(run["compare"]["added"], [])

        # the right module WAS touched, so the touch audit also passes
        audit = self.audit_modules(run["view"], exp["modify_modules"])
        self.assertEqual(audit["touched"], exp["modify_modules"])
        self.assertAlmostEqual(
            audit["module_reuse_accuracy"],
            exp["good"]["module_reuse_accuracy"])
        self.assertAlmostEqual(
            audit["unnecessary_module_modification_rate"], 0.0)

        # ONLY module-grain scope attribution condemns it
        self.assertFalse(run["scope"]["modification_scope_accuracy"])

    def test_mixed_grain_requirement_escalates(self):
        # a requirement changing BOTH a program field and a module behavior is
        # legitimate schema input but has no single-grain consumer; the resolver
        # must escalate instead of emitting an unappliable delta list
        case = self.load_case("TC-R-010")
        case["study_requirement"]["requirements"][0]["population"] = 'SAFFL == "N"'
        result = resolve_case(case, self.env, self.state_dir)[0]
        self.assertEqual(result["status"], "WAITING_FOR_HUMAN")
        self.assertEqual(result["reason"], "MIXED_GRAIN_DELTA_UNSUPPORTED")
        self.assertEqual(sorted(result["fields"]),
                         ["population", "teae_definition"])

    def test_apply_module_deltas_rejects_program_grain(self):
        view_dir = materialize_view(self.env, self.state_dir, self.study_id)
        rogue = {"type": "population_filter", "target_file": "modules/teae.R",
                 "evidence": {"standard_text": "x"}, "replacement": "y"}
        with self.assertRaises(ValueError):
            apply_module_deltas(view_dir, [rogue])

    def test_audit_covers_registry_manifest_and_deletions(self):
        exp = self.case["expected"]

        def damage(view_dir):
            (view_dir / "modules/metadata.yaml").write_text("functions: []\n")
            (view_dir / "modules/response.R").unlink()

        run = self.run_scenario(damage)
        audit = self.audit_modules(run["view"], exp["modify_modules"])
        self.assertIn("modules/metadata.yaml", audit["touched"])
        self.assertIn("modules/response.R", audit["touched"])
        self.assertGreater(audit["unnecessary_module_modification_rate"], 0.0)
        self.assertLess(audit["module_reuse_accuracy"], 1.0)
