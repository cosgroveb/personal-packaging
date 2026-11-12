#!/usr/bin/env python3
import ast
import contextlib
import io
import os
import importlib.util
from unittest import mock
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import sys
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]


class RegressionTests(unittest.TestCase):
    def test_websocket_eof_and_deadline(self):
        tree = ast.parse((ROOT / 'live-serve/scripts/runtime-test.py').read_text())
        function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'receive')
        namespace = {'time': time}
        exec(compile(ast.Module(body=[function], type_ignores=[]), '<receive>', 'exec'), namespace)
        left, right = socket.socketpair()
        try:
            right.close()
            with self.assertRaises(EOFError):
                namespace['receive'](left, time.monotonic() + 1)
            with self.assertRaises(TimeoutError):
                namespace['receive'](left, time.monotonic() - 1)
        finally:
            left.close()

    def test_divergent_push_url_fails_before_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            scripts = root / 'live-serve/scripts'
            scripts.mkdir(parents=True)
            shutil.copy(ROOT / 'live-serve/scripts/release', scripts)
            subprocess.run(['git', 'init', '-q', str(root)], check=True)
            subprocess.run(['git', '-C', str(root), 'remote', 'add', 'origin', 'https://github.com/cosgroveb/personal-packaging.git'], check=True)
            subprocess.run(['git', '-C', str(root), 'remote', 'set-url', '--push', 'origin', 'https://example.com/other.git'], check=True)
            result = subprocess.run([str(scripts / 'release')], text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('unexpected push URL', result.stderr)
            tags = subprocess.check_output(['git', '-C', str(root), 'tag'], text=True)
            self.assertEqual(tags, '')

    def test_actual_help_commands(self):
        for args, expected in [(('help',), ('live-serve', 'help')), (('live-serve', 'help'), ('test', 'build', 'package', 'publish', 'release', 'help'))]:
            result = subprocess.run(['make', '-s', '-C', str(ROOT), *args], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            for item in expected:
                self.assertIn(item, result.stdout)

    def test_bare_package_runs_verification(self):
        result = subprocess.run(['make', '-n', '-s', '-C', str(ROOT), 'live-serve'], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('python3 tests/test_regressions.py', result.stdout)
        self.assertIn('./scripts/matrix', result.stdout)

    def test_make_dispatch_and_unknown_goals(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copy(ROOT / 'Makefile', root)
            for name in ('alpha', 'beta'):
                (root / name).mkdir()
                (root / name / 'Makefile').write_text('help:\n\t@echo value=$(VALUE)\n')
            def make(*args):
                return subprocess.run(['make', '-s', '-C', str(root), *args], text=True, capture_output=True)
            selected = make('alpha', 'help', 'VALUE=passed')
            self.assertEqual(selected.returncode, 0, selected.stderr)
            self.assertEqual(selected.stdout.strip(), 'value=passed')
            for args in [('alpha', 'beta'), ('alpha', 'typo'), ('typo',)]:
                self.assertNotEqual(make(*args).returncode, 0)

    def test_packagecloud_mapping_and_partial_failure(self):
        spec = importlib.util.spec_from_file_location('publish', ROOT / 'live-serve/scripts/publish.py')
        publish = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(publish)
        data = {'deb': [{'index_name': 'debian', 'versions': [{'index_name': s} for s in ('bookworm', 'trixie', 'sid')]}, {'index_name': 'ubuntu', 'versions': [{'index_name': 'noble'}]}]}
        calls = []
        def run(args, **kwargs):
            calls.append(args)
            return subprocess.CompletedProcess(args, 9 if len(calls) == 4 else 0)
        env = {'PACKAGECLOUD_REPOSITORY': 'cosgroveb/test', 'PACKAGECLOUD_TOKEN': 'test-token'}
        errors = io.StringIO()
        with mock.patch.dict(os.environ, env), mock.patch.object(publish.shutil, 'which', return_value='/fake/package_cloud'), mock.patch.object(publish, 'distributions', return_value=data), mock.patch.object(publish.subprocess, 'run', side_effect=run), contextlib.redirect_stderr(errors):
            self.assertEqual(publish.main(), 9)
        report = errors.getvalue()
        self.assertIn('prior successes:', report)
        self.assertIn('Upload failed for live-serve_0.4.3-1_trixie_amd64.deb', report)
        self.assertIn('unattempted:', report)
        for suite, arch in [('trixie', 'arm64'), ('sid', 'amd64'), ('sid', 'arm64'), ('noble', 'amd64'), ('noble', 'arm64')]:
            distro = publish.MAPPING[suite]
            self.assertIn(f'cosgroveb/test/{distro}/{suite}: live-serve_0.4.3-1_{suite}_{arch}.deb', report)
        self.assertEqual([c[2] for c in calls[1:]], ['cosgroveb/test/debian/bookworm', 'cosgroveb/test/debian/bookworm', 'cosgroveb/test/debian/trixie'])
        self.assertEqual(len(calls), 4)
        with mock.patch.dict(os.environ, {'PACKAGECLOUD_REPOSITORY': 'other/example', 'PACKAGECLOUD_TOKEN': 'x'}):
            with self.assertRaises(ValueError):
                publish.main()
        with mock.patch.dict(os.environ, {'PACKAGECLOUD_REPOSITORY': 'cosgroveb/test', 'PACKAGECLOUD_TOKEN': ''}):
            with self.assertRaises(ValueError):
                publish.main()
        with mock.patch.dict(os.environ, env), mock.patch.object(publish.shutil, 'which', return_value=None):
            with self.assertRaises(ValueError):
                publish.main()
        calls.clear()
        with mock.patch.dict(os.environ, env), mock.patch.object(publish.shutil, 'which', return_value='/fake/package_cloud'), mock.patch.object(publish, 'distributions', return_value=data), mock.patch.object(publish.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)) as push:
            self.assertEqual(publish.main(), 0)
        self.assertEqual([c.args[0][2] for c in push.call_args_list[1:]], [f'cosgroveb/test/{d}/{s}' for s, d in publish.MAPPING.items() for _ in range(2)])
        data['deb'][0]['versions'].pop()
        with mock.patch.dict(os.environ, env), mock.patch.object(publish.shutil, 'which', return_value='/fake/package_cloud'), mock.patch.object(publish, 'distributions', return_value=data), mock.patch.object(publish.subprocess, 'run', side_effect=run):
            with self.assertRaises(ValueError):
                publish.main()
        self.assertEqual(len(calls), 1)

    def test_invalid_build_targets_fail(self):
        build = str(ROOT / 'live-serve/scripts/build')
        for suite, arch in (('wrong', 'amd64'), ('bookworm', 'wrong')):
            result = subprocess.run([build, suite, arch], text=True, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('unsupported', result.stderr)

    def test_missing_artifact_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ('dpkg-deb', 'sha256sum'):
                tool = Path(tmp) / name
                tool.write_text('#!/bin/sh\nexit 0\n')
                tool.chmod(0o755)
            env = dict(os.environ, PATH=f'{tmp}:{os.environ["PATH"]}')
            result = subprocess.run([str(ROOT / 'live-serve/scripts/validate-artifacts'), tmp], env=env, capture_output=True)
            self.assertNotEqual(result.returncode, 0)

    def test_release_lookup_failure_is_fatal(self):
        with tempfile.TemporaryDirectory() as tmp:
            gh = Path(tmp) / 'gh'
            gh.write_text('#!/bin/sh\nexit 23\n')
            gh.chmod(0o755)
            env = dict(os.environ, PATH=f'{tmp}:{os.environ["PATH"]}')
            result = subprocess.run([str(ROOT / 'live-serve/scripts/check-release'), 'live-serve/v0.4.3-1'], env=env)
            self.assertEqual(result.returncode, 23)


if __name__ == '__main__':
    unittest.main()
