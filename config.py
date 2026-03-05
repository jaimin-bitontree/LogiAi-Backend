from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    MONGODB_URI:        str
    DB_NAME:            str
    GMAIL_ADDRESS:      str
    GMAIL_APP_PASSWORD: str
    IMAP_GMAIL:        str
    IMAP_PORT:         int
<<<<<<< HEAD
    GROQ_API_KEY:                  str
    LANGUAGE_CONFIDENCE_THRESHOLD: float = 0.85
    LANGUAGE_DETECT_MODEL:         str   = "llama-3.1-8b-instant"
    LANGUAGE_TRANSLATE_MODEL:      str   = "llama-3.3-70b-versatile"

=======
    API_BASE_URL:      str = "http://localhost:8000"
>>>>>>> 139d472 (added conversional id and fix bugs)

    class Config:
        env_file = ".env"


settings = Settings()
