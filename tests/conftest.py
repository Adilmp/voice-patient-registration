import os
import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("SEED_DATA", "false")

from app.database import Base, get_db  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture()
def client():
    """A TestClient wired to a fresh, isolated SQLite file per test."""
    db_fd, db_path = tempfile.mkstemp(suffix=".db")
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    engine.dispose()
    os.close(db_fd)
    os.remove(db_path)


VALID_PATIENT = {
    "first_name": "Alice",
    "last_name": "Nguyen",
    "date_of_birth": "03/15/1992",
    "sex": "Female",
    "phone_number": "212-555-0100",
    "address_line_1": "10 Test Ave",
    "city": "Brooklyn",
    "state": "ny",
    "zip_code": "11201",
}
