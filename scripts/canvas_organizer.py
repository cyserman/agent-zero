#!/usr/bin/env python3
"""
Canvas Asset Organizer — watches a drop zone and sorts files by session.

Mimics Manus's thread-separated asset dashboard locally on the SSD.
Runs as a background watchdog: saves Canvas exports (HTML, Py, MD, etc.)
into date/session-stamped folders for Angie to index and search.

Usage:
    python3 canvas_organizer.py

Paths are on the SSD per NDCoder Protocol (never internal drive).
"""

import os
import shutil
import time
from datetime import datetime
from pathlib import Path

# --- NDCoder Protocol: all paths on SSD, never ~ ---
SSD_BASE = "/mnt/chromeos/removable/Angie/AGENT_VAULT"
DROP_ZONE = os.path.join(SSD_BASE, "Canvas_Dropzone")
LIBRARY_DIR = os.path.join(SSD_BASE, "Canvas_Library")


def setup_directories():
    os.makedirs(DROP_ZONE, exist_ok=True)
    os.makedirs(LIBRARY_DIR, exist_ok=True)
    print(f"[*] Watching for new Canvas assets in: {DROP_ZONE}")
    print(f"[*] Organizing assets into: {LIBRARY_DIR}")


def get_thread_folder_name():
    """Group assets by day + session (Morning/Afternoon/Evening)."""
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    hour = now.hour
    if hour < 12:
        session = "Morning_Session"
    elif hour < 18:
        session = "Afternoon_Session"
    else:
        session = "Evening_Session"
    return f"Thread_{date_str}_{session}"


def process_new_files():
    for filename in os.listdir(DROP_ZONE):
        file_path = os.path.join(DROP_ZONE, filename)

        if not os.path.isfile(file_path) or filename.startswith("."):
            continue

        thread_folder_name = get_thread_folder_name()
        dest_folder = os.path.join(LIBRARY_DIR, thread_folder_name)
        os.makedirs(dest_folder, exist_ok=True)

        dest_path = os.path.join(dest_folder, filename)
        if os.path.exists(dest_path):
            base, ext = os.path.splitext(filename)
            timestamp = datetime.now().strftime("%H%M%S")
            dest_path = os.path.join(dest_folder, f"{base}_{timestamp}{ext}")

        try:
            shutil.move(file_path, dest_path)
            print(f"[+] Archived: {filename} -> {thread_folder_name}/")
        except Exception as e:
            print(f"[-] Error moving {filename}: {e}")


def run_watchdog():
    setup_directories()
    try:
        while True:
            process_new_files()
            time.sleep(10)
    except KeyboardInterrupt:
        print("\n[*] Canvas Organizer shutting down. Stay bulletproof, Chris.")


if __name__ == "__main__":
    run_watchdog()
