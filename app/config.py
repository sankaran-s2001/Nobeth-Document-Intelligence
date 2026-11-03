import os
from pathlib import Path
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Load .env file from project root
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")


class AppConfig(BaseModel):
    # Gemini AI Configuration
    gemini_api_key: str = Field(default_factory=lambda: os.getenv("GEMINI_API_KEY", "").strip())
    gemini_primary_model: str = Field(
        default_factory=lambda: os.getenv("GEMINI_PRIMARY_MODEL", "gemini-3.5-flash-lite").strip()
    )
    gemini_fallback_model: str = Field(
        default_factory=lambda: os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.1-flash-lite").strip()
    )
    gemini_data_mode: str = Field(
        default_factory=lambda: os.getenv("GEMINI_DATA_MODE", "unknown").strip().lower()
    )

    # Server
    host: str = Field(default_factory=lambda: os.getenv("HOST", "127.0.0.1").strip())
    port: int = Field(default_factory=lambda: int(os.getenv("PORT", "8000")))

    # Security & Resource Limits
    max_upload_mb: int = Field(default_factory=lambda: int(os.getenv("MAX_UPLOAD_MB", "25")))
    max_files_per_job: int = Field(default_factory=lambda: int(os.getenv("MAX_FILES_PER_JOB", "10")))
    max_pdf_pages: int = Field(default_factory=lambda: int(os.getenv("MAX_PDF_PAGES", "50")))
    max_image_pixels: int = Field(default_factory=lambda: int(os.getenv("MAX_IMAGE_PIXELS", "40000000")))
    max_docx_images: int = Field(default_factory=lambda: int(os.getenv("MAX_DOCX_IMAGES", "100")))
    max_concurrent_jobs: int = Field(default_factory=lambda: int(os.getenv("MAX_CONCURRENT_JOBS", "2")))
    job_retention_hours: int = Field(default_factory=lambda: int(os.getenv("JOB_RETENTION_HOURS", "24")))
    open_browser: bool = Field(
        default_factory=lambda: os.getenv("OPEN_BROWSER", "true").strip().lower() in ("true", "1", "yes")
    )

    # Storage Paths
    base_dir: Path = BASE_DIR
    data_dir: Path = BASE_DIR / "data"
    jobs_dir: Path = BASE_DIR / "data" / "jobs"
    db_path: Path = BASE_DIR / "data" / "nobeth_doc_intel.db"
    static_dir: Path = BASE_DIR / "app" / "static"
    templates_dir: Path = BASE_DIR / "app" / "templates"
    fonts_dir: Path = BASE_DIR / "app" / "static" / "assets" / "fonts"

    def ensure_directories(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.fonts_dir.mkdir(parents=True, exist_ok=True)


config = AppConfig()
config.ensure_directories()

