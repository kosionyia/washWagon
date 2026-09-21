
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from app.models.user import Role



class User(BaseModel):
    name: str = Field(max_length=125)
    email: EmailStr


class UserRegister(User):
    zone: str = Field(min_length=1, max_length=25)
    password: str = Field(min_length=8)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(User):
    id: int
    role: Role = Role.CUSTOMER

    model_config = ConfigDict(from_attributes=True)
    
class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
