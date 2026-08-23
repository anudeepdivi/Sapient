from harness.adapter import SponsorEnv
from harness.deltas import apply_deltas, materialize
from harness.modification_scope import modification_scope
from harness.preservation import compare_programs, compute_metrics
from harness.resolver import resolve_case
from harness.r_executor import run_r_file
from tests.harness_base import HarnessTestCase

# Deliberately authored negative implementation: applies the required
# population filter correctly but also renames the intermediate frame and
# rewrites the unrelated severity summary. Output frame is identical to the
# minimal application; it must still fail the scope oracle.
BAD_REFACTOR = '''library(dplyr)
source("modules/teae.R")

adae <- data.frame(
  USUBJID = c("S001", "S001", "S002", "S003", "S002"),
  AETERM  = c("Headache", "Nausea", "Fatigue", "Dizziness", "Rash"),
  AESTDT  = as.Date(c("2024-01-10", "2024-02-01", "2024-01-20",
                      "2024-02-15", "2023-12-28")),
  AESEV   = c("MILD", "MODERATE", "MILD", "SEVERE", "MILD")
)
adsl <- data.frame(
  USUBJID   = c("S001", "S002", "S003"),
  TRTSDT    = as.Date(c("2024-01-05", "2024-01-08", "2024-02-11")),
  SAFFL     = c("Y", "Y", "N"),
  SPECIALFL = c("N", "Y", "N")
)

ae_events <- derive_teae(adae, adsl$TRTSDT[match(adae$USUBJID, adsl$USUBJID)])
ae_events <- inner_join(ae_events, select(adsl, USUBJID, SAFFL, SPECIALFL),
                        by = "USUBJID")
ae_final <- filter(ae_events, SAFFL == "Y" & SPECIALFL == "Y")
cat("Treatment-emergent AEs:", sum(ae_final$TRTEMFL == "Y", na.rm = TRUE), "\\n")
severity_counts <- as.data.frame(table(ae_final$AESEV))
names(severity_counts) <- c("AESEV", "n")
print(severity_counts)

out_path <- Sys.getenv("SAPIENT_STD_OUTPUT", "data/output/ADAE_v2.rds")
dir.create(dirname(out_path), showWarnings = FALSE, recursive = TRUE)
saveRDS(ae_final, out_path)
'''

# Second negative implementation: correct filter, frame untouched, but
# gratuitous churn — re-indented continuation, pipe-rewritten join, swapped
# summary order. Behavior-preserving churn is still unauthorized.
BAD_CHURN = '''library(dplyr)
source("modules/teae.R")

adae <- data.frame(
  USUBJID = c("S001", "S001", "S002", "S003", "S002"),
  AETERM  = c("Headache", "Nausea", "Fatigue", "Dizziness", "Rash"),
  AESTDT  = as.Date(c("2024-01-10", "2024-02-01", "2024-01-20",
                          "2024-02-15", "2023-12-28")),
  AESEV   = c("MILD", "MODERATE", "MILD", "SEVERE", "MILD")
)
adsl <- data.frame(
  USUBJID   = c("S001", "S002", "S003"),
  TRTSDT    = as.Date(c("2024-01-05", "2024-01-08", "2024-02-11")),
  SAFFL     = c("Y", "Y", "N"),
  SPECIALFL = c("N", "Y", "N")
)

ae1 <- derive_teae(adae, adsl$TRTSDT[match(adae$USUBJID, adsl$USUBJID)])
ae1 <- ae1 %>% inner_join(select(adsl, USUBJID, SAFFL, SPECIALFL), by = "USUBJID")
ae1 <- filter(ae1, SAFFL == "Y" & SPECIALFL == "Y")
print(count(ae1, AESEV))
cat("Treatment-emergent AEs:", sum(ae1$TRTEMFL == "Y", na.rm = TRUE), "\\n")

out_path <- Sys.getenv("SAPIENT_STD_OUTPUT", "data/output/ADAE_v2.rds")
dir.create(dirname(out_path), showWarnings = FALSE, recursive = TRUE)
saveRDS(ae1, out_path)
'''

# Third negative implementation: all churn smuggled ONTO the authorized line
# itself — the correct filter plus an extra row-reordering stage appended in
# the same call chain. Frame content is unchanged (row order is not compared
# by the key-based preservation oracle) and it executes green, so this evades
# every behavioral check; only scope attribution catches it.
BAD_INLINE = '''library(dplyr)
source("modules/teae.R")

adae <- data.frame(
  USUBJID = c("S001", "S001", "S002", "S003", "S002"),
  AETERM  = c("Headache", "Nausea", "Fatigue", "Dizziness", "Rash"),
  AESTDT  = as.Date(c("2024-01-10", "2024-02-01", "2024-01-20",
                      "2024-02-15", "2023-12-28")),
  AESEV   = c("MILD", "MODERATE", "MILD", "SEVERE", "MILD")
)
adsl <- data.frame(
  USUBJID   = c("S001", "S002", "S003"),
  TRTSDT    = as.Date(c("2024-01-05", "2024-01-08", "2024-02-11")),
  SAFFL     = c("Y", "Y", "N"),
  SPECIALFL = c("N", "Y", "N")
)

ae1 <- derive_teae(adae, adsl$TRTSDT[match(adae$USUBJID, adsl$USUBJID)])
ae1 <- inner_join(ae1, select(adsl, USUBJID, SAFFL, SPECIALFL), by = "USUBJID")
ae1 <- filter(ae1, SAFFL == "Y" & SPECIALFL == "Y") %>% arrange(desc(AESTDT))
cat("Treatment-emergent AEs:", sum(ae1$TRTEMFL == "Y", na.rm = TRUE), "\\n")
print(count(ae1, AESEV))

out_path <- Sys.getenv("SAPIENT_STD_OUTPUT", "data/output/ADAE_v2.rds")
dir.create(dirname(out_path), showWarnings = FALSE, recursive = TRUE)
saveRDS(ae1, out_path)
'''


class TestTCR009(HarnessTestCase):
    def setUp(self):
        super().setUp()
        self.env = SponsorEnv(self.env_root)
        self.case = self.load_case("TC-R-009")
        self.std_rel = self.case["standard"]
        self.study_id = self.case["study_requirement"]["study_id"]
        self.base = self.env.read_program(self.std_rel)
        result = resolve_case(self.case, self.env, self.state_dir)[0]
        self.assertEqual(result["action"], self.case["expected"]["action"])
        self.deltas = result["deltas"]
        self.good = apply_deltas(self.base, self.deltas)

    def _run(self, code):
        path = materialize(self.env, self.std_rel, code,
                           self.study_id, self.state_dir)
        out = self.state_dir / "preservation" / f"{path.stem}.rds"
        return run_r_file(path, cwd=self.env.root,
                          env={"SAPIENT_STD_OUTPUT": str(out)})

    def _preservation(self, code):
        expected = self.case["expected"]
        compare = compare_programs(self.env, self.std_rel, self.base, code,
                                   self.study_id, self.state_dir)
        return compute_metrics(compare, expected["removed_keys"],
                               expected["added_keys"])

    def test_single_declared_population_delta(self):
        expected = self.case["expected"]
        self.assertEqual(self.deltas[0]["type"], expected["delta_types"][0])
        self.assertEqual(len(self.deltas), 1)

    def test_good_passes_execution_preservation_and_scope(self):
        expected = self.case["expected"]
        executed = self._run(self.good)
        self.assertTrue(executed["success"], executed["stderr"])
        metrics = self._preservation(self.good)
        self.assertEqual(metrics["standard_preservation_rate"], 1.0)
        self.assertTrue(metrics["removed_exact"])
        self.assertTrue(metrics["added_exact"])
        scope = modification_scope(self.base, self.good, self.deltas,
                                   executed=executed["success"])
        self.assertEqual(scope["required_change_precision"],
                         expected["good"]["required_change_precision"])
        self.assertEqual(scope["unnecessary_modification_rate"],
                         expected["good"]["unnecessary_modification_rate"])
        self.assertTrue(scope["modification_scope_accuracy"])
        self.assertEqual(scope["deviations_from_standard"], [])
        self.assertEqual(scope["deviations_in_modified"], [])

    def test_authorized_change_carries_the_declared_evidence(self):
        scope = modification_scope(self.base, self.good, self.deltas)
        delta = self.deltas[0]
        self.assertTrue(scope["applied_as_declared"])
        self.assertEqual(len(scope["sanctioned_base_lines"]), 1)
        self.assertEqual(len(scope["sanctioned_modified_lines"]), 1)
        base_line = self.base.splitlines()[scope["sanctioned_base_lines"][0]]
        mod_line = self.good.splitlines()[scope["sanctioned_modified_lines"][0]]
        self.assertIn(delta["evidence"]["standard_text"], base_line)
        self.assertIn(delta["replacement"], mod_line)

    def _assert_bad(self, bad_code):
        expected = self.case["expected"]
        executed = self._run(bad_code)
        self.assertTrue(executed["success"], executed["stderr"])
        metrics = self._preservation(bad_code)
        # passes the entire TC-R-008 behavioral oracle ...
        self.assertEqual(metrics["standard_preservation_rate"],
                         1.0 if expected["bad"]["preservation_passes"] else 0.0)
        self.assertTrue(metrics["removed_exact"])
        self.assertTrue(metrics["added_exact"])
        # ... yet fails the scope oracle
        scope = modification_scope(self.base, bad_code, self.deltas,
                                   executed=executed["success"])
        self.assertFalse(scope["modification_scope_accuracy"])
        self.assertLess(scope["required_change_precision"], 1.0)
        self.assertGreater(scope["unnecessary_modification_rate"], 0.0)
        self.assertTrue(scope["deviations_from_standard"]
                        or scope["deviations_in_modified"])
        return scope

    def test_bad_refactor_rewrite_fails_scope_despite_identical_output(self):
        self._assert_bad(BAD_REFACTOR)

    def test_bad_silent_churn_fails_scope_despite_identical_output(self):
        self._assert_bad(BAD_CHURN)

    def test_bad_same_line_churn_on_the_authorized_line_fails_scope(self):
        # regression for the substring-authorization evasion: churn appended
        # to the one legitimate line must not inherit its authorization
        self._assert_bad(BAD_INLINE)
