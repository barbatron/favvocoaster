# 🎢 FavvoCoaster

Auto-queue top tracks from artists when you like collaboration songs on Spotify.

## What it does

When you like a song on Spotify:
1. FavvoCoaster checks if the song is a **collaboration** (multiple artists)
2. If none of the artists are already in your library (they're "new" to you)
3. It automatically adds the **top track** from each new artist to your play queue

This helps you discover more music from artists you encounter through collaborations!

## Features

- 🎵 **Smart scraping rules** - Only triggers on multi-artist tracks with new artists
- ⚙️ **Configurable** - Adjust minimum artists, tracks per artist, polling interval
- 🔌 **Extensible rules engine** - Easy to add custom rules
- 🏃 **Dry-run mode** - Test without making changes
- 📊 **Status command** - Check your current setup

## Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/favvocoaster.git
cd favvocoaster

# Install with pip
pip install -e .

# Or with uv
uv pip install -e .
```

## Setup

### 1. Create a Spotify App

1. Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Create a new app
3. Set the redirect URI to `http://localhost:8888/callback`
4. Note your Client ID and Client Secret

### 2. Configure Environment

```bash
# Copy the example config
cp .env.example .env

# Edit .env with your credentials
nano .env
```

Set your Spotify credentials:
```
SPOTIFY_CLIENT_ID=your_client_id_here
SPOTIFY_CLIENT_SECRET=your_client_secret_here
```

### 3. Run FavvoCoaster

```bash
# Start the watcher (continuous mode)
favvocoaster

# Or run once
favvocoaster --once

# Test without making changes
favvocoaster --dry-run

# Check status
favvocoaster --status
```

On first run, a browser window will open for Spotify authentication.

## Configuration

All settings can be configured via environment variables or `.env` file:

| Variable | Default | Description |
|----------|---------|-------------|
| `SPOTIFY_CLIENT_ID` | (required) | Your Spotify app client ID |
| `SPOTIFY_CLIENT_SECRET` | (required) | Your Spotify app client secret |
| `SPOTIFY_REDIRECT_URI` | `http://localhost:8888/callback` | OAuth redirect URI |
| `SCRAPE_MIN_ARTISTS` | `2` | Minimum artists to trigger scraping |
| `SCRAPE_TOP_TRACKS_LIMIT` | `1` | Top tracks to queue per artist |
| `SCRAPE_SKIP_KNOWN_ARTISTS` | `true` | Skip if any artist is known |
| `SCRAPE_POLL_INTERVAL_SECONDS` | `30` | How often to check for new likes |
| `SCRAPE_KNOWN_ARTISTS_SCAN_LIMIT` | `500` | Liked songs to scan for known artists |

## Scraping Rules

The default rules are:

1. **Minimum Artists Rule**: Track must have at least N artists (default: 2)
   - Single-artist tracks are ignored
   
2. **No Known Artists Rule**: None of the track's artists should already be in your liked songs
   - If you already have songs from an artist, they're considered "known"

### Adding Custom Rules

You can extend the rules engine programmatically:

```python
from favvocoaster.rules import ScrapeRulesEngine, CustomPredicateRule

# Example: Only scrape during evening hours
def evening_only(context):
    return 18 <= context.timestamp.hour < 24

engine = ScrapeRulesEngine(settings.scraping)
engine.add_rule(CustomPredicateRule(
    predicate=evening_only,
    rule_name="EveningOnly",
    description="Only scrape between 6 PM and midnight"
))
```

## How "Known Artists" Works

When FavvoCoaster starts, it scans your recent liked songs (default: last 500) to build an index of artists you already know. Any artist appearing in your liked songs is considered "known".

This means:
- If you like a song with Artist A + Artist B
- And you already have songs from Artist A in your library
- FavvoCoaster won't scrape, because Artist A is "known"

This prevents you from getting recommendations for artists you're already familiar with.

## Usage Examples

### Basic Usage
```bash
# Start watching for new liked songs
favvocoaster
```

### Debug Mode
```bash
# See detailed logging
favvocoaster --debug
```

### One-time Check
```bash
# Process any new likes and exit
favvocoaster --once
```

### Test Run
```bash
# See what would happen without queuing tracks
favvocoaster --dry-run
```

## Requirements

- Python 3.12+
- Active Spotify Premium subscription (required for queue control)
- Spotify must be playing on a device for queue additions to work

## License

MIT
