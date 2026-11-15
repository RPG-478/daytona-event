import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from orchestrator_a.run import execute, make_patch


FAKE = r'''#!/usr/bin/env python3
import json, os, pathlib, sys, time
assert sys.argv[1:3] == ['--profile', 'headless']
assert pathlib.Path(sys.argv[4]).is_file()
mode = os.environ.get('FAKE_MODE', 'success')
if mode == 'timeout':
    time.sleep(10)
if mode == 'error':
    print('dsh: MISSING_CREDENTIAL: secret-diagnostic', file=sys.stderr)
    print(json.dumps({'type':'final', 'reason':{'kind':'error', 'error':{'code':'AUTH'}}, 'text':''}))
    sys.exit(2)
counter = pathlib.Path('counter')
n = int(counter.read_text()) + 1 if counter.exists() else 1
counter.write_text(str(n))
if mode == 'missing':
    print(json.dumps({'type':'final', 'reason':{'kind':'completed'}, 'text':'completed'}))
    sys.exit(0)
if mode == 'modify-source':
    pathlib.Path('solution.py').write_text('def value(): return 42\n')
if mode == 'no-tests':
    pathlib.Path('test_solution.py').write_text('# no tests\n')
elif mode == 'all-skipped':
    pathlib.Path('test_solution.py').write_text('import pytest\n@pytest.mark.skip(reason="skip")\ndef test_skipped(): pass\n')
elif mode == 'xpassed':
    pathlib.Path('test_solution.py').write_text('import pytest\n@pytest.mark.xfail(strict=False)\ndef test_xpass(): pass\n')
elif mode == 'repair' and n == 1:
    pathlib.Path('test_solution.py').write_text('def test_value():\n    assert False\n')
else:
    if mode == 'repair':
        assert 'previous pytest run' in sys.argv[-1]
    pathlib.Path('test_solution.py').write_text('import solution\ndef test_value():\n    assert solution.value() == 42\n')
if mode == 'long-output':
    print(json.dumps({'type':'thinking', 'text':'あ' * 300000}, ensure_ascii=False))
print(json.dumps({'type':'final', 'reason':{'kind':'completed'}, 'text':('完' * 300000 + '\u2028\u2029') if mode == 'long-output' else 'completed'}, ensure_ascii=False))
'''


def setup(monkeypatch, tmp_path, mode):
    fake = tmp_path / 'fake-dsh'
    fake.write_text(FAKE)
    fake.chmod(0o755)
    monkeypatch.setenv('FAKE_MODE', mode)
    monkeypatch.setenv('NOSANA_API_KEY', 'secret-diagnostic')
    return str(fake)


def run(fake, attempts=2, timeout=20):
    return execute('def value():\n    return 42\n', 'http://127.0.0.1:1/v1', 'model', fake, attempts, timeout)


def test_success(monkeypatch, tmp_path):
    result = run(setup(monkeypatch, tmp_path, 'success'))
    assert result['status'] == 'succeeded'
    assert result['attempts'] == 1
    assert 'def test_value' in result['test_code']


def test_large_utf8_output_and_final_event(monkeypatch, tmp_path):
    result = run(setup(monkeypatch, tmp_path, 'long-output'))
    assert result['status'] == 'succeeded'
    assert any('[truncated]' in line for line in result['logs'])


def test_failed_test_is_repaired(monkeypatch, tmp_path):
    result = run(setup(monkeypatch, tmp_path, 'repair'))
    assert result['status'] == 'succeeded'
    assert result['attempts'] == 2
    assert any('pytest exited 1' in line for line in result['logs'])


def test_no_tests_is_not_success(monkeypatch, tmp_path):
    result = run(setup(monkeypatch, tmp_path, 'no-tests'))
    assert result['status'] == 'failed'
    assert result['attempts'] == 2
    assert any('pytest exited 5' in line for line in result['logs'])


def test_missing_test_not_success(monkeypatch, tmp_path):
    result = run(setup(monkeypatch, tmp_path, 'missing'))
    assert result['status'] == 'failed'
    assert result['attempts'] == 2


def test_all_skipped_is_not_success(monkeypatch, tmp_path):
    result = run(setup(monkeypatch, tmp_path, 'all-skipped'))
    assert result['status'] == 'failed'
    assert result['attempts'] == 2
    assert any('No test passed' in line for line in result['logs'])


def test_xpass_is_not_success(monkeypatch, tmp_path):
    result = run(setup(monkeypatch, tmp_path, 'xpassed'), attempts=1)
    assert result['status'] == 'failed'


def test_modified_source_not_success(monkeypatch, tmp_path):
    result = run(setup(monkeypatch, tmp_path, 'modify-source'))
    assert result['status'] == 'failed'
    assert 'changed the source' in result['message']


def test_dsh_error_does_not_expose_stderr(monkeypatch, tmp_path):
    result = run(setup(monkeypatch, tmp_path, 'error'))
    assert result['status'] == 'failed'
    assert result['error_code'] == 'AUTH'
    assert 'secret-diagnostic' not in str(result)


def test_timeout(monkeypatch, tmp_path):
    started = time.monotonic()
    result = run(setup(monkeypatch, tmp_path, 'timeout'), timeout=1)
    assert result['status'] == 'timed_out'
    assert time.monotonic() - started < 5


def test_patch_quotes_user_values():
    patch = make_patch('https://example.test/v1', 'my:model')
    assert 'baseURL: "https://example.test/v1"' in patch
    assert 'model: "my:model"' in patch
    assert 'apiKeyEnv: NOSANA_API_KEY' in patch
