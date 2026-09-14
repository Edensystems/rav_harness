import re
import tkinter as tk
from tkinter import ttk

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AuthScreen(ttk.Frame):
    """Login and registration screen with tab switching."""

    COLORS = {
        "bg": "#0f172a",
        "card": "#1e293b",
        "accent": "#3b82f6",
        "accent_hover": "#2563eb",
        "text": "#f8fafc",
        "muted": "#94a3b8",
        "error": "#f87171",
        "success": "#4ade80",
        "input_bg": "#334155",
        "tab_inactive": "#475569",
    }

    def __init__(self, master, on_auth_success, on_auth_request):
        super().__init__(master, style="Auth.TFrame")
        self.on_auth_success = on_auth_success
        self.on_auth_request = on_auth_request
        self.mode = tk.StringVar(value="login")
        self.show_password = tk.BooleanVar(value=False)
        self._busy = False

        self._build_styles()
        self._build_layout()

    def _build_styles(self):
        style = ttk.Style()
        style.configure("Auth.TFrame", background=self.COLORS["bg"])
        style.configure("AuthCard.TFrame", background=self.COLORS["card"])
        style.configure(
            "AuthTitle.TLabel",
            background=self.COLORS["card"],
            foreground=self.COLORS["text"],
            font=("Segoe UI", 20, "bold"),
        )
        style.configure(
            "AuthSubtitle.TLabel",
            background=self.COLORS["card"],
            foreground=self.COLORS["muted"],
            font=("Segoe UI", 10),
        )
        style.configure(
            "AuthField.TLabel",
            background=self.COLORS["card"],
            foreground=self.COLORS["muted"],
            font=("Segoe UI", 9, "bold"),
        )
        style.configure(
            "AuthStatus.TLabel",
            background=self.COLORS["card"],
            foreground=self.COLORS["error"],
            font=("Segoe UI", 9),
            wraplength=360,
        )

    def _build_layout(self):
        outer = tk.Frame(self, bg=self.COLORS["bg"])
        outer.pack(fill="both", expand=True)

        card = tk.Frame(outer, bg=self.COLORS["card"], padx=36, pady=32)
        card.place(relx=0.5, rely=0.5, anchor="center")

        ttk.Label(card, text="Betting Automation", style="AuthTitle.TLabel").pack(anchor="w")
        ttk.Label(
            card,
            text="Secure client access with single-device sessions",
            style="AuthSubtitle.TLabel",
        ).pack(anchor="w", pady=(4, 18))

        tabs = tk.Frame(card, bg=self.COLORS["card"])
        tabs.pack(fill="x", pady=(0, 16))
        self.login_tab_btn = tk.Button(
            tabs,
            text="Sign In",
            command=lambda: self._switch_mode("login"),
            relief="flat",
            bd=0,
            padx=16,
            pady=8,
            cursor="hand2",
        )
        self.login_tab_btn.pack(side="left", padx=(0, 8))
        self.register_tab_btn = tk.Button(
            tabs,
            text="Create Account",
            command=lambda: self._switch_mode("register"),
            relief="flat",
            bd=0,
            padx=16,
            pady=8,
            cursor="hand2",
        )
        self.register_tab_btn.pack(side="left")
        self._refresh_tabs()

        self.form_frame = tk.Frame(card, bg=self.COLORS["card"])
        self.form_frame.pack(fill="x")

        self.email_var = tk.StringVar()
        self.password_var = tk.StringVar()
        self.confirm_var = tk.StringVar()
        self.phone_var = tk.StringVar()

        self.submit_btn = tk.Button(
            card,
            text="Sign In",
            command=self._submit,
            bg=self.COLORS["accent"],
            fg="white",
            activebackground=self.COLORS["accent_hover"],
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=20,
            pady=12,
            font=("Segoe UI", 10, "bold"),
            cursor="hand2",
        )

        self._build_form_fields()

        self.status_label = ttk.Label(card, text="", style="AuthStatus.TLabel")
        self.status_label.pack(anchor="w", pady=(8, 0))

        self.submit_btn.pack(fill="x", pady=(18, 0))

        hint = ttk.Label(
            card,
            text="Password: 8+ chars with letters and numbers",
            style="AuthSubtitle.TLabel",
        )
        hint.pack(anchor="w", pady=(12, 0))

    def _entry(self, parent, textvariable, show=None):
        entry = tk.Entry(
            parent,
            textvariable=textvariable,
            show=show,
            bg=self.COLORS["input_bg"],
            fg=self.COLORS["text"],
            insertbackground=self.COLORS["text"],
            relief="flat",
            font=("Segoe UI", 10),
        )
        entry.pack(fill="x", ipady=8, pady=(4, 10))
        return entry

    def _build_form_fields(self):
        for widget in self.form_frame.winfo_children():
            widget.destroy()

        ttk.Label(self.form_frame, text="EMAIL", style="AuthField.TLabel").pack(anchor="w")
        self.email_entry = self._entry(self.form_frame, self.email_var)

        pwd_row = tk.Frame(self.form_frame, bg=self.COLORS["card"])
        pwd_row.pack(fill="x")
        ttk.Label(pwd_row, text="PASSWORD", style="AuthField.TLabel").pack(side="left")
        tk.Button(
            pwd_row,
            text="Show" if not self.show_password.get() else "Hide",
            command=self._toggle_password,
            bg=self.COLORS["card"],
            fg=self.COLORS["accent"],
            relief="flat",
            bd=0,
            cursor="hand2",
            font=("Segoe UI", 8, "bold"),
        ).pack(side="right")

        show = "" if self.show_password.get() else "*"
        self.password_entry = self._entry(self.form_frame, self.password_var, show=show)

        if self.mode.get() == "register":
            ttk.Label(self.form_frame, text="CONFIRM PASSWORD", style="AuthField.TLabel").pack(anchor="w")
            self.confirm_entry = self._entry(self.form_frame, self.confirm_var, show=show)
            ttk.Label(self.form_frame, text="PHONE (OPTIONAL)", style="AuthField.TLabel").pack(anchor="w")
            self.phone_entry = self._entry(self.form_frame, self.phone_var)
        else:
            self.confirm_entry = None
            self.phone_entry = None

        self._update_submit_label()

    def _update_submit_label(self):
        if hasattr(self, "submit_btn"):
            label = "Create Account" if self.mode.get() == "register" else "Sign In"
            self.submit_btn.config(text=label)

    def _toggle_password(self):
        self.show_password.set(not self.show_password.get())
        self._build_form_fields()

    def _refresh_tabs(self):
        active = self.COLORS["accent"]
        inactive = self.COLORS["tab_inactive"]
        if self.mode.get() == "login":
            self.login_tab_btn.config(bg=active, fg="white")
            self.register_tab_btn.config(bg=inactive, fg=self.COLORS["text"])
        else:
            self.register_tab_btn.config(bg=active, fg="white")
            self.login_tab_btn.config(bg=inactive, fg=self.COLORS["text"])

    def _switch_mode(self, mode):
        self.mode.set(mode)
        self.set_status("")
        self._refresh_tabs()
        self._build_form_fields()

    def set_status(self, message, success=False):
        self.status_label.config(
            text=message,
            foreground=self.COLORS["success"] if success else self.COLORS["error"],
        )

    def set_busy(self, busy: bool):
        self._busy = busy
        state = tk.DISABLED if busy else tk.NORMAL
        if busy:
            self.submit_btn.config(state=state, text="Please wait...")
        else:
            self._update_submit_label()
            self.submit_btn.config(state=state)

    def _validate(self) -> dict | None:
        email = self.email_var.get().strip().lower()
        password = self.password_var.get()

        if not EMAIL_PATTERN.match(email):
            self.set_status("Enter a valid email address.")
            return None
        if not password:
            self.set_status("Password is required.")
            return None

        if self.mode.get() == "register":
            if password != self.confirm_var.get():
                self.set_status("Passwords do not match.")
                return None
            if not re.match(r"^(?=.*[A-Za-z])(?=.*\d).{8,}$", password):
                self.set_status("Password must be 8+ chars with letters and numbers.")
                return None
            return {
                "mode": "register",
                "email": email,
                "password": password,
                "phone_number": self.phone_var.get().strip() or None,
            }

        return {"mode": "login", "email": email, "password": password}

    def _submit(self):
        if self._busy:
            return
        payload = self._validate()
        if not payload:
            return
        self.set_busy(True)
        self.on_auth_request(payload, self._auth_finished)

    def _auth_finished(self, success: bool, message: str = "", data=None):
        self.set_busy(False)
        if success and data:
            self.set_status("Welcome back!" if self.mode.get() == "login" else "Account created successfully!", success=True)
            self.on_auth_success(data)
        else:
            self.set_status("Authentication failed.")
            self._update_submit_label()
