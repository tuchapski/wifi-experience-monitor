import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ServerSettings:
    database_url: str
    recording_storage_root: Path
    enrollment_token: str | None
    agent_offline_after_seconds: float
    telemetry_retention_hours: int

    @classmethod
    def from_environment(cls) -> "ServerSettings":
        database_url = os.getenv("SERVER_DATABASE_URL")
        if not database_url:
            raise RuntimeError("SERVER_DATABASE_URL is required")

        storage_root = Path(
            os.getenv("WEM_RECORDING_STORAGE_ROOT", "./storage/recordings")
        ).expanduser()
        enrollment_token = os.getenv("SERVER_ENROLLMENT_TOKEN")
        offline_after = float(os.getenv("SERVER_AGENT_OFFLINE_AFTER_SECONDS", "15"))
        telemetry_retention_hours = int(os.getenv("SERVER_TELEMETRY_RETENTION_HOURS", "24"))

        if offline_after <= 0:
            raise ValueError("SERVER_AGENT_OFFLINE_AFTER_SECONDS must be greater than zero")
        if telemetry_retention_hours <= 0:
            raise ValueError("SERVER_TELEMETRY_RETENTION_HOURS must be greater than zero")

        return cls(
            database_url=database_url,
            recording_storage_root=storage_root,
            enrollment_token=enrollment_token,
            agent_offline_after_seconds=offline_after,
            telemetry_retention_hours=telemetry_retention_hours,
        )
