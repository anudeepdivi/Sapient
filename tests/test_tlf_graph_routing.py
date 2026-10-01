import contextlib
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


_STUBBED = ("chromadb", "sentence_transformers")
for _name in _STUBBED:
    if _name not in sys.modules:
        _stub = types.ModuleType(_name)
        _stub.__getattr__ = lambda attribute: _Stub()
        sys.modules[_name] = _stub

from orchestration.graph import build_graph
from orchestration.nodes import tlf_generator
from templates.adam_templates import render_footer
from config import R_EXECUTABLE


def write_xpt(path, columns):
    """Write a real XPT carrying exactly the named columns."""
    values = ", ".join(f'{name}="{name}"' for name in columns.split(","))
    subprocess.run([R_EXECUTABLE, "-e",
                    f'haven::write_xpt(data.frame({values}), "{path}")'],
                   check=True, capture_output=True, text=True, timeout=120)


def columns_on_disk(path):
    return subprocess.run([R_EXECUTABLE, "-e",
                           f'cat(paste(names(haven::read_xpt("{path}")), collapse=","))'],
                          capture_output=True, text=True, timeout=120).stdout.strip()


def adsl_program(value="subject-1"):
    return (f'result <- data.frame(USUBJID="{value}", AGE=30)\n'
            + render_footer("ADSL"))


def base_state(**overrides):
    state = {
        "study_id": "TEST001",
        "adam_programs": {"ADSL": adsl_program()},
        "adam_execution": {},
        "accepted_adam": {},
        "tlf_programs": {},
        "tlf_skipped": {},
        "tlf_pending": {},
        "tlf_blocked": {},
        "mockshells": [],
        "lot_entries": [{"table_number": "14.1.1", "data_source": ["ADSL"]}],
        "validation_results": {},
        "needs_regeneration": [],
        "regen_count": 0,
        "errors": [],
        "completed": False,
    }
    state.update(overrides)
    return state


def graph_run(adam_outcomes, state=None, execution_dir=".", publish=None):
    """Run the real graph from adam_generator, with the R runner and both LLM clients
    replaced. adam_outcomes maps an execution attempt index to {dataset: success}.
    publish(round_index, dataset, path) is called for every accepted dataset, so a test
    can put real, round-dependent content behind the stable publication path."""
    tlf_generator._adam_columns_cache = None
    tlf_generator._adam_columns_cache_key = None
    state = state or base_state()
    message = types.SimpleNamespace(content='{"status": "pass", "severity": "none", "issues": []}')
    qc = types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])
    code = types.SimpleNamespace(content="tbl <- basic_table()\n")
    generated = types.SimpleNamespace(choices=[types.SimpleNamespace(message=code)])

    calls = {"tlf": 0, "tables": []}
    executor = "orchestration.nodes.adam_executor.run_all_adam_programs"
    rounds = {"n": 0}

    def fake_execute(programs, adam_dir=None):
        outcome = adam_outcomes[min(rounds["n"], len(adam_outcomes) - 1)]
        index = rounds["n"]
        rounds["n"] += 1
        results = {}
        for name in programs:
            ok = outcome.get(name, True)
            path = f"{execution_dir}/{name}.xpt" if ok else None
            if ok and publish:
                publish(index, name, path)
            results[name] = {
                "success": ok,
                "stage": "accepted" if ok else "metacore_compliance",
                "accepted_path": path,
                "metacore": {"success": ok},
            }
        return results

    def fake_tlf_llm(*args, **kwargs):
        calls["tlf"] += 1
        prompt = kwargs["messages"][0]["content"]
        calls["tables"].append(next((line.split(": ", 1)[1] for line in prompt.splitlines()
                                     if line.startswith("TABLE NUMBER: ")), "?"))
        return generated

    graph = None
    clean_gate = {"passed": True, "issues": []}
    with contextlib.ExitStack() as stack:
        # The upstream nodes are replaced before build_graph() so the graph registers
        # the pass-through; adam_generator, adam_executor, tlf_generator, validator and
        # every edge between them stay real.
        for node in ("sap_reader", "lot_generator", "mockshell_generator"):
            stack.enter_context(patch(f"orchestration.nodes.{node}.run",
                                      side_effect=lambda s: {**s}))
        graph = build_graph()
        # Input-file existence is not what these tests exercise, and data/ is not
        # committed to the worktree, so the gate would reject every program on a
        # missing-file check before routing is ever reached.
        for module in ("adam_executor", "validator"):
            stack.enter_context(patch(f"orchestration.nodes.{module}.run_gate",
                                      return_value=clean_gate))
        stack.enter_context(patch(executor, side_effect=fake_execute))
        stack.enter_context(patch("orchestration.nodes.validator.create_with_retry", return_value=qc))
        stack.enter_context(patch("orchestration.nodes.validator.check_conformance", return_value={}))
        stack.enter_context(patch("orchestration.nodes.validator.compare_reference", return_value={}))
        stack.enter_context(patch("orchestration.nodes.tlf_generator.create_with_retry", side_effect=fake_tlf_llm))
        stack.enter_context(patch("orchestration.nodes.tlf_generator.get_cached", return_value=None))
        stack.enter_context(patch("orchestration.nodes.tlf_generator.set_cached", return_value=None))
        stack.enter_context(patch("orchestration.nodes.adam_generator.get_cached", return_value=None))
        stack.enter_context(patch("orchestration.nodes.adam_generator.set_cached", return_value=None))
        return graph.invoke(state), calls


class GraphRetryTest(unittest.TestCase):
    def test_buildable_failure_is_retried_and_then_accepted(self):
        final, _ = graph_run([{"ADSL": False}, {"ADSL": True}])
        self.assertEqual(final["regen_count"], 2)
        self.assertIn("ADSL", final["accepted_adam"])
        self.assertEqual(final["needs_regeneration"], [])

    def test_tlf_generated_after_the_retry_accepts_adam(self):
        final, calls = graph_run([{"ADSL": False}, {"ADSL": True}])
        self.assertIn("14.1.1", final["tlf_programs"])
        self.assertEqual(final["tlf_skipped"], {})
        self.assertEqual(calls["tlf"], 1)
        self.assertTrue(final["completed"], final["tlf_skipped"])

    def test_terminal_block_ends_the_run_without_retrying_forever(self):
        state = base_state(
            adam_programs={},
            lot_entries=[{"table_number": "14.1.1", "data_source": ["ADTTE"]}])
        final, calls = graph_run([{}], state=state)

        self.assertIn("14.1.1", final["tlf_blocked"])
        self.assertNotIn("14.1.1", final["tlf_pending"])
        self.assertEqual(final["needs_regeneration"], [])
        self.assertFalse(final["completed"])
        self.assertEqual(final["regen_count"], 1)
        self.assertEqual(calls["tlf"], 0)

    def test_pending_keeps_completion_false_and_persists_failure_is_capped(self):
        final, _ = graph_run([{"ADSL": False}])
        self.assertIn("14.1.1", final["tlf_pending"])
        self.assertFalse(final["completed"])
        self.assertLessEqual(final["regen_count"], 3)

    def test_skips_clear_once_the_table_becomes_eligible(self):
        pending, _ = graph_run([{"ADSL": False}])
        self.assertIn("14.1.1", pending["tlf_skipped"])

        recovered, _ = graph_run([{"ADSL": True}],
                                 state=base_state(
                                     tlf_skipped=pending["tlf_skipped"],
                                     tlf_pending=pending["tlf_pending"]))

        self.assertIn("14.1.1", recovered["tlf_programs"])
        self.assertEqual(recovered["tlf_skipped"], {})
        self.assertEqual(recovered["tlf_pending"], {})
        self.assertEqual(recovered["tlf_blocked"], {})

    def test_completion_is_false_while_work_is_pending(self):
        final, _ = graph_run([{"ADSL": False}])
        self.assertFalse(final["completed"])

    def test_exhausted_retries_are_recorded_on_the_state(self):
        """The cap ends the loop with work outstanding. Without a record the run looks
        finished, and test.py prints `completed` as the success signal."""
        final, _ = graph_run([{"ADSL": False}])

        self.assertEqual(final["regen_count"], 3)
        self.assertTrue(final["retry_exhausted"])
        self.assertIn("ADSL", final["needs_regeneration"])
        self.assertFalse(final["completed"])

    def test_retry_exhausted_is_false_when_the_run_converges(self):
        final, _ = graph_run([{"ADSL": False}, {"ADSL": True}])

        self.assertFalse(final["retry_exhausted"])
        self.assertTrue(final["completed"])

    def test_recorded_lot_failure_is_not_reported_as_a_complete_run(self):
        errors = ["lot_generator: empty response from LLM"]
        final, _ = graph_run([{"ADSL": True}], state=base_state(errors=errors))

        self.assertEqual(final["errors"], errors)
        self.assertFalse(final["completed"])


class GraphRepublicationTest(unittest.TestCase):
    """runner.py republishes every accepted dataset to a stable canonical path, so the
    publication path is not a change signal — only the content behind it is."""

    def test_tlf_is_regenerated_when_its_accepted_adam_is_republished(self):
        with tempfile.TemporaryDirectory() as directory:
            # ADSL gains a column on republication; ADAE is only accepted in round 2.
            published = {0: "USUBJID,AGE", 1: "USUBJID,AGE,TRT01P"}

            def publish(round_index, name, path):
                columns = "USUBJID" if name == "ADAE" else published[round_index]
                write_xpt(path, columns)

            state = base_state(lot_entries=[
                {"table_number": "14.1.1", "data_source": ["ADSL"]},
                {"table_number": "14.1.2", "data_source": ["ADAE"]},
            ])
            final, calls = graph_run(
                [{"ADSL": True, "ADAE": False}, {"ADSL": True, "ADAE": True}],
                state=state, execution_dir=directory, publish=publish)

            self.assertEqual(final["regen_count"], 2)
            self.assertTrue(final["completed"], final["tlf_skipped"])
            self.assertEqual(final["tlf_skipped"], {})
            # The accepted artifact really did change under the same path.
            self.assertEqual(columns_on_disk(Path(directory) / "ADSL.xpt"),
                             "USUBJID,AGE,TRT01P")
            # 14.1.1 was rebuilt once its input changed; 14.1.2's input did not change
            # after it was generated, so it was not rebuilt.
            self.assertEqual(calls["tables"].count("14.1.1"), 2)
            self.assertEqual(calls["tables"].count("14.1.2"), 1)

    def test_unchanged_adam_does_not_rebuild_its_table(self):
        with tempfile.TemporaryDirectory() as directory:
            def publish(round_index, name, path):
                write_xpt(path, "USUBJID,AGE")

            state = base_state(lot_entries=[
                {"table_number": "14.1.1", "data_source": ["ADSL"]},
                {"table_number": "14.1.2", "data_source": ["ADAE"]},
            ])
            final, calls = graph_run(
                [{"ADSL": True, "ADAE": False}, {"ADSL": True, "ADAE": True}],
                state=state, execution_dir=directory, publish=publish)

            self.assertTrue(final["completed"], final["tlf_skipped"])
            self.assertEqual(calls["tables"].count("14.1.1"), 1)
            self.assertEqual(calls["tables"], ["14.1.1", "14.1.2"])


class GraphStaleRebuildTest(unittest.TestCase):
    """Republication makes a table stale. When the rebuild cannot happen, the superseded
    program must not survive as if it were still current."""

    def listing_fails_after_first_call(self):
        """The column listing is the only R call that carries SAPIENT_ADAM_FILES, so this
        fails the listing alone and leaves the XPT writers real."""
        real_run = subprocess.run
        seen = {"n": 0}

        def runner(cmd, *args, **kwargs):
            if isinstance(kwargs.get("env"), dict) and "SAPIENT_ADAM_FILES" in kwargs["env"]:
                seen["n"] += 1
                if seen["n"] > 1:
                    return subprocess.CompletedProcess(cmd, 1, "", "Error: cannot open XPT")
            return real_run(cmd, *args, **kwargs)

        return runner, seen

    def test_superseded_tlf_is_dropped_when_the_rebuild_cannot_happen(self):
        runner, seen = self.listing_fails_after_first_call()
        with tempfile.TemporaryDirectory() as directory:
            published = {0: "USUBJID,AGE", 1: "USUBJID,AGE,TRT01P"}

            def publish(round_index, name, path):
                write_xpt(path, published[round_index] if name == "ADSL" else "USUBJID")

            # ADAE failing while 14.1.2 waits on it is only the trigger for a second round;
            # nothing flags 14.1.1 for regeneration, so only the schema change moves it.
            state = base_state(lot_entries=[
                {"table_number": "14.1.1", "data_source": ["ADSL"]},
                {"table_number": "14.1.2", "data_source": ["ADAE"]},
            ])
            with patch("subprocess.run", side_effect=runner):
                final, calls = graph_run(
                    [{"ADSL": True, "ADAE": False}, {"ADSL": True, "ADAE": True}],
                    state=state, execution_dir=directory, publish=publish)

            # The accepted artifact really did change under the same path.
            self.assertEqual(columns_on_disk(Path(directory) / "ADSL.xpt"),
                             "USUBJID,AGE,TRT01P")
        self.assertEqual(final["regen_count"], 2)
        self.assertEqual(seen["n"], 2)
        self.assertEqual(calls["tables"].count("14.1.1"), 1)
        # The program built against the superseded columns is not still on the books.
        self.assertNotIn("14.1.1", final["tlf_programs"])
        self.assertIn("14.1.1", final["tlf_pending"])
        self.assertIn("14.1.1", final["tlf_skipped"])
        self.assertIn("column listing unavailable", final["tlf_skipped"]["14.1.1"])
        self.assertNotIn("14.1.1", final.get("tlf_input_fingerprint") or {})
        self.assertFalse(final["completed"])
        self.assertFalse(final["retry_exhausted"])

    def test_unverifiable_table_is_held_rather_than_retained(self):
        """Without a listing the accepted schema cannot be re-read, so no table can be
        certified as current — including one whose columns did not in fact change. Holding
        is the safe direction: the table is pending and retryable, not silently accepted."""
        runner, seen = self.listing_fails_after_first_call()
        with tempfile.TemporaryDirectory() as directory:
            def publish(round_index, name, path):
                write_xpt(path, "USUBJID,AGE" if name == "ADSL" else "USUBJID")

            state = base_state(lot_entries=[
                {"table_number": "14.1.1", "data_source": ["ADSL"]},
                {"table_number": "14.1.2", "data_source": ["ADAE"]},
            ])
            with patch("subprocess.run", side_effect=runner):
                final, calls = graph_run(
                    [{"ADSL": True, "ADAE": False}, {"ADSL": True, "ADAE": True}],
                    state=state, execution_dir=directory, publish=publish)

            # ADSL is republished with exactly the columns it had in round 1.
            self.assertEqual(columns_on_disk(Path(directory) / "ADSL.xpt"), "USUBJID,AGE")
        self.assertEqual(seen["n"], 2)
        self.assertEqual(calls["tables"].count("14.1.1"), 1)
        for table in ("14.1.1", "14.1.2"):
            with self.subTest(table=table):
                self.assertNotIn(table, final["tlf_programs"])
                self.assertIn(table, final["tlf_pending"])
                self.assertNotIn(table, final["tlf_blocked"])
                self.assertIn("cannot open XPT", final["tlf_skipped"][table])
        # Held tables are not queued for regeneration, so the run ends incomplete with the
        # reason recorded rather than looping or claiming success.
        self.assertEqual(final["needs_regeneration"], [])
        self.assertFalse(final["retry_exhausted"])
        self.assertFalse(final["completed"])


class GraphRoutingDefectTest(unittest.TestCase):
    def test_pending_table_is_not_starved_by_a_sibling_table(self):
        """Two tables: 14.1.1 waits on ADSL, 14.1.2 builds independently. Once ADSL is
        accepted on retry, 14.1.1 must be generated too."""
        state = base_state(
            lot_entries=[
                {"table_number": "14.1.1", "data_source": ["ADSL"]},
                {"table_number": "14.1.2", "data_source": ["ADAE"]},
            ])

        final, calls = graph_run([{"ADSL": False, "ADAE": True}, {"ADSL": True, "ADAE": True}],
                                state=state)

        self.assertIn("14.1.1", final["tlf_programs"], final["tlf_skipped"])
        self.assertIn("14.1.2", final["tlf_programs"])
        self.assertEqual(final["tlf_skipped"], {})
        # 14.1.2 succeeded in round 1 and must not be rebuilt in round 2.
        self.assertEqual(calls["tlf"], 2)


if __name__ == "__main__":
    unittest.main()
