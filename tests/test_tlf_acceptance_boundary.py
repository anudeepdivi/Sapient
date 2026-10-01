import os
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("NVIDIA_API_KEY", "test")
os.environ.setdefault("HF_TOKEN", "test")

if "openai" not in sys.modules:
    _openai = types.ModuleType("openai")
    _openai.OpenAI = lambda *a, **k: None
    for _name in ("RateLimitError", "APITimeoutError", "APIConnectionError",
                  "InternalServerError", "BadRequestError"):
        setattr(_openai, _name, type(_name, (Exception,), {}))
    sys.modules["openai"] = _openai

class _Stub:
    def __init__(self, *args, **kwargs):
        pass

    def __call__(self, *args, **kwargs):
        return _Stub()

    def __getattr__(self, name):
        return _Stub()


_STUBBED = ("chromadb", "sentence_transformers", "fitz")
for _name in _STUBBED:
    if _name not in sys.modules:
        _stub = types.ModuleType(_name)
        _stub.__getattr__ = lambda attribute: _Stub()
        sys.modules[_name] = _stub

from config import R_EXECUTABLE
from r_layer.runner import run_adam_program
from orchestration.graph import should_regenerate
from orchestration.nodes import adam_executor, tlf_generator, validator
from orchestration.nodes.adam_generator import failure_feedback

# The node modules are imported now, so the stand-ins have done their job. Drop them
# so another test module importing these sees the real (absent) package and reports
# its own environment failure instead of inheriting a silent fake.
for _name in ("openai",) + _STUBBED:
    sys.modules.pop(_name, None)


def make_xpt(path: Path, value: str, columns: str = "USUBJID") -> None:
    """Write a real one-row XPT so the column-listing R call has something to read."""
    subprocess.run(
        [R_EXECUTABLE, "-e",
         f'haven::write_xpt(data.frame({columns}="{value}"), "{path}")'],
        check=True, capture_output=True, text=True, timeout=120)


def write_xpt_columns(path: Path, columns: str) -> None:
    """Write a real XPT carrying exactly the named columns."""
    values = ", ".join(f'{name}="{name.lower()}"' for name in columns.split(","))
    subprocess.run(
        [R_EXECUTABLE, "-e",
         f'haven::write_xpt(data.frame({values}), "{path}")'],
        check=True, capture_output=True, text=True, timeout=120)


def write_adsl_program(value: str = "accepted-subject") -> str:
    return ('d <- data.frame(USUBJID="x", AGE=30)\n'
            f'result <- data.frame(USUBJID="{value}", AGE=30)\n'
            'xportr::xportr_write(result, path = file.path(Sys.getenv("SAPIENT_ADAM_DIR"), '
            '"ADSL.xpt"), domain = "ADSL")\n')


class TlfAcceptanceBoundaryTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.calls = []
        tlf_generator._adam_columns_cache = None
        tlf_generator._adam_columns_cache_key = None
        self.retry = patch("orchestration.nodes.tlf_generator.create_with_retry",
                           side_effect=self._fake_llm)
        self.retry.start()
        self.addCleanup(self.retry.stop)
        for name, value in (("get_cached", None), ("set_cached", None)):
            cached = patch(f"orchestration.nodes.tlf_generator.{name}", return_value=value)
            cached.start()
            self.addCleanup(cached.stop)

    def _fake_llm(self, *args, **kwargs):
        self.calls.append(kwargs["messages"][0]["content"])
        message = types.SimpleNamespace(content="tbl <- basic_table()\n")
        return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])

    def state(self, **overrides):
        base = {
            "study_id": "TEST001",
            "adam_programs": {},
            "adam_execution": {},
            "accepted_adam": {},
            "tlf_programs": {},
            "tlf_skipped": {},
            "mockshells": [],
            "lot_entries": [],
            "validation_results": {},
            "needs_regeneration": [],
            "regen_count": 0,
            "errors": [],
            "completed": False,
        }
        base.update(overrides)
        return base

    def entry(self, table_number="14.1.1", data_source=None):
        return {"table_number": table_number, "data_source": data_source or ["ADSL"]}

    # 1. current-run accepted ADaM -> TLF proceeds
    def test_accepted_adam_makes_tlf_proceed(self):
        make_xpt(self.root / "ADSL.xpt", "a")
        result = tlf_generator.run(self.state(
            lot_entries=[self.entry()],
            accepted_adam={"ADSL": str(self.root / "ADSL.xpt")}))

        self.assertIn("14.1.1", result["tlf_programs"])
        self.assertEqual(result["tlf_skipped"], {})
        self.assertEqual(len(self.calls), 1)

    # 2. stale canonical XPT on disk is not acceptance
    def test_stale_canonical_xpt_is_not_accepted_output(self):
        (self.root / "data").mkdir()
        stale_dir = self.root / "data" / "adam"
        stale_dir.mkdir()
        make_xpt(stale_dir / "ADSL.xpt", "stale")

        with patch.object(tlf_generator, "BASE_DIR", self.root):
            result = tlf_generator.run(self.state(
                lot_entries=[self.entry()], accepted_adam={}))

        self.assertNotIn("14.1.1", result["tlf_programs"])
        self.assertIn("14.1.1", result["tlf_skipped"])
        self.assertIn("not accepted in current run", result["tlf_skipped"]["14.1.1"])
        self.assertEqual(self.calls, [])

    # 3. clean first-pass acceptance -> TLF eligible, no regeneration needed
    def test_clean_first_pass_execution_makes_tlf_eligible(self):
        with patch("orchestration.nodes.adam_executor.run_all_adam_programs",
                   return_value={"ADSL": {"success": True, "accepted_path": str(self.root / "ADSL.xpt")}}):
            executed = adam_executor.run(self.state(
                adam_programs={"ADSL": write_adsl_program()}))
        self.assertEqual(executed["accepted_adam"], {"ADSL": str(self.root / "ADSL.xpt")})
        self.assertEqual(executed["needs_regeneration"], [])

        make_xpt(self.root / "ADSL.xpt", "a")
        result = tlf_generator.run(self.state(
            lot_entries=[self.entry()], **{
                k: executed[k] for k in ("accepted_adam", "adam_execution", "needs_regeneration")}))

        self.assertIn("14.1.1", result["tlf_programs"])
        self.assertEqual(result["tlf_skipped"], {})

    # 4. rejected ADaM -> no acceptance -> TLF must not consume the old file
    def test_rejected_adam_does_not_release_tlf(self):
        stale_dir = self.root / "data" / "adam"
        stale_dir.mkdir(parents=True)
        make_xpt(stale_dir / "ADSL.xpt", "stale")

        with patch("orchestration.nodes.adam_executor.run_all_adam_programs",
                   return_value={"ADSL": {"success": False, "stage": "metacore_compliance",
                                          "accepted_path": None}}), \
             patch.object(tlf_generator, "BASE_DIR", self.root):
            executed = adam_executor.run(self.state(
                adam_programs={"ADSL": write_adsl_program()}))
            result = tlf_generator.run(self.state(
                lot_entries=[self.entry()], **{
                    k: executed[k] for k in ("accepted_adam", "adam_execution", "needs_regeneration")}))

        self.assertEqual(executed["accepted_adam"], {})
        self.assertIn("ADSL", executed["needs_regeneration"])
        self.assertNotIn("14.1.1", result["tlf_programs"])
        self.assertIn("14.1.1", result["tlf_skipped"])

    # 5. a prior skip must not survive once the table becomes eligible
    def test_prior_skip_is_cleared_when_table_becomes_eligible(self):
        make_xpt(self.root / "ADSL.xpt", "a")
        first = tlf_generator.run(self.state(lot_entries=[self.entry()]))
        self.assertIn("14.1.1", first["tlf_skipped"])

        second = tlf_generator.run(self.state(
            lot_entries=[self.entry()],
            accepted_adam={"ADSL": str(self.root / "ADSL.xpt")},
            tlf_skipped=first["tlf_skipped"]))

        self.assertIn("14.1.1", second["tlf_programs"])
        self.assertEqual(second["tlf_skipped"], {})

    # 6. run completion reflects skipped TLF work
    def test_completion_is_false_while_tlf_is_skipped(self):
        message = types.SimpleNamespace(content='{"status": "pass", "severity": "none", "issues": []}')
        qc = types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])
        with patch("orchestration.nodes.validator.create_with_retry", return_value=qc):
            blocked = validator.run(self.state(
                adam_programs={}, tlf_skipped={"14.1.1": "ADaM not accepted in current run: ADSL"},
                lot_entries=[self.entry()]))
            self.assertFalse(blocked["completed"])

            done = validator.run(self.state(
                adam_programs={}, tlf_skipped={}, tlf_programs={"14.1.1": "x"},
                lot_entries=[self.entry()]))
        self.assertTrue(done["completed"])

    # 7. column grounding lists accepted datasets only
    def test_column_grounding_covers_accepted_datasets_only(self):
        stale_dir = self.root / "data" / "adam"
        stale_dir.mkdir(parents=True)
        make_xpt(stale_dir / "ADAE.xpt", "stale")
        make_xpt(self.root / "ADSL.xpt", "a")

        block = tlf_generator.adam_columns_block({"ADSL": str(self.root / "ADSL.xpt")})

        self.assertIn("ADSL", block)
        self.assertNotIn("ADAE", block)

    # 8. a buildable-but-failed dataset is pending, not a terminal blocker
    def test_failed_but_buildable_dataset_is_pending(self):
        with patch("orchestration.nodes.adam_executor.run_all_adam_programs",
                   return_value={"ADSL": {"success": False, "stage": "metacore_compliance",
                                          "accepted_path": None}}):
            executed = adam_executor.run(self.state(
                adam_programs={"ADSL": write_adsl_program()}))

        result = tlf_generator.run(self.state(
            lot_entries=[self.entry()], **{
                k: executed[k] for k in ("accepted_adam", "adam_execution", "needs_regeneration")}))

        self.assertIn("14.1.1", result["tlf_pending"])
        self.assertNotIn("14.1.1", result["tlf_blocked"])
        self.assertIn("ADSL", executed["needs_regeneration"])
        self.assertIn("not accepted in current run", result["tlf_skipped"]["14.1.1"])

    # 9. a dataset with no input mapping blocks terminally and is not retried
    def test_dataset_without_input_mapping_blocks_terminally(self):
        entry = self.entry(data_source=["ADTTE"])
        with patch("orchestration.nodes.adam_executor.run_all_adam_programs",
                   return_value={}):
            executed = adam_executor.run(self.state(adam_programs={"ADTTE": "x <- 1"}))

        result = tlf_generator.run(self.state(lot_entries=[entry], **{
            k: executed[k] for k in ("accepted_adam", "adam_execution", "needs_regeneration")}))

        self.assertIn("14.1.1", result["tlf_blocked"])
        self.assertNotIn("14.1.1", result["tlf_pending"])
        self.assertIn("no input mapping", result["tlf_skipped"]["14.1.1"])
        # Terminal: nothing was queued for regeneration, so the run cannot spin.
        self.assertEqual(executed["needs_regeneration"], [])
        self.assertEqual(self.calls, [])

    # 10. a terminal block is not reported as success, and does not re-enter regeneration
    def test_terminal_block_fails_the_run_without_regeneration(self):
        entry = self.entry(data_source=["ADTTE"])
        with patch("orchestration.nodes.adam_executor.run_all_adam_programs",
                   return_value={}):
            executed = adam_executor.run(self.state(adam_programs={"ADTTE": "x <- 1"}))
        blocked = tlf_generator.run(self.state(lot_entries=[entry], **{
            k: executed[k] for k in ("accepted_adam", "adam_execution", "needs_regeneration")}))

        message = types.SimpleNamespace(content='{"status": "pass", "severity": "none", "issues": []}')
        qc = types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])
        with patch("orchestration.nodes.validator.create_with_retry", return_value=qc):
            result = validator.run(blocked)

        self.assertFalse(result["completed"])
        self.assertEqual(result["needs_regeneration"], [])
        self.assertEqual(should_regenerate(result), "done")

    # 11. a pending table clears once its ADaM is accepted
    def test_pending_table_recovers_after_acceptance(self):
        with patch("orchestration.nodes.adam_executor.run_all_adam_programs",
                   return_value={"ADSL": {"success": False, "stage": "r_execution",
                                          "accepted_path": None}}):
            first = tlf_generator.run(self.state(
                lot_entries=[self.entry()], accepted_adam={},
                needs_regeneration=["ADSL"]))
        self.assertIn("14.1.1", first["tlf_pending"])

        make_xpt(self.root / "ADSL.xpt", "a")
        second = tlf_generator.run(self.state(
            lot_entries=[self.entry()], accepted_adam={"ADSL": str(self.root / "ADSL.xpt")},
            tlf_skipped=first["tlf_skipped"], tlf_pending=first["tlf_pending"]))

        self.assertIn("14.1.1", second["tlf_programs"])
        self.assertEqual(second["tlf_skipped"], {})
        self.assertEqual(second["tlf_pending"], {})
        self.assertEqual(second["tlf_blocked"], {})

    # 12. republishing to the same canonical path must not serve stale columns
    def test_republished_adam_columns_replace_the_cached_listing(self):
        """runner.py republishes every accepted dataset to a stable canonical path, so
        the path is unchanged between rounds while the bytes behind it are not."""
        target = self.root / "ADSL.xpt"
        write_xpt_columns(target, "USUBJID, AGE")
        first = tlf_generator.adam_columns_block({"ADSL": str(target)})

        write_xpt_columns(target, "USUBJID, AGE, TRT01P")
        second = tlf_generator.adam_columns_block({"ADSL": str(target)})

        self.assertIn("AGE", first)
        self.assertNotIn("TRT01P", first)
        self.assertIn("TRT01P", second)

    # 13. a failed column listing is never presented as "this run has no ADaM columns"
    def test_failed_column_listing_is_reported_and_not_cached(self):
        target = self.root / "ADSL.xpt"
        write_xpt_columns(target, "USUBJID")
        broken = types.SimpleNamespace(
            stdout="", stderr="Error: package 'haven' is not installed", returncode=1)

        with patch("subprocess.run", return_value=broken):
            block = tlf_generator.adam_columns_block({"ADSL": str(target)})

        self.assertIn("UNAVAILABLE", block)
        self.assertIn("haven", block)
        # Not cached: a healthy R afterwards must still yield the real listing.
        self.assertIn("USUBJID", tlf_generator.adam_columns_block({"ADSL": str(target)}))

    # 14. a LoT entry with no data_source is unbound, not buildable-with-no-inputs
    def test_entry_without_data_source_is_blocked_rather_than_generated(self):
        for source in ([], None):
            with self.subTest(data_source=source):
                entry = {"table_number": "14.1.1"}
                if source is not None:
                    entry["data_source"] = source
                result = tlf_generator.run(self.state(
                    lot_entries=[entry], accepted_adam={"ADSL": str(self.root / "ADSL.xpt")}))

                self.assertNotIn("14.1.1", result["tlf_programs"])
                self.assertIn("14.1.1", result["tlf_blocked"])
                self.assertIn("14.1.1", result["tlf_skipped"])
                self.assertNotIn("14.1.1", result["tlf_pending"])
                self.assertEqual(self.calls, [])

    # 15. a pending reason must not outlive the dataset it waits on
    def test_stale_pending_reason_is_cleared_once_only_a_terminal_block_remains(self):
        result = tlf_generator.run(self.state(
            lot_entries=[self.entry(data_source=["ADSL", "ADTTE"])],
            accepted_adam={"ADSL": str(self.root / "ADSL.xpt")},
            tlf_pending={"14.1.1": "ADaM not accepted in current run: ADSL"},
            tlf_skipped={"14.1.1": "ADaM not accepted in current run: ADSL"}))

        self.assertNotIn("14.1.1", result["tlf_pending"])
        self.assertIn("14.1.1", result["tlf_blocked"])
        self.assertIn("no input mapping", result["tlf_skipped"]["14.1.1"])

    # 16. R execution output must reach the retry prompt
    def test_r_execution_diagnostics_reach_the_regeneration_prompt(self):
        """A plain R failure carries no `error` key — the explanation is in stdout — so
        reading only `error` delivered the retry an empty list of failed checks."""
        execution = run_adam_program(
            "ADSL", 'stop("ADSL: object `TRT01P` not found")', adam_dir=self.root)
        self.assertFalse(execution["success"])

        feedback = failure_feedback(self.state(validation_results={"ADSL": {
            "status": "fail", "stage": "r_execution", "issues": [],
            "execution": execution}}), "ADSL")

        self.assertIn("TRT01P", feedback)
        self.assertIn("R exit code: 1", feedback)
        self.assertIn("r_execution", feedback)

    # 17. a recorded upstream failure means the run cannot be reported complete
    def test_recorded_pipeline_error_prevents_a_completed_run(self):
        message = types.SimpleNamespace(content='{"status": "pass", "severity": "none", "issues": []}')
        qc = types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])
        failed_lot = ["lot_generator: failed to parse LLM response"]

        with patch("orchestration.nodes.validator.create_with_retry", return_value=qc):
            blocked = validator.run(self.state(
                adam_programs={}, lot_entries=[], tlf_skipped={}, errors=failed_lot))
            clean = validator.run(self.state(
                adam_programs={}, lot_entries=[], tlf_skipped={}))

        self.assertEqual(blocked["needs_regeneration"], [])
        self.assertFalse(blocked["completed"])
        self.assertTrue(clean["completed"])

    # 18. a non-object JSON verdict is recorded, not raised
    def test_non_object_validator_json_is_recorded_instead_of_crashing(self):
        for content in ("[1, 2, 3]", "null"):
            with self.subTest(content=content):
                message = types.SimpleNamespace(content=content)
                qc = types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])
                with patch("orchestration.nodes.validator.create_with_retry", return_value=qc):
                    result = validator.run(self.state(
                        adam_programs={}, lot_entries=[self.entry()],
                        tlf_programs={"14.1.1": "x <- 1"}))

                self.assertEqual(result["validation_results"]["14.1.1"]["status"], "fail")
                self.assertIn("14.1.1", result["needs_regeneration"])
                self.assertFalse(result["completed"])

    # 19. a failed column listing must not produce an ungrounded table
    def test_failed_column_listing_holds_the_table_pending_instead_of_generating(self):
        make_xpt(self.root / "ADSL.xpt", "a")
        broken = types.SimpleNamespace(
            stdout="", stderr="Error: could not find function 'haven'", returncode=1)

        with patch("subprocess.run", return_value=broken):
            result = tlf_generator.run(self.state(
                lot_entries=[self.entry()],
                accepted_adam={"ADSL": str(self.root / "ADSL.xpt")}))

        self.assertNotIn("14.1.1", result["tlf_programs"])
        self.assertIn("14.1.1", result["tlf_pending"])
        self.assertNotIn("14.1.1", result["tlf_blocked"])
        self.assertIn("column listing unavailable", result["tlf_skipped"]["14.1.1"])
        self.assertIn("haven", result["tlf_skipped"]["14.1.1"])
        self.assertEqual(self.calls, [])

        message = types.SimpleNamespace(content='{"status": "pass", "severity": "none", "issues": []}')
        qc = types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])
        with patch("orchestration.nodes.validator.create_with_retry", return_value=qc):
            validated = validator.run(self.state(
                adam_programs={}, lot_entries=[self.entry()],
                tlf_skipped=result["tlf_skipped"], tlf_pending=result["tlf_pending"]))
        self.assertFalse(validated["completed"])

    # 20. the hold is retryable: a working listing releases the table
    def test_table_generates_once_the_column_listing_recovers(self):
        target = self.root / "ADSL.xpt"
        write_xpt_columns(target, "USUBJID,AGE")
        broken = types.SimpleNamespace(stdout="", stderr="R failed", returncode=1)

        with patch("subprocess.run", return_value=broken):
            held = tlf_generator.run(self.state(
                lot_entries=[self.entry()], accepted_adam={"ADSL": str(target)}))
        self.assertIn("14.1.1", held["tlf_pending"])
        self.assertEqual(self.calls, [])

        recovered = tlf_generator.run(self.state(
            lot_entries=[self.entry()], accepted_adam={"ADSL": str(target)},
            tlf_skipped=held["tlf_skipped"], tlf_pending=held["tlf_pending"]))

        self.assertIn("14.1.1", recovered["tlf_programs"])
        self.assertEqual(recovered["tlf_skipped"], {})
        self.assertEqual(recovered["tlf_pending"], {})
        self.assertEqual(len(self.calls), 1)

    # 21. a table bound to two ADaM is invalidated when either one's schema changes
    def test_one_changed_input_invalidates_a_multi_input_table(self):
        """Each declared dataset contributes to the digest of what a table was built from,
        so a change to any one of them is a change to that table's ground."""
        adsl = self.root / "ADSL.xpt"
        adae = self.root / "ADAE.xpt"
        write_xpt_columns(adae, "USUBJID,TRTA")
        write_xpt_columns(adsl, "USUBJID,AGE")
        entries = [self.entry("14.1.1", ["ADSL", "ADAE"]), self.entry("14.1.2", ["ADAE"])]
        accepted = {"ADSL": str(adsl), "ADAE": str(adae)}

        first = tlf_generator.run(self.state(lot_entries=entries, accepted_adam=accepted))
        self.assertEqual(len(self.calls), 2)
        self.assertIn("14.1.1", first["tlf_input_fingerprint"])
        self.assertIn("14.1.2", first["tlf_input_fingerprint"])

        write_xpt_columns(adsl, "USUBJID,AGE,TRT01P")  # only ADSL changed
        second = tlf_generator.run(self.state(
            lot_entries=entries, accepted_adam=accepted,
            tlf_programs=first["tlf_programs"],
            tlf_input_fingerprint=first["tlf_input_fingerprint"]))

        rebuilt = [call.split("TABLE NUMBER: ", 1)[1].splitlines()[0]
                   for call in self.calls[2:]]
        self.assertEqual(rebuilt, ["14.1.1"])
        self.assertIn("ADSL: USUBJID, AGE, TRT01P", self.calls[2])
        self.assertEqual(second["tlf_programs"].keys(), first["tlf_programs"].keys())

    # 22. reordering columns is a schema change, not a re-encoding
    def test_column_reordering_invalidates_the_table(self):
        target = self.root / "ADSL.xpt"
        write_xpt_columns(target, "USUBJID,AGE")
        first = tlf_generator.run(self.state(
            lot_entries=[self.entry()], accepted_adam={"ADSL": str(target)}))
        self.assertIn("ADSL: USUBJID, AGE", self.calls[0])

        write_xpt_columns(target, "AGE,USUBJID")
        tlf_generator.run(self.state(
            lot_entries=[self.entry()], accepted_adam={"ADSL": str(target)},
            tlf_programs=first["tlf_programs"],
            tlf_input_fingerprint=first["tlf_input_fingerprint"]))

        self.assertEqual(len(self.calls), 2)
        self.assertIn("ADSL: AGE, USUBJID", self.calls[1])


if __name__ == "__main__":
    unittest.main()
