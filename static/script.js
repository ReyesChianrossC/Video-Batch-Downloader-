/* =================================================================
   Video Downloader — Frontend Logic
   =================================================================
   - Connects to /api/events (SSE) for real-time log + state updates
   - Handles file upload (drag-and-drop + click)
   - Handles direct URL download
   - Updates progress bar, status badge, log console
   - Saves download folder preference to localStorage
   ================================================================= */

"use strict";

// ── DOM refs ───────────────────────────────────────────────────────────────
const $ = (id) => document.getElementById(id);

const statusBadge      = $("status-badge");
const statusText       = $("status-text");
const dropZone         = $("drop-zone");
const fileInput        = $("file-input");
const fileInfo         = $("file-info");
const fileNameText     = $("file-name");
const clearFileBtn     = $("clear-file");
const btnDownloadFile  = $("btn-download-file");
const urlInput         = $("url-input");
const nameInput        = $("name-input");
const btnDownloadUrl   = $("btn-download-url");
const folderInput      = $("folder-input");
const mutedCheck       = $("muted-check");
const unmutedCheck     = $("unmuted-check");
const fullLengthCheck  = $("full-length-check");
const timeInput        = $("time-input");
const timeRow          = $("time-row");
const concurrentSlider = $("concurrent-slider");
const concurrentValue  = $("concurrent-value");
const optionsToggle    = $("options-toggle");
const optionsBody      = $("options-body");
const toggleArrow      = $("toggle-arrow");
const btnStop          = $("btn-stop");
const progressBar      = $("progress-bar");
const progressTrack    = $("progress-track");
const progressText     = $("progress-text");
const progressPct      = $("progress-pct");
const logConsole       = $("log-console");
const logPlaceholder   = $("log-placeholder");
const btnClearLog      = $("btn-clear-log");
const btnScrollBottom  = $("btn-scroll-bottom");
const toastContainer   = $("toast-container");

// ── State ─────────────────────────────────────────────────────────────────
let selectedFile   = null;
let isRunning      = false;
let autoScroll     = true;

// ── Persist folder path ───────────────────────────────────────────────────
const FOLDER_KEY = "vd_download_folder";
folderInput.value = localStorage.getItem(FOLDER_KEY) || "";
folderInput.addEventListener("change", () => {
  localStorage.setItem(FOLDER_KEY, folderInput.value.trim());
});

// ── Browse folder ─────────────────────────────────────────────────────────
$("btn-browse-folder").addEventListener("click", async () => {
  try {
    $("btn-browse-folder").disabled = true;
    const res = await fetch("/api/browse", { method: "POST" });
    const data = await res.json();
    if (res.ok && data.folder) {
      folderInput.value = data.folder;
      localStorage.setItem(FOLDER_KEY, data.folder);
    } else if (!res.ok && data.error && data.error !== "No folder selected.") {
      showToast(data.error, "error");
    }
  } catch (err) {
    showToast("Could not open folder picker.", "error");
  } finally {
    $("btn-browse-folder").disabled = false;
  }
});

// ── Options toggle ────────────────────────────────────────────────────────
optionsToggle.addEventListener("click", () => {
  const expanded = optionsToggle.getAttribute("aria-expanded") === "true";
  optionsToggle.setAttribute("aria-expanded", String(!expanded));
  optionsBody.classList.toggle("hidden", expanded);
  toggleArrow.classList.toggle("collapsed", expanded);
});

// ── Full-length toggle ────────────────────────────────────────────────────
fullLengthCheck.addEventListener("change", () => {
  timeRow.style.opacity   = fullLengthCheck.checked ? "0.35" : "1";
  timeInput.disabled      = fullLengthCheck.checked;
});

// ── Concurrent slider ─────────────────────────────────────────────────────
concurrentSlider.addEventListener("input", () => {
  concurrentValue.textContent = concurrentSlider.value;
});

// ── Drag-and-drop ─────────────────────────────────────────────────────────
["dragenter", "dragover"].forEach((evt) => {
  dropZone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropZone.classList.add("drag-over");
  });
});

["dragleave", "drop"].forEach((evt) => {
  dropZone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropZone.classList.remove("drag-over");
  });
});

dropZone.addEventListener("drop", (e) => {
  const file = e.dataTransfer.files[0];
  if (file) setSelectedFile(file);
});

dropZone.addEventListener("keydown", (e) => {
  if (e.key === "Enter" || e.key === " ") fileInput.click();
});

fileInput.addEventListener("change", () => {
  if (fileInput.files[0]) setSelectedFile(fileInput.files[0]);
});

function setSelectedFile(file) {
  if (!file.name.endsWith(".txt")) {
    showToast("Please select a .txt file.", "error");
    return;
  }
  selectedFile = file;
  fileNameText.textContent  = file.name;
  fileInfo.classList.remove("hidden");
  dropZone.classList.add("hidden");
  btnDownloadFile.disabled  = false;
}

clearFileBtn.addEventListener("click", () => {
  selectedFile              = null;
  fileInput.value           = "";
  fileInfo.classList.add("hidden");
  dropZone.classList.remove("hidden");
  btnDownloadFile.disabled  = true;
});

// ── Download from file ────────────────────────────────────────────────────
btnDownloadFile.addEventListener("click", async () => {
  if (!selectedFile) return;

  const folder = folderInput.value.trim();
  if (!folder) {
    showToast("Please enter a download folder path in Options.", "error");
    folderInput.focus();
    return;
  }

  const form = new FormData();
  form.append("file",            selectedFile);
  form.append("download_folder", folder);
  form.append("muted",           mutedCheck.checked);
  form.append("unmuted",         unmutedCheck.checked);
  form.append("full_length",     fullLengthCheck.checked);
  form.append("time_limit",      timeInput.value);
  form.append("concurrent",      concurrentSlider.value);
  form.append("quality",         $("quality-select").value);

  try {
    const res  = await fetch("/api/download/file", { method: "POST", body: form });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Unknown error");
    showToast(data.message, "success");
    localStorage.setItem(FOLDER_KEY, folder);
  } catch (err) {
    showToast(err.message, "error");
  }
});

// ── Download single URL ───────────────────────────────────────────────────
btnDownloadUrl.addEventListener("click", async () => {
  const url    = urlInput.value.trim();
  const name   = nameInput.value.trim() || "video";
  const folder = folderInput.value.trim();

  if (!url) {
    showToast("Please enter a video URL.", "error");
    urlInput.focus();
    return;
  }
  if (!folder) {
    showToast("Please enter a download folder path in Options.", "error");
    folderInput.focus();
    return;
  }

  const payload = {
    url,
    name,
    download_folder: folder,
    muted:           mutedCheck.checked,
    unmuted:         unmutedCheck.checked,
    full_length:     fullLengthCheck.checked,
    time_limit:      parseInt(timeInput.value, 10) || 60,
    concurrent:      parseInt(concurrentSlider.value, 10) || 3,
    quality:         $("quality-select").value,
  };

  try {
    const res  = await fetch("/api/download/url", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Unknown error");
    showToast(data.message, "success");
    localStorage.setItem(FOLDER_KEY, folder);
  } catch (err) {
    showToast(err.message, "error");
  }
});

// ── Stop ──────────────────────────────────────────────────────────────────
btnStop.addEventListener("click", async () => {
  try {
    await fetch("/api/stop", { method: "POST" });
    showToast("Stop signal sent.", "warning");
  } catch (err) {
    showToast("Could not reach server.", "error");
  }
});

// ── Log console ───────────────────────────────────────────────────────────
btnClearLog.addEventListener("click", clearLog);
btnScrollBottom.addEventListener("click", () => {
  logConsole.scrollTop = logConsole.scrollHeight;
  autoScroll = true;
});

logConsole.addEventListener("scroll", () => {
  const atBottom = logConsole.scrollTop + logConsole.clientHeight >= logConsole.scrollHeight - 20;
  autoScroll = atBottom;
});

function clearLog() {
  logConsole.innerHTML = '<p class="log-placeholder" id="log-placeholder">Log cleared.</p>';
}

function appendLog(text, level = "info") {
  const placeholder = logConsole.querySelector(".log-placeholder");
  if (placeholder) placeholder.remove();

  const now     = new Date();
  const hh      = String(now.getHours()).padStart(2, "0");
  const mm      = String(now.getMinutes()).padStart(2, "0");
  const ss      = String(now.getSeconds()).padStart(2, "0");
  const timeStr = `${hh}:${mm}:${ss}`;

  const line = document.createElement("div");
  line.className = "log-line";
  line.innerHTML = `
    <span class="log-time">${timeStr}</span>
    <span class="log-text-${level}">${escapeHtml(text)}</span>
  `;
  logConsole.appendChild(line);

  if (autoScroll) logConsole.scrollTop = logConsole.scrollHeight;

  // Limit log lines to 500
  const lines = logConsole.querySelectorAll(".log-line");
  if (lines.length > 500) lines[0].remove();
}

// ── Progress + status ─────────────────────────────────────────────────────
function updateProgress(current, total) {
  const pct = total > 0 ? Math.round((current / total) * 100) : 0;
  progressBar.style.width         = `${pct}%`;
  progressText.textContent        = total > 0 ? `${current} / ${total}` : "—";
  progressPct.textContent         = `${pct}%`;
  progressTrack.setAttribute("aria-valuenow", pct);
}

const STATUS_LABELS = {
  idle:        "Idle",
  downloading: "Downloading",
  muting:      "Muting B-roll",
  done:        "Done ✓",
  error:       "Error",
};

function updateStatus(state) {
  const { status, running, progress, total } = state;
  statusBadge.setAttribute("data-status", status);
  statusText.textContent = STATUS_LABELS[status] || status;
  isRunning              = running;

  // Button states
  btnStop.disabled          = !running;
  btnDownloadFile.disabled  = running || !selectedFile;
  btnDownloadUrl.disabled   = running;

  if (typeof progress === "number" && typeof total === "number") {
    updateProgress(progress, total);
  }

  if (status === "done") {
    updateProgress(total, total);
    showToast("Download complete! 🎉", "success");
  }
  if (status === "error") {
    showToast("An error occurred. Check the log.", "error");
  }
}

// ── SSE connection ────────────────────────────────────────────────────────
function connectSSE() {
  const es = new EventSource("/api/events");

  es.onmessage = (e) => {
    try {
      const msg = JSON.parse(e.data);
      if (msg.type === "heartbeat") return;
      if (msg.type === "log"  ) appendLog(msg.data.text, msg.data.level);
      if (msg.type === "state") updateStatus(msg.data);
    } catch (_) {
      // Ignore malformed messages
    }
  };

  es.onerror = () => {
    es.close();
    // Reconnect after 3 seconds
    setTimeout(connectSSE, 3000);
  };
}

// ── Toasts ────────────────────────────────────────────────────────────────
const TOAST_ICONS = { success: "✅", error: "❌", warning: "⚠️", info: "ℹ️" };

function showToast(message, type = "info", duration = 4000) {
  const toast    = document.createElement("div");
  toast.className = `toast ${type}`;
  toast.innerHTML = `<span>${TOAST_ICONS[type] || ""}</span><span>${escapeHtml(message)}</span>`;
  toastContainer.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity   = "0";
    toast.style.transform = "translateX(20px)";
    toast.style.transition = "opacity .3s, transform .3s";
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

// ── Utils ─────────────────────────────────────────────────────────────────
function escapeHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

// ── Init ──────────────────────────────────────────────────────────────────
(async function init() {
  // Load current status
  try {
    const res  = await fetch("/api/status");
    const data = await res.json();
    updateStatus(data);
  } catch (_) {}

  // Connect SSE
  connectSSE();

  // Set initial button state
  btnDownloadFile.disabled = true;
})();
