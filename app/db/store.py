import json
import os
import re
import sqlite3
from typing import Any, Dict, List, Tuple

SCHEMA_PATH = os.path.join(os.path.dirname(__file__), 'schema.sql')


def connect(db_path: str = ':memory:') -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    if db_path != ':memory:':
        conn.execute('PRAGMA journal_mode=WAL')
    return conn


def init_db(conn) -> None:
    with open(SCHEMA_PATH, 'r', encoding='utf-8') as f:
        schema = f.read()

    # Drop existing tables to make init idempotent
    # Create table regex
    for match in re.finditer(r'CREATE TABLE (\w+)', schema):
        table_name = match.group(1)
        conn.execute(f'DROP TABLE IF EXISTS {table_name}')

    conn.executescript(schema)
    conn.commit()


def insert_row(conn, table: str, row: Dict[str, Any]) -> None:
    cols = ', '.join(row.keys())
    placeholders = ', '.join(['?'] * len(row))
    values = []
    for v in row.values():
        if isinstance(v, (dict, list)):
            values.append(json.dumps(v))
        else:
            values.append(v)

    sql = f'INSERT OR REPLACE INTO {table} ({cols}) VALUES ({placeholders})'
    cursor = conn.cursor()
    cursor.execute(sql, values)
    conn.commit()


def insert_many(conn, table: str, rows: List[Dict[str, Any]]) -> None:
    for row in rows:
        insert_row(conn, table, row)


def query(conn, sql: str, params: Tuple = ()) -> List[Dict]:
    cursor = conn.cursor()
    cursor.execute(sql, params)
    results = [dict(r) for r in cursor.fetchall()]
    return results


def count(conn, table: str) -> int:
    cursor = conn.cursor()
    cursor.execute(f'SELECT count(*) FROM {table}')
    return cursor.fetchone()[0]
