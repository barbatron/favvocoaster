"""Configuration management for FavvoCoaster."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SpotifySettings(BaseSettings):
    """Spotify API configuration."""

    model_config = SettingsConfigDict(env_prefix="SPOTIFY_")

    client_id: str = Field(description="Spotify App Client ID")
    client_secret: str = Field(description="Spotify App Client Secret")
    redirect_uri: str = Field(
        default="http://localhost:8888/callback",
        description="OAuth redirect URI",
    )


class ScrapingSettings(BaseSettings):
    """Scraping behavior configuration."""

    model_config = SettingsConfigDict(env_prefix="SCRAPE_")

    # Minimum number of artists required to trigger scraping
    min_artists: int = Field(
        default=2,
        description="Minimum number of artists on a track to trigger scraping",
    )

    # Maximum number of top tracks to fetch per artist
    top_tracks_limit: int = Field(
        default=1,
        description="Number of top tracks to fetch per artist",
    )

    # Whether to skip artists already in user's library
    skip_known_artists: bool = Field(
        default=True,
        description="Skip scraping if any artist is already known",
    )

    # Polling interval in seconds
    poll_interval_seconds: int = Field(
        default=30,
        description="How often to check for new liked songs",
    )

    # Maximum liked songs to scan for known artists
    known_artists_scan_limit: int = Field(
        default=500,
        description="How many recent liked songs to scan for known artists",
    )


class AppSettings(BaseSettings):
    """Main application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    spotify: SpotifySettings = Field(default_factory=SpotifySettings)
    scraping: ScrapingSettings = Field(default_factory=ScrapingSettings)

    # Debug mode
    debug: bool = Field(default=False, description="Enable debug logging")


def load_settings() -> AppSettings:
    """Load application settings from environment."""
    return AppSettings()
