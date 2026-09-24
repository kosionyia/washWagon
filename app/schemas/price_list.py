from pydantic import BaseModel, Field

from app.schemas.order import GarmentType


class CreatePrice(BaseModel):
    garment: GarmentType
    unit_price: int = Field(
        gt=0,
        description="Price in Kobo",
        )


class UpdatePrice(BaseModel):
    unit_price: int = Field(
        gt=0,
        description="Price in Kobo",

        )


class PriceOut(BaseModel):
    id: int
    garment: GarmentType
    unit_price: int = Field(
        description='Price in Kobo',
    )
