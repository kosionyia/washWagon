from typing import Optional

from sqlmodel import SQLModel, Field
from app.schemas.order import GarmentType

class PriceList(SQLModel, table=True):
    
    __tablename__ = "price_list"

    id: Optional[int] = Field(default=None, primary_key=True)
    garment: GarmentType = Field(unique=True, index=True)
    unit_price: int = Field(gt=0)

