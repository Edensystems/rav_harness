"""Dialog for adding credits via crypto or WhatsApp."""

from __future__ import annotations

import threading
import webbrowser
import tkinter as tk
from tkinter import messagebox

import requests

from client_config import load_server_url
from client_theme import TOKENS, apply_theme, create_card, create_flat_button

SERVER_URL = load_server_url()


class AddCreditsDialog(tk.Toplevel):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.title("Add credits")
        self.geometry("720x420")
        self.transient(master)
        self.configure(bg=TOKENS["background"])
        apply_theme(self)
        self.grab_set()

        shell = tk.Frame(self, bg=TOKENS["background"], padx=14, pady=12)
        shell.pack(fill="both", expand=True)
        shell.columnconfigure(0, weight=1)
        shell.columnconfigure(1, weight=1)
        shell.rowconfigure(2, weight=1)

        tk.Label(
            shell,
            text="Add credits",
            bg=TOKENS["background"],
            fg=TOKENS["text_primary"],
            font=("Segoe UI", 14, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w")
        tk.Label(
            shell,
            text="Pay with crypto or message WhatsApp. Credits are added after the payment is confirmed.",
            bg=TOKENS["background"],
            fg=TOKENS["text_muted"],
            font=TOKENS["font_ui_sm"],
            wraplength=680,
            justify="left",
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 12))

        self.crypto_status = tk.StringVar(value="Loading payment details…")
        self.whatsapp_status = tk.StringVar(value="Loading payment details…")
        self.coin_var = tk.StringVar(value="—")
        self.network_var = tk.StringVar(value="—")
        self.address_var = tk.StringVar(value="")
        self.whatsapp_number_var = tk.StringVar(value="—")
        self._whatsapp_url = ""
        self._address = ""

        self._build_crypto_card(shell)
        self._build_whatsapp_card(shell)
        self._load_options()

    def _is_alive(self) -> bool:
        try:
            return bool(self.winfo_exists())
        except tk.TclError:
            return False

    def _build_crypto_card(self, parent) -> None:
        card = create_card(parent, padx=12, pady=12, highlight=True)
        card.grid(row=2, column=0, sticky="nsew", padx=(0, 8))
        tk.Label(
            card,
            text="1  Cryptocurrency",
            bg=TOKENS["surface_2"],
            fg=TOKENS["text_primary"],
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w")
        tk.Label(
            card,
            textvariable=self.crypto_status,
            bg=TOKENS["surface_2"],
            fg=TOKENS["text_muted"],
            font=TOKENS["font_ui_sm"],
            wraplength=300,
            justify="left",
        ).pack(anchor="w", pady=(4, 12))

        tk.Label(card, text="Coin", bg=TOKENS["surface_2"], fg=TOKENS["text_muted"], font=TOKENS["font_ui_sm"]).pack(anchor="w")
        tk.Label(
            card,
            textvariable=self.coin_var,
            bg=TOKENS["surface_2"],
            fg=TOKENS["text_primary"],
            font=("Segoe UI", 16, "bold"),
        ).pack(anchor="w")
        tk.Label(
            card,
            textvariable=self.network_var,
            bg=TOKENS["surface_2"],
            fg=TOKENS["text_secondary"],
            font=TOKENS["font_ui_sm"],
        ).pack(anchor="w", pady=(0, 10))

        tk.Label(card, text="Address", bg=TOKENS["surface_2"], fg=TOKENS["text_muted"], font=TOKENS["font_ui_sm"]).pack(anchor="w")
        address_box = tk.Entry(
            card,
            textvariable=self.address_var,
            readonlybackground=TOKENS["surface_elevated"],
            fg=TOKENS["text_primary"],
            relief="flat",
            font=TOKENS["font_mono"],
            state="readonly",
        )
        address_box.pack(fill="x", ipady=8, pady=(4, 10))
        self.copy_button = create_flat_button(card, "Copy address", self._copy_address, variant="primary")
        self.copy_button.pack(anchor="w")
        self.copy_button.configure(state=tk.DISABLED)

    def _build_whatsapp_card(self, parent) -> None:
        card = create_card(parent, padx=12, pady=12)
        card.grid(row=2, column=1, sticky="nsew", padx=(8, 0))
        tk.Label(
            card,
            text="2  WhatsApp",
            bg=TOKENS["surface_2"],
            fg=TOKENS["text_primary"],
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w")
        tk.Label(
            card,
            textvariable=self.whatsapp_status,
            bg=TOKENS["surface_2"],
            fg=TOKENS["text_muted"],
            font=TOKENS["font_ui_sm"],
            wraplength=300,
            justify="left",
        ).pack(anchor="w", pady=(4, 12))

        tk.Label(card, text="Contact number", bg=TOKENS["surface_2"], fg=TOKENS["text_muted"], font=TOKENS["font_ui_sm"]).pack(anchor="w")
        tk.Label(
            card,
            textvariable=self.whatsapp_number_var,
            bg=TOKENS["surface_2"],
            fg=TOKENS["text_primary"],
            font=("Segoe UI", 16, "bold"),
        ).pack(anchor="w", pady=(0, 12))
        self.whatsapp_button = create_flat_button(card, "Open WhatsApp message", self._open_whatsapp, variant="primary")
        self.whatsapp_button.pack(anchor="w")
        self.whatsapp_button.configure(state=tk.DISABLED)

    def _load_options(self) -> None:
        def request():
            try:
                resp = requests.get(
                    f"{SERVER_URL}/api/billing/payments",
                    headers=self.app.auth_headers(),
                    timeout=20,
                )
                if resp.status_code != 200:
                    raise RuntimeError(resp.json().get("detail", resp.text) if resp.text else "Could not load payment options.")
                data = resp.json()
                if self._is_alive():
                    self.after(0, lambda payload=data: self._apply(payload))
            except Exception as exc:
                if self._is_alive():
                    self.after(0, lambda msg=str(exc): messagebox.showerror("Add credits", msg, parent=self))

        threading.Thread(target=request, daemon=True).start()

    def _apply(self, payload: dict) -> None:
        crypto = payload.get("crypto") or {}
        whatsapp = payload.get("whatsapp") or {}
        self._address = str(crypto.get("address") or "")
        self._whatsapp_url = str(whatsapp.get("url") or "")

        coin = crypto.get("coin") or "Crypto"
        network = crypto.get("network") or ""
        self.coin_var.set(coin)
        self.network_var.set(f"Network: {network}" if network else "Network not specified")
        self.address_var.set(self._address or "Not configured")
        if crypto.get("configured"):
            self.crypto_status.set(f"Send {coin} to this address, then wait for confirmation.")
            self.copy_button.configure(state=tk.NORMAL)
        else:
            self.crypto_status.set("Crypto payments are not configured on the server yet.")
            self.copy_button.configure(state=tk.DISABLED)

        number = whatsapp.get("number") or ""
        self.whatsapp_number_var.set(f"+{number}" if number else "Not configured")
        if whatsapp.get("configured"):
            self.whatsapp_status.set("Open WhatsApp with a pre-filled message that includes your account email.")
            self.whatsapp_button.configure(state=tk.NORMAL)
        else:
            self.whatsapp_status.set("WhatsApp contact is not configured on the server yet.")
            self.whatsapp_button.configure(state=tk.DISABLED)

    def _copy_address(self) -> None:
        if not self._address:
            return
        self.clipboard_clear()
        self.clipboard_append(self._address)
        self.crypto_status.set("Address copied. Send the payment, then wait for credits to be added.")

    def _open_whatsapp(self) -> None:
        if not self._whatsapp_url:
            return
        webbrowser.open(self._whatsapp_url)
