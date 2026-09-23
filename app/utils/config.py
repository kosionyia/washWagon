from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str | None = None
    REDIS_URL: str | None = None
    SECRET_KEY: str | None = None
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_SECONDS: int = 3600
    WEBHOOK_SECRET: str = "washwagon"

    OPS_MANAGER_NAME: str = "WashWagon Ops"
    OPS_MANAGER_EMAIL: str = "manager@washwagon.com"
    OPS_MANAGER_PASSWORD: str = "washwagon26"

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()
