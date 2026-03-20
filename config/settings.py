from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    MONGODB_URI:        str
    DB_NAME:            str
    GMAIL_ADDRESS:      str
    GMAIL_TOKEN_JSON:   str  # OAuth2 token JSON string

    GEMINI_API_KEY:    str
    LANGUAGE_CONFIDENCE_THRESHOLD: float = 0.85
    LANGUAGE_DETECT_MODEL:         str   = "gemini-2.5-flash"
    LANGUAGE_TRANSLATE_MODEL:      str   = "gemini-2.5-flash"
    EXTRACTION_MODEL:              str   = "gemini-2.5-flash"

    OPERATOR_EMAIL:    str = ""
    SYSTEM_EMAIL:      str

    CLOUDINARY_CLOUD_NAME:  str
    CLOUDINARY_API_KEY:     str
    CLOUDINARY_API_SECRET:  str

    API_BASE_URL:       str = "http://localhost:8000"
    FRONTEND_URL:       str = "http://localhost:5173"
    JWT_SECRET_KEY:     str
    JWT_EXPIRE_MINUTES: int = 1440

    class Config:
        env_file = ".env"


settings = Settings()
