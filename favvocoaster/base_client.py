"""Abstract base class for music streaming service clients."""

from abc import ABC, abstractmethod
from typing import Optional

from .models import Artist, Track


class MusicServiceClient(ABC):
    """Abstract interface for music streaming service clients.

    All streaming service implementations (Spotify, Tidal, etc.) should
    implement this interface to work with FavvoCoaster.
    """

    @property
    @abstractmethod
    def service_name(self) -> str:
        """Return the name of this service (e.g., 'Spotify', 'Tidal')."""
        pass

    @property
    @abstractmethod
    def user_id(self) -> str:
        """Get the current user's ID on this service."""
        pass

    @abstractmethod
    def get_liked_songs(self, limit: int = 50, offset: int = 0) -> list[Track]:
        """Fetch user's liked/favorite songs.

        Args:
            limit: Maximum number of tracks to return.
            offset: Index of first track to return.

        Returns:
            List of Track objects.
        """
        pass

    @abstractmethod
    def get_all_liked_songs(self, max_tracks: int = 500) -> list[Track]:
        """Fetch all user's liked songs up to a limit.

        Args:
            max_tracks: Maximum number of tracks to fetch.

        Returns:
            List of Track objects.
        """
        pass

    @abstractmethod
    def get_recently_liked_songs(self, count: int = 10) -> list[Track]:
        """Get the most recently liked songs.

        Args:
            count: Number of recent songs to fetch.

        Returns:
            List of Track objects, most recent first.
        """
        pass

    @abstractmethod
    def get_artist_top_tracks(
        self, artist_id: str, limit: int = 1, country: str = "US"
    ) -> list[Track]:
        """Get an artist's top/popular tracks.

        Args:
            artist_id: Service-specific artist ID.
            limit: Maximum number of tracks to return.
            country: Country code for regional availability.

        Returns:
            List of Track objects.
        """
        pass

    @abstractmethod
    def add_to_queue(self, track_uri: str) -> bool:
        """Add a track to the user's playback queue.

        Args:
            track_uri: Service-specific track URI/ID.

        Returns:
            True if successful, False otherwise.
        """
        pass

    def add_tracks_to_queue(self, track_uris: list[str]) -> int:
        """Add multiple tracks to the playback queue.

        Args:
            track_uris: List of track URIs/IDs.

        Returns:
            Number of tracks successfully added.
        """
        added = 0
        for uri in track_uris:
            if self.add_to_queue(uri):
                added += 1
        return added

    @abstractmethod
    def get_current_playback(self) -> Optional[dict]:
        """Get information about the user's current playback.

        Returns:
            Playback info dict or None if nothing playing.
        """
        pass

    @abstractmethod
    def is_playing(self) -> bool:
        """Check if user has an active playback session.

        Returns:
            True if playing, False otherwise.
        """
        pass
