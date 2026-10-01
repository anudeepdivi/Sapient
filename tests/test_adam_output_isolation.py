import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from config import R_EXECUTABLE
from r_layer.runner import run_adam_program, run_all_adam_programs
from templates.adam_templates import render_header, render_footer


class TestAdamOutputIsolation(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def export(self, dataset='ADSL'):
        return (f'haven::write_xpt(data.frame(USUBJID="new-output"), '
                f'file.path(Sys.getenv("SAPIENT_ADAM_DIR"), "{dataset}.xpt"))')

    def assert_diagnostics_and_cleanup(self, result):
        attempt = Path(result['attempt_dir'])
        self.assertTrue((attempt / 'result.json').is_file())
        self.assertTrue((attempt / f'{result["dataset"]}_generated.R').is_file())
        self.assertEqual(list(attempt.glob('work-*')), [])

    def test_no_export_cannot_reuse_previous_output(self):
        output = self.root / 'ADSL.xpt'
        output.write_bytes(b'previous output')
        with patch('r_layer.runner.validate_metacore') as validate:
            first = run_adam_program('ADSL', 'invisible(NULL)', adam_dir=self.root)
            second = run_adam_program('ADSL', 'invisible(NULL)', adam_dir=self.root)
        validate.assert_not_called()
        self.assertNotEqual(first['attempt_dir'], second['attempt_dir'])
        for result in (first, second):
            self.assertFalse(result['success'])
            self.assertIsNone(result['accepted_path'])
            self.assertIn('Expected output not written', result['stdout'])
            self.assert_diagnostics_and_cleanup(result)
        self.assertEqual(output.read_bytes(), b'previous output')

    def test_accepted_export_is_published_only_after_validation(self):
        output = self.root / 'ADSL.xpt'
        output.write_bytes(b'previous output')
        candidate_bytes = []

        def accept(dataset, adam_dir):
            candidate = Path(adam_dir) / f'{dataset}.xpt'
            self.assertNotEqual(candidate, output)
            self.assertEqual(output.read_bytes(), b'previous output')
            candidate_bytes.append(candidate.read_bytes())
            return {'success': True}

        with patch('r_layer.runner.validate_metacore', side_effect=accept):
            result = run_adam_program('ADSL', self.export(), adam_dir=self.root)
        self.assertTrue(result['success'], result)
        self.assertEqual(result['accepted_path'], str(output))
        self.assertEqual(output.read_bytes(), candidate_bytes[0])
        self.assert_diagnostics_and_cleanup(result)

    def test_failed_or_rejected_program_preserves_canonical_output(self):
        output = self.root / 'ADSL.xpt'
        cases = [
            ('execution', 'stop("failed attempt")', False),
            ('unreadable', 'writeLines("not an XPT", file.path(Sys.getenv("SAPIENT_ADAM_DIR"), "ADSL.xpt"))', False),
            ('metacore', self.export(), True),
        ]
        for name, code, validation_called in cases:
            with self.subTest(name=name):
                output.write_bytes(b'previous output')
                with patch('r_layer.runner.validate_metacore', return_value={
                        'success': False, 'error': 'rejected specification'}) as validate:
                    result = run_adam_program('ADSL', code, adam_dir=self.root)
                self.assertEqual(validate.called, validation_called)
                self.assertFalse(result['success'])
                self.assertIsNone(result['accepted_path'])
                self.assertEqual(output.read_bytes(), b'previous output')
                self.assert_diagnostics_and_cleanup(result)

    def test_parent_must_be_explicit_and_batch_uses_accepted_parent(self):
        (self.root / 'ADSL.xpt').write_bytes(b'old canonical parent')
        parent_code = '\n'.join([
            'parent <- haven::read_xpt(file.path(Sys.getenv("SAPIENT_ADAM_INPUT_DIR"), "ADSL.xpt"))',
            'stopifnot(parent$USUBJID == "new-output")',
            self.export('ADAE'),
        ])
        blocked = run_adam_program('ADAE', parent_code, adam_dir=self.root)
        self.assertEqual(blocked['stage'], 'blocked')
        self.assertIsNone(blocked['accepted_path'])
        with patch.dict('os.environ', {'SAPIENT_ADAM_INPUT_DIR': '/not/the/parent'}), \
                patch('r_layer.runner.validate_metacore', return_value={'success': True}):
            results = run_all_adam_programs(
                {'ADAE': parent_code, 'ADSL': self.export()}, adam_dir=self.root)
        for result in results.values():
            self.assertTrue(result['success'], result)
            self.assert_diagnostics_and_cleanup(result)

    def test_per_variable_caller_writes_experiment_and_reads_canonical_parent(self):
        from scripts import gen_derivations

        canonical = self.root / 'data' / 'adam'
        experiment = self.root / 'data' / 'adam_experiment'
        scripts = self.root / 'r_layer' / 'scripts'
        canonical.mkdir(parents=True)
        scripts.mkdir(parents=True)
        (scripts / 'compare_reference.R').write_text('invisible(NULL)\n')
        parent = canonical / 'ADSL.xpt'
        subprocess.run([R_EXECUTABLE, '-e',
                        f'haven::write_xpt(data.frame(USUBJID="canonical-parent"), {json.dumps(str(parent))})'],
                       check=True, capture_output=True, text=True, timeout=60)
        (canonical / 'ADAE.xpt').write_bytes(b'canonical result must stay unchanged')
        before = {p.name: p.read_bytes() for p in canonical.glob('*.xpt')}
        parent_line = next(line for line in render_header('ADAE').splitlines()
                           if line.startswith('adsl <-'))
        # Exercise the real path expressions without requiring clinical data/specs.
        export = render_footer('ADAE').splitlines()[-1].replace(
            'xportr::xportr_write', 'haven::write_xpt').replace(', domain = "ADAE"', '')
        with patch.object(gen_derivations, 'BASE_DIR', self.root), \
                patch.object(gen_derivations, 'get_spec_rules', return_value=[]), \
                patch.object(gen_derivations, 'spine_columns', return_value=set()), \
                patch.object(gen_derivations, 'run_steps', return_value=({}, [])), \
                patch.object(gen_derivations, 'spine', return_value='result <- adsl'), \
                patch.object(gen_derivations, 'render_header', return_value=parent_line), \
                patch.object(gen_derivations, 'render_footer', return_value=export), \
                patch.object(gen_derivations, 'gen_step', side_effect=AssertionError('No LLM calls')), \
                patch('r_layer.runner.validate_metacore', return_value={'success': True}), \
                contextlib.redirect_stdout(io.StringIO()) as captured:
            gen_derivations.main('ADAE')
        self.assertIn('assembled program executes: True', captured.getvalue())
        self.assertTrue((experiment / 'ADAE.xpt').is_file())
        self.assertEqual(before, {p.name: p.read_bytes() for p in canonical.glob('*.xpt')})
        check = subprocess.run([R_EXECUTABLE, '-e',
                                f'stopifnot(haven::read_xpt({json.dumps(str(experiment / "ADAE.xpt"))})$USUBJID == "canonical-parent")'],
                               capture_output=True, text=True, timeout=60)
        self.assertEqual(check.returncode, 0, check.stderr)

    def test_partial_upstream_failure_never_publishes_or_unblocks_dependent(self):
        for failure in ('execution', 'metacore'):
            with self.subTest(failure=failure):
                (self.root / 'ADSL.xpt').write_bytes(b'accepted old parent')
                (self.root / 'ADAE.xpt').write_bytes(b'accepted old child')
                marker = self.root / 'child-executed'
                child = f'writeLines("executed", {json.dumps(str(marker))})'
                parent = self.export()
                if failure == 'execution':
                    parent += '\nstop("failed after writing XPT")'
                with patch('r_layer.runner.validate_metacore', return_value={
                        'success': False, 'error': 'rejected'}) as validate:
                    results = run_all_adam_programs(
                        {'ADAE': child, 'ADSL': parent}, adam_dir=self.root)
                self.assertEqual(validate.called, failure == 'metacore')
                self.assertFalse(results['ADSL']['success'])
                self.assertIsNone(results['ADSL']['accepted_path'])
                self.assertEqual(results['ADAE']['stage'], 'blocked')
                self.assertIsNone(results['ADAE']['accepted_path'])
                self.assertFalse(marker.exists())
                self.assertEqual((self.root / 'ADSL.xpt').read_bytes(), b'accepted old parent')
                self.assertEqual((self.root / 'ADAE.xpt').read_bytes(), b'accepted old child')
                self.assert_diagnostics_and_cleanup(results['ADSL'])

    def test_failed_package_query_is_not_cached_as_an_empty_library(self):
        """An empty cached set makes check_package_allowlist reject every library() call
        as uninstalled for the rest of the process, so a failed query must not persist."""
        from r_layer import deterministic_checks

        original = deterministic_checks._installed_packages_cache
        self.addCleanup(setattr, deterministic_checks, '_installed_packages_cache', original)
        deterministic_checks._installed_packages_cache = None

        broken = subprocess.CompletedProcess([], 1, '', 'Rscript: could not open')
        healthy = subprocess.CompletedProcess([], 0, 'haven\ndplyr\nrtables\n', '')
        with patch('r_layer.deterministic_checks.subprocess.run', return_value=broken):
            self.assertEqual(deterministic_checks._installed_packages(), set())
        with patch('r_layer.deterministic_checks.subprocess.run', return_value=healthy):
            self.assertIn('haven', deterministic_checks._installed_packages())
            self.assertEqual(deterministic_checks.check_package_allowlist('library(haven)'), [])


if __name__ == '__main__':
    unittest.main()
