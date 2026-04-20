"""
auto_muter.py — Headless B-Roll Video Muter
=============================================
No tkinter. Can be imported by app.py or run standalone.

Usage (standalone):
    python auto_muter.py <folder_path>
"""

import os
import sys
import subprocess
import logging
import time
import glob

def _ensure_ffmpeg_path():
    """Ensure ffmpeg bin folder is in PATH if installed via Winget."""
    try:
        local_appdata = os.environ.get("LOCALAPPDATA", "")
        if not local_appdata:
            return
        winget_path = os.path.join(local_appdata, "Microsoft", "WinGet", "Packages")
        if not os.path.isdir(winget_path):
            return
        
        search_pattern = os.path.join(winget_path, "**", "bin", "ffmpeg.exe")
        for match in glob.glob(search_pattern, recursive=True):
            bin_dir = os.path.dirname(match)
            if bin_dir.lower() not in os.environ["PATH"].lower():
                os.environ["PATH"] = bin_dir + os.pathsep + os.environ["PATH"]
                break
    except Exception:
        pass

_ensure_ffmpeg_path()

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("auto_muter.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

VIDEO_EXTENSIONS = {".mp4", ".avi", ".mov", ".mkv", ".wmv", ".flv", ".webm", ".m4v"}


def mute_broll_videos(folder_path: str, progress_callback=None) -> tuple:
    """
    Mute all B-roll videos in *folder_path* using FFmpeg (stream copy, no re-encode).

    A file is treated as B-roll if its name starts with 'broll' or 'b'
    (case-insensitive), but NOT 'ba' (to avoid false matches).

    Args:
        folder_path:       Absolute path to the video folder.
        progress_callback: Optional callable(current, total, filename).
                           Called before AND after each file is processed.

    Returns:
        (processed_count, total_broll_count)
    """
    if not os.path.isdir(folder_path):
        logger.error(f"Invalid folder path: {folder_path}")
        return 0, 0

    # Find all B-roll video files
    try:
        entries = os.listdir(folder_path)
    except PermissionError as exc:
        logger.error(f"Cannot read folder: {exc}")
        return 0, 0

    broll_videos = [
        os.path.join(folder_path, f)
        for f in entries
        if (
            f.lower().startswith(("broll", "b"))
            and not f.lower().startswith("ba")
            and os.path.splitext(f)[1].lower() in VIDEO_EXTENSIONS
        )
    ]

    total = len(broll_videos)
    if total == 0:
        logger.info("No B-roll videos found to mute.")
        return 0, 0

    logger.info(f"Found {total} B-roll video(s) to mute.")
    processed = 0

    for i, video_path in enumerate(broll_videos, 1):
        filename = os.path.basename(video_path)
        base, ext = os.path.splitext(video_path)
        temp_path = f"{base}_temp{ext}"

        # Notify: starting this file
        if progress_callback:
            try:
                progress_callback(i - 1, total, filename)
            except Exception:
                pass

        logger.info(f"Muting ({i}/{total}): {filename}")

        try:
            cmd = [
                "ffmpeg",
                "-i", video_path,
                "-an",          # Remove audio
                "-c:v", "copy", # Copy video stream (no re-encode)
                "-y",           # Overwrite temp file if exists
                temp_path,
            ]
            subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
                timeout=300,    # 5-minute timeout per file
            )

            if os.path.exists(temp_path) and os.path.getsize(temp_path) > 0:
                os.replace(temp_path, video_path)
                processed += 1
                logger.info(f"  ✓ Muted: {filename}")
            else:
                logger.error(f"  ✗ Temp file empty or missing for: {filename}")
                if os.path.exists(temp_path):
                    os.remove(temp_path)

        except subprocess.CalledProcessError as exc:
            logger.error(f"  ✗ FFmpeg error on {filename}: {exc.stderr[:300]}")
            if os.path.exists(temp_path):
                os.remove(temp_path)

        except subprocess.TimeoutExpired:
            logger.error(f"  ✗ FFmpeg timed out on: {filename}")
            if os.path.exists(temp_path):
                os.remove(temp_path)

        except FileNotFoundError:
            logger.error(
                "  ✗ 'ffmpeg' not found in PATH. "
                "Please install FFmpeg: https://ffmpeg.org/download.html"
            )
            break

        except Exception as exc:
            logger.error(f"  ✗ Unexpected error on {filename}: {exc}")
            if os.path.exists(temp_path):
                os.remove(temp_path)

        # Notify: finished this file
        if progress_callback:
            try:
                progress_callback(i, total, filename)
            except Exception:
                pass

    logger.info(f"Muting complete: {processed}/{total} file(s) processed.")
    return processed, total


# ── Standalone entry point ────────────────────────────────────────────────────
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python auto_muter.py <folder_path>")
        sys.exit(1)

    folder = sys.argv[1]
    print(f"\nMuting B-roll videos in: {folder}\n")

    def _cli_callback(current: int, total: int, filename: str):
        if current < total:
            print(f"  [{current + 1}/{total}] Processing: {filename}")
        else:
            print(f"  [{current}/{total}] Done: {filename}")

    processed, total = mute_broll_videos(folder, _cli_callback)
    print(f"\n✔ Done! Muted {processed}/{total} B-roll video(s).")