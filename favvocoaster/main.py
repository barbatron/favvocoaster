"""Main entry point for FavvoCoaster."""

import argparse
import logging
import sys

from .config import load_settings
from .rules import ScrapeRulesEngine
from .spotify_client import SpotifyClient
from .watcher import LikedSongsWatcher


def setup_logging(debug: bool = False) -> None:
    """Configure logging for the application.

    Args:
        debug: Enable debug level logging.
    """
    level = logging.DEBUG if debug else logging.INFO
    format_str = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    logging.basicConfig(
        level=level,
        format=format_str,
        datefmt=date_format,
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    # Reduce noise from spotipy
    logging.getLogger("spotipy").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments.

    Returns:
        Parsed arguments.
    """
    parser = argparse.ArgumentParser(
        description="FavvoCoaster - Auto-queue top tracks from artists of newly liked songs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  favvocoaster                    # Start with default settings
  favvocoaster --debug            # Enable debug logging
  favvocoaster --once             # Run once and exit (don't loop)
  favvocoaster --dry-run          # Show what would be queued without doing it

Environment Variables:
  SPOTIFY_CLIENT_ID       Spotify App Client ID (required)
  SPOTIFY_CLIENT_SECRET   Spotify App Client Secret (required)
  SPOTIFY_REDIRECT_URI    OAuth redirect URI (default: http://localhost:8888/callback)
  SCRAPE_MIN_ARTISTS      Min artists to trigger scraping (default: 2)
  SCRAPE_TOP_TRACKS_LIMIT Top tracks per artist (default: 1)
  SCRAPE_POLL_INTERVAL_SECONDS  Polling interval (default: 30)
        """,
    )

    parser.add_argument(
        "--debug", "-d", action="store_true", help="Enable debug logging"
    )

    parser.add_argument(
        "--once",
        "-1",
        action="store_true",
        help="Run once and exit (don't continuously poll)",
    )

    parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Show what would be done without making changes",
    )

    parser.add_argument(
        "--status",
        "-s",
        action="store_true",
        help="Show current status and configuration, then exit",
    )

    return parser.parse_args()


def show_status(spotify: SpotifyClient, settings) -> None:
    """Display current status and configuration.

    Args:
        spotify: Spotify client.
        settings: Application settings.
    """
    print("\n🎢 FavvoCoaster Status")
    print("=" * 50)

    # User info
    try:
        user_id = spotify.user_id
        print(f"\n👤 Logged in as: {user_id}")
    except Exception as e:
        print(f"\n❌ Not authenticated: {e}")
        return

    # Playback status
    if spotify.is_playing():
        playback = spotify.get_current_playback()
        if playback and playback.get("item"):
            track = playback["item"]
            print(f"🎵 Currently playing: {track['name']}")
    else:
        print("⏸️  No active playback")

    # Configuration
    print(f"\n⚙️  Configuration:")
    print(f"   Min artists to trigger: {settings.scraping.min_artists}")
    print(f"   Top tracks per artist: {settings.scraping.top_tracks_limit}")
    print(f"   Skip known artists: {settings.scraping.skip_known_artists}")
    print(f"   Poll interval: {settings.scraping.poll_interval_seconds}s")

    print()


def main() -> int:
    """Main entry point.

    Returns:
        Exit code.
    """
    args = parse_args()

    # Load configuration
    try:
        settings = load_settings()
    except Exception as e:
        print(f"❌ Configuration error: {e}")
        print(
            "\nMake sure you have set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET "
            "environment variables or created a .env file."
        )
        return 1

    # Setup logging
    setup_logging(debug=args.debug or settings.debug)
    logger = logging.getLogger(__name__)

    logger.info("🎢 FavvoCoaster starting up...")

    # Initialize Spotify client
    try:
        spotify = SpotifyClient(settings.spotify)
        logger.info(f"Authenticated as: {spotify.user_id}")
    except Exception as e:
        logger.error(f"Failed to authenticate with Spotify: {e}")
        print(
            "\n💡 Tip: Make sure your Spotify app is configured with the redirect URI: "
            f"{settings.spotify.redirect_uri}"
        )
        return 1

    # Status mode
    if args.status:
        show_status(spotify, settings)
        return 0

    # Initialize rules engine
    rules_engine = ScrapeRulesEngine(settings.scraping)
    logger.info(f"Active rules: {rules_engine.list_rules()}")

    # Dry run mode - modify the spotify client to not actually queue
    if args.dry_run:
        logger.info("🔍 DRY RUN MODE - no changes will be made")
        original_add_to_queue = spotify.add_to_queue

        def dry_run_add_to_queue(track_uri: str) -> bool:
            logger.info(f"[DRY RUN] Would queue: {track_uri}")
            return True

        spotify.add_to_queue = dry_run_add_to_queue

    # Create and start watcher
    watcher = LikedSongsWatcher(
        spotify_client=spotify,
        rules_engine=rules_engine,
        settings=settings.scraping,
    )

    try:
        if args.once:
            # Single run mode
            logger.info("Running single check...")
            watcher.build_known_artists_index()
            queued = watcher.run_once()
            if queued:
                logger.info(f"Queued {len(queued)} track(s)")
            else:
                logger.info("No tracks queued")
        else:
            # Continuous mode
            watcher.start()

    except KeyboardInterrupt:
        logger.info("Shutting down...")

    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return 1

    logger.info("👋 Goodbye!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
