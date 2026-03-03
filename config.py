from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    MONGODB_URI:        str
    DB_NAME:            str
    GMAIL_ADDRESS:      str
    GMAIL_APP_PASSWORD: str
    IMAP_GMAIL:        str
    IMAP_PORT:         int

    class Config:
        env_file = ".env"


settings = Settings()
