"""
main.py
-------
Entry point for the Sdab YouTube Downloader desktop application.

Run with:  python main.py

This module contains only GUI/presentation code (Tkinter). All download
logic lives in downloader.py, and small helpers live in utils.py, so the
project stays easy to navigate and test. The visual styling below uses
only the Python standard library (tkinter/ttk) - no extra GUI dependency
is required.
"""

from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, ttk

from downloader import DownloadError, ProgressInfo, download
from utils import (
    ffmpeg_is_available,
    format_bytes,
    format_eta,
    is_probably_youtube_url,
    sanitize_folder_path,
)

# ---------------------------------------------------------------------------
# App metadata (shown in the title bar and Help -> About dialog)
# ---------------------------------------------------------------------------
APP_NAME = "Sdab YouTube Downloader"
APP_VERSION = "1.0"
APP_AUTHOR = "Reaksmey An"
APP_GITHUB_URL = "https://github.com/reaksmeyan"

APP_MIN_SIZE = (620, 620)

MP4_QUALITIES = ["best", "2160", "1440", "1080", "720", "480", "360"]
MP3_QUALITIES = ["320", "256", "192", "128", "96"]

DISCLAIMER_TEXT = (
    "For personal use with content you own or are permitted to download only. "
    "Respect YouTube's Terms of Service and applicable copyright law."
)

# ---------------------------------------------------------------------------
# Color palette - a single place to tweak the look of the whole app
# ---------------------------------------------------------------------------
COLOR_BG = "#f4f5fb"          # window background
COLOR_CARD = "#ffffff"        # card/panel background
COLOR_BORDER = "#e3e6f0"      # subtle card border
COLOR_TEXT = "#1e2233"        # primary text
COLOR_TEXT_MUTED = "#767b91"  # secondary text

COLOR_PRIMARY = "#5b4bf5"       # accent (buttons, focus, selected states)
COLOR_PRIMARY_HOVER = "#4837e0"
COLOR_PRIMARY_SOFT = "#eeecfe"  # light tint of the accent, for unselected pills

COLOR_SUCCESS = "#18a558"
COLOR_SUCCESS_SOFT = "#e6f7ee"
COLOR_DANGER = "#e64848"
COLOR_DANGER_SOFT = "#fdecec"
COLOR_WARNING = "#e08b2b"
COLOR_WARNING_SOFT = "#fdf1e2"

GRADIENT_START = "#5b4bf5"
GRADIENT_END = "#9155f0"

FONT_FAMILY = "Segoe UI"  # falls back gracefully on non-Windows systems


# ---------------------------------------------------------------------------
# Small color helpers used to paint the gradient header
# ---------------------------------------------------------------------------
def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def _rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#%02x%02x%02x" % rgb


def _blend(c1: str, c2: str, t: float) -> str:
    r1, g1, b1 = _hex_to_rgb(c1)
    r2, g2, b2 = _hex_to_rgb(c2)
    return _rgb_to_hex(
        (
            int(r1 + (r2 - r1) * t),
            int(g1 + (g2 - g1) * t),
            int(b1 + (b2 - b1) * t),
        )
    )


class PillButton(tk.Button):
    """A flat, rounded-feeling button with a hover color change.

    Real rounded corners aren't available in plain tkinter without extra
    image assets, so this uses a flat, borderless button with generous
    padding and a hover-state color swap, which reads as "modern enough"
    without adding any external dependency.
    """

    def __init__(
        self,
        parent,
        text: str,
        command,
        bg: str,
        fg: str,
        hover_bg: str | None = None,
        font_size: int = 10,
        bold: bool = True,
        **kwargs,
    ) -> None:
        self._bg = bg
        self._hover_bg = hover_bg or bg
        self._fg = fg
        super().__init__(
            parent,
            text=text,
            command=command,
            bg=bg,
            fg=fg,
            activebackground=self._hover_bg,
            activeforeground=fg,
            relief="flat",
            bd=0,
            cursor="hand2",
            font=(FONT_FAMILY, font_size, "bold" if bold else "normal"),
            padx=16,
            pady=8,
            highlightthickness=0,
            **kwargs,
        )
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)

    def _on_enter(self, _event=None) -> None:
        if str(self["state"]) != "disabled":
            self.configure(bg=self._hover_bg)

    def _on_leave(self, _event=None) -> None:
        if str(self["state"]) != "disabled":
            self.configure(bg=self._bg)

    def set_colors(self, bg: str, fg: str, hover_bg: str | None = None) -> None:
        self._bg = bg
        self._fg = fg
        self._hover_bg = hover_bg or bg
        self.configure(bg=bg, fg=fg, activebackground=self._hover_bg, activeforeground=fg)


class YouTubeDownloaderApp(tk.Tk):
    """Main application window."""

    def __init__(self) -> None:
        super().__init__()
        self.title(APP_NAME)
        self.minsize(*APP_MIN_SIZE)
        self.geometry("680x700")
        self.configure(bg=COLOR_BG)

        # Queue used to pass progress updates safely from the background
        # download thread back to the main GUI thread.
        self._progress_queue: "queue.Queue[ProgressInfo]" = queue.Queue()
        self._download_thread: threading.Thread | None = None
        self._is_downloading = False

        self.output_dir = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "Downloads"))
        self.url_var = tk.StringVar()
        self.format_var = tk.StringVar(value="mp4")
        self.quality_var = tk.StringVar(value="best")
        self.status_var = tk.StringVar(value="Ready.")

        self._configure_ttk_style()
        self._build_menu()
        self._build_widgets()
        self._check_ffmpeg_and_warn()
        self._poll_progress_queue()

    # ------------------------------------------------------------------
    # Style
    # ------------------------------------------------------------------
    def _configure_ttk_style(self) -> None:
        style = ttk.Style(self)
        # "clam" is the theme that best supports custom colors across
        # platforms - the default Windows theme largely ignores them.
        style.theme_use("clam")

        style.configure(
            "TEntry",
            fieldbackground=COLOR_CARD,
            bordercolor=COLOR_BORDER,
            lightcolor=COLOR_BORDER,
            darkcolor=COLOR_BORDER,
            padding=8,
            relief="flat",
        )
        style.map(
            "TEntry",
            bordercolor=[("focus", COLOR_PRIMARY)],
            lightcolor=[("focus", COLOR_PRIMARY)],
            darkcolor=[("focus", COLOR_PRIMARY)],
        )

        style.configure(
            "TCombobox",
            fieldbackground=COLOR_CARD,
            background=COLOR_CARD,
            bordercolor=COLOR_BORDER,
            arrowcolor=COLOR_PRIMARY,
            padding=6,
            relief="flat",
        )
        style.map("TCombobox", bordercolor=[("focus", COLOR_PRIMARY)])

        # Progress bar - a neutral style plus color variants that we swap
        # between depending on download state (in progress / done / error).
        for name, color in (
            ("Accent", COLOR_PRIMARY),
            ("Success", COLOR_SUCCESS),
            ("Danger", COLOR_DANGER),
        ):
            style.configure(
                f"{name}.Horizontal.TProgressbar",
                troughcolor=COLOR_BORDER,
                background=color,
                bordercolor=COLOR_BORDER,
                lightcolor=color,
                darkcolor=color,
                thickness=16,
            )

        style.configure("TScrollbar", background=COLOR_BORDER, troughcolor=COLOR_BG, arrowsize=12)

    # ------------------------------------------------------------------
    # Menu bar
    # ------------------------------------------------------------------
    def _build_menu(self) -> None:
        menu_bar = tk.Menu(self)

        file_menu = tk.Menu(menu_bar, tearoff=0)
        file_menu.add_command(label="Choose Output Folder...", command=self._browse_folder)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.destroy)
        menu_bar.add_cascade(label="File", menu=file_menu)

        help_menu = tk.Menu(menu_bar, tearoff=0)
        help_menu.add_command(
            label="Project on GitHub", command=lambda: webbrowser.open(APP_GITHUB_URL)
        )
        help_menu.add_separator()
        help_menu.add_command(label="About", command=self._show_about_dialog)
        menu_bar.add_cascade(label="Help", menu=help_menu)

        self.configure(menu=menu_bar)

    def _show_about_dialog(self) -> None:
        AboutDialog(self)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_widgets(self) -> None:
        self._build_header()

        body = tk.Frame(self, bg=COLOR_BG)
        body.pack(fill="both", expand=True, padx=20, pady=(0, 16))
        body.columnconfigure(0, weight=1)

        self._build_url_card(body, row=0)
        self._build_options_card(body, row=1)
        self._build_folder_card(body, row=2)
        self._build_action_row(body, row=3)
        self._build_progress_section(body, row=4)
        self._build_log_card(body, row=5)
        body.rowconfigure(5, weight=1)

        disclaimer = tk.Label(
            body,
            text=DISCLAIMER_TEXT,
            bg=COLOR_BG,
            fg=COLOR_TEXT_MUTED,
            wraplength=640,
            justify="left",
            font=(FONT_FAMILY, 8),
        )
        disclaimer.grid(row=6, column=0, sticky="ew", pady=(10, 0))

    def _build_header(self) -> None:
        height = 92
        canvas = tk.Canvas(self, height=height, highlightthickness=0, bd=0)
        canvas.pack(fill="x", side="top")

        def draw(_event=None) -> None:
            canvas.delete("all")
            width = max(canvas.winfo_width(), 1)
            steps = 60
            for i in range(steps):
                t = i / steps
                color = _blend(GRADIENT_START, GRADIENT_END, t)
                x0 = int(width * i / steps)
                x1 = int(width * (i + 1) / steps)
                canvas.create_rectangle(x0, 0, x1, height, fill=color, width=0)
            canvas.create_text(
                24, height // 2 - 10, anchor="w",
                text="\u25B6  " + APP_NAME,
                fill="white", font=(FONT_FAMILY, 18, "bold"),
            )
            canvas.create_text(
                24, height // 2 + 18, anchor="w",
                text="Save YouTube videos as MP4 or MP3, right from your desktop",
                fill="#eae7ff", font=(FONT_FAMILY, 9),
            )
            canvas.create_text(
                width - 20, height - 14, anchor="e",
                text=f"v{APP_VERSION}",
                fill="#eae7ff", font=(FONT_FAMILY, 8),
            )

        canvas.bind("<Configure>", draw)
        self._header_canvas = canvas

    def _make_card(self, parent, title: str, icon: str, row: int) -> tk.Frame:
        outer = tk.Frame(parent, bg=COLOR_CARD, highlightbackground=COLOR_BORDER,
                          highlightthickness=1, bd=0)
        outer.grid(row=row, column=0, sticky="ew", pady=(0, 14))
        outer.columnconfigure(0, weight=1)

        header = tk.Label(
            outer, text=f"{icon}  {title}", bg=COLOR_CARD, fg=COLOR_TEXT,
            font=(FONT_FAMILY, 10, "bold"), anchor="w",
        )
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 4))

        content = tk.Frame(outer, bg=COLOR_CARD)
        content.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 16))
        content.columnconfigure(0, weight=1)
        return content

    def _build_url_card(self, parent, row: int) -> None:
        content = self._make_card(parent, "YouTube URL", "\U0001F517", row)
        self.url_entry = ttk.Entry(content, textvariable=self.url_var, font=(FONT_FAMILY, 10))
        self.url_entry.grid(row=0, column=0, sticky="ew", ipady=6)
        self.url_entry.focus_set()

    def _build_options_card(self, parent, row: int) -> None:
        content = self._make_card(parent, "Format & Quality", "\u2699", row)
        content.columnconfigure(0, weight=1)

        # --- Segmented "pill" toggle for MP4 / MP3, instead of plain
        # radio buttons - visually clearer and more interactive to click.
        toggle_row = tk.Frame(content, bg=COLOR_CARD)
        toggle_row.grid(row=0, column=0, sticky="w", pady=(0, 14))

        self.mp4_button = PillButton(
            toggle_row, text="\U0001F3AC  MP4 Video", command=lambda: self._select_format("mp4"),
            bg=COLOR_PRIMARY, fg="white", hover_bg=COLOR_PRIMARY_HOVER,
        )
        self.mp4_button.grid(row=0, column=0, padx=(0, 8))

        self.mp3_button = PillButton(
            toggle_row, text="\U0001F3B5  MP3 Audio", command=lambda: self._select_format("mp3"),
            bg=COLOR_PRIMARY_SOFT, fg=COLOR_PRIMARY,
        )
        self.mp3_button.grid(row=0, column=1)

        # --- Quality dropdown
        quality_row = tk.Frame(content, bg=COLOR_CARD)
        quality_row.grid(row=1, column=0, sticky="w")

        tk.Label(
            quality_row, text="Quality:", bg=COLOR_CARD, fg=COLOR_TEXT_MUTED,
            font=(FONT_FAMILY, 9),
        ).grid(row=0, column=0, sticky="w", padx=(0, 8))

        self.quality_combo = ttk.Combobox(
            quality_row, textvariable=self.quality_var, values=MP4_QUALITIES,
            state="readonly", width=14, font=(FONT_FAMILY, 9),
        )
        self.quality_combo.grid(row=0, column=1)

    def _build_folder_card(self, parent, row: int) -> None:
        content = self._make_card(parent, "Save To", "\U0001F4C1", row)
        content.columnconfigure(0, weight=1)

        self.folder_entry = ttk.Entry(content, textvariable=self.output_dir, font=(FONT_FAMILY, 10))
        self.folder_entry.grid(row=0, column=0, sticky="ew", ipady=6)

        browse_btn = PillButton(
            content, text="Browse...", command=self._browse_folder,
            bg=COLOR_PRIMARY_SOFT, fg=COLOR_PRIMARY, font_size=9,
        )
        browse_btn.grid(row=0, column=1, padx=(10, 0))

    def _build_action_row(self, parent, row: int) -> None:
        row_frame = tk.Frame(parent, bg=COLOR_BG)
        row_frame.grid(row=row, column=0, sticky="ew", pady=(0, 14))

        self.download_button = PillButton(
            row_frame, text="\u2B07  Download", command=self._on_download_clicked,
            bg=COLOR_PRIMARY, fg="white", hover_bg=COLOR_PRIMARY_HOVER, font_size=11,
        )
        self.download_button.grid(row=0, column=0)

        self.cancel_button = PillButton(
            row_frame, text="Cancel", command=self._on_cancel_clicked,
            bg=COLOR_BORDER, fg=COLOR_TEXT_MUTED, font_size=10,
        )
        self.cancel_button.grid(row=0, column=1, padx=(10, 0))
        self.cancel_button.configure(state="disabled", cursor="arrow")

    def _build_progress_section(self, parent, row: int) -> None:
        frame = tk.Frame(parent, bg=COLOR_BG)
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 14))
        frame.columnconfigure(0, weight=1)

        self.progress_bar = ttk.Progressbar(
            frame, orient="horizontal", mode="determinate", maximum=100,
            style="Accent.Horizontal.TProgressbar",
        )
        self.progress_bar.grid(row=0, column=0, sticky="ew")

        self.status_label = tk.Label(
            frame, textvariable=self.status_var, bg=COLOR_BG, fg=COLOR_TEXT_MUTED,
            font=(FONT_FAMILY, 9), anchor="w",
        )
        self.status_label.grid(row=1, column=0, sticky="ew", pady=(8, 0))

    def _build_log_card(self, parent, row: int) -> None:
        outer = tk.Frame(parent, bg=COLOR_CARD, highlightbackground=COLOR_BORDER,
                          highlightthickness=1, bd=0)
        outer.grid(row=row, column=0, sticky="nsew")
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(1, weight=1)

        tk.Label(
            outer, text="\U0001F4CB  Log", bg=COLOR_CARD, fg=COLOR_TEXT,
            font=(FONT_FAMILY, 10, "bold"), anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 4))

        text_frame = tk.Frame(outer, bg=COLOR_CARD)
        text_frame.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))
        text_frame.columnconfigure(0, weight=1)
        text_frame.rowconfigure(0, weight=1)

        self.log_text = tk.Text(
            text_frame, height=8, state="disabled", wrap="word", relief="flat",
            bg="#fbfbfe", fg=COLOR_TEXT, font=("Consolas", 9), padx=10, pady=8,
            highlightthickness=1, highlightbackground=COLOR_BORDER,
        )
        self.log_text.grid(row=0, column=0, sticky="nsew")
        self.log_text.tag_configure("error", foreground=COLOR_DANGER)
        self.log_text.tag_configure("warning", foreground=COLOR_WARNING)
        self.log_text.tag_configure("success", foreground=COLOR_SUCCESS)
        self.log_text.tag_configure("muted", foreground=COLOR_TEXT_MUTED)

        log_scroll = ttk.Scrollbar(text_frame, orient="vertical", command=self.log_text.yview)
        log_scroll.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=log_scroll.set)

    # ------------------------------------------------------------------
    # Format toggle
    # ------------------------------------------------------------------
    def _select_format(self, fmt: str) -> None:
        self.format_var.set(fmt)
        if fmt == "mp4":
            self.mp4_button.set_colors(COLOR_PRIMARY, "white", COLOR_PRIMARY_HOVER)
            self.mp3_button.set_colors(COLOR_PRIMARY_SOFT, COLOR_PRIMARY)
            self.quality_combo.configure(values=MP4_QUALITIES)
            self.quality_var.set("best")
        else:
            self.mp3_button.set_colors(COLOR_PRIMARY, "white", COLOR_PRIMARY_HOVER)
            self.mp4_button.set_colors(COLOR_PRIMARY_SOFT, COLOR_PRIMARY)
            self.quality_combo.configure(values=MP3_QUALITIES)
            self.quality_var.set("192")

    # ------------------------------------------------------------------
    # Startup checks
    # ------------------------------------------------------------------
    def _check_ffmpeg_and_warn(self) -> None:
        if not ffmpeg_is_available():
            self._log(
                "WARNING: ffmpeg was not found on this system. MP3 conversion and "
                "merging high-resolution MP4 streams will fail until it is installed. "
                "See README.md for instructions.",
                tag="warning",
            )
            self._set_status("Warning: ffmpeg not found - see log and README.md", COLOR_WARNING)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------
    def _browse_folder(self) -> None:
        chosen = filedialog.askdirectory(initialdir=self.output_dir.get() or os.getcwd())
        if chosen:
            self.output_dir.set(chosen)

    def _on_download_clicked(self) -> None:
        if self._is_downloading:
            return

        url = self.url_var.get().strip()
        out_dir = sanitize_folder_path(self.output_dir.get())
        fmt = self.format_var.get()
        quality = self.quality_var.get()

        if not is_probably_youtube_url(url):
            messagebox.showerror(
                APP_NAME, "Please paste a valid YouTube video URL "
                "(e.g. https://www.youtube.com/watch?v=... or https://youtu.be/...)."
            )
            return

        if not out_dir:
            messagebox.showerror(APP_NAME, "Please choose an output folder.")
            return

        if not os.path.isdir(out_dir):
            try:
                os.makedirs(out_dir, exist_ok=True)
            except OSError as exc:
                messagebox.showerror(APP_NAME, f"Could not create output folder:\n{exc}")
                return

        if fmt == "mp3" and not ffmpeg_is_available():
            messagebox.showerror(
                APP_NAME,
                "MP3 conversion requires ffmpeg, which was not found on this system.\n\n"
                "Please install ffmpeg first (see README.md) and try again.",
            )
            return

        self._start_download(url, out_dir, fmt, quality)

    def _on_cancel_clicked(self) -> None:
        # yt-dlp does not offer a clean mid-download cancel hook when used
        # as a library in a simple synchronous call, so we mark the flag
        # and let the user know the current file will still finish; the
        # important, honest thing is not to claim we stopped a download
        # that is actually still running in the background thread.
        self._log(
            "Cancel requested. The current file will finish downloading; "
            "close the app if you need to stop immediately.",
            tag="warning",
        )
        self.cancel_button.configure(state="disabled", cursor="arrow")

    # ------------------------------------------------------------------
    # Download orchestration
    # ------------------------------------------------------------------
    def _start_download(self, url: str, out_dir: str, fmt: str, quality: str) -> None:
        self._is_downloading = True
        self.download_button.configure(state="disabled", cursor="arrow")
        self.cancel_button.configure(state="normal", cursor="hand2")
        self.progress_bar.configure(style="Accent.Horizontal.TProgressbar", value=0)
        self._set_status("Starting download...", COLOR_TEXT_MUTED)
        self._log(f"Starting {fmt.upper()} download: {url}")

        def progress_callback(info: ProgressInfo) -> None:
            # Called from the background thread - just hand it off to the
            # thread-safe queue; the actual GUI update happens on the main
            # thread inside _poll_progress_queue.
            self._progress_queue.put(info)

        def worker() -> None:
            try:
                final_path = download(url, out_dir, fmt, quality, progress_callback)
                self._progress_queue.put(
                    ProgressInfo(status="done", percent=100.0, message=final_path)
                )
            except DownloadError as exc:
                self._progress_queue.put(ProgressInfo(status="error", message=str(exc)))
            except Exception as exc:  # noqa: BLE001
                self._progress_queue.put(
                    ProgressInfo(status="error", message=f"Unexpected error: {exc}")
                )

        self._download_thread = threading.Thread(target=worker, daemon=True)
        self._download_thread.start()

    def _poll_progress_queue(self) -> None:
        try:
            while True:
                info = self._progress_queue.get_nowait()
                self._handle_progress_info(info)
        except queue.Empty:
            pass
        finally:
            # Reschedule ourselves - this is the standard safe pattern for
            # bridging a worker thread to the Tkinter main loop.
            self.after(150, self._poll_progress_queue)

    def _set_status(self, text: str, color: str) -> None:
        self.status_var.set(text)
        self.status_label.configure(fg=color)

    def _handle_progress_info(self, info: ProgressInfo) -> None:
        if info.status == "downloading":
            self.progress_bar.configure(value=info.percent)
            speed = format_bytes(info.speed) + "/s" if info.speed else "?"
            eta = format_eta(info.eta)
            self._set_status(
                f"\u2B07  Downloading {info.filename or ''}   "
                f"{info.percent:0.1f}%   {speed}   ETA {eta}",
                COLOR_TEXT_MUTED,
            )
        elif info.status == "converting":
            self.progress_bar.configure(value=100)
            self._set_status(info.message or "Converting...", COLOR_PRIMARY)
        elif info.status == "finished":
            self._set_status(info.message or "Finishing up...", COLOR_PRIMARY)
        elif info.status == "done":
            self._is_downloading = False
            self.download_button.configure(state="normal", cursor="hand2")
            self.cancel_button.configure(state="disabled", cursor="arrow")
            self.progress_bar.configure(style="Success.Horizontal.TProgressbar", value=100)
            self._set_status("\u2705  Download complete.", COLOR_SUCCESS)
            self._log(f"Saved to: {info.message}", tag="success")
            messagebox.showinfo(APP_NAME, f"Download complete!\n\nSaved to:\n{info.message}")
        elif info.status == "error":
            self._is_downloading = False
            self.download_button.configure(state="normal", cursor="hand2")
            self.cancel_button.configure(state="disabled", cursor="arrow")
            self.progress_bar.configure(style="Danger.Horizontal.TProgressbar")
            self._set_status("\u274C  Error - see log.", COLOR_DANGER)
            self._log(f"ERROR: {info.message}", tag="error")
            messagebox.showerror(APP_NAME, info.message)

    # ------------------------------------------------------------------
    # Logging helper
    # ------------------------------------------------------------------
    def _log(self, message: str, tag: str | None = None) -> None:
        self.log_text.configure(state="normal")
        if tag:
            self.log_text.insert("end", message + "\n", tag)
        else:
            self.log_text.insert("end", message + "\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")


class AboutDialog(tk.Toplevel):
    """Modal 'Help -> About' dialog showing app metadata and a clickable
    link to the project's GitHub page."""

    def __init__(self, parent: YouTubeDownloaderApp) -> None:
        super().__init__(parent)
        self.title(f"About {APP_NAME}")
        self.configure(bg=COLOR_CARD)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        width, height = 360, 300
        self.geometry(f"{width}x{height}")
        self.update_idletasks()
        x = parent.winfo_x() + (parent.winfo_width() - width) // 2
        y = parent.winfo_y() + (parent.winfo_height() - height) // 2
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")

        tk.Label(
            self, text="\u25B6", bg=COLOR_CARD, fg=COLOR_PRIMARY,
            font=(FONT_FAMILY, 30, "bold"),
        ).pack(pady=(24, 6))

        tk.Label(
            self, text=APP_NAME, bg=COLOR_CARD, fg=COLOR_TEXT,
            font=(FONT_FAMILY, 13, "bold"),
        ).pack()

        tk.Label(
            self, text=f"Version {APP_VERSION}", bg=COLOR_CARD, fg=COLOR_TEXT_MUTED,
            font=(FONT_FAMILY, 9),
        ).pack(pady=(2, 16))

        info_frame = tk.Frame(self, bg=COLOR_CARD)
        info_frame.pack(fill="x", padx=30)

        tk.Label(
            info_frame, text="Creative idea", bg=COLOR_CARD, fg=COLOR_TEXT_MUTED,
            font=(FONT_FAMILY, 8), anchor="w",
        ).pack(fill="x")
        tk.Label(
            info_frame, text=APP_AUTHOR, bg=COLOR_CARD, fg=COLOR_TEXT,
            font=(FONT_FAMILY, 10, "bold"), anchor="w",
        ).pack(fill="x", pady=(0, 10))

        tk.Label(
            info_frame, text="GitHub", bg=COLOR_CARD, fg=COLOR_TEXT_MUTED,
            font=(FONT_FAMILY, 8), anchor="w",
        ).pack(fill="x")

        link = tk.Label(
            info_frame, text=APP_GITHUB_URL, bg=COLOR_CARD, fg=COLOR_PRIMARY,
            font=(FONT_FAMILY, 10, "underline"), anchor="w", cursor="hand2",
        )
        link.pack(fill="x")
        link.bind("<Button-1>", lambda _e: webbrowser.open(APP_GITHUB_URL))

        PillButton(
            self, text="Close", command=self.destroy,
            bg=COLOR_PRIMARY, fg="white", hover_bg=COLOR_PRIMARY_HOVER, font_size=9,
        ).pack(pady=(20, 0))


def main() -> None:
    app = YouTubeDownloaderApp()
    app.mainloop()


if __name__ == "__main__":
    main()
