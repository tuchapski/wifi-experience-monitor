from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from wem.profiles.defaults import (
    DEFAULT_PROFILE_DESCRIPTION,
    DEFAULT_PROFILE_NAME,
    default_profile_config,
)
from wem.profiles.models import TestProfileConfig
from wem.storage.models import TestProfileRecord, TestProfileVersionRecord

if TYPE_CHECKING:
    from wem.storage.database import Database


class ProfileError(Exception):
    pass


class ProfileNotFoundError(ProfileError):
    pass


class ProfileVersionNotFoundError(ProfileError):
    pass


class DuplicateProfileNameError(ProfileError):
    pass


class ProfileDisabledError(ProfileError):
    pass


class ActiveProfileDisabledError(ProfileError):
    pass


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class ProfileService:
    def __init__(self, database: "Database") -> None:
        self.database = database

    def ensure_default(self) -> None:
        with self.database.session() as session:
            count = session.scalar(select(func.count()).select_from(TestProfileRecord))
            if count:
                return

            now = _utc_now()
            profile = TestProfileRecord(
                name=DEFAULT_PROFILE_NAME,
                description=DEFAULT_PROFILE_DESCRIPTION,
                enabled=True,
                active_version_id=None,
                created_at=now,
                updated_at=now,
            )
            session.add(profile)
            session.flush()

            version = TestProfileVersionRecord(
                profile_id=profile.id,
                version=1,
                config_json=default_profile_config().model_dump_json(),
                created_at=now,
            )
            session.add(version)
            session.flush()
            profile.active_version_id = version.id
            session.commit()

    def list_profiles(self) -> list[tuple[TestProfileRecord, TestProfileVersionRecord]]:
        with self.database.session() as session:
            profiles = list(
                session.scalars(select(TestProfileRecord).order_by(TestProfileRecord.id))
            )
            return [(profile, self._latest_version(session, profile.id)) for profile in profiles]

    def get(self, profile_id: int) -> tuple[TestProfileRecord, TestProfileVersionRecord]:
        with self.database.session() as session:
            profile = self._profile(session, profile_id)
            return profile, self._latest_version(session, profile.id)

    def active(self) -> tuple[TestProfileRecord, TestProfileVersionRecord]:
        with self.database.session() as session:
            profile = session.scalar(
                select(TestProfileRecord).where(TestProfileRecord.active_version_id.is_not(None))
            )
            if profile is None or profile.active_version_id is None:
                raise ProfileNotFoundError("No active test profile is configured.")
            version = session.get(TestProfileVersionRecord, profile.active_version_id)
            if version is None or version.profile_id != profile.id:
                raise ProfileVersionNotFoundError("The active profile version is unavailable.")
            return profile, version

    def create(
        self,
        *,
        name: str,
        description: str | None,
        enabled: bool,
        config: TestProfileConfig,
    ) -> tuple[TestProfileRecord, TestProfileVersionRecord]:
        now = _utc_now()
        with self.database.session() as session:
            profile = TestProfileRecord(
                name=name,
                description=description,
                enabled=enabled,
                active_version_id=None,
                created_at=now,
                updated_at=now,
            )
            session.add(profile)
            try:
                session.flush()
                version = TestProfileVersionRecord(
                    profile_id=profile.id,
                    version=1,
                    config_json=config.model_dump_json(),
                    created_at=now,
                )
                session.add(version)
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                message = f'A profile named "{name}" already exists.'
                raise DuplicateProfileNameError(message) from exc
            return profile, version

    def update(
        self,
        profile_id: int,
        *,
        name: str,
        description: str | None,
        enabled: bool,
        config: TestProfileConfig,
    ) -> tuple[TestProfileRecord, TestProfileVersionRecord]:
        with self.database.session() as session:
            profile = self._profile(session, profile_id)
            if profile.active_version_id is not None and not enabled:
                raise ActiveProfileDisabledError(
                    "The active profile cannot be disabled; activate another profile first."
                )

            next_version = (
                session.scalar(
                    select(func.max(TestProfileVersionRecord.version)).where(
                        TestProfileVersionRecord.profile_id == profile.id
                    )
                )
                or 0
            ) + 1
            now = _utc_now()
            profile.name = name
            profile.description = description
            profile.enabled = enabled
            profile.updated_at = now
            version = TestProfileVersionRecord(
                profile_id=profile.id,
                version=next_version,
                config_json=config.model_dump_json(),
                created_at=now,
            )
            session.add(version)
            try:
                session.flush()
                if profile.active_version_id is not None:
                    profile.active_version_id = version.id
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                message = f'A profile named "{name}" already exists.'
                raise DuplicateProfileNameError(message) from exc
            return profile, version

    def activate(self, profile_id: int) -> tuple[TestProfileRecord, TestProfileVersionRecord]:
        with self.database.session() as session:
            profile = self._profile(session, profile_id)
            if not profile.enabled:
                raise ProfileDisabledError("A disabled profile cannot be activated.")
            version = self._latest_version(session, profile.id)
            session.execute(update(TestProfileRecord).values(active_version_id=None))
            profile.active_version_id = version.id
            profile.updated_at = _utc_now()
            session.commit()
            return profile, version

    def versions(self, profile_id: int) -> list[TestProfileVersionRecord]:
        with self.database.session() as session:
            self._profile(session, profile_id)
            return list(
                session.scalars(
                    select(TestProfileVersionRecord)
                    .where(TestProfileVersionRecord.profile_id == profile_id)
                    .order_by(TestProfileVersionRecord.version.desc())
                )
            )

    def version(self, profile_id: int, version_number: int) -> TestProfileVersionRecord:
        with self.database.session() as session:
            self._profile(session, profile_id)
            version = session.scalar(
                select(TestProfileVersionRecord).where(
                    TestProfileVersionRecord.profile_id == profile_id,
                    TestProfileVersionRecord.version == version_number,
                )
            )
            if version is None:
                raise ProfileVersionNotFoundError(
                    f"Profile {profile_id} has no version {version_number}."
                )
            return version

    @staticmethod
    def configuration(version: TestProfileVersionRecord) -> TestProfileConfig:
        return TestProfileConfig.model_validate_json(version.config_json)

    @staticmethod
    def _profile(session: Session, profile_id: int) -> TestProfileRecord:
        profile = session.get(TestProfileRecord, profile_id)
        if profile is None:
            raise ProfileNotFoundError(f"Profile {profile_id} was not found.")
        return profile

    @staticmethod
    def _latest_version(session: Session, profile_id: int) -> TestProfileVersionRecord:
        version = session.scalar(
            select(TestProfileVersionRecord)
            .where(TestProfileVersionRecord.profile_id == profile_id)
            .order_by(TestProfileVersionRecord.version.desc())
            .limit(1)
        )
        if version is None:
            raise ProfileVersionNotFoundError(f"Profile {profile_id} has no versions.")
        return version
