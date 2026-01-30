import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Tuple

import requests

from utils.config import load_config, save_config


_app_config = load_config()

# Prefer environment variables, fall back to config.json
SUPABASE_URL = os.getenv("SUPABASE_URL", _app_config.api_url or "")
SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", _app_config.supabase_key or "")
INSTALLATION_ID = os.getenv("INSTALLATION_ID", _app_config.installation_id or "")

# How long the app may run purely offline after last successful online check
try:
    MAX_OFFLINE_DAYS = int(os.getenv("MAX_OFFLINE_DAYS", str(_app_config.max_offline_days)))
except Exception:
    MAX_OFFLINE_DAYS = 7

# Offline cache location
CACHE_DIR = Path(os.getenv("BKFOODS_DATA_DIR", str(Path.home() / ".bkfoods")))
CACHE_DIR.mkdir(parents=True, exist_ok=True)
CACHE_FILE = CACHE_DIR / "license_cache.json"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def has_internet(timeout: float = 3.0) -> bool:
    """Quick connectivity check using a cheap HEAD request."""
    if not SUPABASE_URL:
        return False
    try:
        requests.head(SUPABASE_URL, timeout=timeout)
        return True
    except Exception:
        return False


def fetch_license_from_supabase() -> Optional[dict]:
    """
    Fetch license data for this installation from Supabase REST.
    Expects a row in table `license` filtered by installation_id.
    """
    if not (SUPABASE_URL and SUPABASE_ANON_KEY and INSTALLATION_ID):
        return None

    url = f"{SUPABASE_URL}/rest/v1/license"
    params = {
        "installation_id": f"eq.{INSTALLATION_ID}",
        "select": "status,valid_until",
    }
    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        "Accept": "application/json",
    }

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=5)
    except Exception:
        return None

    if not resp.ok:
        return None

    try:
        data = resp.json()
    except Exception:
        return None

    if not data:
        return None

    row = data[0]
    return {
        "status": bool(row.get("status")),
        "valid_until": row.get("valid_until"),  # ISO8601 string
    }


def _parse_iso_datetime(value: str) -> Optional[datetime]:
    if not value:
        return None
    try:
        # Allow common Z-suffix UTC strings
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def load_cached_license() -> Optional[dict]:
    if not CACHE_FILE.exists():
        return None
    try:
        with CACHE_FILE.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_license_cache(license_data: dict) -> None:
    """Store license data + last_online_check in a local JSON file."""
    cache_payload = {
        "status": bool(license_data.get("status")),
        "valid_until": license_data.get("valid_until"),
        "last_online_check": _now_utc().isoformat(),
    }
    try:
        with CACHE_FILE.open("w", encoding="utf-8") as f:
            json.dump(cache_payload, f)
    except Exception:
        # Cache failure should not crash the app
        pass


def is_license_valid(license_data: dict, now: Optional[datetime] = None) -> bool:
    now = now or _now_utc()
    if not license_data:
        return False

    status = bool(license_data.get("status"))
    valid_until_raw = license_data.get("valid_until")
    valid_until = _parse_iso_datetime(valid_until_raw) if isinstance(valid_until_raw, str) else None

    if not status or not valid_until:
        return False

    return now <= valid_until


def check_license() -> Tuple[bool, str]:
    """
    Main entry point.

    Rules:
    - If internet is available:
        - Fetch license from Supabase.
        - If valid, cache and allow.
        - If invalid, block with "License expired".
    - If internet is not available:
        - Read cached license file.
        - Allow only if valid_until is not expired AND
          offline usage has not exceeded MAX_OFFLINE_DAYS since last online check.
    """
    now = _now_utc()

    # Online path
    if has_internet():
        license_data = fetch_license_from_supabase()
        if not license_data or not is_license_valid(license_data, now):
            return False, "License expired or invalid. Please Renew the Key."

        # Cache successful online result
        save_license_cache(license_data)
        return True, "License valid (online)."

    # Offline path
    cache = load_cached_license()
    if not cache:
        return False, "No cached license found and no internet connection. Please go online to validate your license."

    if not is_license_valid(cache, now):
        return False, "Cached license has expired. Please go online to renew your license."

    # Enforce maximum offline duration based on last_online_check
    last_online_str = cache.get("last_online_check")
    last_online = _parse_iso_datetime(last_online_str) if isinstance(last_online_str, str) else None
    if not last_online:
        return False, "Offline usage limit reached. Please go online to validate your license."

    if now - last_online > timedelta(days=MAX_OFFLINE_DAYS):
        return False, f"Offline usage limit of {MAX_OFFLINE_DAYS} days exceeded. Please connect to the internet to re-validate your license."

    return True, "License valid (offline cache)."


def _prompt_for_new_license() -> bool:
    """
    Prompt the user to enter a new license installation_id,
    save it to config.json, and reload in-memory settings.

    Returns True if user provided a new installation_id, False otherwise.
    """
    try:
        import tkinter as tk
        from tkinter import simpledialog, messagebox

        root = tk.Tk()
        root.withdraw()

        new_installation_id = simpledialog.askstring(
            "Update License",
            "Enter new license (installation_id):",
            parent=root,
        )
        if not new_installation_id:
            root.destroy()
            return False

        # Update config file
        cfg = load_config()
        cfg.installation_id = new_installation_id.strip()
        save_config(cfg)

        # Reload module-level settings from updated config
        _reload_settings()

        messagebox.showinfo("License Updated", "License details saved. Retrying validation.")
        root.destroy()
        return True
    except Exception:
        return False


def _reload_settings() -> None:
    """Reload configuration into module-level settings."""
    global _app_config, SUPABASE_URL, SUPABASE_ANON_KEY, INSTALLATION_ID, MAX_OFFLINE_DAYS
    _app_config = load_config()
    SUPABASE_URL = os.getenv("SUPABASE_URL", _app_config.api_url or "")
    SUPABASE_ANON_KEY = os.getenv("SUPABASE_ANON_KEY", _app_config.supabase_key or "")
    INSTALLATION_ID = os.getenv("INSTALLATION_ID", _app_config.installation_id or "")
    try:
        MAX_OFFLINE_DAYS = int(os.getenv("MAX_OFFLINE_DAYS", str(_app_config.max_offline_days)))
    except Exception:
        MAX_OFFLINE_DAYS = 7


def ensure_valid_license_or_exit() -> None:
    """
    Helper to be called at app startup.
    Exits the process with an explanatory message if license invalid.
    """
    ok, msg = check_license()
    if ok:
        return

    # Try to show a GUI popup; fall back to console output if that fails.
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()  # hide the main root window
        choice = messagebox.askyesno(
            "License Error",
            f"{msg}\n\nWould you like to enter a new license now?",
            parent=root,
        )
        root.destroy()
        if not choice:
            raise SystemExit(1)
    except Exception:
        # If GUI popup fails (e.g., no display), print the message and exit.
        print(msg)
        raise SystemExit(1)

    # User chose to update license; prompt for new details and retry.
    updated = _prompt_for_new_license()
    if not updated:
        raise SystemExit(1)

    ok, retry_msg = check_license()
    if ok:
        return

    # Final failure: show message and exit.
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("License Error", retry_msg)
        root.destroy()
    except Exception:
        print(retry_msg)

    raise SystemExit(1)


