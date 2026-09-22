"""
utils.py
--------
Small, reusable helper functions used by the rest of the application:
- validating that a string looks like a YouTube URL
- checking that ffmpeg is available on the system (required for MP3 conversion
  and for merging separate audio/video streams into a single MP4)
- formatting byte counts and ETAs for the progress display
"""

from __future__ import annotations

import re
import shutil

# A reasonably strict (but not overly clever) pattern for the YouTube URLs
# a normal user is likely to paste: standard watch URLs, short youtu.be links,
# and shorts links. This is intentionally permissive about query parameters.
_YOUTUBE_URL_PATTERN = re.compile(
    r"^(https?://)?(www\.)?"
    r"(youtube\.com/(watch\?v=|shorts/|embed/)|youtu\.be/)"
    r"[A-Za-z0-9_\-]{6,}",
    re.IGNORECASE,
)


def is_probably_youtube_url(url: str) -> bool:
    """Return True if `url` looks like a YouTube video URL.

    This is a lightweight sanity check only. The real validation happens
    when yt-dlp tries to extract information from the URL - that is the
    authoritative check. This function just helps catch obvious typos
    (empty strings, pasted text that isn't a URL at all, etc.) early,
    with a friendly error message instead of a stack trace.
    """
    if not url:
        return False
    return bool(_YOUTUBE_URL_PATTERN.match(url.strip()))


def ffmpeg_is_available() -> bool:
    """Return True if an `ffmpeg` executable can be found on PATH.

    ffmpeg is required by yt-dlp to:
      * extract/convert audio to MP3, and
      * merge separately-downloaded video-only and audio-only streams into
        a single MP4 file (needed for most videos above 360p on YouTube).

    It is NOT bundled with this application - the user must install it
    separately (see README.md for Windows install instructions).
    """
    return shutil.which("ffmpeg") is not None


def format_bytes(num_bytes) -> str:
    """Format a byte count as a short human-readable string, e.g. '12.3 MB'."""
    if num_bytes is None:
        return "?"
    try:
        num_bytes = float(num_bytes)
    except (TypeError, ValueError):
        return "?"

    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num_bytes < 1024.0:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} PB"


def format_eta(seconds) -> str:
    """Format a countdown in seconds as 'MM:SS', or '--:--' if unknown."""
    if seconds is None:
        return "--:--"
    try:
        seconds = int(seconds)
    except (TypeError, ValueError):
        return "--:--"
    minutes, secs = divmod(max(seconds, 0), 60)
    return f"{minutes:02d}:{secs:02d}"


def sanitize_folder_path(path: str) -> str:
    """Strip surrounding whitespace/quotes a user might accidentally paste
    in when copying a folder path from Windows Explorer's address bar."""
    return path.strip().strip('"').strip("'")
