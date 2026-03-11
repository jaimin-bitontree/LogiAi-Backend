from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    MONGODB_URI:        str
    DB_NAME:            str
    GMAIL_ADDRESS:      str
    GMAIL_APP_PASSWORD: str
    IMAP_GMAIL:        str
    IMAP_PORT:         int
    GROQ_API_KEY:                  str
    GROQ_API_KEY_2:                str = ""  # Optional second API key
    GROQ_API_KEY_3:                str = ""  # Optional third API key
    LANGUAGE_CONFIDENCE_THRESHOLD: float = 0.85
    LANGUAGE_DETECT_MODEL:         str   = "llama-3.1-8b-instant"
    LANGUAGE_TRANSLATE_MODEL:      str   = "llama-3.1-8b-instant"
    EXTRACTION_MODEL:              str   = "llama-3.1-8b-instant"
    SMTP_HOST:                     str   = "smtp.gmail.com"
    SMTP_PORT:                     int   = 587
    OPERATOR_EMAIL:                str   = ""
    SYSTEM_EMAIL:                  str

    API_BASE_URL:      str = "http://localhost:8000"

    class Config:
        env_file = ".env"


settings = Settings()

# Build list of available API keys
GROQ_API_KEYS = [settings.GROQ_API_KEY]
if settings.GROQ_API_KEY_2:
    GROQ_API_KEYS.append(settings.GROQ_API_KEY_2)
if settings.GROQ_API_KEY_3:
    GROQ_API_KEYS.append(settings.GROQ_API_KEY_3)

