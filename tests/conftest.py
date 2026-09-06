import os
import sqlite3
import tempfile
from fastapi.testclient import TestClient
from app.api import __init__ as api

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
