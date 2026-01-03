"""HTTP request/response logging for debugging API calls.

Provides millisecond-precision timing and logs to a separate file.
Strips authorization headers for security.
"""

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

# Create a dedicated logger for HTTP traffic
http_logger = logging.getLogger("favvocoaster.http")

# Headers to redact from logs
SENSITIVE_HEADERS = {"authorization", "x-tidal-token", "cookie", "set-cookie"}


def setup_http_logging(
    log_file: Optional[Path] = None,
    console: bool = False,
) -> None:
    """Configure HTTP request/response logging.

    Args:
        log_file: Path to log file. Defaults to favvocoaster_http.log
        console: Also log to console (very verbose!)
    """
    log_file = log_file or Path("favvocoaster_http.log")

    # Create formatter with millisecond precision
    formatter = logging.Formatter(
        "%(asctime)s.%(msecs)03d [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # File handler
    file_handler = logging.FileHandler(log_file, mode="a")
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)
    http_logger.addHandler(file_handler)

    # Optional console handler
    if console:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(logging.DEBUG)
        http_logger.addHandler(console_handler)

    http_logger.setLevel(logging.DEBUG)
    http_logger.propagate = False  # Don't bubble up to root logger

    http_logger.info(f"=== HTTP logging started at {datetime.now().isoformat()} ===")


def _sanitize_headers(headers: dict) -> dict:
    """Remove sensitive headers from log output."""
    return {
        k: ("***REDACTED***" if k.lower() in SENSITIVE_HEADERS else v)
        for k, v in headers.items()
    }


def _truncate(text: str, max_len: int = 2000) -> str:
    """Truncate long response bodies."""
    if len(text) <= max_len:
        return text
    return text[:max_len] + f"... [truncated, {len(text)} total chars]"


class TimedRequestsSession:
    """Wrapper around requests.Session that logs all HTTP calls with timing."""

    def __init__(self, session):
        self._session = session
        self._request_counter = 0

    def request(self, method: str, url: str, **kwargs) -> "requests.Response":
        """Make a request and log it with timing."""
        self._request_counter += 1
        req_id = self._request_counter

        # Extract and sanitize headers
        headers = kwargs.get("headers", {})
        safe_headers = _sanitize_headers(headers)

        # Log request
        params = kwargs.get("params", {})
        # Also sanitize params that might have sensitive data
        safe_params = {k: v for k, v in params.items() if k.lower() != "sessionid"}
        if "sessionId" in params:
            safe_params["sessionId"] = "***REDACTED***"

        http_logger.debug(
            f"[REQ-{req_id}] --> {method} {url}\n"
            f"    Params: {safe_params}\n"
            f"    Headers: {safe_headers}"
        )

        # Time the request
        start = time.perf_counter()
        try:
            response = self._session.request(method, url, **kwargs)
            elapsed_ms = (time.perf_counter() - start) * 1000

            # Log response
            resp_headers = _sanitize_headers(dict(response.headers))
            body_preview = _truncate(response.text)

            http_logger.debug(
                f"[REQ-{req_id}] <-- {response.status_code} {response.reason} "
                f"({elapsed_ms:.1f}ms)\n"
                f"    Headers: {resp_headers}\n"
                f"    Body: {body_preview}"
            )

            return response

        except Exception as e:
            elapsed_ms = (time.perf_counter() - start) * 1000
            http_logger.error(
                f"[REQ-{req_id}] <-- ERROR after {elapsed_ms:.1f}ms: {e}"
            )
            raise

    # Delegate all other attributes to the wrapped session
    def __getattr__(self, name):
        return getattr(self._session, name)


def patch_tidalapi_session(tidal_session) -> None:
    """Patch a tidalapi Session to log all HTTP requests.

    Args:
        tidal_session: A tidalapi.Session instance
    """
    if hasattr(tidal_session, "_http_logging_patched"):
        return  # Already patched

    original_request_session = tidal_session.request_session
    tidal_session.request_session = TimedRequestsSession(original_request_session)
    tidal_session._http_logging_patched = True

    http_logger.info("Patched tidalapi session for HTTP logging")


def patch_spotipy_client(spotify_client) -> None:
    """Patch a spotipy.Spotify client to log all HTTP requests.

    Args:
        spotify_client: A spotipy.Spotify instance
    """
    if hasattr(spotify_client, "_http_logging_patched"):
        return  # Already patched

    # Spotipy uses _session internally
    if hasattr(spotify_client, "_session"):
        original_session = spotify_client._session
        spotify_client._session = TimedRequestsSession(original_session)
        spotify_client._http_logging_patched = True
        http_logger.info("Patched spotipy client for HTTP logging")
