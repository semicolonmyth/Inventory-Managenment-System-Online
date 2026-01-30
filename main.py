import math
import customtkinter as ctk
from pathlib import Path
from PIL import Image


from db.local_db import get_session, init_db
from sync.uploader import CloudUploader
from sync.restorer import CloudRestorer
from ui.dashboard import AdminDashboardFrame, UserDashboardFrame
from ui.login import LoginFrame
from ui.new_sale import NewSaleFrame
from ui.products import ProductsFrame
from ui.reports import ReportsFrame
from ui.expenses import ExpensesFrame
from utils.config import load_config, save_config
from utils.theme_utils import get_theme_color
from license_manager import ensure_valid_license_or_exit


class MainWindow(ctk.CTk):
    """Main application window with left-side navigation."""

    def __init__(self) -> None:
        super().__init__()

        self.config = load_config()
        self.current_user = None

        # Ensure database and tables exist
        init_db()

        # Set appearance mode to "System" to support light/dark switching
        ctk.set_appearance_mode("dark")

        # Set UI scaling
        ctk.set_widget_scaling(self.config.ui_scaling)

        # Resolve theme path - handle both built-in themes and custom JSON files
        theme_path = self._resolve_theme_path(self.config.theme)
        ctk.set_default_color_theme(theme_path)

        self.title(self.config.app_title)
        self.geometry("1024x600")
        self.minsize(900, 520)

        # Set application icon
        self._set_app_icon()

        # Layout: navigation on the left, content on the right, footer at bottom
        self.columnconfigure(0, weight=0)
        self.columnconfigure(1, weight=1)
        self.rowconfigure(0, weight=1)
        self.rowconfigure(1, weight=0)  # Footer row (no expansion)

        self._create_nav()
        self._create_content_area()
        self._create_footer()

        # Start on login page
        self.show_frame("login")

    def _create_nav(self) -> None:
        # Keep reference so we can hide sidebar on login screen
        self.nav = ctk.CTkFrame(self, width=200)
        self.nav.grid(row=0, column=0, sticky="nsw", rowspan=1)
        self.nav.grid_propagate(False)

        # App title / logo area with logo image
        logo_frame = ctk.CTkFrame(self.nav, fg_color="transparent")
        logo_frame.pack(fill="x", padx=16, pady=(16, 12))

        # Load and display logo
        icons_dir = Path(__file__).parent / "Icons"
        logo_path = icons_dir / "Bk_Logo.png"
        if logo_path.exists():
            try:
                logo_image = Image.open(logo_path)
                logo_image = logo_image.resize((40, 40), Image.Resampling.LANCZOS)
                logo_photo = ctk.CTkImage(
                    light_image=logo_image, dark_image=logo_image, size=(40, 40)
                )
                logo_label = ctk.CTkLabel(logo_frame, image=logo_photo, text="")
                logo_label.pack(side="left", padx=(0, 10))
            except Exception:
                pass  # If logo fails to load, continue without it

        title_label = ctk.CTkLabel(
            logo_frame,
            text=self.config.app_title,
            font=ctk.CTkFont(size=18, weight="bold"),
            anchor="w",
            fg_color="transparent",
        )
        title_label.pack(side="left", fill="x", expand=True)

        # Remove any selection/highlight background
        try:
            # Access the underlying tkinter label to remove selection background
            tk_label = title_label._text_label
            tk_label.configure(selectbackground=tk_label.cget("bg"))
            tk_label.configure(highlightthickness=0)
        except Exception:
            pass

        # Icon mapping for buttons
        icon_map = {
            "dashboard": "Dasboard.png",
            "billing": "Billing.png",
            "products": "Products.png",
            "expenses": "Reports.png",  # Placeholder icon
            "employees": "Employees.png",
            "reports": "Reports.png",
            "settings": "settings.png",
            "upload": "Upload.png",
            "login": "login.png",
        }

        buttons = [
            ("Dashboard", "dashboard"),
            ("Billing", "billing"),
            ("Products", "products"),
            ("Expenses", "expenses"),
            ("Employees", "employees"),
            ("Reports", "reports"),
            ("Settings", "settings"),
            ("Upload", "upload"),
            ("Login", "login"),
        ]

        icons_dir = Path(__file__).parent / "Icons"
        self.nav_buttons: dict[str, ctk.CTkButton] = {}
        for text, key in buttons:
            # Load icon if available using PIL
            icon_image = None
            icon_path = icons_dir / icon_map.get(key, "")
            if icon_path.exists():
                try:
                    pil_image = Image.open(icon_path)
                    icon_image = ctk.CTkImage(
                        light_image=pil_image, dark_image=pil_image, size=(20, 20)
                    )
                except Exception:
                    icon_image = None

            btn = ctk.CTkButton(
                self.nav,
                text=text,
                command=lambda k=key: self.show_frame(k),
                anchor="w",  # Left align text and icon
                height=38,
                font=ctk.CTkFont(size=13, weight="bold"),
                image=icon_image,
                compound="left" if icon_image else None,
            )
            btn.pack(fill="x", padx=20, pady=4)
            self.nav_buttons[key] = btn
        self.appearance_mode = "dark"

    def _refresh_nav(self) -> None:
        allowed = {
            True: [
                "login",
                "dashboard",
                "billing",
                "products",
                "expenses",
                "reports",
                "settings",
                "employees",
                "upload",
            ],
            False: [
                "login",
                "dashboard",
                "billing",
                "products",
                "expenses",
                "reports",
                "settings",
                "upload",
            ],
        }
        is_admin = bool(
            getattr(self, "current_user", None)
            and getattr(self.current_user, "is_admin", False)
        )
        show_keys = set(allowed[is_admin])
        for key, btn in getattr(self, "nav_buttons", {}).items():
            if key in show_keys:
                btn.pack_forget()
                btn.pack(
                    fill="x", padx=20, pady=4
                )  # Match the same padding as initial creation
            else:
                btn.pack_forget()
        # Rename Reports to s for non-admin
        if "reports" in getattr(self, "nav_buttons", {}):
            self.nav_buttons["reports"].configure(
                text="Sales" if not is_admin else "Reports"
            )

    def _create_content_area(self) -> None:
        # Root content area with top title bar and central page container
        self.content = ctk.CTkFrame(self)
        self.content.grid(row=0, column=1, sticky="nsew", rowspan=1)
        self.content.rowconfigure(0, weight=0)  # top bar
        self.content.rowconfigure(1, weight=1)  # main page area
        self.content.columnconfigure(0, weight=1)

        # Top bar
        self.top_bar = ctk.CTkFrame(self.content, height=48)
        self.top_bar.grid(row=0, column=0, sticky="ew")
        self.top_bar.grid_propagate(False)
        self.top_bar.columnconfigure(0, weight=1)

        self.top_title_label = ctk.CTkLabel(
            self.top_bar,
            text="Dashboard",
            font=ctk.CTkFont(size=18, weight="bold"),
            anchor="w",
        )
        self.top_title_label.grid(row=0, column=0, padx=20, pady=10, sticky="w")

        # Inner page container
        self.page_container = ctk.CTkFrame(
            self.content,
            fg_color="transparent",
        )
        self.page_container.grid(row=1, column=0, sticky="nsew", padx=16, pady=12)
        self.page_container.rowconfigure(0, weight=1)
        self.page_container.columnconfigure(0, weight=1)

        # Pre-create known frames
        self.frames: dict[str, ctk.CTkFrame] = {
            "login": LoginFrame(self.page_container, app=self),
            "dashboard_admin": AdminDashboardFrame(self.page_container, app=self),
            "dashboard_user": UserDashboardFrame(self.page_container, app=self),
            "billing": NewSaleFrame(self.page_container, app=self),
            "products": ProductsFrame(self.page_container, app=self),
            "expenses": ExpensesFrame(self.page_container, app=self),
            "reports": ReportsFrame(self.page_container, app=self),
        }

        for frame in self.frames.values():
            frame.grid(row=0, column=0, sticky="nsew")

        # Simple placeholders / special pages
        self.frames["settings"] = self._make_settings_frame()
        self.frames["employees"] = self._make_employees_frame()
        self.frames["upload"] = self._make_upload_frame()
        self.frames["settings"].grid(row=0, column=0, sticky="nsew")
        self.frames["employees"].grid(row=0, column=0, sticky="nsew")
        self.frames["upload"].grid(row=0, column=0, sticky="nsew")

    def _create_footer(self) -> None:
        """Create animated footer at the bottom of the window."""
        # Footer frame spanning both columns
        self.footer = ctk.CTkFrame(self, height=28, fg_color="transparent")
        self.footer.grid(row=1, column=0, columnspan=2, sticky="ew")
        self.footer.grid_propagate(False)
        self.footer.columnconfigure(0, weight=1)

        # Animated footer label
        footer_text = "Store Management System by Semicolon! For any help| Contact: 03253260029"
        self.footer_label = ctk.CTkLabel(
            self.footer,
            text=footer_text,
            font=ctk.CTkFont(size=9),
        )
        self.footer_label.grid(row=0, column=0, pady=3)

        # Animation variables
        self.animation_phase = 0.0
        self.animation_running = True

        # Start animation
        self._animate_footer()

    def _get_theme_footer_color(self) -> tuple[int, int, int]:
        """Get base footer color based on current theme."""
        appearance = ctk.get_appearance_mode()

        # Get theme-specific colors
        if appearance == "Dark":
            # For dark theme: use a light accent color (cyan/blue)
            # Base color: light blue/cyan that stands out on dark background
            return (100, 180, 255)  # Light blue
        elif appearance == "Light":
            # For light theme: use a darker accent color
            # Base color: blue that stands out on light background
            return (50, 120, 220)  # Medium blue
        else:
            # System/default: use adaptive color
            # Use a neutral blue that works in both
            return (74, 158, 255)  # Standard blue

    def _animate_footer(self) -> None:
        """Animate footer with subtle color pulse effect based on theme."""
        if not self.animation_running:
            return

        try:
            # Get theme-appropriate base color
            base_r, base_g, base_b = self._get_theme_footer_color()

            # Create a smooth pulse effect using sine wave
            # Oscillate between 0.6 and 1.0 for subtle effect
            phase = math.sin(self.animation_phase) * 0.2 + 0.8

            # Create a gradient effect by varying brightness
            r = max(0, min(255, int(base_r * phase)))
            g = max(0, min(255, int(base_g * phase)))
            b = max(0, min(255, int(base_b * phase)))
            color_hex = f"#{r:02x}{g:02x}{b:02x}"

            # Apply color
            self.footer_label.configure(text_color=color_hex)

            # Increment phase for next animation step
            self.animation_phase += 0.04  # Controls animation speed (slower = smoother)

            # Continue animation after 50ms
            self.after(50, self._animate_footer)
        except Exception:
            # If animation fails, use default theme color
            try:
                appearance = ctk.get_appearance_mode()
                if appearance == "Dark":
                    self.footer_label.configure(text_color="#64B4FF")
                elif appearance == "Light":
                    self.footer_label.configure(text_color="#3278DC")
                else:
                    self.footer_label.configure(text_color="#4A9EFF")
            except Exception:
                pass

    def _make_placeholder(self, title: str) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(self.page_container)
        label = ctk.CTkLabel(
            frame,
            text=title,
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        label.pack(padx=24, pady=24, anchor="w")
        return frame

    def _make_upload_frame(self) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(self.page_container)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        # Make it scrollable so all content is visible
        scrollable = ctk.CTkScrollableFrame(frame)
        scrollable.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        scrollable.columnconfigure(0, weight=1)

        # Upload section
        upload_label = ctk.CTkLabel(
            scrollable,
            text="Upload to Cloud (Supabase)",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        upload_label.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="w")

        upload_info = ctk.CTkLabel(
            scrollable,
            text="Click the button below to sync products, invoices, "
            "and stock transactions to Supabase.",
            justify="left",
            wraplength=520,
        )
        upload_info.grid(row=1, column=0, padx=20, pady=(0, 10), sticky="w")

        upload_btn = ctk.CTkButton(
            scrollable,
            text="Upload Data",
            command=self.run_cloud_sync,
        )
        upload_btn.grid(row=2, column=0, padx=20, pady=(10, 5), sticky="w")

        self.upload_status_label = ctk.CTkLabel(scrollable, text="", text_color="green")
        self.upload_status_label.grid(
            row=3, column=0, padx=20, pady=(5, 20), sticky="w"
        )

        # Separator
        separator = ctk.CTkFrame(scrollable, height=2, fg_color="gray50")
        separator.grid(row=4, column=0, sticky="ew", padx=20, pady=10)

        # Restore Backup section
        restore_label = ctk.CTkLabel(
            scrollable,
            text="Restore Backup from Cloud",
            font=ctk.CTkFont(size=18, weight="bold"),
        )
        restore_label.grid(row=5, column=0, padx=20, pady=(20, 10), sticky="w")

        restore_info = ctk.CTkLabel(
            scrollable,
            text="⚠️ Warning: This will replace all local data with data from Supabase. "
            "This action cannot be undone. Make sure you have a backup if needed.",
            justify="left",
            wraplength=520,
            text_color="orange",
        )
        restore_info.grid(row=6, column=0, padx=20, pady=(0, 10), sticky="w")

        restore_btn = ctk.CTkButton(
            scrollable,
            text="Restore Backup from Supabase",
            command=self.run_restore_backup,
            fg_color="#DC3545",
            hover_color="#C82333",
        )
        restore_btn.grid(row=7, column=0, padx=20, pady=(10, 5), sticky="w")

        self.restore_status_label = ctk.CTkLabel(
            scrollable, text="", text_color="green"
        )
        self.restore_status_label.grid(
            row=8, column=0, padx=20, pady=(5, 20), sticky="w"
        )

        return frame

    def show_frame(self, key: str) -> None:
        if hasattr(self, "nav_buttons"):
            self._refresh_nav()
        if key == "dashboard":
            if getattr(self, "current_user", None) and getattr(
                self.current_user, "is_admin", False
            ):
                key = "dashboard_admin"
            else:
                key = "dashboard_user"
        frame = self.frames.get(key)
        if frame is not None:
            if key == "login":
                self.top_title_label.configure(
                    text="Store Management System", anchor="center"
                )

                if hasattr(self, "nav"):
                    self.nav.grid_remove()
                self.content.grid_configure(
                    row=0, column=0, columnspan=2, sticky="nsew"
                )
            else:
                if key == "dashboard_admin":
                    self.top_title_label.configure(text=f"")  # Remove duplicate title
                elif key == "dashboard_user":
                    self.top_title_label.configure(text=f"")  # Remove duplicate title
                elif key == "billing":
                    self.top_title_label.configure(text=f"")
                elif key == "products":
                    self.top_title_label.configure(text=f"")
                    # Update delete button visibility for admin users
                    if hasattr(
                        self.frames.get("products"), "_update_delete_button_visibility"
                    ):
                        self.frames["products"]._update_delete_button_visibility()
                elif key == "expenses":
                    self.top_title_label.configure(text="Expense Tracking")
                    if hasattr(self.frames.get("expenses"), "load_expenses"):
                        self.frames["expenses"].load_expenses()
                elif key == "reports":
                    self.top_title_label.configure(text="Reports")
                elif key == "settings":
                    self.top_title_label.configure(text="Settings")
                elif key == "employees":
                    self.top_title_label.configure(text="Employee Management")
                    # Refresh employees frame content when accessed
                    if hasattr(self, "employees_frame_container"):
                        self._refresh_employees_frame()
                elif key == "upload":
                    self.top_title_label.configure(
                        text="Here You can Upload or Restore your data from Cloud"
                    )
                if hasattr(self, "nav"):
                    self.nav.grid(row=0, column=0, sticky="nsw")
                self.content.grid_configure(
                    row=0, column=1, columnspan=1, sticky="nsew"
                )
            frame.tkraise()

    def _set_app_icon(self) -> None:
        """Set the application window icon."""
        icons_dir = Path(__file__).parent / "Icons"
        icon_path = icons_dir / "appico.ico"

        if icon_path.exists():
            try:
                # Method 1: Use iconbitmap for .ico files (best for Windows)
                self.iconbitmap(str(icon_path))
            except Exception:
                # Method 2: Fallback - convert to PhotoImage if iconbitmap fails
                try:
                    # Load the icon image
                    icon_image = Image.open(icon_path)
                    # Convert to PhotoImage for iconphoto
                    import tkinter as tk
                    from PIL import ImageTk

                    photo = ImageTk.PhotoImage(icon_image)
                    # Set as window icon (False means don't set for all future toplevels)
                    self.iconphoto(False, photo)
                    # Keep a reference to prevent garbage collection
                    self._icon_photo = photo
                except Exception:
                    # If both methods fail, try with PNG logo as last resort
                    logo_path = icons_dir / "Bk_Logo.png"
                    if logo_path.exists():
                        try:
                            icon_image = Image.open(logo_path)
                            import tkinter as tk
                            from PIL import ImageTk

                            photo = ImageTk.PhotoImage(icon_image)
                            self.iconphoto(False, photo)
                            self._icon_photo = photo
                        except Exception:
                            # If all methods fail, continue without icon
                            pass

    def _resolve_theme_path(self, theme: str) -> str:
        """Resolve theme path to absolute path if it's a custom theme file.

        Built-in themes: "blue", "dark-blue", "green" - return as-is
        Custom themes: "themes/lavender.json" - convert to absolute path
        """
        # Built-in themes don't need path resolution
        if theme in ["blue", "dark-blue", "green"]:
            return theme

        # Custom theme - check if it's a relative path
        if theme.startswith("themes/"):
            themes_dir = Path(__file__).parent / "themes"
            theme_file = themes_dir / theme.replace("themes/", "")
            if theme_file.exists():
                # Return absolute path as string
                return str(theme_file.absolute())

        # If it's already an absolute path, return as-is
        if Path(theme).is_absolute() and Path(theme).exists():
            return theme

        # Fallback: return as-is (might be a relative path that works)
        return theme

    def _get_available_themes(self) -> dict[str, str]:
        """Get all available themes (built-in + custom JSON files).

        Returns dict mapping display names to theme paths/names.
        """
        themes = {
            "Blue (Light)": "blue",
            "Dark Blue": "dark-blue",
            "Green": "green",
        }

        # Add custom themes from themes folder
        themes_dir = Path(__file__).parent / "themes"
        if themes_dir.exists():
            for theme_file in themes_dir.glob("*.json"):
                theme_name = theme_file.stem.replace("_", " ").title()
                # Store relative path for config, but use absolute for loading
                theme_path = f"themes/{theme_file.name}"
                themes[theme_name] = theme_path

        return themes

    def _set_color_scheme(self, theme_name: str) -> None:
        """Change theme and save to config.json.

        theme_name can be:
        - Built-in theme: "blue", "dark-blue", "green"
        - Custom theme: "themes/lavender.json", "themes/breeze.json", etc.
        """
        try:
            # Resolve theme path (convert to absolute if custom theme)
            theme_path = self._resolve_theme_path(theme_name)
            ctk.set_default_color_theme(theme_path)
            # Save relative path to config (for portability)
            self.config.theme = theme_name
            save_config(self.config)

            # Note: Some widgets with hardcoded colors may need app restart to fully update
            # Most theme-aware widgets will update when frames are re-accessed
        except Exception as e:
            # If theme fails to load, try to fall back to dark-blue
            try:
                ctk.set_default_color_theme("dark-blue")
                self.config.theme = "dark-blue"
                save_config(self.config)
            except Exception:
                pass

    def _make_settings_frame(self) -> ctk.CTkFrame:
        frame = ctk.CTkFrame(self.page_container)
        frame.columnconfigure(0, weight=1)

        # Scrollable frame for settings
        scrollable = ctk.CTkScrollableFrame(frame)
        scrollable.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        scrollable.columnconfigure(0, weight=1)

        title = ctk.CTkLabel(
            scrollable,
            text="Settings",
            font=ctk.CTkFont(size=20, weight="bold"),
        )
        title.grid(row=0, column=0, padx=10, pady=(10, 20), sticky="w")

        row = 1

        # ========== UI Scaling ==========
        scaling_frame = ctk.CTkFrame(scrollable)
        scaling_frame.grid(row=row, column=0, sticky="ew", padx=10, pady=10)
        scaling_frame.columnconfigure(1, weight=1)
        row += 1

        ctk.CTkLabel(
            scaling_frame, text="UI Scaling", font=ctk.CTkFont(size=14, weight="bold")
        ).grid(row=0, column=0, columnspan=2, padx=15, pady=(15, 5), sticky="w")

        ctk.CTkLabel(scaling_frame, text="Adjust the size of UI elements:").grid(
            row=1, column=0, columnspan=2, padx=15, pady=(5, 10), sticky="w"
        )

        self.scaling_label = ctk.CTkLabel(
            scaling_frame, text=f"{self.config.ui_scaling:.1f}x"
        )
        self.scaling_label.grid(row=2, column=0, padx=15, pady=10, sticky="w")

        scaling_slider = ctk.CTkSlider(
            scaling_frame,
            from_=0.75,
            to=1.5,
            number_of_steps=15,
            command=self._on_scaling_change,
        )
        scaling_slider.set(self.config.ui_scaling)
        scaling_slider.grid(row=2, column=1, padx=15, pady=10, sticky="ew")

        ctk.CTkLabel(scaling_frame, text="(0.75x - 1.5x)").grid(
            row=3, column=0, columnspan=2, padx=15, pady=(0, 15), sticky="w"
        )

        # ========== Appearance Mode ==========
        appearance_frame = ctk.CTkFrame(scrollable)
        appearance_frame.grid(row=row, column=0, sticky="ew", padx=10, pady=10)
        appearance_frame.columnconfigure(1, weight=1)
        row += 1

        ctk.CTkLabel(
            appearance_frame,
            text="Appearance Mode",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, columnspan=2, padx=15, pady=(15, 5), sticky="w")

        ctk.CTkLabel(appearance_frame, text="Choose light or dark mode:").grid(
            row=1, column=0, columnspan=2, padx=15, pady=(5, 10), sticky="w"
        )

        appearance_combo = ctk.CTkComboBox(
            appearance_frame,
            values=["System", "Dark", "Light"],
            command=lambda v: self._set_appearance_mode(v),
            width=220,
        )
        appearance_combo.set(ctk.get_appearance_mode())
        appearance_combo.grid(row=2, column=0, padx=15, pady=(0, 15), sticky="w")

        # ========== Color Theme ==========
        theme_frame = ctk.CTkFrame(scrollable)
        theme_frame.grid(row=row, column=0, sticky="ew", padx=10, pady=10)
        theme_frame.columnconfigure(1, weight=1)
        row += 1

        ctk.CTkLabel(
            theme_frame, text="Color Theme", font=ctk.CTkFont(size=14, weight="bold")
        ).grid(row=0, column=0, columnspan=2, padx=15, pady=(15, 5), sticky="w")

        ctk.CTkLabel(theme_frame, text="Choose a color scheme:").grid(
            row=1, column=0, columnspan=2, padx=15, pady=(5, 10), sticky="w"
        )

        # Get all available themes (built-in + custom)
        theme_options = self._get_available_themes()

        # Reverse lookup to find display name from current theme
        current_display = "Dark Blue"  # default
        for display, theme_val in theme_options.items():
            if theme_val == self.config.theme:
                current_display = display
                break

        scheme_combo = ctk.CTkComboBox(
            theme_frame,
            values=list(theme_options.keys()),
            command=lambda v: self._set_color_scheme(theme_options[v]),
            width=220,
        )
        scheme_combo.set(current_display)
        scheme_combo.grid(row=2, column=0, padx=15, pady=(0, 15), sticky="w")

        ctk.CTkLabel(
            theme_frame,
            text="Custom themes from themes/ folder are auto-detected.",
            font=ctk.CTkFont(size=10),
            text_color="gray",
        ).grid(row=3, column=0, columnspan=2, padx=15, pady=(0, 15), sticky="w")

        # ========== Password Change (Admin only) ==========
        is_admin = bool(
            getattr(self, "current_user", None)
            and getattr(self.current_user, "is_admin", False)
        )

        if is_admin:
            password_frame = ctk.CTkFrame(scrollable)
            password_frame.grid(row=row, column=0, sticky="ew", padx=10, pady=10)
            password_frame.columnconfigure(1, weight=1)
            row += 1

            ctk.CTkLabel(
                password_frame,
                text="Change Password",
                font=ctk.CTkFont(size=14, weight="bold"),
            ).grid(row=0, column=0, columnspan=2, padx=15, pady=(15, 5), sticky="w")

            ctk.CTkLabel(password_frame, text="Current Password:").grid(
                row=1, column=0, padx=15, pady=10, sticky="w"
            )
            self.current_password_entry = ctk.CTkEntry(
                password_frame,
                placeholder_text="Enter current password",
                show="*",
                width=250,
            )
            self.current_password_entry.grid(
                row=1, column=1, padx=15, pady=10, sticky="w"
            )

            ctk.CTkLabel(password_frame, text="New Password:").grid(
                row=2, column=0, padx=15, pady=10, sticky="w"
            )
            self.new_password_entry = ctk.CTkEntry(
                password_frame,
                placeholder_text="Enter new password",
                show="*",
                width=250,
            )
            self.new_password_entry.grid(row=2, column=1, padx=15, pady=10, sticky="w")

            ctk.CTkLabel(password_frame, text="Confirm Password:").grid(
                row=3, column=0, padx=15, pady=10, sticky="w"
            )
            self.confirm_password_entry = ctk.CTkEntry(
                password_frame,
                placeholder_text="Confirm new password",
                show="*",
                width=250,
            )
            self.confirm_password_entry.grid(
                row=3, column=1, padx=15, pady=10, sticky="w"
            )

            self.password_status_label = ctk.CTkLabel(
                password_frame, text="", font=ctk.CTkFont(size=11)
            )
            self.password_status_label.grid(
                row=4, column=0, columnspan=2, padx=15, pady=(5, 10), sticky="w"
            )

            change_password_btn = ctk.CTkButton(
                password_frame,
                text="Change Password",
                command=self._change_password,
                width=150,
            )
            change_password_btn.grid(row=5, column=0, padx=15, pady=(0, 15), sticky="w")

        frame.rowconfigure(0, weight=1)
        return frame

    def _on_scaling_change(self, value: float) -> None:
        """Handle UI scaling change."""
        self.scaling_label.configure(text=f"{value:.1f}x")
        ctk.set_widget_scaling(value)
        self.config.ui_scaling = value
        save_config(self.config)

    def _set_appearance_mode(self, mode: str) -> None:
        """Change appearance mode (System/Dark/Light)."""
        try:
            ctk.set_appearance_mode(mode)
        except Exception:
            pass

    def _change_password(self) -> None:
        """Change admin password."""
        if not getattr(self, "current_user", None):
            self._show_password_status("No user logged in.", "red")
            return

        current = self.current_password_entry.get()
        new = self.new_password_entry.get()
        confirm = self.confirm_password_entry.get()

        if not current or not new or not confirm:
            self._show_password_status("All fields are required.", "red")
            return

        if new != confirm:
            self._show_password_status("New passwords do not match.", "red")
            return

        if len(new) < 3:
            self._show_password_status("Password must be at least 3 characters.", "red")
            return

        # Verify current password
        if self.current_user.password_hash != current:
            self._show_password_status("Current password is incorrect.", "red")
            return

        # Update password
        from db.local_db import get_session
        from db.models import User

        session = get_session()
        try:
            user = session.query(User).get(self.current_user.id)
            if user:
                user.password_hash = new
                session.commit()
                self.current_user.password_hash = new
                self._show_password_status("Password changed successfully!", "green")
                # Clear fields
                self.current_password_entry.delete(0, "end")
                self.new_password_entry.delete(0, "end")
                self.confirm_password_entry.delete(0, "end")
            else:
                self._show_password_status("User not found.", "red")
        except Exception as e:
            session.rollback()
            self._show_password_status(f"Error: {str(e)}", "red")
        finally:
            session.close()

    def _show_password_status(self, message: str, color: str) -> None:
        """Show password change status."""
        if hasattr(self, "password_status_label"):
            self.password_status_label.configure(text=message, text_color=color)

    def _make_employees_frame(self) -> ctk.CTkFrame:
        """Create employee management frame for admin."""
        frame = ctk.CTkFrame(self.page_container)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(1, weight=1)

        # Store frame reference for dynamic content
        self.employees_frame_container = frame

        # Create placeholder - will be populated when accessed
        self._refresh_employees_frame()

        return frame

    def _refresh_employees_frame(self) -> None:
        """Refresh employees frame content based on current user."""
        # Clear existing content
        for widget in self.employees_frame_container.winfo_children():
            widget.destroy()

        # Check if admin
        is_admin = bool(
            getattr(self, "current_user", None)
            and getattr(self.current_user, "is_admin", False)
        )

        if not is_admin:
            ctk.CTkLabel(
                self.employees_frame_container,
                text="Access Denied\nOnly administrators can manage employees.",
                font=ctk.CTkFont(size=16),
                text_color="red",
            ).pack(expand=True)
            return

        # Header with Add button
        header = ctk.CTkFrame(self.employees_frame_container, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 10))
        header.columnconfigure(0, weight=1)

        add_btn = ctk.CTkButton(
            header, text="+ Add Employee", command=self._add_employee, width=150
        )
        add_btn.grid(row=0, column=0, padx=10, sticky="e")

        # Employees table
        table_frame = ctk.CTkFrame(self.employees_frame_container)
        table_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 20))
        table_frame.columnconfigure(0, weight=1)
        table_frame.rowconfigure(0, weight=1)

        import tkinter.ttk as ttk

        style = ttk.Style()
        style.configure(
            "Employees.Treeview",
            background="white",
            foreground="black",
            fieldbackground="white",
            borderwidth=0,
        )
        style.configure("Employees.Treeview.Heading", font=("TkDefaultFont", 9, "bold"))

        self.employees_table = ttk.Treeview(
            table_frame,
            columns=("username", "role", "created", "actions"),
            show="headings",
            style="Employees.Treeview",
        )

        self.employees_table.heading("username", text="Username")
        self.employees_table.heading("role", text="Role")
        self.employees_table.heading("created", text="Created")
        self.employees_table.heading("actions", text="Actions")

        self.employees_table.column("username", width=250, anchor="w")
        self.employees_table.column("role", width=120, anchor="center")
        self.employees_table.column("created", width=150, anchor="w")
        self.employees_table.column(
            "actions", width=0, stretch=False
        )  # Hide actions column

        scrollbar = ttk.Scrollbar(
            table_frame, orient="vertical", command=self.employees_table.yview
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.employees_table.configure(yscrollcommand=scrollbar.set)
        self.employees_table.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)

        # Action buttons frame
        actions_frame = ctk.CTkFrame(
            self.employees_frame_container, fg_color="transparent"
        )
        actions_frame.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 20))

        self.edit_employee_btn = ctk.CTkButton(
            actions_frame,
            text="Edit Selected",
            command=self._edit_selected_employee,
            width=120,
            state="disabled",
        )
        self.edit_employee_btn.pack(side="left", padx=5)

        self.delete_employee_btn = ctk.CTkButton(
            actions_frame,
            text="Delete Selected",
            command=self._delete_selected_employee,
            width=120,
            fg_color="#DC3545",
            hover_color="#C82333",
            state="disabled",
        )
        self.delete_employee_btn.pack(side="left", padx=5)

        refresh_btn = ctk.CTkButton(
            actions_frame, text="Refresh", command=self._load_employees, width=100
        )
        refresh_btn.pack(side="right", padx=5)

        # Bind selection change and double-click
        self.employees_table.bind("<<TreeviewSelect>>", self._on_employee_select)
        self.employees_table.bind("<Double-1>", self._on_employee_double_click)

        # Load employees
        self._load_employees()

    def _on_employee_select(self, event) -> None:
        """Enable/disable action buttons based on selection."""
        selection = self.employees_table.selection()
        if selection:
            self.edit_employee_btn.configure(state="normal")
            self.delete_employee_btn.configure(state="normal")
        else:
            self.edit_employee_btn.configure(state="disabled")
            self.delete_employee_btn.configure(state="disabled")

    def _edit_selected_employee(self) -> None:
        """Edit selected employee."""
        selection = self.employees_table.selection()
        if not selection:
            return
        user_id = int(selection[0])
        from db.local_db import get_session
        from db.models import User

        session = get_session()
        try:
            user = session.query(User).get(user_id)
            if user:
                self._edit_employee(user)
        finally:
            session.close()

    def _delete_selected_employee(self) -> None:
        """Delete selected employee."""
        selection = self.employees_table.selection()
        if not selection:
            return
        user_id = int(selection[0])
        from db.local_db import get_session
        from db.models import User

        session = get_session()
        try:
            user = session.query(User).get(user_id)
            if user:
                self._delete_employee(user)
        finally:
            session.close()

    def _load_employees(self) -> None:
        """Load employees into table."""
        # Check if employees table exists
        if not hasattr(self, "employees_table"):
            return

        from db.local_db import get_session
        from db.models import User

        # Clear existing rows
        for row in self.employees_table.get_children():
            self.employees_table.delete(row)

        session = get_session()
        try:
            users = session.query(User).order_by(User.username).all()
            for user in users:
                role = "Admin" if user.is_admin else "User"
                created = (
                    user.created_at.date().isoformat() if user.created_at else "Unknown"
                )

                # Insert row
                self.employees_table.insert(
                    "",
                    "end",
                    iid=str(user.id),
                    values=(user.username, role, created, ""),
                )
        finally:
            session.close()

    def _on_employee_double_click(self, event) -> None:
        """Handle double-click on employee row."""
        selection = self.employees_table.selection()
        if not selection:
            return
        user_id = int(selection[0])
        from db.local_db import get_session
        from db.models import User

        session = get_session()
        try:
            user = session.query(User).get(user_id)
            if user:
                self._edit_employee(user)
        finally:
            session.close()

    def _add_employee(self) -> None:
        """Open dialog to add new employee."""
        win = ctk.CTkToplevel(self)
        win.title("Add Employee")
        win.geometry("400x300")
        win.grab_set()

        ctk.CTkLabel(
            win, text="Add New Employee", font=ctk.CTkFont(size=16, weight="bold")
        ).pack(pady=20)

        # Username
        ctk.CTkLabel(win, text="Username:").pack(pady=5)
        username_entry = ctk.CTkEntry(win, width=250)
        username_entry.pack(pady=5)

        # Password
        ctk.CTkLabel(win, text="Password:").pack(pady=5)
        password_entry = ctk.CTkEntry(win, width=250, show="*")
        password_entry.pack(pady=5)

        # Role
        ctk.CTkLabel(win, text="Role:").pack(pady=5)
        role_combo = ctk.CTkComboBox(win, values=["User", "Admin"], width=250)
        role_combo.set("User")
        role_combo.pack(pady=5)

        status_label = ctk.CTkLabel(win, text="", font=ctk.CTkFont(size=11))
        status_label.pack(pady=10)

        def save() -> None:
            username = username_entry.get().strip()
            password = password_entry.get()
            is_admin = role_combo.get() == "Admin"

            if not username or not password:
                status_label.configure(
                    text="Username and password required.", text_color="red"
                )
                return

            if len(password) < 3:
                status_label.configure(
                    text="Password must be at least 3 characters.", text_color="red"
                )
                return

            from db.local_db import get_session
            from db.models import User

            session = get_session()
            try:
                # Check if username exists
                existing = session.query(User).filter(User.username == username).first()
                if existing:
                    status_label.configure(
                        text="Username already exists.", text_color="red"
                    )
                    return

                # Create new user
                new_user = User(
                    username=username, password_hash=password, is_admin=is_admin
                )
                session.add(new_user)
                session.commit()

                status_label.configure(
                    text="Employee added successfully!", text_color="green"
                )
                self.after(1000, win.destroy)
                self._load_employees()
            except Exception as e:
                session.rollback()
                status_label.configure(text=f"Error: {str(e)}", text_color="red")
            finally:
                session.close()

        btn_frame = ctk.CTkFrame(win, fg_color="transparent")
        btn_frame.pack(pady=20)

        ctk.CTkButton(btn_frame, text="Save", command=save, width=100).pack(
            side="left", padx=10
        )
        ctk.CTkButton(
            btn_frame, text="Cancel", command=win.destroy, width=100, fg_color="gray50"
        ).pack(side="left", padx=10)

    def _edit_employee(self, user) -> None:
        """Open dialog to edit employee."""
        win = ctk.CTkToplevel(self)
        win.title("Edit Employee")
        win.geometry("400x350")
        win.grab_set()

        ctk.CTkLabel(
            win,
            text=f"Edit Employee: {user.username}",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(pady=20)

        # Username
        ctk.CTkLabel(win, text="Username:").pack(pady=5)
        username_entry = ctk.CTkEntry(win, width=250)
        username_entry.insert(0, user.username)
        username_entry.pack(pady=5)

        # Password (optional)
        ctk.CTkLabel(win, text="New Password (leave empty to keep current):").pack(
            pady=5
        )
        password_entry = ctk.CTkEntry(win, width=250, show="*")
        password_entry.pack(pady=5)

        # Role
        ctk.CTkLabel(win, text="Role:").pack(pady=5)
        role_combo = ctk.CTkComboBox(win, values=["User", "Admin"], width=250)
        role_combo.set("Admin" if user.is_admin else "User")
        role_combo.pack(pady=5)

        status_label = ctk.CTkLabel(win, text="", font=ctk.CTkFont(size=11))
        status_label.pack(pady=10)

        def save() -> None:
            new_username = username_entry.get().strip()
            new_password = password_entry.get()
            is_admin = role_combo.get() == "Admin"

            if not new_username:
                status_label.configure(text="Username is required.", text_color="red")
                return

            if new_password and len(new_password) < 3:
                status_label.configure(
                    text="Password must be at least 3 characters.", text_color="red"
                )
                return

            from db.local_db import get_session
            from db.models import User

            session = get_session()
            try:
                # Get user from database
                db_user = session.query(User).get(user.id)
                if not db_user:
                    status_label.configure(text="User not found.", text_color="red")
                    return

                # Check if username changed and if new username exists
                if new_username != user.username:
                    existing = (
                        session.query(User)
                        .filter(User.username == new_username)
                        .first()
                    )
                    if existing:
                        status_label.configure(
                            text="Username already exists.", text_color="red"
                        )
                        return
                    db_user.username = new_username

                # Update password if provided
                if new_password:
                    db_user.password_hash = new_password

                # Update role
                db_user.is_admin = is_admin

                session.commit()

                # Update current_user if it's the logged-in user
                if (
                    getattr(self, "current_user", None)
                    and self.current_user.id == user.id
                ):
                    self.current_user.username = db_user.username
                    self.current_user.is_admin = db_user.is_admin
                    if new_password:
                        self.current_user.password_hash = db_user.password_hash

                status_label.configure(
                    text="Employee updated successfully!", text_color="green"
                )
                self.after(1000, win.destroy)
                self._load_employees()
            except Exception as e:
                session.rollback()
                status_label.configure(text=f"Error: {str(e)}", text_color="red")
            finally:
                session.close()

        btn_frame = ctk.CTkFrame(win, fg_color="transparent")
        btn_frame.pack(pady=20)

        ctk.CTkButton(btn_frame, text="Save", command=save, width=100).pack(
            side="left", padx=10
        )
        ctk.CTkButton(
            btn_frame, text="Cancel", command=win.destroy, width=100, fg_color="gray50"
        ).pack(side="left", padx=10)

    def _delete_employee(self, user) -> None:
        """Delete employee with confirmation."""
        # Prevent deleting yourself
        if getattr(self, "current_user", None) and self.current_user.id == user.id:
            self._show_error_popup("You cannot delete your own account.")
            return

        # Confirmation dialog
        win = ctk.CTkToplevel(self)
        win.title("Confirm Delete")
        win.geometry("400x200")
        win.grab_set()

        ctk.CTkLabel(
            win,
            text=f"Are you sure you want to delete employee '{user.username}'?",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(pady=20)

        ctk.CTkLabel(win, text="This action cannot be undone.", text_color="red").pack(
            pady=10
        )

        def confirm_delete() -> None:
            from db.local_db import get_session
            from db.models import User

            session = get_session()
            try:
                db_user = session.query(User).get(user.id)
                if db_user:
                    session.delete(db_user)
                    session.commit()
                    win.destroy()
                    self._load_employees()
                    self._show_toast(
                        f"Employee '{user.username}' deleted successfully."
                    )
            except Exception as e:
                session.rollback()
                self._show_error_popup(f"Error deleting employee: {str(e)}")
            finally:
                session.close()

        btn_frame = ctk.CTkFrame(win, fg_color="transparent")
        btn_frame.pack(pady=20)

        ctk.CTkButton(
            btn_frame,
            text="Delete",
            command=confirm_delete,
            width=100,
            fg_color="#DC3545",
            hover_color="#C82333",
        ).pack(side="left", padx=10)
        ctk.CTkButton(
            btn_frame, text="Cancel", command=win.destroy, width=100, fg_color="gray50"
        ).pack(side="left", padx=10)

    def _show_error_popup(self, message: str) -> None:
        """Show error popup."""
        win = ctk.CTkToplevel(self)
        win.title("Error")
        win.grab_set()
        frame = ctk.CTkFrame(win)
        frame.pack(padx=20, pady=20)
        lbl = ctk.CTkLabel(
            frame, text=message, text_color="red", font=ctk.CTkFont(weight="bold")
        )
        lbl.pack(padx=15, pady=15)
        btn = ctk.CTkButton(frame, text="OK", command=win.destroy, width=100)
        btn.pack(padx=15, pady=(0, 15))

    def _show_toast(self, message: str) -> None:
        """Show toast notification."""
        toast = ctk.CTkToplevel(self)
        toast.overrideredirect(True)
        from utils.theme_utils import get_theme_color

        primary_color = get_theme_color("primary")
        frame = ctk.CTkFrame(toast, fg_color=primary_color)
        lbl = ctk.CTkLabel(
            frame, text=message, text_color="white", font=ctk.CTkFont(weight="bold")
        )
        lbl.pack(padx=15, pady=12)
        frame.pack()
        self.update_idletasks()
        x = self.winfo_rootx() + self.winfo_width() - 300
        y = self.winfo_rooty() + self.winfo_height() - 100
        toast.geometry(f"280x50+{x}+{y}")
        self.after(3000, toast.destroy)

    def run_cloud_sync(self) -> None:
        """Create uploader and run full sync when Upload button is pressed."""
        try:
            if hasattr(self, "upload_status_label"):
                self.upload_status_label.configure(text="Syncing...", text_color="blue")
            self.update()

            session = get_session()
            uploader = CloudUploader(session)
            uploader.upload_all()
            if hasattr(self, "upload_status_label"):
                self.upload_status_label.configure(text="Sync completed successfully.", text_color="green")
            self._show_toast("Sync completed successfully.")
        except Exception as exc:
            msg = str(exc)
            # Check for common network errors to give friendlier message
            if "NameResolutionError" in msg or "ConnectionError" in msg or "getaddrinfo failed" in msg:
                 msg = f"Connection failed. Please check your internet.\n({msg})"
            
            if hasattr(self, "upload_status_label"):
                self.upload_status_label.configure(
                    text=f"Sync failed: {msg}", text_color="red"
                )
            # Show error popup but do NOT raise (prevents crash)
            try:
                self._show_error_popup(f"Sync failed: {msg}")
            except Exception:
                pass # Fallback if popup fails
        finally:
            try:
                session.close()
            except Exception:
                pass

    def run_restore_backup(self) -> None:
        """Restore backup from Supabase when Restore Backup button is pressed."""
        # Show confirmation dialog
        win = ctk.CTkToplevel(self)
        win.title("Confirm Restore Backup")
        win.grab_set()
        win.geometry("500x250")

        warning_label = ctk.CTkLabel(
            win,
            text="⚠️ WARNING: Restore Backup",
            font=ctk.CTkFont(size=16, weight="bold"),
            text_color="red",
        )
        warning_label.pack(padx=20, pady=(20, 10))

        info_label = ctk.CTkLabel(
            win,
            text="This will replace ALL local data with data from Supabase:\n\n"
            "• All products\n"
            "• All invoices and invoice items\n"
            "• All stock transactions\n"
            "• All users\n\n"
            "This action CANNOT be undone!\n\n"
            "Are you sure you want to continue?",
            justify="left",
            wraplength=450,
        )
        info_label.pack(padx=20, pady=10)

        def confirm_restore() -> None:
            win.destroy()
            try:
                if hasattr(self, "restore_status_label"):
                    self.restore_status_label.configure(
                        text="Restoring backup...", text_color="blue"
                    )
                self.update()

                session = get_session()
                restorer = CloudRestorer(session)
                restorer.restore_all()

                if hasattr(self, "restore_status_label"):
                    self.restore_status_label.configure(
                        text="Backup restored successfully! Please restart the application.",
                        text_color="green",
                    )

                # Show success popup
                self._show_toast("Backup restored successfully!")
            except Exception as exc:
                if hasattr(self, "restore_status_label"):
                    self.restore_status_label.configure(
                        text=f"Restore failed: {exc}", text_color="red"
                    )
                self._show_error_popup(f"Restore failed: {exc}")
            finally:
                try:
                    session.close()
                except Exception:
                    pass

        btn_frame = ctk.CTkFrame(win, fg_color="transparent")
        btn_frame.pack(pady=20)

        ctk.CTkButton(
            btn_frame,
            text="Cancel",
            command=win.destroy,
            width=120,
            fg_color="gray50",
        ).pack(side="left", padx=10)

        ctk.CTkButton(
            btn_frame,
            text="Yes, Restore Backup",
            command=confirm_restore,
            width=180,
            fg_color="#DC3545",
            hover_color="#C82333",
        ).pack(side="left", padx=10)


def main() -> None:
    # Ensure license is valid before starting the main application window
    ensure_valid_license_or_exit()
    app = MainWindow()
    app.mainloop()


if __name__ == "__main__":
    main()
