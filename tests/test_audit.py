import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.harness.audit import AuditWriter
import pytest

def test_append_verify():
    writer = AuditWriter()
    events = [
        {"timestamp": "t1", "actor_type": "user", "actor_id": "u1", "case_id": "c1", "event_type": "init"},
        {"timestamp": "t2", "actor_type": "bot", "actor_id": "b1", "case_id": "c1", "event_type": "process"},
        {"timestamp": "t3", "actor_type": "system", "actor_id": "s1", "case_id": "c1", "event_type": "complete"},
    ]
    for e in events:
        writer.append(e)
    
    result = writer.verify_chain()
    assert result['ok'] is True
    assert result['broken_at'] is None
    writer.close()

def test_empty():
    writer = AuditWriter()
    result = writer.verify_chain()
    assert result['ok'] is True
    assert result['broken_at'] is None
    writer.close()

def test_tamper():
    writer = AuditWriter()
    events = [
        {"timestamp": "t1", "actor_type": "user", "actor_id": "u1", "case_id": "c1", "event_type": "init"},
        {"timestamp": "t2", "actor_type": "bot", "actor_id": "b1", "case_id": "c1", "event_type": "process"},
        {"timestamp": "t3", "actor_type": "system", "actor_id": "s1", "case_id": "c1", "event_type": "complete"},
    ]
    for e in events:
        writer.append(e)
    
    # Simulate tampering: modify row 2 (seq=2)
    # Update after_state and payload
    writer.conn.execute("UPDATE AuditEvent SET after_state='tampered', payload='{\"x\": 1}' WHERE seq=2")
    writer.conn.commit()
    
    result = writer.verify_chain()
    assert result['ok'] is False
    # The tampering happens at seq 2
    assert result['broken_at'] == 2
    writer.close()

def test_linkage():
    writer = AuditWriter()
    events = [
        {"timestamp": "t1", "actor_type": "user", "actor_id": "u1", "case_id": "c1", "event_type": "init"},
        {"timestamp": "t2", "actor_type": "bot", "actor_id": "b1", "case_id": "c1", "event_type": "process"},
    ]
    for e in events:
        writer.append(e)
    
    # Verify linkage manually:
    # row 1's this_hash should equal row 2's prev_hash
    cur = writer.conn.cursor()
    cur.execute('SELECT this_hash FROM AuditEvent WHERE seq=1')
    hash1 = cur.fetchone()[0]
    cur.execute('SELECT prev_hash FROM AuditEvent WHERE seq=2')
    hash2 = cur.fetchone()[0]
    assert hash1 == hash2
    
    writer.close()
