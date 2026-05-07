from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openrouter_api_key: str
    default_model: str = "meta-llama/llama-3.3-70b-instruct:free"


settings = Settings()  # type: ignore[call-arg]
