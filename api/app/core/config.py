from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/skwata"
    APP_ENV: str = "dev"
    ADMIN_RESET_TOKEN: str = "change-me"
    WHATSAPP_TOKEN: str = ""
    WHATSAPP_PHONE_ID: str = ""
    PSP_PROVIDER: str = "mock"            # mock | tingg
    TINGG_ACCESS_KEY: str = ""
    TINGG_IV_KEY: str = ""
    TINGG_SECRET_KEY: str = ""
    TINGG_SERVICE_CODE: str = ""
    TINGG_COUNTRY_CODE: str = "BWA"
    TINGG_CURRENCY_CODE: str = "BWP"
    TINGG_EXPRESS_URL: str = "https://checkout.sandbox.tingg.africa/express/checkout"
    PUBLIC_BASE_URL: str = "http://localhost:8000"

    model_config = SettingsConfigDict(env_file=".env")

settings = Settings()