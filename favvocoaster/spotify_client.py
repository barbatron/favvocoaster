"""Spotify API client wrapper for FavvoCoaster."""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import spotipy
from spotipy.oauth2 import SpotifyOAuth

from .config import SpotifySettings
from .models import Artist, Track

logger = logging.getLogger(__name__)

# Required Spotify scopes for the application
REQUIRED_SCOPES = [
    "user-library-read",  # Read liked songs
    "user-read-playback-state",  # Read current playback
    "user-modify-playback-state",  # Add to queue
    "user-read-currently-playing",  # Read currently playing
]


class SpotifyClient:
    """Wrapper around spotipy for FavvoCoaster operations."""

    def __init__(self, settings: SpotifySettings, cache_path: Optional[Path] = None):
        """Initialize the Spotify client.

        Args:
            settings: Spotify API configuration.
            cache_path: Path to store OAuth token cache.
        """
        self.settings = settings
        self._cache_path = cache_path or Path(".spotify_cache")

        auth_manager = SpotifyOAuth(
            client_id=settings.client_id,
            client_secret=settings.client_secret,
            redirect_uri=settings.redirect_uri,
            scope=" ".join(REQUIRED_SCOPES),
            cache_path=str(self._cache_path),
            open_browser=True,
        )

        self._client = spotipy.Spotify(auth_manager=auth_manager)
        self._user_id: Optional[str] = None

    @property
    def user_id(self) -> str:
        """Get the current user's Spotify ID."""
        if self._user_id is None:
            user_info = self._client.current_user()
            self._user_id = user_info["id"]
        return self._user_id

    def get_liked_songs(self, limit: int = 50, offset: int = 0) -> list[Track]:
        """Fetch user's liked songs.

        Args:
            limit: Maximum number of tracks to return (max 50).
            offset: Index of first track to return.

        Returns:
            List of Track objects.
        """
        results = self._client.current_user_saved_tracks(limit=limit, offset=offset)
        return [self._parse_saved_track(item) for item in results.get("items", [])]

    def get_all_liked_songs(self, max_tracks: int = 500) -> list[Track]:
        """Fetch all user's liked songs up to a limit.

        Args:
            max_tracks: Maximum number of tracks to fetch.

        Returns:
            List of Track objects.
        """
        tracks: list[Track] = []
        offset = 0
        batch_size = 50

        while offset < max_tracks:
            batch = self.get_liked_songs(limit=batch_size, offset=offset)
            if not batch:
                break
            tracks.extend(batch)
            offset += batch_size
            logger.debug(f"Fetched {len(tracks)} liked songs so far...")

        return tracks[:max_tracks]

    def get_recently_liked_songs(self, count: int = 10) -> list[Track]:
        """Get the most recently liked songs.

        Args:
            count: Number of recent songs to fetch.

        Returns:
            List of Track objects, most recent first.
        """
        return self.get_liked_songs(limit=min(count, 50))

    def get_artist_top_tracks(
        self, artist_id: str, limit: int = 1, country: str = "US"
    ) -> list[Track]:
        """Get an artist's top tracks.

        Args:
            artist_id: Spotify artist ID.
            limit: Maximum number of tracks to return.
            country: Country code for market.

        Returns:
            List of Track objects.
        """
        try:
            results = self._client.artist_top_tracks(artist_id, country=country)
            tracks = [
                self._parse_track(item) for item in results.get("tracks", [])[:limit]
            ]
            return tracks
        except Exception as e:
            logger.error(f"Failed to get top tracks for artist {artist_id}: {e}")
            return []

    def add_to_queue(self, track_uri: str) -> bool:
        """Add a track to the user's playback queue.

        Args:
            track_uri: Spotify track URI.

        Returns:
            True if successful, False otherwise.
        """
        try:
            self._client.add_to_queue(track_uri)
            logger.info(f"Added to queue: {track_uri}")
            return True
        except spotipy.SpotifyException as e:
            if e.http_status == 404:
                logger.warning(
                    "No active device found. Cannot add to queue. "
                    "Make sure Spotify is playing on a device."
                )
            else:
                logger.error(f"Failed to add to queue: {e}")
            return False

    def add_tracks_to_queue(self, track_uris: list[str]) -> int:
        """Add multiple tracks to the playback queue.

        Args:
            track_uris: List of Spotify track URIs.

        Returns:
            Number of tracks successfully added.
        """
        added = 0
        for uri in track_uris:
            if self.add_to_queue(uri):
                added += 1
        return added

    def get_current_playback(self) -> Optional[dict]:
        """Get information about the user's current playback.

        Returns:
            Playback info dict or None if nothing playing.
        """
        return self._client.current_playback()

    def is_playing(self) -> bool:
        """Check if user has an active playback session.

        Returns:
            True if playing, False otherwise.
        """
        playback = self.get_current_playback()
        return playback is not None and playback.get("is_playing", False)

    def _parse_saved_track(self, item: dict) -> Track:
        """Parse a saved track item from Spotify API response.

        Args:
            item: Raw API response item.

        Returns:
            Parsed Track object.
        """
        track_data = item["track"]
        added_at = None
        if "added_at" in item:
            try:
                added_at = datetime.fromisoformat(
                    item["added_at"].replace("Z", "+00:00")
                )
            except (ValueError, TypeError):
                pass

        return Track(
            id=track_data["id"],
            name=track_data["name"],
            uri=track_data["uri"],
            artists=[self._parse_artist(a) for a in track_data["artists"]],
            added_at=added_at,
        )

    def _parse_track(self, track_data: dict) -> Track:
        """Parse a track from Spotify API response.

        Args:
            track_data: Raw API track data.

        Returns:
            Parsed Track object.
        """
        return Track(
            id=track_data["id"],
            name=track_data["name"],
            uri=track_data["uri"],
            artists=[self._parse_artist(a) for a in track_data["artists"]],
        )

    def _parse_artist(self, artist_data: dict) -> Artist:
        """Parse an artist from Spotify API response.

        Args:
            artist_data: Raw API artist data.

        Returns:
            Parsed Artist object.
        """
        return Artist(
            id=artist_data["id"],
            name=artist_data["name"],
            uri=artist_data["uri"],
        )
