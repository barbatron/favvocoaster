"""Scraping rules engine for FavvoCoaster.

This module provides a flexible, extensible system for defining when
"scraping" (auto-queueing top tracks from artists) should occur.

Rules are composable and can be easily added, removed, or modified.
"""

import logging
from abc import ABC, abstractmethod
from typing import Callable

from .config import ScrapingSettings
from .models import Artist, ScrapeContext, ScrapeResult, Track

logger = logging.getLogger(__name__)


class ScrapeRule(ABC):
    """Base class for scraping rules.

    Each rule evaluates whether scraping should proceed for a given track.
    Rules can be combined using AND/OR logic.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name for this rule."""
        pass

    @abstractmethod
    def evaluate(self, context: ScrapeContext) -> tuple[bool, str]:
        """Evaluate this rule against the given context.

        Args:
            context: The scraping context with track and user info.

        Returns:
            Tuple of (passed: bool, reason: str).
        """
        pass


class MinimumArtistsRule(ScrapeRule):
    """Rule: Track must have at least N artists (collaboration check)."""

    def __init__(self, min_artists: int = 2):
        self.min_artists = min_artists

    @property
    def name(self) -> str:
        return f"MinimumArtists(>={self.min_artists})"

    def evaluate(self, context: ScrapeContext) -> tuple[bool, str]:
        artist_count = len(context.track.artists)
        if artist_count >= self.min_artists:
            return True, f"Track has {artist_count} artists (>= {self.min_artists})"
        return (
            False,
            f"Track has only {artist_count} artist(s), need >= {self.min_artists}",
        )


class NoKnownArtistsRule(ScrapeRule):
    """Rule: None of the track's artists should be 'known' (in user's library)."""

    def __init__(self, skip_if_any_known: bool = True):
        self.skip_if_any_known = skip_if_any_known

    @property
    def name(self) -> str:
        return "NoKnownArtists"

    def evaluate(self, context: ScrapeContext) -> tuple[bool, str]:
        if not self.skip_if_any_known:
            return True, "Known artist check disabled"

        known_in_track = context.track.artist_ids & context.known_artist_ids
        if known_in_track:
            known_names = [
                a.name for a in context.track.artists if a.id in known_in_track
            ]
            return (
                False,
                f"Already known artist(s): {', '.join(known_names)}",
            )
        return True, "No known artists on this track"


class CustomPredicateRule(ScrapeRule):
    """Rule using a custom predicate function for maximum flexibility."""

    def __init__(
        self,
        predicate: Callable[[ScrapeContext], bool],
        rule_name: str,
        description: str = "",
    ):
        self._predicate = predicate
        self._name = rule_name
        self._description = description

    @property
    def name(self) -> str:
        return self._name

    def evaluate(self, context: ScrapeContext) -> tuple[bool, str]:
        try:
            result = self._predicate(context)
            reason = self._description if self._description else f"{self._name}: {result}"
            return result, reason
        except Exception as e:
            logger.error(f"Error evaluating custom rule {self._name}: {e}")
            return False, f"Rule evaluation error: {e}"


class ScrapeRulesEngine:
    """Engine for evaluating scraping rules against tracks.

    Provides a way to combine multiple rules and determine which
    artists should be scraped for top tracks.
    """

    def __init__(self, settings: ScrapingSettings):
        """Initialize the rules engine with settings.

        Args:
            settings: Scraping configuration.
        """
        self.settings = settings
        self._rules: list[ScrapeRule] = []
        self._setup_default_rules()

    def _setup_default_rules(self) -> None:
        """Set up the default scraping rules based on settings."""
        # Rule 1: Must be a collaboration (multiple artists)
        self._rules.append(MinimumArtistsRule(min_artists=self.settings.min_artists))

        # Rule 2: No known artists
        self._rules.append(
            NoKnownArtistsRule(skip_if_any_known=self.settings.skip_known_artists)
        )

    def add_rule(self, rule: ScrapeRule) -> None:
        """Add a custom rule to the engine.

        Args:
            rule: The rule to add.
        """
        self._rules.append(rule)
        logger.info(f"Added scraping rule: {rule.name}")

    def remove_rule(self, rule_name: str) -> bool:
        """Remove a rule by name.

        Args:
            rule_name: Name of the rule to remove.

        Returns:
            True if rule was found and removed.
        """
        for i, rule in enumerate(self._rules):
            if rule.name == rule_name:
                self._rules.pop(i)
                logger.info(f"Removed scraping rule: {rule_name}")
                return True
        return False

    def clear_rules(self) -> None:
        """Remove all rules."""
        self._rules.clear()

    def list_rules(self) -> list[str]:
        """Get list of active rule names.

        Returns:
            List of rule names.
        """
        return [rule.name for rule in self._rules]

    def evaluate(self, context: ScrapeContext) -> ScrapeResult:
        """Evaluate all rules for a given track context.

        Args:
            context: The scraping context.

        Returns:
            ScrapeResult indicating whether to scrape and for which artists.
        """
        track = context.track
        logger.debug(
            f"Evaluating scraping rules for: {track.name} "
            f"by {', '.join(track.artist_names)}"
        )

        # Evaluate all rules (AND logic - all must pass)
        for rule in self._rules:
            passed, reason = rule.evaluate(context)
            logger.debug(f"  Rule '{rule.name}': {'PASS' if passed else 'FAIL'} - {reason}")

            if not passed:
                return ScrapeResult(
                    should_scrape=False,
                    reason=f"Rule '{rule.name}' failed: {reason}",
                    artists_to_scrape=[],
                )

        # All rules passed - determine which artists to scrape
        # Only scrape artists that are NOT already known
        artists_to_scrape = [
            artist
            for artist in track.artists
            if artist.id not in context.known_artist_ids
        ]

        if not artists_to_scrape:
            return ScrapeResult(
                should_scrape=False,
                reason="All artists already known, none to scrape",
                artists_to_scrape=[],
            )

        return ScrapeResult(
            should_scrape=True,
            reason=f"All {len(self._rules)} rules passed",
            artists_to_scrape=artists_to_scrape,
        )


# ============================================================================
# Example custom rules that users can add for more specific behavior
# ============================================================================


def create_genre_filter_rule(
    allowed_genres: set[str], excluded_genres: set[str] | None = None
) -> CustomPredicateRule:
    """Create a rule that filters by genre.

    Note: This would require additional API calls to get artist genres.
    Provided as an example of rule extensibility.
    """

    def genre_predicate(context: ScrapeContext) -> bool:
        # This is a placeholder - would need to fetch artist genres
        return True

    return CustomPredicateRule(
        predicate=genre_predicate,
        rule_name="GenreFilter",
        description=f"Filter by genres: {allowed_genres}",
    )


def create_popularity_threshold_rule(min_popularity: int = 0) -> CustomPredicateRule:
    """Create a rule that filters by track popularity.

    Note: Would need track popularity data in the Track model.
    """

    def popularity_predicate(context: ScrapeContext) -> bool:
        # Placeholder - track popularity would need to be added to model
        return True

    return CustomPredicateRule(
        predicate=popularity_predicate,
        rule_name=f"MinPopularity({min_popularity})",
        description=f"Track must have popularity >= {min_popularity}",
    )


def create_time_of_day_rule(
    start_hour: int, end_hour: int
) -> CustomPredicateRule:
    """Create a rule that only allows scraping during certain hours.

    Args:
        start_hour: Start hour (0-23).
        end_hour: End hour (0-23).
    """

    def time_predicate(context: ScrapeContext) -> bool:
        current_hour = context.timestamp.hour
        if start_hour <= end_hour:
            return start_hour <= current_hour < end_hour
        else:
            # Handles overnight ranges like 22-6
            return current_hour >= start_hour or current_hour < end_hour

    return CustomPredicateRule(
        predicate=time_predicate,
        rule_name=f"TimeOfDay({start_hour:02d}:00-{end_hour:02d}:00)",
        description=f"Only scrape between {start_hour}:00 and {end_hour}:00",
    )
