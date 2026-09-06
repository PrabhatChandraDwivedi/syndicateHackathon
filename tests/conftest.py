import os
import sqlite3
import tempfile
from fastapi.testclient import TestClient
try:
    # Prefer importing the FastAPI app exposed by app.api
    from app.api import app as api
except Exception:
    # Fallback: import the __init__ module to avoid import-time failures in CI environments
    from importlib import import_module
    api = import_module('app.api').__dict__.get('app')  # type: ignore

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
