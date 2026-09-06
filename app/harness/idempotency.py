import json
import sqlite3
import time
import hashlib
from typing import Any, Dict, Optional

def action_key(case_id: str, action: str, payload: Optional[dict] = None) -> str:
    """
    Deterministic key generator based on the payload content and context.
    """
    payload_str = json.dumps(payload or {}, sort_keys=True)
    content = f"{case_id}|{action}|{payload_str}"
    return hashlib.sha256(content.encode()).hexdigest()[:32]

class IdempotencyStore:
    def __init__(self, db_path: str = ":memory:"):
        """
        Initialize the SQLite store.
        """
        self.conn = sqlite3.connect(db_path, isolation_level=None)
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS ActionState "
            "(key TEXT PRIMARY KEY, case_id TEXT, action TEXT, state TEXT, result TEXT, created_at REAL)"
        )
        self.conn.commit()

    def begin(self, key: str, case_id: str, action: str) -> bool:
        """
        Attempt to claim the key by inserting state 'in_progress'.
        Returns True if this caller successfully claimed the key, False otherwise.
        """
        try:
            self.conn.execute(
                "INSERT INTO ActionState (key, case_id, action, state, result, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (key, case_id, action, "in_progress", None, time.time()),
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            # Key already exists
            return False

    def complete(self, key: str, result: Optional[dict] = None) -> None:
        """
        Mark the action as done and store the result.
        """
        result_json = json.dumps(result or {})
        self.conn.execute(
            "UPDATE ActionState SET state = ?, result = ? WHERE key = ?",
            ("done", result_json, key),
        )
        self.conn.commit()

    def fail(self, key: str, error: str) -> None:
        """
        Mark the action as failed and store the error message.
        """
        self.conn.execute(
            "UPDATE ActionState SET state = ?, result = ? WHERE key = ?",
            ("failed", error, key),
        )
        self.conn.commit()

    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve the state for a key.
        Returns a dictionary with keys: key, case_id, action, state, result (parsed back).
        Returns None if key not found.
        """
        cursor = self.conn.execute("SELECT * FROM ActionState WHERE key = ?", (key,))
        row = cursor.fetchone()
        if not row:
            return None

        # Convert tuple row to dictionary using cursor description for column names
        columns = [description[0] for description in cursor.description]
        row_dict = dict(zip(columns, row))
        
        # Parse JSON result if possible
        try:
            row_dict["result"] = json.loads(row_dict["result"])
        except (json.JSONDecodeError, TypeError):
            pass
        return row_dict

    def is_done(self, key: str) -> bool:
        """
        Check if the state is exactly 'done'.
        """
        state_row = self.get(key)
        return state_row is not None and state_row["state"] == "done"

    def close(self) -> None:
        """
        Close the database connection.
        """
        self.conn.close()

def run_once(
    store: IdempotencyStore, 
    case_id: str, 
    action: str, 
    fn, 
    payload: Optional[dict] = None
) -> dict:
    """
    Execute fn once for the given case/action payload, ensuring idempotency.
    Returns a dictionary with execution status and details.
    """
    key = action_key(case_id, action, payload)
    
    # Check if already done
    if store.is_done(key):
        stored_result = store.get(key).get("result")
        return {
            "executed": False,
            "reason": "already done",
            "result": stored_result,
        }

    # Attempt to begin (claim)
    if not store.begin(key, case_id, action):
        return {
            "executed": False,
            "reason": "in progress",
            "result": None,
        }

    # Function executed, handle result
    try:
        result = fn()
        store.complete(key, result)
        return {
            "executed": True,
            "reason": "ok",
            "result": result,
        }
    except Exception as e:
        store.fail(key, str(e))
        raise
