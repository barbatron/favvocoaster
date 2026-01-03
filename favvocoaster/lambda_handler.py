"""AWS Lambda handler for FavvoCoaster.

Runs as a scheduled Lambda function (via EventBridge) to poll for new liked songs.
Stores Spotify OAuth tokens in SSM Parameter Store.
"""

import json
import logging
import os
from typing import Any

import boto3
import spotipy
from spotipy.oauth2 import SpotifyOAuth

from .config import ScrapingSettings, SpotifySettings
from .rules import ScrapeRulesEngine
from .spotify_client import SpotifyClient
from .watcher import LikedSongsWatcher

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# SSM parameter names
SSM_TOKEN_PARAM = os.environ.get("SSM_TOKEN_PARAM", "/favvocoaster/spotify_token")


class SSMTokenCache:
    """Spotipy cache handler that stores tokens in AWS SSM Parameter Store."""

    def __init__(self, param_name: str):
        self.param_name = param_name
        self.ssm = boto3.client("ssm")

    def get_cached_token(self) -> dict | None:
        """Retrieve token from SSM."""
        try:
            response = self.ssm.get_parameter(
                Name=self.param_name, WithDecryption=True
            )
            token_info = json.loads(response["Parameter"]["Value"])
            logger.info("Retrieved token from SSM")
            return token_info
        except self.ssm.exceptions.ParameterNotFound:
            logger.warning(f"No token found in SSM at {self.param_name}")
            return None
        except Exception as e:
            logger.error(f"Failed to get token from SSM: {e}")
            return None

    def save_token_to_cache(self, token_info: dict) -> None:
        """Save token to SSM."""
        try:
            self.ssm.put_parameter(
                Name=self.param_name,
                Value=json.dumps(token_info),
                Type="SecureString",
                Overwrite=True,
            )
            logger.info("Saved token to SSM")
        except Exception as e:
            logger.error(f"Failed to save token to SSM: {e}")
            raise


class LambdaSpotifyClient(SpotifyClient):
    """SpotifyClient that uses SSM for token storage."""

    def __init__(self, settings: SpotifySettings, ssm_param: str):
        self.settings = settings
        self._user_id = None

        # Use SSM-backed cache
        cache_handler = SSMTokenCache(ssm_param)

        auth_manager = SpotifyOAuth(
            client_id=settings.client_id,
            client_secret=settings.client_secret,
            redirect_uri=settings.redirect_uri,
            scope=" ".join([
                "user-library-read",
                "user-read-playback-state",
                "user-modify-playback-state",
                "user-read-currently-playing",
            ]),
            cache_handler=cache_handler,
            open_browser=False,
        )

        self._client = spotipy.Spotify(auth_manager=auth_manager)


def get_settings_from_env() -> tuple[SpotifySettings, ScrapingSettings]:
    """Load settings from Lambda environment variables."""
    spotify = SpotifySettings(
        client_id=os.environ["SPOTIFY_CLIENT_ID"],
        client_secret=os.environ["SPOTIFY_CLIENT_SECRET"],
        redirect_uri=os.environ.get(
            "SPOTIFY_REDIRECT_URI", "http://localhost:8888/callback"
        ),
    )

    scraping = ScrapingSettings(
        min_artists=int(os.environ.get("SCRAPE_MIN_ARTISTS", "2")),
        top_tracks_limit=int(os.environ.get("SCRAPE_TOP_TRACKS_LIMIT", "1")),
        skip_known_artists=os.environ.get("SCRAPE_SKIP_KNOWN_ARTISTS", "true").lower()
        == "true",
        known_artists_scan_limit=int(
            os.environ.get("SCRAPE_KNOWN_ARTISTS_SCAN_LIMIT", "500")
        ),
    )

    return spotify, scraping


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda handler function.

    Triggered by EventBridge schedule to check for new liked songs.
    """
    logger.info("FavvoCoaster Lambda invoked")
    logger.info(f"Event: {json.dumps(event)}")

    try:
        # Load settings
        spotify_settings, scraping_settings = get_settings_from_env()

        # Initialize Spotify client with SSM token storage
        ssm_param = os.environ.get("SSM_TOKEN_PARAM", SSM_TOKEN_PARAM)
        spotify = LambdaSpotifyClient(spotify_settings, ssm_param)

        logger.info(f"Authenticated as: {spotify.user_id}")

        # Check if there's an active playback device
        if not spotify.is_playing():
            logger.info("No active playback - skipping (can't add to queue)")
            return {
                "statusCode": 200,
                "body": json.dumps({"message": "No active playback, skipped"}),
            }

        # Initialize rules engine and watcher
        rules_engine = ScrapeRulesEngine(scraping_settings)
        watcher = LikedSongsWatcher(
            spotify_client=spotify,
            rules_engine=rules_engine,
            settings=scraping_settings,
        )

        # Build known artists index and run once
        watcher.build_known_artists_index()
        queued_tracks = watcher.run_once()

        result = {
            "statusCode": 200,
            "body": json.dumps({
                "message": f"Processed successfully, queued {len(queued_tracks)} tracks",
                "queued": [t.name for t in queued_tracks],
            }),
        }
        logger.info(f"Result: {result}")
        return result

    except Exception as e:
        logger.error(f"Lambda execution failed: {e}", exc_info=True)
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)}),
        }


# For local testing
if __name__ == "__main__":
    # Simulate Lambda invocation
    result = handler({}, None)
    print(json.dumps(result, indent=2))
