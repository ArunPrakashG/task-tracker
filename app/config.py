from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str
    redis_url: str = "redis://localhost:6379/0"
    rate_limit_requests: int = 30
    rate_limit_window_seconds: int = 60

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
