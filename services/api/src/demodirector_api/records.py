"""Append-only workflow snapshots with compare-and-swap transitions."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Protocol

from google.cloud import firestore


class RecordConflict(ValueError):
    pass


class RecordStore(Protocol):
    def get(self, key: str) -> tuple[int, dict[str, Any]] | None: ...

    def put(self, key: str, expected: int, payload: dict[str, Any]) -> int: ...


class SQLiteRecordStore:
    def __init__(self, database: Path) -> None:
        self.database = database
        database.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(database) as connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS workflow_records "
                "(key TEXT, version INTEGER, payload TEXT, PRIMARY KEY(key, version))"
            )

    def get(self, key: str) -> tuple[int, dict[str, Any]] | None:
        with sqlite3.connect(self.database) as connection:
            row = connection.execute(
                "SELECT version, payload FROM workflow_records WHERE key=? "
                "ORDER BY version DESC LIMIT 1",
                (key,),
            ).fetchone()
        return None if row is None else (row[0], json.loads(row[1]))

    def put(self, key: str, expected: int, payload: dict[str, Any]) -> int:
        with sqlite3.connect(self.database, timeout=30) as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = (
                connection.execute(
                    "SELECT MAX(version) FROM workflow_records WHERE key=?",
                    (key,),
                ).fetchone()[0]
                or 0
            )
            if current != expected:
                raise RecordConflict("Workflow changed; reload before continuing.")
            connection.execute(
                "INSERT INTO workflow_records VALUES (?, ?, ?)",
                (key, expected + 1, json.dumps(payload)),
            )
        return expected + 1


class FirestoreRecordStore:
    def __init__(self, client: firestore.Client) -> None:
        self.client = client
        self.collection = client.collection("workflow_records")

    def get(self, key: str) -> tuple[int, dict[str, Any]] | None:
        snapshot = self.collection.document(key).get()
        data = snapshot.to_dict() if snapshot.exists else None
        return None if data is None else (int(data["version"]), data["payload"])

    def put(self, key: str, expected: int, payload: dict[str, Any]) -> int:
        reference = self.collection.document(key)

        @firestore.transactional
        def write(transaction: Any) -> int:
            snapshot = reference.get(transaction=transaction)
            current = int((snapshot.to_dict() or {}).get("version", 0))
            if current != expected:
                raise RecordConflict("Workflow changed; reload before continuing.")
            value = {"version": expected + 1, "payload": payload}
            transaction.set(reference, value)
            transaction.create(reference.collection("history").document(str(expected + 1)), value)
            return expected + 1

        return int(write(self.client.transaction()))
