import sys
import os
import datetime
import pytest
import json
import zipfile
import io

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.harness.evidence import build_manifest, build_pack, write_pack, read_pack_names

def test_zip_signature():
    case = {'case_id': 'c1'}
    events = []
    data = build_pack(case, events)
    assert data.startswith(b'PK')

def test_read_pack_names():
    case = {'case_id': 'c2'}
    events = []
    data = build_pack(case, events)
    names = read_pack_names(data)
    expected = ['README.txt', 'audit_events.json', 'case.json', 'manifest.json', 'transactions.json']
    assert names == expected

def test_manifest_event_count():
    case = {'case_id': 'c3'}
    events = [{'id': 1}, {'id': 2}, {'id': 3}]
    manifest = build_manifest(case, events)
    assert manifest['event_count'] == 3

def test_case_round_trip():
    case = {
        'case_id': 'c2',
        'status': 'PENDING',
        'confidence': 0.75,
        'metadata': {'key': 'value'}
    }
    data = build_pack(case, [])
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        content = zf.read('case.json').decode()
        loaded = json.loads(content)
        assert loaded == case

def test_write_pack_creates_file(tmp_path):
    case = {'case_id': 'c3'}
    events = []
    path = tmp_path / "evidence.zip"
    result_path = write_pack(str(path), case, events)
    assert result_path == str(path)
    assert path.exists()
    assert path.stat().st_size > 0

    with zipfile.ZipFile(path) as zf:
        assert 'case.json' in zf.namelist()

def test_datetime_serialization():
    case = {'case_id': 'c4', 'timestamp': datetime.datetime(2022, 5, 15, 12, 30, tzinfo=datetime.timezone.utc)}
    try:
        build_pack(case, [])
    except TypeError:
        pytest.fail("Datetime serialization failed.")

def test_transactions_defaults():
    case = {'case_id': 'c5'}
    events = []
    data = build_pack(case, events, transactions=None)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        assert 'transactions.json' in zf.namelist()
        content = zf.read('transactions.json').decode()
        assert content == '[]'
