from fastapi.testclient import TestClient
from sqlalchemy.engine import Engine

from app.schemas.order import GarmentType
from tests.test_helpers import authorization, order_payload, seed_booking_data


def test_price_equals_item_quantities_times_price_list(
    acceptance_client: TestClient,
    acceptance_engine: Engine,
) -> None:
    shirt_price = 150_000
    jean_price = 200_000
    slot_id, customers = seed_booking_data(
        acceptance_engine,
        prices={
            GarmentType.SHIRT: shirt_price,
            GarmentType.JEAN: jean_price,
        },
    )
    items = [
        {"garment": "shirt", "quantity": 2},
        {"garment": "jean", "quantity": 3},
    ]

    response = acceptance_client.post(
        "/orders/",
        json=order_payload(slot_id, items),
        headers=authorization(customers[0]),
    )

    assert response.status_code == 201
    assert response.json()["total"] == (2 * shirt_price) + (3 * jean_price)
