from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    MONGODB_URI:        str
    DB_NAME:            str
    GMAIL_ADDRESS:      str
    GMAIL_APP_PASSWORD: str
    IMAP_GMAIL:        str
    IMAP_PORT:         int
    GEMINI_API_KEY:    str
    LANGUAGE_CONFIDENCE_THRESHOLD: float = 0.85
    LANGUAGE_DETECT_MODEL:         str   = "gemini-2.5-flash"
    LANGUAGE_TRANSLATE_MODEL:      str   = "gemini-2.5-flash"
    EXTRACTION_MODEL:              str   = "gemini-2.5-flash"
    SMTP_HOST:                     str   = "smtp.gmail.com"
    SMTP_PORT:                     int   = 587
    
    #GEMINI_API_KEY:                str
    #LANGUAGE_DETECT_MODEL:         str   = "gemini-1.5-flash"
    #LANGUAGE_TRANSLATE_MODEL:      str   = "gemini-1.5-flash"
    #EXTRACTION_MODEL:              str   = "gemini-1.5-pro"
    
    OPERATOR_EMAIL:                str   = ""
    SYSTEM_EMAIL:                  str

    CLOUDINARY_CLOUD_NAME:          str
    CLOUDINARY_API_KEY:             str
    CLOUDINARY_API_SECRET:          str

    API_BASE_URL:      str = "http://localhost:8000"
    JWT_SECRET_KEY:    str
    JWT_EXPIRE_MINUTES: int = 1440

    class Config:
        env_file = ".env"


settings = Settings()

# No need for multiple API keys with Gemini (higher rate limits)

