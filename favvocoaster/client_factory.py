"""Factory for creating music service clients."""

import logging
from pathlib import Path
from typing import Optional

from .base_client import MusicServiceClient
from .config import AppSettings, MusicService

logger = logging.getLogger(__name__)


def create_music_client(
    settings: AppSettings,
    cache_path: Optional[Path] = None,
) -> MusicServiceClient:
    """Create the appropriate music client based on settings.

    Args:
        settings: Application settings.
        cache_path: Optional path for token cache.

    Returns:
        Configured MusicServiceClient instance.

    Raises:
        ValueError: If service is not supported.
        ImportError: If required library is not installed.
    """
    service = settings.service

    if service == MusicService.SPOTIFY:
        from .spotify_client import SpotifyClient

        logger.info("Using Spotify as music service")
        return SpotifyClient(
            settings=settings.spotify,
            cache_path=cache_path or Path(".spotify_cache"),
        )

    elif service == MusicService.TIDAL:
        try:
            from .tidal_client import TidalClient, TIDALAPI_AVAILABLE

            if not TIDALAPI_AVAILABLE:
                raise ImportError(
                    "tidalapi is not installed. Install with: pip install tidalapi"
                )

            logger.info("Using Tidal as music service")
            return TidalClient(
                settings=settings.tidal,
                session_file=cache_path or Path(settings.tidal.session_file),
            )
        except ImportError as e:
            logger.error(f"Failed to load Tidal client: {e}")
            raise

    else:
        raise ValueError(f"Unsupported music service: {service}")
