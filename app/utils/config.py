from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr

class Settings(BaseSettings):
    DATABASE_URL: str
    SQL_ECHO: bool = False
    REDIS_URL: str | None = None
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_SECONDS: int = 3600


    PAYSTACK_SECRET_KEY: SecretStr
    PAYSTACK_BASE_URL: str = "https://api.paystack.co"
    PAYSTACK_CALLBACK_URL: str | None = None
    PAYSTACK_CURRENCY: str = "NGN"


    OPS_MANAGER_NAME: str = "WashWagon Ops"
    OPS_MANAGER_EMAIL: str = "manager@washwagon.com"
    OPS_MANAGER_PASSWORD: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()
