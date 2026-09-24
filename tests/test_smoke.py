import os

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SECRET_KEY"] = "test-secret-key"

from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_check() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {
        "message": "washWagon API is running",
    }


def test_openapi_contains_core_routes() -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200

    paths = response.json()["paths"]
    assert {
        "/auth/login",
        "/auth/register",
        "/orders/",
        "/prices/",
        "/slots/",
        "/users/me",
        "/zones/",
    } <= set(paths)
