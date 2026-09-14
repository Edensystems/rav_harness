"""Admin tools for credit grants and billable action rates."""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox

import requests

from client_config import load_server_url
from client_theme import TOKENS, apply_theme, create_card, create_flat_button, themed_entry

SERVER_URL = load_server_url()


def _format_credits(value) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "0"
    if number.is_integer():
        return str(int(number))
    return f"{number:.4f}".rstrip("0").rstrip(".")


class AdminBillingDialog(tk.Toplevel):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.users = []
        self.rates = []
        self.title("Billing & Credits")
        self.geometry("860x560")
        self.transient(master)
        self.configure(bg=TOKENS["background"])
        apply_theme(self)

        shell = tk.Frame(self, bg=TOKENS["background"], padx=14, pady=12)
        shell.pack(fill="both", expand=True)
        shell.columnconfigure(0, weight=1)
        shell.columnconfigure(1, weight=1)
        shell.rowconfigure(0, weight=1)

        self._build_users_card(shell)
        self._build_rates_card(shell)
        self.refresh()

    def _is_alive(self) -> bool:
        try:
            return bool(self.winfo_exists())
        except tk.TclError:
            return False

    def _build_users_card(self, parent) -> None:
        card = create_card(parent, padx=12, pady=12)
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        tk.Label(
            card,
            text="User credits",
            bg=TOKENS["surface_2"],
            fg=TOKENS["text_primary"],
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w")
        tk.Label(
            card,
            text="Select a user, then set or add credits.",
            bg=TOKENS["surface_2"],
            fg=TOKENS["text_muted"],
            font=TOKENS["font_ui_sm"],
        ).pack(anchor="w", pady=(2, 8))

        self.user_list = tk.Listbox(
            card,
            height=16,
            exportselection=False,
            bg=TOKENS["surface_elevated"],
            fg=TOKENS["text_primary"],
            selectbackground=TOKENS["accent_soft"],
            highlightthickness=0,
            bd=0,
            font=TOKENS["font_ui_sm"],
        )
        self.user_list.pack(fill="both", expand=True)
        self.user_list.bind("<<ListboxSelect>>", self._on_user_select)

        form = tk.Frame(card, bg=TOKENS["surface_2"])
        form.pack(fill="x", pady=(10, 0))
        tk.Label(form, text="Credits", bg=TOKENS["surface_2"], fg=TOKENS["text_secondary"]).pack(side="left")
        self.credit_entry = themed_entry(form, width=12)
        self.credit_entry.pack(side="left", padx=8)
        create_flat_button(form, "Set balance", self._set_credits, variant="primary").pack(side="left")
        create_flat_button(form, "Add amount", self._add_credits).pack(side="left", padx=6)

    def _build_rates_card(self, parent) -> None:
        card = create_card(parent, padx=12, pady=12, highlight=True)
        card.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        tk.Label(
            card,
            text="Billable actions",
            bg=TOKENS["surface_2"],
            fg=TOKENS["text_primary"],
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w")
        tk.Label(
            card,
            text="Set 0 to make an action free. Charge is taken only after a successful action.",
            bg=TOKENS["surface_2"],
            fg=TOKENS["text_muted"],
            font=TOKENS["font_ui_sm"],
            wraplength=360,
            justify="left",
        ).pack(anchor="w", pady=(2, 8))

        self.rate_list = tk.Listbox(
            card,
            height=16,
            exportselection=False,
            bg=TOKENS["surface_elevated"],
            fg=TOKENS["text_primary"],
            selectbackground=TOKENS["accent_soft"],
            highlightthickness=0,
            bd=0,
            font=TOKENS["font_ui_sm"],
        )
        self.rate_list.pack(fill="both", expand=True)
        self.rate_list.bind("<<ListboxSelect>>", self._on_rate_select)

        form = tk.Frame(card, bg=TOKENS["surface_2"])
        form.pack(fill="x", pady=(10, 0))
        tk.Label(form, text="Rate per success", bg=TOKENS["surface_2"], fg=TOKENS["text_secondary"]).pack(side="left")
        self.rate_entry = themed_entry(form, width=10)
        self.rate_entry.pack(side="left", padx=8)
        create_flat_button(form, "Save rate", self._save_rate, variant="primary").pack(side="left")
        create_flat_button(form, "Refresh", self.refresh).pack(side="left", padx=6)

    def refresh(self) -> None:
        def request():
            try:
                users_resp = requests.get(f"{SERVER_URL}/admin/users", headers=self.app.auth_headers(), timeout=20)
                rates_resp = requests.get(f"{SERVER_URL}/admin/billing", headers=self.app.auth_headers(), timeout=20)
                if users_resp.status_code != 200:
                    raise RuntimeError(users_resp.json().get("detail", users_resp.text))
                if rates_resp.status_code != 200:
                    raise RuntimeError(rates_resp.json().get("detail", rates_resp.text))
                users = users_resp.json()
                rates = rates_resp.json()
                if self._is_alive():
                    self.after(0, lambda: self._populate(users, rates))
            except Exception as exc:
                if self._is_alive():
                    self.after(0, lambda msg=str(exc): messagebox.showerror("Admin", msg, parent=self))

        threading.Thread(target=request, daemon=True).start()

    def _populate(self, users, rates) -> None:
        if not self._is_alive():
            return
        self.users = users
        self.rates = rates
        self.user_list.delete(0, tk.END)
        for user in users:
            self.user_list.insert(
                tk.END,
                f"{user['email']}  ·  {_format_credits(user['credits'])} cr  ·  {user['role']}",
            )
        self.rate_list.delete(0, tk.END)
        for item in rates:
            badge = f"{_format_credits(item['rate'])} cr" if item["billable"] else "free"
            self.rate_list.insert(tk.END, f"{item['label']}  ·  {badge}")

    def _selected_user(self):
        idxs = self.user_list.curselection()
        if not idxs:
            messagebox.showinfo("Admin", "Select a user first.", parent=self)
            return None
        return self.users[idxs[0]]

    def _selected_rate(self):
        idxs = self.rate_list.curselection()
        if not idxs:
            messagebox.showinfo("Admin", "Select an action first.", parent=self)
            return None
        return self.rates[idxs[0]]

    def _on_user_select(self, _event=None) -> None:
        idxs = self.user_list.curselection()
        if not idxs:
            return
        self.credit_entry.delete(0, tk.END)
        self.credit_entry.insert(0, _format_credits(self.users[idxs[0]]["credits"]))

    def _on_rate_select(self, _event=None) -> None:
        idxs = self.rate_list.curselection()
        if not idxs:
            return
        self.rate_entry.delete(0, tk.END)
        self.rate_entry.insert(0, _format_credits(self.rates[idxs[0]]["rate"]))

    def _set_credits(self) -> None:
        self._submit_credits(mode="set")

    def _add_credits(self) -> None:
        self._submit_credits(mode="add")

    def _submit_credits(self, mode: str) -> None:
        user = self._selected_user()
        if not user:
            return
        try:
            amount = float(self.credit_entry.get().strip())
        except ValueError:
            messagebox.showerror("Admin", "Enter a valid credit amount.", parent=self)
            return

        payload = {"credits": amount} if mode == "set" else {"delta": amount}

        def request():
            try:
                resp = requests.patch(
                    f"{SERVER_URL}/admin/users/{user['id']}/credits",
                    headers=self.app.auth_headers(),
                    json=payload,
                    timeout=20,
                )
                if resp.status_code != 200:
                    raise RuntimeError(resp.json().get("detail", resp.text))
                if self._is_alive():
                    self.after(0, self.refresh)
                    self.after(0, self.app.refresh_billing)
            except Exception as exc:
                if self._is_alive():
                    self.after(0, lambda msg=str(exc): messagebox.showerror("Admin", msg, parent=self))

        threading.Thread(target=request, daemon=True).start()

    def _save_rate(self) -> None:
        item = self._selected_rate()
        if not item:
            return
        try:
            rate = float(self.rate_entry.get().strip())
        except ValueError:
            messagebox.showerror("Admin", "Enter a valid rate. Use 0 to make the action free.", parent=self)
            return

        def request():
            try:
                resp = requests.put(
                    f"{SERVER_URL}/admin/billing",
                    headers=self.app.auth_headers(),
                    json={"task_type": item["task_type"], "rate": rate},
                    timeout=20,
                )
                if resp.status_code != 200:
                    raise RuntimeError(resp.json().get("detail", resp.text))
                if self._is_alive():
                    self.after(0, self.refresh)
                    self.after(0, self.app.refresh_billing)
            except Exception as exc:
                if self._is_alive():
                    self.after(0, lambda msg=str(exc): messagebox.showerror("Admin", msg, parent=self))

        threading.Thread(target=request, daemon=True).start()
