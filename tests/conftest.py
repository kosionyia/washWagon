from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

import app.models  # noqa: F401 -- registers every table
from app.main import app
from app.utils.database import get_session


@pytest.fixture
def acceptance_engine(tmp_path) -> Generator[Engine, None, None]:
    database = tmp_path / "acceptance.db"
    engine = create_engine(
        f"sqlite:///{database}",
        connect_args={"check_same_thread": False, "timeout": 10},
    )
    SQLModel.metadata.create_all(engine)
    yield engine
    SQLModel.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def acceptance_client(
    acceptance_engine: Engine,
) -> Generator[TestClient, None, None]:
    def test_session() -> Generator[Session, None, None]:
        with Session(acceptance_engine) as session:
            yield session

    app.dependency_overrides[get_session] = test_session
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()
