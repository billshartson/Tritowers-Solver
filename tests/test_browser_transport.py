"""Deterministic bridge/worker race tests; no browser runtime or private images."""
import os
from pathlib import Path
import shutil
import subprocess

import pytest


def test_browser_transport_races():
    node = shutil.which('node')
    if not node:
        if os.environ.get('CI'):
            pytest.fail('Node.js is required for browser transport regressions in CI.')
        pytest.skip('Node.js is not installed.')
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([node, 'tests/js/browser_transport.cjs'], cwd=root,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert '5 browser transport regression scenarios passed' in result.stdout
