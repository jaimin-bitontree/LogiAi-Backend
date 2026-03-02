from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    MONGODB_URI: str = "mongodb://localhost:27017"
    DB_NAME:     str = "logiai_db"

    class Config:
        env_file = ".env"


settings = Settings()
