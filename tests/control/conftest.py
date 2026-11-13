"""Shared fixtures of the control tests (tests/control): the repo root, the installed build, EOS."""
import os
import shutil

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TB = "/eos/experiment/drdcalo/siw-ecal/TB2026-06"


@pytest.fixture(scope="session")
def repo():
    return ROOT


@pytest.fixture(scope="session")
def k4env():
    """The tests that run Gaudi need the environment of init_siwecalsoft.sh and a built install/."""
    if not os.environ.get("SIWECAL_SOFT_ROOT") or shutil.which("k4run") is None:
        pytest.skip("source init_siwecalsoft.sh first (k4run, SIWECAL_SOFT_ROOT)")
    prefix = os.environ.get("SIWECAL_PREFIX", os.path.join(ROOT, "install"))
    if not os.path.isdir(prefix):
        pytest.skip("no install/: run ./build.sh")
    return dict(os.environ)


@pytest.fixture(scope="session")
def eos():
    if not os.path.isdir(TB):
        pytest.skip("EOS project area not mounted")
    return TB


def tracked_files(root):
    """Files that belong to the source tree: everything but build products, local work and virtualenvs."""
    skip = {".git", "build", "install", "work", ".venv", "__pycache__", ".pytest_cache"}
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in skip]
        for n in fn:
            if n.endswith((".pyc", ".log")):
                continue
            yield os.path.relpath(os.path.join(dp, n), root)
