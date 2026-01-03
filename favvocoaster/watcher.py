"""Event listener for monitoring liked songs and triggering scraping."""

import logging
import time
from datetime import datetime
from typing import Callable, Optional

from .base_client import MusicServiceClient
from .config import ScrapingSettings
from .models import ScrapeContext, Track
from .rules import ScrapeRulesEngine

logger = logging.getLogger(__name__)


class LikedSongsWatcher:
    """Watches for newly liked songs and triggers scraping when appropriate.

    Works with any MusicServiceClient implementation (Spotify, Tidal, etc.).
    Since most services don't provide webhooks for library changes, this uses
    polling to detect new liked songs.
    """

    def __init__(
        self,
        music_client: MusicServiceClient,
        rules_engine: ScrapeRulesEngine,
        settings: ScrapingSettings,
        on_scrape_triggered: Optional[Callable[[Track, list[Track]], None]] = None,
    ):
        """Initialize the watcher.

        Args:
            music_client: Music service API client.
            rules_engine: Rules engine for determining when to scrape.
            settings: Scraping configuration.
            on_scrape_triggered: Optional callback when scraping occurs.
        """
        self.client = music_client
        self.rules_engine = rules_engine
        self.settings = settings
        self.on_scrape_triggered = on_scrape_triggered

        self._known_artist_ids: set[str] = set()
        self._seen_track_ids: set[str] = set()
        self._running = False
        self._last_poll_time: Optional[datetime] = None

    # Keep backward compatibility
    @property
    def spotify(self) -> MusicServiceClient:
        """Backward compatible alias for music client."""
        return self.client

    def build_known_artists_index(self) -> set[str]:
        """Build an index of known artist IDs from user's liked songs.

        Returns:
            Set of known artist IDs.
        """
        logger.info(
            f"Building known artists index from last "
            f"{self.settings.known_artists_scan_limit} liked songs..."
        )

        liked_songs = self.client.get_all_liked_songs(
            max_tracks=self.settings.known_artists_scan_limit
        )

        known_artists: set[str] = set()
        for track in liked_songs:
            known_artists.update(track.artist_ids)
            # Also track which songs we've seen to avoid re-processing
            self._seen_track_ids.add(track.id)

        self._known_artist_ids = known_artists
        logger.info(
            f"Found {len(known_artists)} known artists from "
            f"{len(liked_songs)} liked songs"
        )

        return known_artists

    def check_for_new_likes(self) -> list[Track]:
        """Check for newly liked songs since last poll.

        Returns:
            List of new tracks (not seen before).
        """
        logger.debug("Fetching recent liked songs...")
        recent_tracks = self.client.get_recently_liked_songs(count=20)
        logger.debug(f"Got {len(recent_tracks)} recent tracks from API")
        
        new_tracks = [t for t in recent_tracks if t.id not in self._seen_track_ids]

        if new_tracks:
            logger.info(f"🆕 Found {len(new_tracks)} new liked song(s):")
            for t in new_tracks:
                logger.info(f"   • {t.name} by {', '.join(t.artist_names)}")
        else:
            logger.debug(f"No new tracks (all {len(recent_tracks)} already seen)")

        return new_tracks

    def process_new_track(self, track: Track) -> list[Track]:
        """Process a newly liked track through the rules engine.

        Args:
            track: The newly liked track.

        Returns:
            List of tracks that were added to queue.
        """
        logger.info(f"Processing: {track.name} by {', '.join(track.artist_names)}")

        # Build the scraping context
        context = ScrapeContext(
            track=track,
            known_artist_ids=self._known_artist_ids,
            user_id=self.client.user_id,
        )

        # Evaluate rules
        result = self.rules_engine.evaluate(context)

        if not result.should_scrape:
            logger.info(f"  → Skip: {result.reason}")
            # Still mark this track as seen and add its artists as known
            self._seen_track_ids.add(track.id)
            self._known_artist_ids.update(track.artist_ids)
            return []

        logger.info(
            f"  → Scraping top tracks for {len(result.artists_to_scrape)} artist(s)..."
        )

        # Fetch top tracks for each artist to scrape
        queued_tracks: list[Track] = []
        for artist in result.artists_to_scrape:
            logger.info(f"    Fetching top tracks for: {artist.name}")
            top_tracks = self.client.get_artist_top_tracks(
                artist.id, limit=self.settings.top_tracks_limit
            )

            for top_track in top_tracks:
                # Don't queue the song that was just liked
                if top_track.id == track.id:
                    continue

                # Don't queue songs already in liked songs
                if top_track.id in self._seen_track_ids:
                    logger.debug(f"      Skipping already-liked: {top_track.name}")
                    continue

                # Add to queue
                if self.client.add_to_queue(top_track.uri):
                    logger.info(f"    ✓ Queued: {top_track.name}")
                    queued_tracks.append(top_track)
                else:
                    logger.warning(f"    ✗ Failed to queue: {top_track.name}")

        # Update known artists and seen tracks
        self._seen_track_ids.add(track.id)
        self._known_artist_ids.update(track.artist_ids)

        # Trigger callback if set
        if self.on_scrape_triggered and queued_tracks:
            self.on_scrape_triggered(track, queued_tracks)

        return queued_tracks

    def run_once(self) -> list[Track]:
        """Run a single check for new liked songs.

        Returns:
            List of all tracks added to queue this run.
        """
        self._last_poll_time = datetime.now()
        all_queued: list[Track] = []

        logger.debug(f"─── Poll at {self._last_poll_time.strftime('%H:%M:%S')} ───")

        try:
            new_tracks = self.check_for_new_likes()

            if not new_tracks:
                logger.debug("Nothing to process")
            
            for track in new_tracks:
                queued = self.process_new_track(track)
                all_queued.extend(queued)

        except Exception as e:
            logger.error(f"Error during poll: {e}", exc_info=True)

        return all_queued

    def start(self) -> None:
        """Start the continuous watching loop."""
        logger.info("Starting liked songs watcher...")
        logger.info(f"Poll interval: {self.settings.poll_interval_seconds} seconds")
        logger.info(f"Active rules: {self.rules_engine.list_rules()}")

        # Build initial index
        self.build_known_artists_index()

        self._running = True
        logger.info("")
        logger.info("="*50)
        logger.info("🎧 Watcher started! Listening for new liked songs...")
        logger.info(f"   Tracking {len(self._seen_track_ids)} songs, {len(self._known_artist_ids)} artists")
        logger.info(f"   Polling every {self.settings.poll_interval_seconds}s (use --debug for verbose)")
        logger.info("="*50)
        logger.info("")

        poll_count = 0
        while self._running:
            try:
                poll_count += 1
                logger.debug(f"Poll #{poll_count}")
                self.run_once()
                logger.debug(f"Sleeping {self.settings.poll_interval_seconds}s...")
                time.sleep(self.settings.poll_interval_seconds)

            except KeyboardInterrupt:
                logger.info("Received interrupt signal")
                self.stop()

            except Exception as e:
                logger.error(f"Unexpected error in watch loop: {e}", exc_info=True)
                time.sleep(self.settings.poll_interval_seconds)

    def stop(self) -> None:
        """Stop the watching loop."""
        logger.info("Stopping watcher...")
        self._running = False


class EventDrivenWatcher:
    """Alternative watcher that can be driven by external events.

    Useful for integration with webhook systems or testing.
    """

    def __init__(
        self,
        music_client: MusicServiceClient,
        rules_engine: ScrapeRulesEngine,
        settings: ScrapingSettings,
    ):
        """Initialize the event-driven watcher.

        Args:
            music_client: Music service API client.
            rules_engine: Rules engine for scraping decisions.
            settings: Scraping configuration.
        """
        self._watcher = LikedSongsWatcher(
            music_client=music_client,
            rules_engine=rules_engine,
            settings=settings,
        )

    def initialize(self) -> None:
        """Initialize the watcher (build known artists index)."""
        self._watcher.build_known_artists_index()

    def on_track_liked(self, track: Track) -> list[Track]:
        """Handle a track liked event.

        Args:
            track: The track that was liked.

        Returns:
            List of tracks added to queue.
        """
        return self._watcher.process_new_track(track)

    @property
    def known_artist_ids(self) -> set[str]:
        """Get the current set of known artist IDs."""
        return self._watcher._known_artist_ids

    @property
    def seen_track_ids(self) -> set[str]:
        """Get the current set of seen track IDs."""
        return self._watcher._seen_track_ids
