from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    slack_bot_token: str = ""
    slack_app_token: str = ""
    slack_signing_secret: str = ""

    youtube_api_key: str = ""

    openai_api_key: str = ""
    openai_model: str = "gpt-4o"

    podcastfy_tts_model: str = "openai"

    google_service_account_file: str = ""
    google_drive_folder_id: str = ""
    google_oauth_client_file: str = ""
    google_oauth_token_file: str = "credentials/google-oauth-token.json"

    notion_token: str = ""
    notion_parent_page_id: str = ""

    demo_mode: bool = False
    force_regenerate: bool = False

    data_dir: Path = Path("./data")
    request_timeout_seconds: float = 60
    llm_timeout_seconds: float = 180
    podcastfy_timeout_seconds: float = 600
    max_videos: int = 5
    llm_concurrency: int = 4

    @property
    def jobs_dir(self) -> Path:
        path = self.data_dir / "jobs"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def cache_dir(self) -> Path:
        path = self.data_dir / "cache"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def audio_dir(self) -> Path:
        path = self.data_dir / "audio"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def transcripts_dir(self) -> Path:
        path = self.data_dir / "transcripts"
        path.mkdir(parents=True, exist_ok=True)
        return path


settings = Settings()
