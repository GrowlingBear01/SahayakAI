import hashlib
import json
import secrets
import sqlite3
import time
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any


APPROVAL_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def canonical_payload(payload: dict[str, Any]) -> str:
    normalized = {key: str(payload[key]).strip() for key in sorted(payload)}
    return json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))


def payload_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_payload(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class SubmissionResult:
    ok: bool
    reason: str | None = None
    reference_number: str | None = None


class MockStore:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = str(database_path)
        self._schema_lock = Lock()
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._schema_lock, closing(self._connect()) as connection:
            with connection:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS tokens (
                        token TEXT PRIMARY KEY,
                        task_id TEXT NOT NULL,
                        payload_hash TEXT NOT NULL,
                        created_at INTEGER NOT NULL,
                        expires_at INTEGER NOT NULL,
                        used_at INTEGER,
                        revoked_at INTEGER,
                        revoke_reason TEXT
                    );
                    CREATE UNIQUE INDEX IF NOT EXISTS one_active_per_task
                        ON tokens(task_id)
                        WHERE used_at IS NULL AND revoked_at IS NULL;
                    CREATE TABLE IF NOT EXISTS submissions (
                        id INTEGER PRIMARY KEY,
                        token TEXT UNIQUE NOT NULL,
                        task_id TEXT NOT NULL,
                        payload_hash TEXT NOT NULL,
                        reference_number TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );
                    """
                )

    def issue_token(
        self, task_id: str, payload: dict[str, Any], ttl_seconds: int = 180
    ) -> str:
        now = int(time.time())
        token = "".join(secrets.choice(APPROVAL_ALPHABET) for _ in range(8))
        with closing(self._connect()) as connection:
            with connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """
                    UPDATE tokens
                    SET revoked_at = ?, revoke_reason = 'superseded'
                    WHERE task_id = ? AND used_at IS NULL AND revoked_at IS NULL
                    """,
                    (now, task_id),
                )
                connection.execute(
                    """
                    INSERT INTO tokens (
                        token, task_id, payload_hash, created_at, expires_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (token, task_id, payload_hash(payload), now, now + ttl_seconds),
                )
        return token

    def submit(
        self, token: str, approval_code: str, payload: dict[str, Any]
    ) -> SubmissionResult:
        now = int(time.time())
        with closing(self._connect()) as connection:
            with connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT * FROM tokens WHERE token = ?", (token,)
                ).fetchone()
                if row is None:
                    return SubmissionResult(False, "invalid_token")
                if row["used_at"] is not None:
                    return SubmissionResult(False, "token_already_used")
                if row["revoked_at"] is not None:
                    return SubmissionResult(False, "token_revoked")
                if row["expires_at"] <= now:
                    return SubmissionResult(False, "token_expired")
                if not secrets.compare_digest(token, approval_code):
                    return SubmissionResult(False, "invalid_approval_code")
                if row["payload_hash"] != payload_hash(payload):
                    return SubmissionResult(False, "payload_mismatch")

                reference = f"DEMO-{secrets.token_hex(4).upper()}"
                created_at = str(now)
                connection.execute(
                    """
                    INSERT INTO submissions (
                        token, task_id, payload_hash, reference_number, created_at
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (token, row["task_id"], row["payload_hash"], reference, created_at),
                )
                connection.execute(
                    "UPDATE tokens SET used_at = ? WHERE token = ?", (now, token)
                )
                return SubmissionResult(True, reference_number=reference)

    def submission_count(self) -> int:
        with closing(self._connect()) as connection:
            return int(
                connection.execute("SELECT COUNT(*) FROM submissions").fetchone()[0]
            )
