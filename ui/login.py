import customtkinter as ctk

from db.local_db import get_session
from db.models import User


class LoginFrame(ctk.CTkFrame):
    """Login screen with username/password validation against SQLite."""

    def __init__(self, master: ctk.CTk, app, **kwargs) -> None:
        super().__init__(master, **kwargs)

        self.app = app

        # Centered login card on dark background
        self.configure(fg_color="transparent")
        self.rowconfigure(0, weight=1)
        self.rowconfigure(1, weight=0)
        self.rowconfigure(2, weight=1)
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=0)
        self.columnconfigure(2, weight=1)

        card = ctk.CTkFrame(self)
        card.grid(row=1, column=1, padx=60, pady=60, sticky="nsew")

        # Grid layout inside card to mimic screenshot
        card.columnconfigure(0, weight=0)
        card.columnconfigure(1, weight=1)
        for r in range(6):
            card.rowconfigure(r, weight=0)

        # Title centered across card
        title = ctk.CTkLabel(
            card,
            text="Login Page",
            font=ctk.CTkFont("poppins",size=28, weight="bold"),
        )
        title.grid(row=0, column=0, columnspan=2, padx=32, pady=(30, 20), sticky="n")

        # Help icon in top-right corner
      

        # Role row (visual only, does not affect login logic)
        role_label = ctk.CTkLabel(
            card,
            text="Role:",
            font=ctk.CTkFont("poppins",size=18, weight="bold"),
        )
        role_label.grid(row=1, column=0, padx=(32, 12), pady=12, sticky="e")

        self.role_combo = ctk.CTkComboBox(
            card,
            values=["Admin", "User"],
            width=280,
            height=40,
        )
        self.role_combo.set("Admin")
        self.role_combo.grid(row=1, column=1, padx=(0, 32), pady=12, sticky="ew")

        # Username row
        user_label = ctk.CTkLabel(
            card,
            text="Username:",
            font=ctk.CTkFont("poppins",size=18, weight="bold"),
        )
        user_label.grid(row=2, column=0, padx=(32, 12), pady=12, sticky="e")

        self.username_entry = ctk.CTkEntry(
            card,
            placeholder_text="Enter username",
            width=320,
            height=40,
        )
        self.username_entry.grid(row=2, column=1, padx=(0, 32), pady=12, sticky="ew")
        self.username_entry.bind("<Return>", lambda e: self._on_login())

        # Password row
        pass_label = ctk.CTkLabel(
            card,
            text="Password:",
            font=ctk.CTkFont("poppins",size=18, weight="bold"),
        )
        pass_label.grid(row=3, column=0, padx=(32, 12), pady=12, sticky="e")

        self.password_entry = ctk.CTkEntry(
            card,
            placeholder_text="Enter password",
            show="*",
            width=320,
            height=40,
        )
        self.password_entry.grid(row=3, column=1, padx=(0, 32), pady=12, sticky="ew")
        self.password_entry.bind("<Return>", lambda e: self._on_login())

        # Login button
        login_button = ctk.CTkButton(
            card,
            text="Login",
            command=self._on_login,
            height=45,
            width=320,
            font=ctk.CTkFont("poppins",size=16, weight="bold"),
        )
        login_button.grid(row=4, column=0, columnspan=2, padx=32, pady=(20, 8))

        # Forgot password + status area
        forgot_label = ctk.CTkLabel(
            card,
            text="Forgot Password?",
            font=ctk.CTkFont("poppins",size=14),
        )
        forgot_label.grid(row=5, column=0, columnspan=2, padx=32, pady=(8, 4), sticky="n")

        self.status_label = ctk.CTkLabel(
            card,
            text="",
            text_color="red",
            font=ctk.CTkFont("poppins",size=14),
        )
        self.status_label.grid(row=6, column=0, columnspan=2, padx=32, pady=(4, 24), sticky="w")

        # Focus username for fast keyboard entry
        self.username_entry.focus_set()

    def _on_login(self) :
        username = self.username_entry.get().strip()
        password = self.password_entry.get()

        if not username or not password:
            self._set_status("Please enter username and password.")
            return

        from utils.security import authenticate, hash_password

        user = None
        ok = False
        session = get_session()
        try:
            user = session.query(User).filter(User.username == username).first()
            if user is not None:
                ok, needs_upgrade = authenticate(user.password_hash, password)
                # Transparently migrate legacy plaintext rows to a hash.
                if ok and needs_upgrade:
                    user.password_hash = hash_password(password)
                    # Re-upload so the cloud copy replaces any legacy plaintext.
                    user.synced = False
                    session.commit()
        finally:
            session.close()

        if user is None or not ok:
            self._set_status("Invalid credentials.")
            return

        self.app.current_user = user
        self._set_status("")
        self.app.show_frame("dashboard")

    def _set_status(self, message: str) -> None:
        self.status_label.configure(text=message)


