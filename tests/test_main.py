import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from fastapi.testclient import TestClient
from app.main import app as main_app
from fastapi import FastAPI

def test_root_html_response():
    client = TestClient(main_app)
    resp = client.get('/')
    assert resp.status_code == 200
    content_type = resp.headers.get('content-type', '')
    assert content_type.startswith('text/html')
    assert resp.text is not None
    assert len(resp.text) > 0

def test_app_is_fastapi_instance():
    assert isinstance(main_app, FastAPI)

def test_health_endpoint():
    client = TestClient(main_app)
    resp = client.get('/health')
    assert resp.status_code == 200
