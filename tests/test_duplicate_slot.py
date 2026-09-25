from datetime import date, time, timedelta

import pytest
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from app.models.slots import Slot
from app.models.zones import Zone


def test_unique_zone_id_and_start_at_rejects_a_duplicate_slot(
    acceptance_engine: Engine,
) -> None:
    with Session(acceptance_engine) as session:
        zone = Zone(name="Duplicate Slot Zone")
        session.add(zone)
        session.flush()
        assert zone.id is not None
        slot_date = date.today() + timedelta(days=1)
        session.add(
            Slot(
                zone_id=zone.id,
                capacity=5,
                date=slot_date,
                start_at=time(9),
                stop_at=time(11),
            )
        )
        session.commit()

        session.add(
            Slot(
                zone_id=zone.id,
                capacity=5,
                date=slot_date,
                start_at=time(9),
                stop_at=time(12),
            )
        )

        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
