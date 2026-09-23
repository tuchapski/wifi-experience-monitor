from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from wifi_server.config import ServerSettings


class ServerDatabase:
    def __init__(self, settings: ServerSettings):
        self.engine: Engine = create_engine(
            settings.database_url,
            pool_pre_ping=True,
        )
        self.session_factory = sessionmaker(
            bind=self.engine,
            class_=Session,
            expire_on_commit=False,
        )

    def session(self) -> Session:
        return self.session_factory()
