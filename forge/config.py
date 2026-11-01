"""forge.config - Cross-platform configuration and directory resolver.

Handles standard configuration, data, and cache paths across:
- Linux / BSD: XDG Base Directory Specification (~/.config, ~/.local/share, ~/.cache)
- macOS: ~/Library/Application Support, ~/Library/Caches
- Windows: %APPDATA%, %LOCALAPPDATA%
"""
from __future__ import annotations

import os
import platform
import sys
from pathlib import Path

APP_NAME = "forge"


def get_platform() -> str:
    """Return normalized platform identifier: 'windows', 'darwin', or 'linux'."""
    sys_name = platform.system().lower()
    if "windows" in sys_name:
        return "windows"
    if "darwin" in sys_name:
        return "darwin"
    return "linux"


def get_config_dir() -> Path:
    """Return user configuration directory for forge."""
    if env_dir := os.environ.get("FORGE_CONFIG_DIR"):
        return Path(env_dir).expanduser().resolve()

    plat = get_platform()
    home = Path.home()

    if plat == "windows":
        app_data = os.environ.get("APPDATA")
        base = Path(app_data) if app_data else home / "AppData" / "Roaming"
        return base / APP_NAME
    elif plat == "darwin":
        return home / "Library" / "Application Support" / APP_NAME
    else:
        # Linux / XDG
        xdg_config = os.environ.get("XDG_CONFIG_HOME")
        base = Path(xdg_config) if xdg_config else home / ".config"
        return base / APP_NAME


def get_data_dir() -> Path:
    """Return user data storage directory (SQLite DBs, state, outputs)."""
    if env_dir := os.environ.get("FORGE_DATA_DIR"):
        return Path(env_dir).expanduser().resolve()

    plat = get_platform()
    home = Path.home()

    if plat == "windows":
        local_app_data = os.environ.get("LOCALAPPDATA")
        base = Path(local_app_data) if local_app_data else home / "AppData" / "Local"
        return base / APP_NAME
    elif plat == "darwin":
        return home / "Library" / "Application Support" / APP_NAME / "data"
    else:
        # Linux / XDG
        xdg_data = os.environ.get("XDG_DATA_HOME")
        base = Path(xdg_data) if xdg_data else home / ".local" / "share"
        return base / APP_NAME


def get_cache_dir() -> Path:
    """Return user cache directory (temporary tokens, ephemeral data)."""
    if env_dir := os.environ.get("FORGE_CACHE_DIR"):
        return Path(env_dir).expanduser().resolve()

    plat = get_platform()
    home = Path.home()

    if plat == "windows":
        local_app_data = os.environ.get("LOCALAPPDATA")
        base = Path(local_app_data) if local_app_data else home / "AppData" / "Local"
        return base / APP_NAME / "Cache"
    elif plat == "darwin":
        return home / "Library" / "Caches" / APP_NAME
    else:
        # Linux / XDG
        xdg_cache = os.environ.get("XDG_CACHE_HOME")
        base = Path(xdg_cache) if xdg_cache else home / ".cache"
        return base / APP_NAME


CONFIG_DIR = get_config_dir()
DATA_DIR = get_data_dir()
CACHE_DIR = get_cache_dir()
DB_PATH = DATA_DIR / "forge.db"
DEFAULT_PROXIES_FILE = CONFIG_DIR / "proxies.txt"


def ensure_dirs() -> None:
    """Ensure standard forge application directories exist."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
