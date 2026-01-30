from dataclasses import dataclass
from pathlib import Path
import json
import sys
from typing import Any


import os
import shutil

# In dev, we read/write utils/config.json. In a frozen EXE (PyInstaller --onefile),
# we prefer a config.json placed in ProgramData so edits persist and are writable.
IS_FROZEN = getattr(sys, "frozen", False)
BASE_DIR = Path(sys.executable).parent if IS_FROZEN else Path(__file__).parent

# 1. Resolve ProgramData/FishManagement/config.json
PROGRAM_DATA = os.getenv('ProgramData', 'C:\\ProgramData')
APP_DATA_DIR = Path(PROGRAM_DATA) / "FishManagement"
try:
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    # Fallback to local appdata if ProgramData fails
    APP_DATA_DIR = Path(os.getenv('LOCALAPPDATA', os.path.expanduser('~'))) / "FishManagement"
    APP_DATA_DIR.mkdir(parents=True, exist_ok=True)

CONFIG_FILE = APP_DATA_DIR / "config.json"
BUNDLED_CONFIG = Path(__file__).with_name("config.json")

# 2. If config doesn't exist in ProgramData, copy from bundle/dev location
if not CONFIG_FILE.exists():
    # Try to find the source config
    source_config = None
    if BUNDLED_CONFIG.exists():
        source_config = BUNDLED_CONFIG
    elif (BASE_DIR / "config.json").exists(): # Check root/dist dir
        source_config = BASE_DIR / "config.json"
        
    if source_config:
        try:
            shutil.copy2(source_config, CONFIG_FILE)
            print(f"Initialized config at {CONFIG_FILE} from {source_config}")
        except Exception as e:
            print(f"Error copying initial config: {e}")


@dataclass
class AppConfig:
    """Simple in-memory config representation backed by config.json."""

    app_title: str = "Store Management System"
    # Use a built-in theme name that CustomTkinter recognizes by default
    theme: str = "dark-blue"
    ui_scaling: float = 1.0
    api_url: str | None = None
    supabase_key: str | None = None
    installation_id: str | None = None
    max_offline_days: int = 7


def _load_raw_config() -> dict[str, Any]:
    """Load raw JSON from CONFIG_FILE, returning {} on any error."""
    try:
        if CONFIG_FILE.is_file():
            text = CONFIG_FILE.read_text(encoding="utf-8")
            data = json.loads(text or "{}")
            if isinstance(data, dict):
                return data
    except Exception:
        # Fail silently and fall back to defaults.
        pass
    return {}


def load_config() -> AppConfig:
    """Load AppConfig from config.json, with safe fallbacks to defaults."""
    raw = _load_raw_config()

    cfg = AppConfig()
    cfg.app_title = raw.get("title", cfg.app_title)
    cfg.theme = raw.get("theme", cfg.theme)
    cfg.ui_scaling = float(raw.get("ui_scaling", cfg.ui_scaling))
    cfg.api_url = raw.get("api_url", cfg.api_url)
    cfg.supabase_key = raw.get("supabase_key", cfg.supabase_key)
    cfg.installation_id = raw.get("installation_id", cfg.installation_id)
    try:
        cfg.max_offline_days = int(raw.get("max_offline_days", cfg.max_offline_days))
    except Exception:
        pass

    return cfg


def save_config(cfg: AppConfig) -> None:
    """Save AppConfig to config.json, preserving existing fields."""
    raw = _load_raw_config()

    # Update only the fields we want to persist
    raw["title"] = cfg.app_title
    raw["theme"] = cfg.theme
    raw["ui_scaling"] = cfg.ui_scaling
    if cfg.api_url:
        raw["api_url"] = cfg.api_url
    if cfg.supabase_key:
        raw["supabase_key"] = cfg.supabase_key
    if cfg.installation_id:
        raw["installation_id"] = cfg.installation_id
    raw["max_offline_days"] = cfg.max_offline_days

    try:
        CONFIG_FILE.write_text(json.dumps(raw, indent=4), encoding="utf-8")
    except Exception:
        # Fail silently if we can't write
        pass
