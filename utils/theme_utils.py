"""
Theme utility functions for getting theme-aware colors.
"""

import customtkinter as ctk
import json
from pathlib import Path
from utils.config import load_config


def _resolve_theme_path(theme: str) -> str | Path:
    """Resolve theme path to absolute path if it's a custom theme file.

    Built-in themes: "blue", "dark-blue", "green" - return as-is
    Custom themes: "themes/lavender.json" - convert to absolute path
    """
    # Built-in themes don't need path resolution
    if theme in ["blue", "dark-blue", "green"]:
        return theme

    # Custom theme - check if it's a relative path
    if theme.startswith("themes/"):
        themes_dir = Path(__file__).parent.parent / "themes"
        theme_file = themes_dir / theme.replace("themes/", "")
        if theme_file.exists():
            return theme_file.absolute()

    # If it's already an absolute path, return as Path
    if Path(theme).is_absolute() and Path(theme).exists():
        return Path(theme)

    # Fallback: try to find it
    themes_dir = Path(__file__).parent.parent / "themes"
    theme_file = themes_dir / theme
    if theme_file.exists():
        return theme_file.absolute()

    # Fallback: return as-is (might be a relative path that works)
    return theme


def get_theme_button_color() -> str:
    """
    Extract the button color from the current theme.
    Returns the color string for the current appearance mode.
    """
    appearance = ctk.get_appearance_mode()
    appearance_idx = 0 if appearance == "Light" else 1

    try:
        # Load theme from config (same way main.py does it)
        config = load_config()
        theme_name = config.theme

        # Handle built-in themes (blue, dark-blue, green)
        if theme_name in ["blue", "dark-blue", "green"]:
            # Built-in theme button colors
            if theme_name == "blue":
                return "#1F538D" if appearance == "Light" else "#14375E"
            elif theme_name == "dark-blue":
                return "#1F538D" if appearance == "Light" else "#14375E"
            elif theme_name == "green":
                return "#2CC985" if appearance == "Light" else "#2FA572"
            return "#4A9EFF"

        # Handle custom theme JSON files
        theme_path = _resolve_theme_path(theme_name)
        path = Path(theme_path)
        if path.exists():
            try:
                with path.open("r", encoding="utf-8") as f:
                    theme_data = json.load(f)
                    button_config = theme_data.get("CTkButton", {})
                    fg_color = button_config.get("fg_color", ["#4A9EFF", "#4A9EFF"])

                    if isinstance(fg_color, list) and len(fg_color) > appearance_idx:
                        return fg_color[appearance_idx]
                    elif isinstance(fg_color, str):
                        return fg_color
            except Exception:
                # If reading/parsing fails, fall through to default
                pass
    except Exception as e:
        # Silently fall through to default
        pass

    # Fallback to default blue
    return "#4A9EFF"


def get_theme_color(color_type: str = "primary") -> str:
    """
    Get theme-aware color based on the current theme.

    Args:
        color_type: Type of color to get. Options:
            - "primary": Primary theme color (button color)
            - "success": Success/green color (keeps semantic meaning)
            - "error": Error/red color (keeps semantic meaning)
            - "warning": Warning/orange color (keeps semantic meaning)
            - "info": Info/blue color
            - "accent": Accent color variation

    Returns:
        Color string for current appearance mode
    """
    appearance = ctk.get_appearance_mode()
    appearance_idx = 0 if appearance == "Light" else 1

    if color_type == "primary":
        return get_theme_button_color()

    elif color_type == "success":
        # Green - keep semantic but ensure visibility
        return "#28A745"

    elif color_type == "error":
        # Red - keep semantic but ensure visibility
        return "#DC3545"

    elif color_type == "warning":
        # Orange - keep semantic but ensure visibility
        return "#FF9800"

    elif color_type == "info":
        # Info blue
        return "#17A2B8"

    elif color_type == "accent":
        # Try to get a variation of the primary color
        primary = get_theme_button_color()
        # Return primary as accent (can be customized later)
        return primary

    return get_theme_button_color()


def adjust_color_brightness(hex_color: str, factor: float) -> str:
    """
    Adjust the brightness of a hex color.

    Args:
        hex_color: Hex color string (e.g., "#FF6B6B")
        factor: Brightness factor (1.0 = no change, >1.0 = brighter, <1.0 = darker)

    Returns:
        Adjusted hex color string
    """
    try:
        hex_color = hex_color.lstrip("#")
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)

        r = max(0, min(255, int(r * factor)))
        g = max(0, min(255, int(g * factor)))
        b = max(0, min(255, int(b * factor)))

        return f"#{r:02x}{g:02x}{b:02x}"
    except Exception:
        return hex_color


def get_card_colors() -> dict[str, str]:
    """
    Get theme-aware colors for dashboard cards.
    Returns variations of the theme color for different card types.
    """
    primary = get_theme_button_color()

    return {
        "sales": primary,  # Primary theme color
        "revenue": adjust_color_brightness(primary, 1.1),  # Slightly brighter
        "discount": adjust_color_brightness(primary, 0.9),  # Slightly darker
        "warning": "#FF9800",  # Keep orange for warnings
        "accent": adjust_color_brightness(primary, 1.2),  # Brighter accent
    }
