from pydantic import BaseModel, ConfigDict, Field

from app.schemas.order import GarmentType


class PriceListUpdate(BaseModel):
    garment: GarmentType
    unit_price: int = Field(gt=0)


class PriceListOut(PriceListUpdate):
    id: int

    model_config = ConfigDict(from_attributes=True)
