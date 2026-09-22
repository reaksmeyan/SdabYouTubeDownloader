# YouTube Downloader (Desktop, Windows)

A small local desktop app with a Tkinter GUI that lets you save a YouTube
video to your computer as an **MP4** (video) or **MP3** (audio-only) file.
It runs entirely on your own machine — there is no server, account, or
cloud component involved.

## ⚖️ Legal notice — read this first

Only use this tool to download videos you **own**, that are licensed for
download/reuse (e.g. Creative Commons, public domain), or for which you
otherwise have the copyright holder's permission. Downloading copyrighted
videos without permission may violate YouTube's
[Terms of Service](https://www.youtube.com/static?template=terms) and
copyright law in your country. You are solely responsible for how you use
this software. This project does not circumvent any DRM/encryption — it
simply automates saving a media stream that your browser would otherwise
stream and discard, using the open-source `yt-dlp` library.

## Requirements

- **Python 3.12+** (Windows): https://www.python.org/downloads/windows/
  - When installing, tick **"Add python.exe to PATH"**.
- **ffmpeg** — required for MP3 conversion and for merging high-resolution
  (720p+) video/audio streams into a single MP4. See install steps below.

## 1. Get the project files

Place `main.py`, `downloader.py`, `utils.py`, and `requirements.txt` in the
same folder, e.g. `C:\Users\<you>\Documents\yt_downloader\`.

## 2. Install Python dependencies

Open **Command Prompt** or **PowerShell** in that folder and run:

```bat
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

(Using a virtual environment (`venv`) is optional but recommended so this
project's dependencies don't affect other Python projects on your machine.)

Tkinter itself does **not** need to be installed separately — it ships
with the standard Windows Python installer.

## 3. Install ffmpeg (Windows)

Pick one:

**Option A — winget (Windows 10/11, easiest):**
```bat
winget install ffmpeg
```

**Option B — manual install:**
1. Download a Windows build from https://www.gyan.dev/ffmpeg/builds/
   (choose the "release essentials" `.zip`).
2. Extract it, e.g. to `C:\ffmpeg`.
3. Add `C:\ffmpeg\bin` to your **System PATH**:
   Settings → System → About → Advanced system settings →
   Environment Variables → edit `Path` → add `C:\ffmpeg\bin`.
4. Open a **new** terminal and confirm it worked:
   ```bat
   ffmpeg -version
   ```

The app will detect on startup whether `ffmpeg` is missing and show a
warning in its log panel; MP4 downloads at 360p may still work without it,
but MP3 conversion and higher-resolution MP4s require it.

## 4. Run the app

```bat
venv\Scripts\activate
python main.py
```

## Using the app

1. Paste a YouTube video URL (e.g. `https://www.youtube.com/watch?v=...`
   or `https://youtu.be/...`).
2. Choose **MP4** or **MP3**.
3. Pick a quality/bitrate (or leave the default).
4. Choose (or accept the default) output folder.
5. Click **Download** and watch progress in the status line and log panel.
6. A confirmation dialog appears with the saved file's path when it's done.

## Project structure

```
yt_downloader/
├── main.py          # Tkinter GUI (presentation layer only)
├── downloader.py     # yt-dlp wrapper: builds options, reports progress, error handling
├── utils.py           # Small standalone helpers (URL check, ffmpeg check, formatting)
├── requirements.txt   # Python dependencies
└── README.md
```

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| "ffmpeg was not found" | Install ffmpeg and ensure `C:\ffmpeg\bin` (or wherever you extracted it) is on PATH, then restart the app. |
| "That doesn't look like a valid YouTube URL" | Make sure you copied the full `https://www.youtube.com/watch?v=...` or `https://youtu.be/...` link. |
| "This video is age-restricted..." / "This video is unavailable" | Some videos require a signed-in YouTube account or are region-locked; this app intentionally does not support logging in with your account credentials. |
| Downloads are slow | Speed depends on your internet connection and YouTube's serving speed for the chosen quality; try a lower quality/resolution. |
| `yt-dlp` errors after YouTube changes something | Update the library: `pip install -U yt-dlp` |

## Notes on how it works

- Video/audio extraction is handled by [`yt-dlp`](https://github.com/yt-dlp/yt-dlp),
  an actively maintained, open-source fork of `youtube-dl`.
- Downloads run in a background thread so the GUI never freezes; progress
  updates are passed to the main thread via a thread-safe queue, which is
  the standard, safe way to bridge worker threads and Tkinter.
- For MP4, yt-dlp downloads the best available video-only and audio-only
  streams and uses ffmpeg to merge them into one `.mp4` file (this is how
  YouTube serves most resolutions above 360p).
- For MP3, yt-dlp downloads the best audio stream and uses ffmpeg to
  transcode it to MP3 at your chosen bitrate.
