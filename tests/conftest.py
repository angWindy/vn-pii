"""Pytest config shared by all tests.

The agent-hook integration tests spawn the real ``pii-lint`` binary
(either via the ``pii-lint`` console script on PATH or through the
hook scripts that shell out to it). The console-script shebang
``#!/usr/bin/python3`` is rewritten by pip at install time and points
at whatever Python the user's system had at install time. If that
interpreter is not the one this repo's editable install registered
the ``pii_linter`` package on, the spawned process crashes with
``ModuleNotFoundError: No module named 'pii_linter'`` and the test
fails for the wrong reason.

The cleanest way to dodge that is to wrap ``pii-lint`` in a tiny
shim that prepends the editable-install root to ``PYTHONPATH`` and
``exec``s the real console script. We do that exactly once per
session, drop the shim on ``PATH`` via a session-scoped env, and
let every test pick it up transparently.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def _pii_lint_shim_dir(tmp_path_factory) -> Path:
    """Create a dir containing a `pii-lint` shim that injects PYTHONPATH.

    The shim resolves the editable-install root by walking up from this
    test file (``tests/conftest.py`` -> repo root), then sets
    ``PYTHONPATH`` to that root and ``exec``s the real console script
    that ``shutil.which('pii-lint')`` points at. The result is a
    ``pii-lint`` that always imports from the checkout under test, no
    matter which Python interpreter the shebang happens to name.
    """
    real_pii_lint = shutil.which("pii-lint")
    if real_pii_lint is None:
        # Nothing to wrap. The tests that need the shim will fail loudly
        # downstream with a clear "pii-lint not on PATH" assertion.
        return tmp_path_factory.mktemp("pii-lint-shim-skip")
    repo_root = Path(__file__).resolve().parent.parent
    shim_dir = tmp_path_factory.mktemp("pii-lint-shim")
    shim = shim_dir / "pii-lint"
    shim.write_text(
        "#!/bin/sh\n"
        f'export PYTHONPATH="{repo_root}:${{PYTHONPATH:-}}"\n'
        f'exec "{real_pii_lint}" "$@"\n'
    )
    shim.chmod(0o755)
    return shim_dir


@pytest.fixture(autouse=False)
def pii_lint_on_path(_pii_lint_shim_dir, monkeypatch):
    """Prepend the shim dir to PATH for the duration of one test."""
    monkeypatch.setenv(
        "PATH", str(_pii_lint_shim_dir) + os.pathsep + os.environ.get("PATH", "")
    )
