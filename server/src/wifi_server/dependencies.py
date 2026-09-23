from collections.abc import Generator
from functools import lru_cache

from sqlalchemy.orm import Session

from wifi_server.config import ServerSettings
from wifi_server.db.session import ServerDatabase


@lru_cache
def get_settings() -> ServerSettings:
    return ServerSettings.from_environment()


@lru_cache
def get_database() -> ServerDatabase:
    return ServerDatabase(get_settings())


def get_session() -> Generator[Session, None, None]:
    session = get_database().session()
    try:
        yield session
    finally:
        session.close()
