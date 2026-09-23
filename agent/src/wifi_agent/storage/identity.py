import os
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True, slots=True)
class AgentIdentity:
    agent_id: str
    agent_token: str
    server_url: str
    enrolled_at: datetime


class AgentIdentityStore:
    def __init__(self, database_path: Path):
        self.database_path = database_path

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(self.database_path.parent, 0o700)

        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS agent_identity (
                    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                    agent_id TEXT NOT NULL,
                    agent_token TEXT NOT NULL,
                    server_url TEXT NOT NULL,
                    enrolled_at TEXT NOT NULL
                )
                """
            )
            connection.commit()

        os.chmod(self.database_path, 0o600)

    def load(self) -> AgentIdentity | None:
        with sqlite3.connect(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT agent_id, agent_token, server_url, enrolled_at
                FROM agent_identity
                WHERE singleton = 1
                """
            ).fetchone()

        if row is None:
            return None

        return AgentIdentity(
            agent_id=row[0],
            agent_token=row[1],
            server_url=row[2],
            enrolled_at=datetime.fromisoformat(row[3]),
        )

    def save(self, identity: AgentIdentity) -> None:
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO agent_identity (
                    singleton,
                    agent_id,
                    agent_token,
                    server_url,
                    enrolled_at
                ) VALUES (1, ?, ?, ?, ?)
                ON CONFLICT(singleton) DO UPDATE SET
                    agent_id = excluded.agent_id,
                    agent_token = excluded.agent_token,
                    server_url = excluded.server_url,
                    enrolled_at = excluded.enrolled_at
                """,
                (
                    identity.agent_id,
                    identity.agent_token,
                    identity.server_url,
                    identity.enrolled_at.isoformat(),
                ),
            )
            connection.commit()

    def clear(self) -> None:
        with sqlite3.connect(self.database_path) as connection:
            connection.execute("DELETE FROM agent_identity WHERE singleton = 1")
            connection.commit()
