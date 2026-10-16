'Checkpoint JSON và sổ dự báo/phản hồi bất biến, ghi trong cùng giao dịch.'
from __future__ import annotations

import json
import sqlite3
from typing import Any


def encode(value: Any) -> str:
    return json.dumps(value, allow_nan=False, sort_keys=True, separators=(',', ':'))


class StateStore:
    def __init__(self, path: str, config: dict[str, int]) -> None:
        self.connection = sqlite3.connect(path, timeout=10, isolation_level=None)
        self.connection.execute('PRAGMA journal_mode=WAL')
        self.connection.execute('PRAGMA synchronous=FULL')
        self.connection.executescript('''
            CREATE TABLE IF NOT EXISTS checkpoint(
              id INTEGER PRIMARY KEY CHECK(id=1), revision INTEGER NOT NULL,
              config TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS forecasts(cycle INTEGER PRIMARY KEY, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS outcomes(cycle INTEGER PRIMARY KEY, payload TEXT NOT NULL);
        ''')
        self.connection.execute('INSERT OR IGNORE INTO checkpoint VALUES(1,0,?,?)',
                                (encode(config), '{}'))
        row = self.connection.execute('SELECT config FROM checkpoint WHERE id=1').fetchone()
        if json.loads(row[0]) != config:
            self.close()
            raise ValueError('Database configuration differs; use a separate database.')

    def load(self) -> tuple[int, dict]:
        revision, payload = self.connection.execute(
            'SELECT revision,payload FROM checkpoint WHERE id=1').fetchone()
        return revision, json.loads(payload)

    def lookup(self, table: str, cycle: int) -> dict | None:
        if table not in ('forecasts', 'outcomes'):
            raise ValueError('Unknown ledger.')
        row = self.connection.execute(f'SELECT payload FROM {table} WHERE cycle=?', (cycle,)).fetchone()
        return json.loads(row[0]) if row else None

    def commit(self, expected_revision: int, state: dict, *,
               forecast: dict | None = None, outcome: dict | None = None) -> int:
        payload = encode(state)  # Validate finite JSON before opening the transaction.
        self.connection.execute('BEGIN IMMEDIATE')
        try:
            cursor = self.connection.execute(
                'UPDATE checkpoint SET revision=revision+1,payload=? WHERE id=1 AND revision=?',
                (payload, expected_revision))
            if cursor.rowcount != 1:
                raise RuntimeError('Stale writer: state reloaded; retry the operation.')
            if forecast is not None:
                self.connection.execute('INSERT INTO forecasts VALUES(?,?)',
                                        (forecast['cycle'], encode(forecast)))
            if outcome is not None:
                self.connection.execute('INSERT INTO outcomes VALUES(?,?)',
                                        (outcome['cycle'], encode(outcome)))
            self.connection.execute('COMMIT')
        except BaseException:
            self.connection.execute('ROLLBACK')
            raise
        return expected_revision + 1

    def close(self) -> None:
        self.connection.close()
