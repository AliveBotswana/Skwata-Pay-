from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/skwata"
    APP_ENV: str = "dev"
    ADMIN_RESET_TOKEN: str = "change-me"
    WHATSAPP_TOKEN: str = ""
    WHATSAPP_PHONE_ID: str = ""

    class Config:
        env_file = ".env"

settings = Settings()