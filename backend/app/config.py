from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    public_base_url: str = "https://xxxx.example.ru"

    gigachat_auth_key: str = ""
    gigachat_scope: str = "GIGACHAT_API_PERS"
    gigachat_token_url: str = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
    gigachat_chat_url: str = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
    gigachat_verify_ssl: bool = False
    gigachat_model: str = "GigaChat"

    bitrix_webhook_url: str = ""
    default_manager_id: int = 1

    dealer_working_hours: str = "09:00-21:00"
    manager_response_sla_minutes: int = 15
    chroma_path: str = "data/chroma"
    chroma_collection_name: str = "autosales_faq"


settings = Settings()
