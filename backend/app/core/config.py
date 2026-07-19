from typing import List
from pydantic_settings import BaseSettings
from pydantic import Field, model_validator

DEFAULT_SECRET_KEY = "change-this-secret-key-in-production"


class Settings(BaseSettings):
    APP_NAME: str = Field(default="Drilling Analysis API")
    APP_VERSION: str = Field(default="1.0.0")
    DEBUG: bool = Field(default=False)
    ENVIRONMENT: str = Field(default="production")
    HOST: str = Field(default="0.0.0.0")
    PORT: int = Field(default=8000)

    # PostgreSQL database
    DATABASE_URL: str = Field(default="postgresql://postgres:postgres@localhost:5432/drilling_db")

    REDIS_HOST: str = Field(default="localhost")
    REDIS_PORT: int = Field(default=6379)
    REDIS_DB: int = Field(default=0)

    CORS_ORIGINS: List[str] = Field(
        default=[
            "http://localhost:3000",
            "http://localhost:5173",
            "http://localhost:5174",
            "http://127.0.0.1:5173",
            "http://127.0.0.1:5174",
            "http://127.0.0.1:64710",
            "http://localhost:64710",
            "https://drilling-frontend.onrender.com",
            "https://drilling-data-visualization-frontend.onrender.com",
            "https://drilling-data-visualization.onrender.com",
        ]
    )

    SECRET_KEY: str = Field(default=DEFAULT_SECRET_KEY)
    ALGORITHM: str = Field(default="HS256")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=30)
    LOG_LEVEL: str = Field(default="INFO")
    MAX_QUERY_LIMIT: int = Field(default=100000)
    DEFAULT_QUERY_LIMIT: int = Field(default=10000)

    @model_validator(mode="after")
    def check_secret_key_in_production(self) -> "Settings":
        if self.ENVIRONMENT == "production" and not self.DEBUG and self.SECRET_KEY == DEFAULT_SECRET_KEY:
            raise ValueError(
                "SECRET_KEY must be set via environment variable in production; "
                "refusing to start with the default placeholder key"
            )
        return self

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()
