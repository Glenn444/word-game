from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    SECRET_KEY : str  # Change this in production!
    ALGORITHM : str
    SESSION_COOKIE_NAME :str
    SESSION_EXPIRY_DAYS: int
    DBNAME :str
    DBSER:str
    DBPASSWORD :str
    DBHOST :str
    ENVIRONMENT:str
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


Config = Settings()