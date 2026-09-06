import sqlite3
import os
from pathlib import Path

SCHEMA_PATH = Path(__file__).resolve().parent.parent / 'schema.sql'

def get_connection(db_path: str | None = None) -> sqlite3.Connection:
    path = db_path or os.environ.get('DB_PATH', './reconcileos.db')
    con = sqlite3.connect(path)
    con.execute('PRAGMA foreign_keys = ON;')
    return con

def apply_schema(db_path: str | None = None) -> None:
    conn = get_connection(db_path)
    with open(SCHEMA_PATH, 'r', encoding='utf-8') as f:
        sql = f.read()
    # Execute in a simple way; SQLite will ignore duplicates if repeated in a clean fashion
    for stmt in filter(None, [s.strip() for s in sql.split(';')]):
        if not stmt:
            continue
        conn.execute(stmt + ';')
    conn.commit()
    conn.close()

def main():
    apply_schema()

if __name__ == '__main__':
    main()
