from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime config, read from .env. Nothing is hardcoded elsewhere."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite+aiosqlite:///:memory:"

    # Required — no default, so a missing key fails at startup, not mid-request.
    vonk_key: str
    vonk_base_url: str = "http://vonk:4000/v1"
    vonk_model: str = "code"
    vonk_embed_model: str = "embedding"
    # Draws the report's images. image-fast keeps a 6-section report under a minute or two.
    vonk_image_model: str = "image-fast"
    image_size: str = "1280x720"
    # Where generated images are cached (a docker volume in compose).
    image_dir: str = "/data/gen"

    # Concept expansion: related concepts asked per node, and vonk calls in flight while
    # a graph streams (the graph stream runs in the API, not as a job).
    concepts_per_node: int = 5
    graph_concurrency: int = 8

    # The report: one section per top-ranked branch of the seed.
    report_max_sections: int = 6
    # Default language of the report text (image prompts are always English).
    report_language: str = "English"
    # Images drawn at once; image models are slower and heavier than chat.
    image_concurrency: int = 2

    # The one key that opens the site (services/access.py). Empty: no login, for local dev only.
    access_key: str = ""

    cors_origins: str = "*"

    # Background jobs (app/services/jobs.py). False: the `worker` container runs them.
    # True: this API process runs them itself and the worker container stays idle.
    jobs_inline: bool = False
    max_concurrent_jobs: int = 2
    # vonk requests in flight at once, across all running jobs.
    generation_concurrency: int = 4

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
