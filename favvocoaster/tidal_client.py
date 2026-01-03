"""Tidal API client wrapper for FavvoCoaster.

Uses tidalapi library for Tidal integration.
Tidal OAuth flow is more complex - typically uses device code flow.
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from .base_client import MusicServiceClient
from .config import TidalSettings
from .models import Artist, Track

logger = logging.getLogger(__name__)

# Only import tidalapi if available
try:
    import tidalapi
    from tidalapi.user import ItemOrder, OrderDirection
    TIDALAPI_AVAILABLE = True
except ImportError:
    TIDALAPI_AVAILABLE = False
    tidalapi = None
    ItemOrder = None
    OrderDirection = None


class TidalClient(MusicServiceClient):
    """Wrapper around tidalapi for FavvoCoaster operations."""

    @property
    def service_name(self) -> str:
        return "Tidal"

    def __init__(
        self,
        settings: TidalSettings,
        session_file: Optional[Path] = None,
        http_logging: bool = False,
    ):
        """Initialize the Tidal client.

        Args:
            settings: Tidal API configuration.
            session_file: Path to store session data for persistence.
            http_logging: Enable detailed HTTP request/response logging.
        """
        if not TIDALAPI_AVAILABLE:
            raise ImportError(
                "tidalapi is not installed. Install with: pip install tidalapi"
            )

        self.settings = settings
        self._session_file = session_file or Path(".tidal_session.json")
        self._user_id: Optional[str] = None
        self._http_logging = http_logging

        # Initialize session
        self._session = tidalapi.Session()

        # Enable HTTP logging if requested
        if http_logging:
            self._setup_http_logging()

        # Try to load existing session or authenticate
        if self._session_file.exists():
            if self._load_session():
                logger.info("Loaded existing Tidal session")
            else:
                self._authenticate()
        else:
            self._authenticate()

    def _setup_http_logging(self) -> None:
        """Set up HTTP request/response logging."""
        try:
            from .http_logging import setup_http_logging, patch_tidalapi_session
            setup_http_logging()
            patch_tidalapi_session(self._session)
            logger.info("HTTP logging enabled - see favvocoaster_http.log")
        except Exception as e:
            logger.warning(f"Failed to setup HTTP logging: {e}")

    def _load_session(self) -> bool:
        """Load session from file.

        Returns:
            True if session was loaded and is valid.
        """
        try:
            import json
            with open(self._session_file) as f:
                data = json.load(f)

            self._session.load_oauth_session(
                token_type=data["token_type"],
                access_token=data["access_token"],
                refresh_token=data.get("refresh_token"),
                expiry_time=datetime.fromisoformat(data["expiry_time"]),
            )

            # Check if session is valid
            if self._session.check_login():
                return True

            logger.warning("Tidal session expired, re-authenticating...")
            return False

        except Exception as e:
            logger.warning(f"Failed to load Tidal session: {e}")
            return False

    def _save_session(self) -> None:
        """Save session to file for persistence."""
        try:
            import json
            data = {
                "token_type": self._session.token_type,
                "access_token": self._session.access_token,
                "refresh_token": self._session.refresh_token,
                "expiry_time": self._session.expiry_time.isoformat()
                if self._session.expiry_time
                else None,
            }
            with open(self._session_file, "w") as f:
                json.dump(data, f)
            logger.debug("Saved Tidal session")
        except Exception as e:
            logger.error(f"Failed to save Tidal session: {e}")

    def _authenticate(self) -> None:
        """Authenticate with Tidal using device code flow."""
        logger.info("Starting Tidal authentication...")

        # Tidal uses device code flow (like TV apps)
        # User visits a URL and enters a code
        login, future = self._session.login_oauth()

        print("\n🎵 Tidal Authentication Required")
        print("=" * 40)
        print(f"1. Go to: {login.verification_uri_complete}")
        print(f"2. Or visit {login.verification_uri} and enter code: {login.user_code}")
        print("\nWaiting for authentication...")

        # Wait for user to complete auth
        future.result()

        if self._session.check_login():
            logger.info("Tidal authentication successful")
            self._save_session()
        else:
            raise RuntimeError("Tidal authentication failed")

    @property
    def user_id(self) -> str:
        """Get the current user's Tidal ID."""
        if self._user_id is None:
            user = self._session.user
            self._user_id = str(user.id)
        return self._user_id

    def get_liked_songs(self, limit: int = 50, offset: int = 0) -> list[Track]:
        """Fetch user's favorite tracks.

        Args:
            limit: Maximum number of tracks to return.
            offset: Index of first track to return.

        Returns:
            List of Track objects.
        """
        try:
            user = self._session.user
            favorites = user.favorites
            
            logger.debug(f"Fetching favorites for user: {user.id}")
            logger.debug(f"  Favorites object: {favorites}")
            logger.debug(f"  Request: limit={limit}, offset={offset}, order=DATE DESC (newest first)")
            
            # Request tracks ordered by date descending (newest first)
            tracks = favorites.tracks(
                limit=limit, 
                offset=offset,
                order=ItemOrder.Date,
                order_direction=OrderDirection.Descending
            )
            
            logger.debug(f"  Got {len(tracks)} tracks from Tidal API")
            if tracks and offset == 0:
                # Log first few tracks to verify we're getting the right data
                logger.debug(f"  First track (newest): {tracks[0].name} by {[a.name for a in tracks[0].artists]} (ID: {tracks[0].id})")
                if len(tracks) > 1:
                    logger.debug(f"  Second track: {tracks[1].name} (ID: {tracks[1].id})")
            
            return [self._parse_track(t) for t in tracks]
        except Exception as e:
            logger.error(f"Failed to get Tidal favorites: {e}", exc_info=True)
            return []

    def get_all_liked_songs(self, max_tracks: int = 500) -> list[Track]:
        """Fetch all user's favorite tracks up to a limit.

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
            logger.debug(f"Fetched {len(tracks)} favorite tracks so far...")

        return tracks[:max_tracks]

    def get_recently_liked_songs(self, count: int = 10) -> list[Track]:
        """Get the most recently favorited tracks.

        Args:
            count: Number of recent tracks to fetch.

        Returns:
            List of Track objects, most recent first.
        """
        logger.debug(f"get_recently_liked_songs called with count={count}")
        tracks = self.get_liked_songs(limit=min(count, 50))
        logger.debug(f"Returning {len(tracks)} recent tracks")
        if tracks:
            logger.debug(f"Most recent: {tracks[0].name} (ID: {tracks[0].id})")
        return tracks

    def get_artist_top_tracks(
        self, artist_id: str, limit: int = 1, country: str = "US"
    ) -> list[Track]:
        """Get an artist's top tracks.

        Args:
            artist_id: Tidal artist ID.
            limit: Maximum number of tracks to return.
            country: Country code (not used by Tidal, included for interface compat).

        Returns:
            List of Track objects.
        """
        try:
            artist = self._session.artist(int(artist_id))
            top_tracks = artist.get_top_tracks(limit=limit)
            return [self._parse_track(t) for t in top_tracks]
        except Exception as e:
            logger.error(f"Failed to get top tracks for artist {artist_id}: {e}")
            return []

    def add_to_queue(self, track_uri: str) -> bool:
        """Add a track to the user's playback queue.

        Note: Tidal's API support for queue management is limited.
        This may not work depending on the playback device.

        Args:
            track_uri: Tidal track ID.

        Returns:
            True if successful, False otherwise.
        """
        try:
            # Extract track ID if URI format
            track_id = track_uri.split(":")[-1] if ":" in track_uri else track_uri

            # Tidal's queue API is device-dependent
            # Try to add to queue via playback controls
            playback = self._session.playback

            if playback is None:
                logger.warning(
                    "No active Tidal playback found. Cannot add to queue. "
                    "Make sure Tidal is playing on a device."
                )
                return False

            # Add track to queue
            track = self._session.track(int(track_id))
            playback.queue_track(track)

            logger.info(f"Added to Tidal queue: {track_id}")
            return True

        except AttributeError:
            logger.warning(
                "Tidal queue management not available. "
                "This feature requires an active Tidal Connect session."
            )
            return False
        except Exception as e:
            logger.error(f"Failed to add to Tidal queue: {e}")
            return False

    def get_current_playback(self) -> Optional[dict]:
        """Get information about the user's current playback.

        Returns:
            Playback info dict or None if nothing playing.
        """
        try:
            playback = self._session.playback
            if playback is None:
                return None

            current = playback.current_track
            if current is None:
                return None

            return {
                "is_playing": True,  # If we got here, something is playing
                "item": {
                    "id": str(current.id),
                    "name": current.name,
                    "artists": [{"name": a.name} for a in current.artists],
                },
            }
        except Exception as e:
            logger.debug(f"Could not get Tidal playback: {e}")
            return None

    def is_playing(self) -> bool:
        """Check if user has an active playback session.

        Returns:
            True if playing, False otherwise.
        """
        playback = self.get_current_playback()
        return playback is not None

    def _parse_track(self, track) -> Track:
        """Parse a tidalapi Track object.

        Args:
            track: tidalapi.Track object.

        Returns:
            Parsed Track object.
        """
        # Handle date parsing
        added_at = None
        if hasattr(track, "user_date_added") and track.user_date_added:
            try:
                added_at = track.user_date_added
                if isinstance(added_at, str):
                    added_at = datetime.fromisoformat(added_at.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                pass

        return Track(
            id=str(track.id),
            name=track.name,
            uri=f"tidal:track:{track.id}",
            artists=[self._parse_artist(a) for a in track.artists],
            added_at=added_at,
        )

    def _parse_artist(self, artist) -> Artist:
        """Parse a tidalapi Artist object.

        Args:
            artist: tidalapi.Artist object.

        Returns:
            Parsed Artist object.
        """
        return Artist(
            id=str(artist.id),
            name=artist.name,
            uri=f"tidal:artist:{artist.id}",
        )


class TidalClientStub(MusicServiceClient):
    """Stub client for when tidalapi is not installed.

    Provides helpful error messages when Tidal is selected but not available.
    """

    @property
    def service_name(self) -> str:
        return "Tidal (not installed)"

    @property
    def user_id(self) -> str:
        raise ImportError("tidalapi is not installed. Install with: pip install tidalapi")

    def get_liked_songs(self, limit: int = 50, offset: int = 0) -> list[Track]:
        raise ImportError("tidalapi is not installed")

    def get_all_liked_songs(self, max_tracks: int = 500) -> list[Track]:
        raise ImportError("tidalapi is not installed")

    def get_recently_liked_songs(self, count: int = 10) -> list[Track]:
        raise ImportError("tidalapi is not installed")

    def get_artist_top_tracks(self, artist_id: str, limit: int = 1, country: str = "US") -> list[Track]:
        raise ImportError("tidalapi is not installed")

    def add_to_queue(self, track_uri: str) -> bool:
        raise ImportError("tidalapi is not installed")

    def get_current_playback(self) -> Optional[dict]:
        raise ImportError("tidalapi is not installed")

    def is_playing(self) -> bool:
        raise ImportError("tidalapi is not installed")
