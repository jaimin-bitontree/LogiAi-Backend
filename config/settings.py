from pydantic_settings import BaseSettings
import os

class Settings(BaseSettings):
    MONGODB_URI:        str
    DB_NAME:            str
    GMAIL_ADDRESS:      str
    GMAIL_APP_PASSWORD: str
    IMAP_GMAIL:        str
    IMAP_PORT:         int
    GROQ_API_KEY:                  str
    GROQ_API_KEY_2:                str 
    GROQ_API_KEY_3:                str 
    LANGUAGE_CONFIDENCE_THRESHOLD: float 
    LANGUAGE_DETECT_MODEL:         str   
    LANGUAGE_TRANSLATE_MODEL:      str   
    EXTRACTION_MODEL:              str   
    SMTP_HOST:                     str   
    SMTP_PORT:                     int   
    OPERATOR_EMAIL:                str   
    SYSTEM_EMAIL:                  str

    CLOUDINARY_CLOUD_NAME:          str
    CLOUDINARY_API_KEY:             str
    CLOUDINARY_API_SECRET:          str

    

    class Config:
        env_file = ".env"


settings = Settings()

# Build list of available API keys
GROQ_API_KEYS = [settings.GROQ_API_KEY]
if settings.GROQ_API_KEY_2:
    GROQ_API_KEYS.append(settings.GROQ_API_KEY_2)
if settings.GROQ_API_KEY_3:
    GROQ_API_KEYS.append(settings.GROQ_API_KEY_3)

