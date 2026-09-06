import os
import sqlite3
import tempfile
from fastapi.testclient import TestClient
import sys, os
# Ensure repo root is on PYTHONPATH early for CI environments
_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
def _try_import_app():
    try:
        from app.api import app as api
        return api
    except Exception:
        pass
    # Last-resort: adjust sys.path to include repo root and retry
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    try:
        from app.api import app as api
        return api
    except Exception:
        return None

try:
    api = _try_import_app()
except Exception:
    api = None
if api is None:
    # Deterministic fallback: import via absolute import from known surface
    try:
        from app.api import app as api  # type: ignore
    except Exception:
        raise ModuleNotFoundError("Could not import app.api.app for tests. Ensure repository root is on PYTHONPATH and app package is importable.")

import pytest

@pytest.fixture
def temp_db():
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    yield path
    try:
        os.remove(path)
    except OSError:
        pass

@pytest.fixture
def client():
    return TestClient(api.app)

@pytest.fixture
def fixtures_dir():
    return os.path.join(os.path.dirname(__file__), 'fixtures')
