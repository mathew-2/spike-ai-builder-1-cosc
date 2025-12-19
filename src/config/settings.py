"""
Configuration module for Spike AI Builder.
Loads environment variables and provides typed configuration access.
"""
import os
from pathlib import Path
from dataclasses import dataclass
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


@dataclass
class LiteLLMConfig:
    """Configuration for LiteLLM API."""
    api_key: str
    base_url: str
    model: str


@dataclass
class GA4Config:
    """Configuration for Google Analytics 4."""
    credentials_path: Path


@dataclass
class SEOConfig:
    """Configuration for SEO data source."""
    spreadsheet_url: str
    spreadsheet_id: str
    credentials_path: Path


@dataclass
class ServerConfig:
    """Configuration for the HTTP server."""
    host: str
    port: int


@dataclass
class AppConfig:
    """Main application configuration."""
    litellm: LiteLLMConfig
    ga4: GA4Config
    seo: SEOConfig
    server: ServerConfig
    log_level: str


def load_config() -> AppConfig:
    """Load and validate configuration from environment variables."""
    
    # Get project root (where credentials.json should be)
    project_root = Path(__file__).parent.parent.parent
    
    return AppConfig(
        litellm=LiteLLMConfig(
            api_key=os.getenv("LITELLM_API_KEY", ""),
            base_url=os.getenv("LITELLM_BASE_URL", "http://3.110.18.218"),
            model=os.getenv("LITELLM_MODEL", "gemini-2.5-flash"),
        ),
        ga4=GA4Config(
            credentials_path=project_root / os.getenv("GA4_CREDENTIALS_PATH", "credentials.json"),
        ),
        seo=SEOConfig(
            spreadsheet_url=os.getenv("SEO_SPREADSHEET_URL", ""),
            spreadsheet_id=os.getenv(
                "SEO_SPREADSHEET_ID",
                "1zzf4ax_H2WiTBVrJigGjF2Q3Yz-qy2qMCbAMKvl6VEE"
            ),
            credentials_path=project_root / os.getenv(
                "SEO_CREDENTIALS_PATH",
                "credentials.json"
            ),
        ),
        server=ServerConfig(
            host=os.getenv("SERVER_HOST", "0.0.0.0"),
            port=int(os.getenv("SERVER_PORT", "8080")),
        ),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
    )


# Global config instance
config = load_config()
