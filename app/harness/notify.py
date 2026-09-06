import sqlite3
import json
import time
from typing import List, Dict, Any

CHANNELS = ('email', 'slack', 'webhook')

class Outbox:
    def __init__(self, db_path: str = ':memory:'):
        self.conn = sqlite3.connect(db_path)
        self.cur = self.conn.cursor()
        self.cur.execute('''
            CREATE TABLE IF NOT EXISTS Outbox (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                channel TEXT,
                recipient TEXT,
                subject TEXT,
                body TEXT,
                case_id TEXT,
                status TEXT,
                -- Number of attempts to send
                attempts INTEGER DEFAULT 0,
                created_at REAL,
                sent_at REAL
            )
        ''')
        self.conn.commit()

    def enqueue(self, channel: str, recipient: str, subject: str, body: str, case_id: str | None = None) -> int:
        if channel not in CHANNELS:
            raise ValueError(f'unknown channel: {channel}')
        self.cur.execute('''
            INSERT INTO Outbox (channel, recipient, subject, body, case_id, status, attempts, created_at)
            VALUES (?, ?, ?, ?, ?, 'pending', 0, ?)
        ''', (channel, recipient, subject, body, case_id, time.time()))
        self.conn.commit()
        return self.cur.lastrowid

    def pending(self, limit: int = 50) -> List[Dict[str, Any]]:
        self.cur.execute('''
            SELECT id, channel, recipient, subject, body, case_id, status, attempts, created_at, sent_at
            FROM Outbox WHERE status = 'pending'
            ORDER BY created_at ASC LIMIT ?
        ''', (limit,))
        rows = self.cur.fetchall()
        cols = [
            'id', 'channel', 'recipient', 'subject', 'body', 'case_id',
            'status', 'attempts', 'created_at', 'sent_at'
        ]
        return [dict(zip(cols, row)) for row in rows]

    def mark_sent(self, msg_id: int) -> None:
        self.cur.execute('''
            UPDATE Outbox SET status = 'sent', sent_at = ?
            WHERE id = ?
        ''', (time.time(), msg_id))
        self.conn.commit()

    def mark_failed(self, msg_id: int, error: str) -> None:
        new_body = f"ERROR: {error}"
        self.cur.execute('''
            UPDATE Outbox SET status = 'failed', attempts = attempts + 1, body = ?
            WHERE id = ?
        ''', (new_body, msg_id))
        self.conn.commit()

    def stats(self) -> Dict[str, int]:
        self.cur.execute('''
            SELECT 
                SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN status = 'sent' THEN 1 ELSE 0 END) as sent,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed
            FROM Outbox
        ''')
        row = self.cur.fetchone()
        return {'pending': row[0] or 0, 'sent': row[1] or 0, 'failed': row[2] or 0}

    def close(self) -> None:
        self.conn.close()

def flush(outbox: Outbox, sender, limit: int = 50) -> dict:
    pending = outbox.pending(limit=limit)
    attempted = 0
    sent = 0
    failed = 0
    
    for msg in pending:
        attempted += 1
        try:
            sender(msg)
            outbox.mark_sent(msg['id'])
            sent += 1
        except Exception as e:
            outbox.mark_failed(msg['id'], str(e))
            failed += 1
            
    return {'attempted': attempted, 'sent': sent, 'failed': failed}
