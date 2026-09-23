from datetime import date, time
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CreateSlot(BaseModel):
    zone_id: int = Field(gt=0)
    date: date
    start_at: time
    stop_at: time
    capacity: int = Field(default=5, gt=0)

    @model_validator(mode="after")
    def validate_time_range(self) -> Self:
        if self.stop_at <= self.start_at:
            raise ValueError("stop_at must be later than start_at")

        return self


class SlotOut(CreateSlot):
    id: int
    booked_count: int

    model_config = ConfigDict(from_attributes=True)
