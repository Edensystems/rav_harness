from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from config import settings

_engine_kwargs = {"pool_pre_ping": True}
if settings.database_url.startswith("postgresql"):
    _engine_kwargs.update({"pool_size": 10, "max_overflow": 20})

engine = create_engine(settings.database_url, **_engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    from models import ActionRate, ActionToggle, CreditLedger, ListItem, TaskOutput, User, UserList, UserSession  # noqa: F401

    Base.metadata.create_all(bind=engine)
