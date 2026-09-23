import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ServerSettings:
    database_url: str
    recording_storage_root: Path

    @classmethod
    def from_environment(cls) -> "ServerSettings":
        database_url = os.getenv("SERVER_DATABASE_URL")
        if not database_url:
            raise RuntimeError("SERVER_DATABASE_URL is required")

        storage_root = Path(
            os.getenv("WEM_RECORDING_STORAGE_ROOT", "./storage/recordings")
        ).expanduser()

        return cls(
            database_url=database_url,
            recording_storage_root=storage_root,
        )
