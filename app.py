"""
Video Downloader — Flask Web Server
====================================
Replaces the old Tkinter-based tiktok_downloader.py.
Provides a browser-accessible UI at http://localhost:5000.

Process safety:
  - All spawned subprocesses are tracked in _active_procs.
  - atexit + signal handlers terminate them when the server exits.
  - Closing the launcher CMD window → Python exits → cleanup runs.
"""

import os
import re
import sys
import json
import time
import atexit
import signal
import logging
import threading
import subprocess
import concurrent.futures
import webbrowser
from datetime import datetime
from queue import Queue
from flask import Flask, request, jsonify, Response, send_from_directory

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler("app.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# ── Flask app ────────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder="static", static_url_path="/static")

# ── Global state ─────────────────────────────────────────────────────────────
_active_procs: list = []          # All subprocess.Popen objects we've started
_procs_lock = threading.Lock()

_sse_messages: list = []           # Append-only log for SSE streaming
_sse_lock = threading.Lock()

_stop_event = threading.Event()    # Set to True to cancel current download

_download_state: dict = {
    "running": False,
    "status": "idle",              # idle | downloading | muting | done | error
    "progress": 0,
    "total": 0,
}
_state_lock = threading.Lock()

# ── Process cleanup ───────────────────────────────────────────────────────────
def _cleanup() -> None:
    """Terminate all tracked subprocesses gracefully."""
    logger.info("Cleanup: terminating all child processes...")
    with _procs_lock:
        for proc in list(_active_procs):
            try:
                proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
    logger.info("Cleanup complete.")


atexit.register(_cleanup)


def _signal_handler(sig, frame):
    _cleanup()
    sys.exit(0)


signal.signal(signal.SIGTERM, _signal_handler)

# Windows: handle console window close event
if sys.platform == "win32":
    try:
        import ctypes
        _CTRL_CLOSE_EVENT = 2
        _HandlerRoutine = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_ulong)

        @_HandlerRoutine
        def _win_ctrl_handler(ctrl_type):
            if ctrl_type == _CTRL_CLOSE_EVENT:
                _cleanup()
                return True
            return False

        ctypes.windll.kernel32.SetConsoleCtrlHandler(_win_ctrl_handler, True)
    except Exception as e:
        logger.warning(f"Could not set Windows console handler: {e}")

# ── SSE helpers ───────────────────────────────────────────────────────────────
def _push(msg_type: str, data) -> None:
    """Append a message to the SSE stream."""
    msg = {"type": msg_type, "data": data, "ts": time.time()}
    with _sse_lock:
        _sse_messages.append(msg)


def _log(text: str, level: str = "info") -> None:
    logger.info(text)
    _push("log", {"text": text, "level": level})


def _set_state(**kwargs) -> None:
    with _state_lock:
        _download_state.update(kwargs)
    _push("state", dict(_download_state))


# ── Core download logic ───────────────────────────────────────────────────────
def extract_urls_from_text(text: str) -> list:
    """Extract (name, url, platform) tuples from a text file."""
    urls = []
    pattern = (
        r"((?:[aAbB]roll\s*\d+|\w+))\s*"
        r"(https?://(?:(?:www\.|vm\.|vt\.|m\.)?(?:tiktok\.com|instagram\.com|youtube\.com|youtu\.be)"
        r"|ig\.me|instagr\.am)/[^\s*]+)"
    )
    for name, url in re.findall(pattern, text, re.IGNORECASE):
        url = url.rstrip("*/") + "/"
        name = re.sub(r"\s+", "", name)
        name = re.sub(r'[<>:"/\\|?*\n\r\t]', "_", name)[:100]
        
        if "tiktok" in url:
            platform = "TikTok"
        elif "youtube" in url or "youtu.be" in url:
            platform = "YouTube"
        else:
            platform = "Instagram"
            
        urls.append((name, url, platform))
    return urls


# No longer creating 'rename_me' subfolders per user request


def _download_single(data: tuple, download_folder: str, full_length: bool,
                     time_limit: int, quality: str = "720", max_retries: int = 3) -> tuple:
    """Download one video; returns (success, name, error_or_None)."""
    name, url, platform = data
    output = os.path.join(download_folder, f"{name}.%(ext)s")

    # To prevent 'pink/green screen', 'av01', or 'HEVC' format errors, we explicitly prioritize H.264
    # streams natively in mp4/m4a before falling back to anything else.
    # Note: YouTube uses 'avc1' for H.264, while TikTok often reports 'h264'.
    if quality == "best":
        format_str = (
            "bv*[vcodec^=avc1][ext=mp4]+ba[ext=m4a]/"
            "bv*[vcodec^=h264][ext=mp4]+ba[ext=m4a]/"
            "b[vcodec^=avc1][ext=mp4]/b[vcodec^=h264][ext=mp4]/"
            "bv*[ext=mp4]+ba[ext=m4a]/bv*+ba/best"
        )
    elif quality in ("1080", "720", "480"):
        format_str = (
            f"bv*[height<={quality}][vcodec^=avc1][ext=mp4]+ba[ext=m4a]/"
            f"bv*[height<={quality}][vcodec^=h264][ext=mp4]+ba[ext=m4a]/"
            f"b[height<={quality}][vcodec^=avc1][ext=mp4]/"
            f"b[height<={quality}][vcodec^=h264][ext=mp4]/"
            f"bv*[height<={quality}][ext=mp4]+ba/best"
        )
    else:
        format_str = (
            "bv*[height<=720][vcodec^=avc1][ext=mp4]+ba[ext=m4a]/"
            "bv*[height<=720][vcodec^=h264][ext=mp4]+ba[ext=m4a]/"
            "b[height<=720][vcodec^=avc1][ext=mp4]/"
            "b[height<=720][vcodec^=h264][ext=mp4]/"
            "bv*[height<=720][ext=mp4]+ba/best"
        )

    cmd = [
        sys.executable, "-m", "yt_dlp",
        "--ignore-errors", "--no-warnings", "--newline", "--no-playlist",
        "-o", output,
        "--concurrent-fragments", "4",
        "--fragment-retries", "3",
        "--retries", "2",
        "--socket-timeout", "10",
        "--format", format_str,
        "--merge-output-format", "mp4",
        url,
    ]
    if not full_length:
        cmd.extend(["--download-sections", f"*0-{time_limit}"])

    for attempt in range(max_retries):
        if _stop_event.is_set():
            return (False, name, "Stopped by user")

        proc = subprocess.Popen(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT, 
            text=True, 
            bufsize=1, 
            encoding='utf-8', 
            errors='replace',
            stdin=subprocess.DEVNULL
        )
        with _procs_lock:
            _active_procs.append(proc)

        try:
            # Continuously read and flush output to prevent buffer freezing
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                # Stream relevant messages to the web UI
                if line.startswith("ERROR:"):
                    _log(f"[{name}] {line}", "error")
                elif "Destination:" in line or "already been downloaded" in line or line.startswith("[TikTok]"):
                    _log(f"[{name}] {line}")
                # We hide the fast-moving % ETA lines to avoid lagging the UI browser, but reading them keeps the pipe empty

            proc.wait(timeout=120)
        except subprocess.TimeoutExpired:
            proc.kill()
        finally:
            with _procs_lock:
                if proc in _active_procs:
                    _active_procs.remove(proc)

        if proc.returncode == 0:
            return (True, name, None)
            
        if attempt < max_retries - 1:
            time.sleep(0.5)
            continue

    return (False, name, "Max retries exceeded or failed")


def _run_download_task(urls: list, opts: dict) -> None:
    """Background thread: download all URLs, then run auto-muter."""
    try:
        download_folder = opts["download_folder"]
        os.makedirs(download_folder, exist_ok=True)

        _log(f"📁 Saving to: {download_folder}")
        _log(f"🔗 Found {len(urls)} URL(s) to download")
        _set_state(running=True, status="downloading", progress=0, total=len(urls))

        full_length = opts.get("full_length", False)
        time_limit = int(opts.get("time_limit", 60) or 60)
        max_workers = int(opts.get("concurrent_workers", 3) or 3)
        quality = str(opts.get("quality", "720"))

        successful, failed = [], []
        completed = 0

        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_download_single, data, download_folder,
                                full_length, time_limit, quality): data
                for data in urls
            }
            for future in concurrent.futures.as_completed(futures):
                if _stop_event.is_set():
                    executor.shutdown(wait=False, cancel_futures=True)
                    break

                data = futures[future]
                completed += 1
                try:
                    success, name, error = future.result()
                    if success:
                        successful.append(name)
                        _log(f"✓ ({completed}/{len(urls)}) {name}", "success")
                    else:
                        failed.append(name)
                        _log(f"✗ ({completed}/{len(urls)}) {name} — {error}", "error")
                except Exception as exc:
                    failed.append(data[0])
                    _log(f"✗ ({completed}/{len(urls)}) {data[0]} — {str(exc)[:100]}", "error")

                _set_state(progress=completed, total=len(urls))

        if _stop_event.is_set():
            _log("⏹ Download stopped by user.", "warning")
            _set_state(running=False, status="idle")
            return

        _log(f"📊 Download complete: {len(successful)} succeeded, {len(failed)} failed")

        # ── Auto-muter ────────────────────────────────────────────────────────
        _log("🔇 Starting B-roll muting...")
        _set_state(status="muting", progress=0, total=0)

        try:
            from auto_muter import mute_broll_videos

            def _mute_cb(current: int, total: int, filename: str):
                _log(f"🔇 Muting ({current}/{total}): {filename}")
                _set_state(progress=current, total=total)

            processed, total_broll = mute_broll_videos(download_folder, _mute_cb)
            if total_broll == 0:
                _log("ℹ No B-roll videos found to mute.")
            else:
                _log(f"✅ Muted {processed}/{total_broll} B-roll video(s).", "success")
        except ImportError:
            _log("⚠ auto_muter.py not found — skipping muting.", "warning")
        except Exception as exc:
            _log(f"⚠ Muting error: {exc}", "warning")

        _log("🎉 All done!", "success")
        _set_state(running=False, status="done")

    except Exception as exc:
        logger.exception(exc)
        _log(f"💥 Unexpected error: {exc}", "error")
        _set_state(running=False, status="error")


# ── Helpers ───────────────────────────────────────────────────────────────────
def _parse_opts(source) -> dict:
    """Parse options from request.form, request.json, or a plain dict."""
    def get(key, default=""):
        val = source.get(key, default)
        return val if val is not None else default

    def to_bool(val, default=True) -> bool:
        s = str(val).lower().strip()
        if s in ("true", "1", "on", "yes"):
            return True
        if s in ("false", "0", "off", "no"):
            return False
        return default

    try:
        time_limit = int(get("time_limit", 60) or 60)
    except (ValueError, TypeError):
        time_limit = 60

    try:
        concurrent = int(get("concurrent", 3) or 3)
    except (ValueError, TypeError):
        concurrent = 3

    return {
        "download_folder": str(get("download_folder", "")).strip(),
        "full_length": to_bool(get("full_length", "false")),
        "time_limit": time_limit,
        "concurrent_workers": concurrent,
        "muted": to_bool(get("muted", "true")),
        "unmuted": to_bool(get("unmuted", "true")),
        "quality": str(get("quality", "720")).strip(),
    }


# ── Flask routes ──────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/status")
def api_status():
    with _state_lock:
        return jsonify(dict(_download_state))


@app.route("/api/events")
def api_events():
    """Server-Sent Events stream for real-time log + state updates."""
    def generate():
        idx = 0
        while True:
            with _sse_lock:
                batch = _sse_messages[idx:]
                idx_new = len(_sse_messages)
            for msg in batch:
                yield f"data: {json.dumps(msg)}\n\n"
            idx = idx_new
            if not batch:
                yield f'data: {json.dumps({"type": "heartbeat"})}\n\n'
            time.sleep(0.3)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.route("/api/download/file", methods=["POST"])
def api_download_file():
    with _state_lock:
        if _download_state["running"]:
            return jsonify({"error": "A download is already in progress."}), 400

    file = request.files.get("file")
    if not file:
        return jsonify({"error": "No file provided."}), 400

    try:
        content = file.read().decode("utf-8", errors="replace")
    except Exception as exc:
        return jsonify({"error": f"Could not read file: {exc}"}), 400

    urls = extract_urls_from_text(content)
    if not urls:
        return jsonify({"error": "No valid TikTok/Instagram URLs found in the file."}), 400

    opts = _parse_opts(request.form)
    if not opts["download_folder"]:
        return jsonify({"error": "Download folder path is required."}), 400

    _stop_event.clear()
    t = threading.Thread(target=_run_download_task, args=(urls, opts), daemon=True)
    t.start()

    return jsonify({"message": f"Downloading {len(urls)} video(s)...", "count": len(urls)})


@app.route("/api/download/url", methods=["POST"])
def api_download_url():
    with _state_lock:
        if _download_state["running"]:
            return jsonify({"error": "A download is already in progress."}), 400

    body = request.get_json(silent=True) or {}
    url = str(body.get("url", "")).strip()
    name = str(body.get("name", "video")).strip() or "video"

    if not url:
        return jsonify({"error": "URL is required."}), 400
    if not re.match(r"https?://", url):
        return jsonify({"error": "Invalid URL format. Must start with http:// or https://"}), 400

    platform = "TikTok" if "tiktok.com" in url else "Instagram"
    urls = [(name, url, platform)]

    opts = _parse_opts(body)
    if not opts["download_folder"]:
        return jsonify({"error": "Download folder path is required."}), 400

    _stop_event.clear()
    t = threading.Thread(target=_run_download_task, args=(urls, opts), daemon=True)
    t.start()

    return jsonify({"message": "Downloading 1 video...", "count": 1})


@app.route("/api/stop", methods=["POST"])
def api_stop():
    _stop_event.set()
    with _procs_lock:
        for proc in list(_active_procs):
            try:
                proc.terminate()
            except Exception:
                pass
    _set_state(running=False, status="idle")
    return jsonify({"message": "Stop signal sent."})


@app.route("/api/browse", methods=["POST"])
def api_browse():
    """Opens a native folder selection dialog on the host machine."""
    import tkinter as tk
    from tkinter import filedialog
    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        folder_path = filedialog.askdirectory(title="Select Download Folder")
        root.destroy()
        
        if folder_path:
            # Convert / to \ for Windows
            folder_path = os.path.normpath(folder_path)
            return jsonify({"folder": folder_path})
        return jsonify({"error": "No folder selected."}), 400
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    PORT = 5000
    url = f"http://localhost:{PORT}"

    print("\n" + "=" * 50)
    print("  Video Downloader — Web UI")
    print(f"  Running at: {url}")
    print("  Close this window to stop the server.")
    print("=" * 50 + "\n")

    # Open browser after Flask is up
    threading.Timer(1.5, lambda: webbrowser.open(url)).start()

    app.run(host="localhost", port=PORT, debug=False, threaded=True)
