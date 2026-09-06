import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from app.harness.notify import Outbox, CHANNELS, flush

@pytest.fixture
def outbox():
    outbox = Outbox()
    yield outbox
    outbox.close()

def make_fake_sender(should_fail_on=None):
    calls = []
    def sender(msg):
        calls.append(msg)
        if should_fail_on and msg['recipient'] == should_fail_on:
            raise Exception("Mock Error")
    sender.calls = calls
    return sender

def test_enqueue_returns_int_and_increases(outbox):
    assert outbox.enqueue("email", "r1@test.com", "S1", "B1") == 1
    assert outbox.enqueue("email", "r2@test.com", "S2", "B2") == 2
    assert outbox.enqueue("email", "r3@test.com", "S3", "B3") == 3

def test_unknown_channel_raises_value_error(outbox):
    with pytest.raises(ValueError, match="unknown channel"):
        outbox.enqueue("sms", "t@test.com", "S", "B")

def test_pending_limit_and_ordering(outbox):
    for i in range(5):
        outbox.enqueue("email", f"r{i}@test.com", "S", "B")
    pending = outbox.pending(limit=3)
    assert len(pending) == 3
    assert pending[0]["recipient"] == "r0@test.com"

def test_mark_sent_updates_stats(outbox):
    outbox.enqueue("email", "t@test.com", "S", "B")
    msg_id = outbox.enqueue("email", "t2@test.com", "S", "B")
    outbox.mark_sent(msg_id)
    assert outbox.stats() == {'pending': 1, 'sent': 1, 'failed': 0}

def test_flush_success_drains_all(outbox):
    for i in range(5):
        outbox.enqueue("email", f"t{i}@test.com", f"Sub{i}", f"Body{i}")
    sender = make_fake_sender()
    result = flush(outbox, sender, 50)
    assert result['attempted'] == 5
    assert result['sent'] == 5
    assert result['failed'] == 0
    assert len(outbox.pending()) == 0

def test_flush_continues_on_failure(outbox):
    outbox.enqueue("email", "good@test.com", "Sub1", "Body1")
    outbox.enqueue("email", "bad@test.com", "Sub2", "Body2")
    outbox.enqueue("email", "good2@test.com", "Sub3", "Body3")
    sender = make_fake_sender(should_fail_on="bad@test.com")
    result = flush(outbox, sender, 50)
    assert result['attempted'] == 3
    assert result['sent'] == 2
    assert result['failed'] == 1
    assert len(outbox.pending()) == 0

def test_mark_failed_increments_attempts_and_body(outbox):
    msg_id = outbox.enqueue("email", "a@test.com", "Sub", "Body")
    outbox.mark_failed(msg_id, "Connection Timeout")
    assert outbox.stats() == {'pending': 0, 'sent': 0, 'failed': 1}
    outbox.cur.execute("SELECT body FROM Outbox WHERE id = ?", (msg_id,))
    row = outbox.cur.fetchone()
    assert "ERROR: Connection Timeout" in row[0]
