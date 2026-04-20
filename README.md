# Video Batch Downloader

A modern, robust, and headless video downloader web application for **TikTok**, **Instagram**, and **YouTube**. Migrated from a legacy Tkinter GUI to a lightweight Flask server with a dynamic, responsive Web UI. 

## Features

- **Multi-Platform Support**: Effortlessly downloads videos from TikTok, Instagram, and YouTube.
- **Batch Processing**: Drag and drop `.txt` files containing multiple video URLs for mass downloading.
- **Seamless Web Interface**: A beautifully designed, dark-themed local website with progress bars, live tracking, and an aesthetically pleasing UI.
- **Live Logging**: Real-time console logs streamed directly to the browser UI via Server-Sent Events (SSE).
- **Auto-Muter (FFmpeg)**: Built-in background processing that safely mutes B-roll videos using FFmpeg without re-encoding them.
- **Smart Codec Resolution**: Specifically engineered to block `av01` (AV1) and `HEVC` video codecs on TikTok to guarantee downloaded MP4s natively play on all standard media players (e.g., VLC, Windows Media Player) without matrix glitches or pink screens.
- **Zero-Touch Dependency Installer**: Natively hooks into Windows `winget` and `pip` on startup. If a user is missing `yt-dlp` or `FFmpeg`, the program automatically installs them and restarts itself without any manual input required!

## Installation & Usage

1. **Clone the repository:**
   ```bash
   git clone https://github.com/ReyesChianrossC/Video-Batch-Downloader-.git
   ```

2. **Launch the Engine:**
   Simply double-click `launcher.bat`!
   
   The launcher will automatically verify your environment. If Python, pip, Flask, yt-dlp, or FFmpeg are missing, it will fetch them automatically.

3. **Open the App:**
   The Web UI will automatically open in your default browser at `http://localhost:5000`.

4. **Select a Download Location:**
   Click the **Options** gear in the UI, then hit **Browse...** to pick exactly where you want videos placed on your machine via a native Windows folder popup.

## Technologies Used

- **Backend**: Python 3, Flask, yt-dlp, FFmpeg
- **Frontend**: HTML5, Vanilla JavaScript, CSS3
- **Automation**: Batch scripts, Windows Explorer API hooks

## Customization

You can freely change the quality, the number of concurrent downloads, the specific video lengths, and the auto-muting rules straight out of the options menu in the dashboard without writing any code.
