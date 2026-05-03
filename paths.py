import os
import platform
from pathlib import Path

APP_NAME = "wmus"

def _windows_localappdata():
    base = os.getenv("LOCALAPPDATA")
    if base:
        return Path(base)
    # Fallback to a reasonable default under the user's home directory
    return Path.home() / "AppData" / "Local"

def get_config_dir(app_name=APP_NAME):
    if platform.system() == "Windows":
        base = _windows_localappdata()
        return base / app_name / "config"
    # Follow XDG spec on Linux/macOS
    base = Path(os.getenv("XDG_CONFIG_HOME") or (Path.home() / ".config"))
    return base / app_name

def get_cache_dir(app_name=APP_NAME):
    if platform.system() == "Windows":
        base = _windows_localappdata()
        return base / app_name / "cache"
    base = Path(os.getenv("XDG_DATA_HOME") or (Path.home() / ".local" / "share"))
    return base / app_name / "cache"

# Module-level constants (single source of truth)
CONFIG_DIR = get_config_dir()
CACHE_DIR = get_cache_dir()

# Ensure directories exist; fall back to home-based paths if creation fails
try:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    fallback_config = Path.home() / ".config" / APP_NAME
    fallback_cache = Path.home() / ".local" / "share" / APP_NAME / "cache"
    fallback_config.mkdir(parents=True, exist_ok=True)
    fallback_cache.mkdir(parents=True, exist_ok=True)
    CONFIG_DIR = fallback_config
    CACHE_DIR = fallback_cache

__all__ = ["APP_NAME", "CONFIG_DIR", "CACHE_DIR", "get_config_dir", "get_cache_dir"]
