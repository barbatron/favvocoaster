#!/usr/bin/env bash
set -e

# FavvoCoaster local setup - one command to get started

SERVICE="tidal"
if [[ "$1" == "--spotify" ]]; then
    SERVICE="spotify"
fi

echo "🎢 FavvoCoaster Local Setup"
echo "==========================="
echo ""

# Detect uv or pip
if command -v uv &> /dev/null; then
    echo "📦 Installing dependencies (using uv)..."
    if [[ "$SERVICE" == "tidal" ]]; then
        uv sync --extra tidal
    else
        uv sync --extra spotify
    fi
    # uv run handles activation
    RUN_CMD="uv run favvocoaster"
else
    # Fallback to pip/venv
    if [[ ! -d ".venv" ]]; then
        echo "📦 Creating virtual environment..."
        python3 -m venv .venv
    fi
    source .venv/bin/activate
    echo "📦 Installing dependencies (using pip)..."
    pip install -q -e ".[all]"
    RUN_CMD="favvocoaster"
fi

# Check Spotify creds if needed
if [[ "$SERVICE" == "spotify" ]]; then
    if [[ -z "$SPOTIFY_CLIENT_ID" || -z "$SPOTIFY_CLIENT_SECRET" ]]; then
        echo ""
        echo "❌ Spotify requires credentials. Set them first:"
        echo ""
        echo "   export SPOTIFY_CLIENT_ID='your_id'"
        echo "   export SPOTIFY_CLIENT_SECRET='your_secret'"
        echo "   ./local_setup.sh --spotify"
        echo ""
        exit 1
    fi
fi

echo ""
echo "🚀 Starting FavvoCoaster with $SERVICE..."
echo "   (Ctrl+C to stop)"
echo ""

# Run
$RUN_CMD --service "$SERVICE"