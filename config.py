from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    MONGODB_URI:        str
    DB_NAME:            str
    GMAIL_ADDRESS:      str
    GMAIL_APP_PASSWORD: str
    IMAP_GMAIL:        str
    IMAP_PORT:         int
    GROQ_API_KEY:                  str
    LANGUAGE_CONFIDENCE_THRESHOLD: float = 0.85
    LANGUAGE_DETECT_MODEL:         str   
    LANGUAGE_TRANSLATE_MODEL:      str


    class Config:
        env_file = ".env"


settings = Settings()
