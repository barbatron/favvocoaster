#!/usr/bin/env python3
"""Helper script to bootstrap Spotify OAuth token for Lambda.

Run this locally ONCE to authenticate and upload the initial token to SSM.
After that, the Lambda will refresh tokens automatically.

Usage:
    python -m favvocoaster.bootstrap_token

Requires:
    - AWS credentials configured (aws configure or env vars)
    - SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET set
    - SSM_TOKEN_PARAM set (optional, defaults to /favvocoaster/spotify_token)
"""

import json
import os

import boto3
import spotipy
from spotipy.oauth2 import SpotifyOAuth

SCOPES = [
    "user-library-read",
    "user-read-playback-state",
    "user-modify-playback-state",
    "user-read-currently-playing",
]


def main():
    # Get credentials
    client_id = os.environ.get("SPOTIFY_CLIENT_ID")
    client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET")
    redirect_uri = os.environ.get("SPOTIFY_REDIRECT_URI", "http://localhost:8888/callback")
    ssm_param = os.environ.get("SSM_TOKEN_PARAM", "/favvocoaster/spotify_token")

    if not client_id or not client_secret:
        print("❌ Set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET env vars")
        return 1

    print("🎵 FavvoCoaster Token Bootstrap")
    print("=" * 40)
    print(f"Client ID: {client_id[:8]}...")
    print(f"Redirect URI: {redirect_uri}")
    print(f"SSM Parameter: {ssm_param}")
    print()

    # Authenticate with Spotify (opens browser)
    print("Opening browser for Spotify authentication...")
    auth_manager = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope=" ".join(SCOPES),
        open_browser=True,
    )

    # Force auth flow
    sp = spotipy.Spotify(auth_manager=auth_manager)
    user = sp.current_user()
    print(f"✓ Authenticated as: {user['display_name']} ({user['id']})")

    # Get the token
    token_info = auth_manager.get_cached_token()
    if not token_info:
        print("❌ Failed to get token")
        return 1

    # Upload to SSM
    print(f"\nUploading token to SSM: {ssm_param}")
    ssm = boto3.client("ssm")

    try:
        ssm.put_parameter(
            Name=ssm_param,
            Value=json.dumps(token_info),
            Type="SecureString",
            Overwrite=True,
        )
        print("✓ Token uploaded to SSM Parameter Store")
    except Exception as e:
        print(f"❌ Failed to upload to SSM: {e}")
        return 1

    print("\n✅ Bootstrap complete! Lambda can now use the token.")
    print("   The token will auto-refresh when it expires.")

    # Cleanup local cache
    if os.path.exists(".cache"):
        os.remove(".cache")
        print("   (Removed local .cache file)")

    return 0


if __name__ == "__main__":
    exit(main())
