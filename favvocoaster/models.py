"""Data models for FavvoCoaster."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Artist:
    """Represents a Spotify artist."""

    id: str
    name: str
    uri: str


@dataclass
class Track:
    """Represents a Spotify track."""

    id: str
    name: str
    uri: str
    artists: list[Artist]
    added_at: Optional[datetime] = None

    @property
    def artist_ids(self) -> set[str]:
        """Get set of artist IDs for this track."""
        return {artist.id for artist in self.artists}

    @property
    def artist_names(self) -> list[str]:
        """Get list of artist names for this track."""
        return [artist.name for artist in self.artists]

    @property
    def is_collaboration(self) -> bool:
        """Check if this track has multiple artists."""
        return len(self.artists) > 1


@dataclass
class ScrapeContext:
    """Context passed to scraping rules for evaluation."""

    track: Track
    known_artist_ids: set[str]
    user_id: str
    timestamp: datetime = field(default_factory=datetime.now)


@dataclass
class ScrapeResult:
    """Result of evaluating scraping rules."""

    should_scrape: bool
    reason: str
    artists_to_scrape: list[Artist] = field(default_factory=list)
