from __future__ import annotations
import sqlite3
import hashlib
import json
from datetime import datetime
from typing import Optional

class AuditWriter:
    def __init__(self, db_path: str = ':memory:'):
        self.conn = sqlite3.connect(db_path)
        self.conn.execute('CREATE TABLE IF NOT EXISTS AuditEvent (seq INTEGER PRIMARY KEY AUTOINCREMENT, timestamp TEXT, actor_type TEXT, actor_id TEXT, case_id TEXT, event_type TEXT, before_state TEXT, after_state TEXT, inputs_hash TEXT, policy_version TEXT, model_version TEXT, neatlogs_trace_id TEXT, prev_hash TEXT, this_hash TEXT, payload TEXT)')
        self.conn.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_audit_unique ON AuditEvent(seq)')
        self.conn.commit()

    def _hash_pair(self, prev_hash: Optional[str], seq: int, payload: dict) -> str:
        m = hashlib.sha256()
        # Ensure prev_hash is a string to avoid TypeError if it is an int
        base = (str(prev_hash) if prev_hash is not None else '') + str(seq) + json.dumps(payload, sort_keys=True)
        m.update(base.encode('utf-8'))
        return m.hexdigest()

    def append(self, payload: dict) -> None:
        cur = self.conn.cursor()
        cur.execute('SELECT this_hash FROM AuditEvent ORDER BY seq DESC LIMIT 1')
        row = cur.fetchone()
        prev_hash_val = row[0] if row else None
        seq = self._get_next_seq()
        this_hash_val = self._hash_pair(prev_hash_val, seq, payload)
        
        json_payload = json.dumps(payload, sort_keys=True)
        
        cur.execute('INSERT INTO AuditEvent (timestamp, actor_type, actor_id, case_id, event_type, before_state, after_state, inputs_hash, policy_version, model_version, neatlogs_trace_id, prev_hash, this_hash, payload, seq) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                    (payload.get('timestamp'), payload.get('actor_type'), payload.get('actor_id'), payload.get('case_id'), payload.get('event_type'), payload.get('before_state'), payload.get('after_state'), payload.get('inputs_hash'), payload.get('policy_version'), payload.get('model_version'), payload.get('neatlogs_trace_id'), prev_hash_val, this_hash_val, json_payload, seq))
        self.conn.commit()

    def _get_next_seq(self) -> int:
        cur = self.conn.cursor()
        cur.execute('SELECT MAX(seq) FROM AuditEvent')
        row = cur.fetchone()
        return (row[0] or 0) + 1

    def verify_chain(self) -> dict:
        cur = self.conn.cursor()
        cur.execute('SELECT seq, prev_hash, this_hash, payload FROM AuditEvent ORDER BY seq ASC')
        rows = cur.fetchall()
        ok = True
        broken_at: Optional[int] = None
        # Verify linkage and hash integrity
        for r in rows:
            seq, prev_hash, this_hash, payload_json = r
            payload = json.loads(payload_json) if payload_json else {}
            expected = self._hash_pair(prev_hash, seq, payload)
            if expected != this_hash:
                ok = False
                broken_at = seq
                break
        return {'ok': ok, 'broken_at': broken_at}

    def close(self):
        self.conn.close()
