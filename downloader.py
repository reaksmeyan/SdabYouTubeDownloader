"""
downloader.py
-------------
Wraps the `yt-dlp` library (https://github.com/yt-dlp/yt-dlp) and exposes a
single function, `download`, that the GUI layer calls from a background
thread. This module has no knowledge of Tkinter - it just reports progress
and status through plain callback functions, which keeps it reusable and
easy to unit test independently of the GUI.

yt-dlp is used instead of the older/unmaintained `youtube-dl` or hand-rolled
scraping because it is actively maintained, open-source, and handles
YouTube's frequently-changing stream formats correctly.

LEGAL / COMPLIANCE NOTE
------------------------
This module only automates the mechanical act of downloading a file the
user points it at, via a general-purpose open-source tool. It does not
circumvent DRM, and it is the responsibility of the person running the
application to only download videos they own, that are covered by a
license that permits downloading (e.g. Creative Commons), or for which
they otherwise have the rights holder's permission. See README.md.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Callable, Optional

import yt_dlp


class DownloadError(Exception):
    """Raised when a download fails for a reason we want to surface
    to the user in a friendly way (as opposed to a raw traceback)."""


@dataclass
class ProgressInfo:
    status: str  # "downloading", "converting", "finished", "error"
    percent: float = 0.0  # 0-100
    downloaded_bytes: Optional[int] = None
    total_bytes: Optional[int] = None
    speed: Optional[float] = None  # bytes/sec
    eta: Optional[int] = None  # seconds
    filename: Optional[str] = None
    message: str = ""


ProgressCallback = Callable[[ProgressInfo], None]


def _build_ydl_opts(
    output_dir: str,
    fmt: str,
    quality: str,
    progress_callback: ProgressCallback,
) -> dict:
    """Build the options dict passed to yt_dlp.YoutubeDL.

    fmt: "mp4" or "mp3"
    quality: for mp4, a target max height like "1080", "720", "480", or
             "best"; for mp3, a target bitrate like "320", "192", "128".
    """
    outtmpl = os.path.join(output_dir, "%(title).150B [%(id)s].%(ext)s")

    common_opts = {
        "outtmpl": outtmpl,
        "noplaylist": True,  # only download the single video in the URL,
                              # not an entire playlist, unless the user
                              # explicitly pastes a playlist URL and we
                              # decide to support that later
        "progress_hooks": [lambda d: _handle_progress_hook(d, progress_callback)],
        "postprocessor_hooks": [lambda d: _handle_postprocessor_hook(d, progress_callback)],
        "quiet": True,
        "no_warnings": True,
        "restrictfilenames": False,
        "windowsfilenames": True,  # sanitize filenames for Windows filesystems
    }

    if fmt == "mp3":
        bitrate = quality if quality in ("320", "256", "192", "128", "96") else "192"
        common_opts.update(
            {
                "format": "bestaudio/best",
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": bitrate,
                    }
                ],
            }
        )
    else:  # mp4
        if quality and quality != "best":
            # Prefer <= requested height, merged into a single mp4 container.
            common_opts["format"] = (
                f"bestvideo[height<={quality}][ext=mp4]+bestaudio[ext=m4a]/"
                f"best[height<={quality}][ext=mp4]/best[height<={quality}]"
            )
        else:
            common_opts["format"] = (
                "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"
            )
        common_opts["merge_output_format"] = "mp4"

    return common_opts


def _handle_progress_hook(d: dict, progress_callback: ProgressCallback) -> None:
    status = d.get("status")
    if status == "downloading":
        total = d.get("total_bytes") or d.get("total_bytes_estimate")
        downloaded = d.get("downloaded_bytes", 0)
        percent = (downloaded / total * 100) if total else 0.0
        progress_callback(
            ProgressInfo(
                status="downloading",
                percent=percent,
                downloaded_bytes=downloaded,
                total_bytes=total,
                speed=d.get("speed"),
                eta=d.get("eta"),
                filename=os.path.basename(d.get("filename", "")),
            )
        )
    elif status == "finished":
        progress_callback(
            ProgressInfo(
                status="converting",
                percent=100.0,
                filename=os.path.basename(d.get("filename", "")),
                message="Download complete, processing file...",
            )
        )
    elif status == "error":
        progress_callback(ProgressInfo(status="error", message="Download hook reported an error."))


def _handle_postprocessor_hook(d: dict, progress_callback: ProgressCallback) -> None:
    if d.get("status") == "started":
        progress_callback(
            ProgressInfo(status="converting", percent=100.0, message="Converting file...")
        )
    elif d.get("status") == "finished":
        progress_callback(
            ProgressInfo(status="converting", percent=100.0, message="Finalizing...")
        )


def download(
    url: str,
    output_dir: str,
    fmt: str,
    quality: str,
    progress_callback: ProgressCallback,
) -> str:
    """Download a single YouTube video as MP4 or MP3.

    Parameters
    ----------
    url: the YouTube video URL
    output_dir: an existing, writable directory to save the file into
    fmt: "mp4" or "mp3"
    quality: resolution (mp4) or bitrate (mp3), see _build_ydl_opts
    progress_callback: called repeatedly with ProgressInfo updates

    Returns
    -------
    The path to the resulting file, if it can be determined.

    Raises
    ------
    DownloadError on any failure (bad URL, network error, age/region
    restricted video requiring login, missing ffmpeg, etc.) with a
    message suitable for display to the end user.
    """
    if fmt not in ("mp4", "mp3"):
        raise DownloadError(f"Unsupported format: {fmt!r}")

    if not os.path.isdir(output_dir):
        raise DownloadError(f"Output folder does not exist: {output_dir}")

    ydl_opts = _build_ydl_opts(output_dir, fmt, quality, progress_callback)

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            # When ffmpeg post-processing changes the extension (e.g. to
            # .mp3), yt-dlp's `prepare_filename` still reports the
            # pre-conversion name, so we adjust the extension manually.
            final_path = ydl.prepare_filename(info)
            if fmt == "mp3":
                final_path = os.path.splitext(final_path)[0] + ".mp3"
            elif fmt == "mp4":
                final_path = os.path.splitext(final_path)[0] + ".mp4"
    except yt_dlp.utils.DownloadError as exc:
        raise DownloadError(_friendly_error_message(str(exc))) from exc
    except Exception as exc:  # noqa: BLE001 - surface anything unexpected, clearly
        raise DownloadError(f"Unexpected error: {exc}") from exc

    progress_callback(
        ProgressInfo(status="finished", percent=100.0, filename=os.path.basename(final_path),
                     message="Done.")
    )
    return final_path


def _friendly_error_message(raw: str) -> str:
    """Translate a handful of common yt-dlp error strings into messages
    that are easier for a non-technical user to understand."""
    lowered = raw.lower()
    if "ffmpeg" in lowered and "not found" in lowered:
        return (
            "ffmpeg was not found on this system. It is required to convert "
            "to MP3 and to merge high-resolution video/audio streams. "
            "See README.md for installation instructions."
        )
    if "private video" in lowered:
        return "This video is private and cannot be downloaded."
    if "video unavailable" in lowered:
        return "This video is unavailable (it may have been removed or is region-restricted)."
    if "sign in to confirm your age" in lowered or "age" in lowered and "restrict" in lowered:
        return "This video is age-restricted and cannot be downloaded without an account."
    if "unable to download webpage" in lowered or "urlopen error" in lowered:
        return "Could not reach YouTube. Please check your internet connection and try again."
    if "unsupported url" in lowered:
        return "That doesn't look like a valid YouTube URL."
    # Fall back to a trimmed version of the raw message.
    return raw.replace("ERROR: ", "").strip()
