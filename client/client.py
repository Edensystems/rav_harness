import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, simpledialog, ttk
import os
import requests
import threading
import json
import tempfile

from client_admin_ui import AdminBillingDialog
from client_auth_ui import AuthScreen
from client_device import get_device_id, get_device_name
from client_dashboard import DashboardBuilder
from client_config import load_automation_identity, load_server_url
from client_payments_ui import AddCreditsDialog

SERVER_URL = load_server_url()


def _schedule_error(widget, message: str, title: str = "Error", parent=None):
    msg = str(message)

    def show():
        if parent is not None and not parent.winfo_exists():
            return
        if parent is None and not widget.winfo_exists():
            return
        messagebox.showerror(title, msg, parent=parent)

    widget.after(0, show)


def _schedule_log(app, message: str):
    msg = str(message)
    app.root.after(0, lambda m=msg: app.log(m))


class ClientApp:
    def __init__(self, root):
        self.root = root
        self.root.geometry("820x980")
        self.root.configure(bg="#0f172a")

        self.token = None
        self.user = None
        self.current_job_id = None
        self.is_running = False
        self.dashboard = None
        self.billing_rates = {}
        self.device_id = get_device_id()
        self.device_name = get_device_name()
        self.identity = load_automation_identity()

        self.root.title(f"{self.identity.name} Client")

        self.build_login_ui()

    def auth_headers(self):
        return {
            "Authorization": f"Bearer {self.token}",
            "X-Device-Id": self.device_id,
            "X-Device-Name": self.device_name,
        }

    def build_login_ui(self):
        for widget in self.root.winfo_children():
            widget.destroy()
        self.auth_screen = AuthScreen(
            self.root,
            on_auth_success=self._on_login_success,
            on_auth_request=self._handle_auth_request,
        )
        self.auth_screen.pack(fill="both", expand=True)

    def _handle_auth_request(self, payload, callback):
        def request():
            try:
                headers = {
                    "X-Device-Id": self.device_id,
                    "X-Device-Name": self.device_name,
                }
                if payload["mode"] == "register":
                    body = {
                        "email": payload["email"],
                        "password": payload["password"],
                        "phone_number": payload.get("phone_number"),
                    }
                    resp = requests.post(f"{SERVER_URL}/auth/register", json=body, headers=headers, timeout=25)
                else:
                    body = {
                        "email": payload["email"],
                        "password": payload["password"],
                        "device_id": self.device_id,
                        "device_name": self.device_name,
                    }
                    resp = requests.post(f"{SERVER_URL}/auth/login", json=body, headers=headers, timeout=25)

                if resp.status_code in (200, 201):
                    self.root.after(0, callback, True, "", resp.json())
                else:
                    detail = resp.json().get("detail", resp.text) if resp.text else "Authentication failed"
                    self.root.after(0, callback, False, detail)
            except requests.exceptions.Timeout:
                self.root.after(0, callback, False, "Request timed out. Check server connection.")
            except requests.exceptions.RequestException as exc:
                self.root.after(0, callback, False, f"Could not connect to server:\n{exc}")
            except json.JSONDecodeError:
                self.root.after(0, callback, False, "Invalid response from server.")

        threading.Thread(target=request, daemon=True).start()

    def _on_login_success(self, data):
        self.token = data["access_token"]
        self.user = data["user"]
        self.root.after(300, self._show_main_after_auth)

    def _show_main_after_auth(self):
        for widget in self.root.winfo_children():
            widget.destroy()
        self.active_list_id = None
        self.active_list_name = None
        self.dashboard = None
        self.build_main_ui()

    def build_main_ui(self):
        DashboardBuilder(self).build()

    def logout(self):
        def request():
            try:
                requests.post(f"{SERVER_URL}/auth/logout", headers=self.auth_headers(), timeout=15)
            except requests.exceptions.RequestException:
                pass
            self.token = None
            self.user = None
            self.root.after(0, self.build_login_ui)

        threading.Thread(target=request, daemon=True).start()

    def open_lists_dialog(self):
        ListsDialog(self.root, self)

    def open_outputs_dashboard(self):
        OutputsDialog(self.root, self)

    def refresh_saved_outputs(self):
        def request():
            try:
                resp = requests.get(f"{SERVER_URL}/api/outputs", headers=self.auth_headers(), timeout=20)
                if resp.status_code == 200:
                    self.root.after(0, self._populate_saved_outputs, resp.json())
                else:
                    detail = resp.json().get("detail", resp.text)
                    _schedule_log(self, f"Could not load output files: {detail}")
            except Exception as exc:
                _schedule_log(self, f"Could not load output files: {exc}")

        threading.Thread(target=request, daemon=True).start()

    def _format_output_label(self, item):
        created = item.get("created_at", "")[:16].replace("T", " ")
        size_kb = max(item.get("file_size", 0), 0) / 1024
        return (
            f"{item['task_type']} | {item['status']} | "
            f"{item['processed']}/{item['total']} | {size_kb:.1f} KB | {created}"
        )

    def _populate_saved_outputs(self, outputs):
        if not hasattr(self, "outputs_listbox"):
            return
        try:
            self.saved_outputs = outputs
            self.outputs_listbox.delete(0, tk.END)
            for item in outputs:
                self.outputs_listbox.insert(tk.END, self._format_output_label(item))

            self.outputs_preview.config(state=tk.NORMAL)
            self.outputs_preview.delete("1.0", tk.END)
            if outputs:
                self.outputs_preview.insert(tk.END, f"{len(outputs)} saved output file(s). Select one to preview.")
            else:
                self.outputs_preview.insert(tk.END, "No saved outputs yet. Run a task to generate output files.")
            self.outputs_preview.config(state=tk.DISABLED)
        except tk.TclError:
            return

    def _get_selected_output(self, silent=False):
        idxs = self.outputs_listbox.curselection()
        if not idxs:
            if not silent:
                messagebox.showinfo("Output Files", "Select an output file first.")
            return None
        return self.saved_outputs[idxs[0]]

    def _show_selected_output(self, _event=None):
        selected = self._get_selected_output(silent=True)
        if not selected:
            return

        def request():
            try:
                resp = requests.get(
                    f"{SERVER_URL}/api/outputs/{selected['id']}",
                    headers=self.auth_headers(),
                    timeout=30,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    self.root.after(0, self._render_output_preview, data)
                else:
                    detail = resp.json().get("detail", resp.text)
                    self.root.after(0, lambda: messagebox.showerror("Error", detail))
            except Exception as exc:
                self.root.after(0, lambda e=exc: messagebox.showerror("Error", str(e)))

        threading.Thread(target=request, daemon=True).start()

    def _render_output_preview(self, data):
        header = (
            f"File: {data['filename']}\n"
            f"Task: {data['task_type']} | Status: {data['status']} | "
            f"Progress: {data['processed']}/{data['total']} | Size: {data['file_size']} bytes\n"
            f"{'-' * 60}\n"
        )
        self.outputs_preview.config(state=tk.NORMAL)
        self.outputs_preview.delete("1.0", tk.END)
        self.outputs_preview.insert(tk.END, header + data.get("content", ""))
        self.outputs_preview.config(state=tk.DISABLED)

    def open_selected_output(self):
        selected = self._get_selected_output()
        if not selected:
            return

        def request():
            try:
                resp = requests.get(
                    f"{SERVER_URL}/api/outputs/{selected['id']}",
                    headers=self.auth_headers(),
                    timeout=30,
                )
                if resp.status_code != 200:
                    detail = resp.json().get("detail", resp.text)
                    self.root.after(0, lambda: messagebox.showerror("Error", detail))
                    return
                data = resp.json()
                temp_dir = os.path.join(tempfile.gettempdir(), "odibets_outputs")
                os.makedirs(temp_dir, exist_ok=True)
                temp_path = os.path.join(temp_dir, data["filename"])
                with open(temp_path, "w", encoding="utf-8") as handle:
                    handle.write(data.get("content", ""))

                def open_file():
                    try:
                        os.startfile(temp_path)
                    except OSError as exc:
                        messagebox.showerror("Error", f"Could not open file:\n{exc}")

                self.root.after(0, open_file)
            except Exception as exc:
                self.root.after(0, lambda e=exc: messagebox.showerror("Error", str(e)))

        threading.Thread(target=request, daemon=True).start()

    def save_selected_output_as(self):
        selected = self._get_selected_output()
        if not selected:
            return

        def request():
            try:
                resp = requests.get(
                    f"{SERVER_URL}/api/outputs/{selected['id']}",
                    headers=self.auth_headers(),
                    timeout=30,
                )
                if resp.status_code != 200:
                    detail = resp.json().get("detail", resp.text)
                    self.root.after(0, lambda: messagebox.showerror("Error", detail))
                    return

                data = resp.json()

                def save_dialog():
                    path = filedialog.asksaveasfilename(
                        parent=self.root,
                        defaultextension=".txt",
                        initialfile=data["filename"],
                        filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
                        title="Save Output File As",
                    )
                    if not path:
                        return
                    with open(path, "w", encoding="utf-8") as handle:
                        handle.write(data.get("content", ""))
                    self.log(f"Output saved to {path}")

                self.root.after(0, save_dialog)
            except Exception as exc:
                self.root.after(0, lambda e=exc: messagebox.showerror("Error", str(e)))

        threading.Thread(target=request, daemon=True).start()

    def load_from_saved_list(self):
        def request():
            try:
                resp = requests.get(f"{SERVER_URL}/api/lists", headers=self.auth_headers(), timeout=20)
                if resp.status_code != 200:
                    self.root.after(
                        0,
                        lambda: messagebox.showerror("Error", resp.json().get("detail", resp.text)),
                    )
                    return
                lists = resp.json()
                if not lists:
                    self.root.after(0, lambda: messagebox.showinfo("Lists", "You have no saved lists yet."))
                    return
                self.root.after(0, self._choose_list_for_input, lists)
            except Exception as exc:
                self.root.after(0, lambda e=exc: messagebox.showerror("Error", str(e)))

        threading.Thread(target=request, daemon=True).start()

    def _choose_list_for_input(self, lists):
        names = [f"{lst['name']} ({len(lst['items'])} items)" for lst in lists]
        choice = simpledialog.askstring(
            "Load Saved List",
            "Enter list name to load:\n" + "\n".join(names),
            parent=self.root,
        )
        if not choice:
            return
        selected = next((lst for lst in lists if lst["name"].lower() == choice.strip().lower()), None)
        if not selected:
            messagebox.showerror("Error", "List not found. Use exact list name.")
            return
        temp_path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            initialfile=f"{selected['name']}.txt",
            title="Save temporary list file",
        )
        if not temp_path:
            return
        with open(temp_path, "w", encoding="utf-8") as handle:
            for item in selected["items"]:
                handle.write(item["value"] + "\n")
        self.file_path_entry.delete(0, tk.END)
        self.file_path_entry.insert(0, temp_path)
        self.active_list_id = selected["id"]
        self.active_list_name = selected["name"]
        self.log(f"Loaded list '{selected['name']}' into {temp_path}")
        self._refresh_input_file_stats(notify=True)

    def _dedupe_and_update_file(self, filepath):
        """Remove duplicate lines from file (first occurrence kept), rewrite file, return stats."""
        try:
            with open(filepath, "r", encoding="utf-8") as handle:
                raw_lines = [line.strip() for line in handle if line.strip()]
        except OSError:
            return None

        seen = set()
        unique_lines = []
        for line in raw_lines:
            if line not in seen:
                seen.add(line)
                unique_lines.append(line)

        removed_count = len(raw_lines) - len(unique_lines)
        if removed_count > 0:
            with open(filepath, "w", encoding="utf-8") as handle:
                handle.write("\n".join(unique_lines))
                if unique_lines:
                    handle.write("\n")

        return {
            "target_numbers": unique_lines,
            "original_count": len(raw_lines),
            "unique_count": len(unique_lines),
            "removed_count": removed_count,
        }

    def _update_list_count_label(self, unique_count, removed_count=0, original_count=None):
        if unique_count == 0:
            self.list_count_var.set("Entries: 0 (file is empty)")
        elif removed_count > 0:
            self.list_count_var.set(
                f"Entries: {unique_count} ready "
                f"({removed_count} duplicate(s) removed from {original_count})"
            )
        else:
            self.list_count_var.set(f"Entries: {unique_count} ready (no duplicates)")

    def _refresh_input_file_stats(self, notify=False):
        filepath = self.file_path_entry.get().strip()
        if not filepath:
            self.list_count_var.set("Entries: —")
            return None

        result = self._dedupe_and_update_file(filepath)
        if result is None:
            self.list_count_var.set("Entries: could not read file")
            messagebox.showerror("Error", "Could not read input file.")
            return None

        self._update_list_count_label(
            result["unique_count"],
            result["removed_count"],
            result["original_count"],
        )

        if result["removed_count"] > 0:
            self.log(
                f"Removed {result['removed_count']} duplicate(s). "
                f"File updated: {result['unique_count']} unique entries remain."
            )
            if notify:
                messagebox.showinfo(
                    "Duplicates Removed",
                    f"Found {result['original_count']} entries with "
                    f"{result['removed_count']} duplicate(s).\n\n"
                    f"The input file was updated.\n"
                    f"Unique entries ready: {result['unique_count']}",
                )

        if result["unique_count"] > 0 and self.token:
            self._sync_clean_list_to_server(result["target_numbers"], filepath)

        return result

    def _default_list_name_from_path(self, filepath):
        stem = os.path.splitext(os.path.basename(filepath))[0].strip()
        return stem or "Imported List"

    def _sync_clean_list_to_server(self, items, filepath):
        list_name = self.active_list_name or self._default_list_name_from_path(filepath)

        def worker():
            try:
                headers = self.auth_headers()
                list_id = self.active_list_id

                if not list_id:
                    resp = requests.get(f"{SERVER_URL}/api/lists", headers=headers, timeout=20)
                    if resp.status_code != 200:
                        detail = resp.json().get("detail", resp.text)
                        _schedule_log(self, f"Could not sync list to account: {detail}")
                        return
                    existing = next(
                        (lst for lst in resp.json() if lst["name"].lower() == list_name.lower()),
                        None,
                    )
                    if existing:
                        list_id = existing["id"]

                if list_id:
                    resp = requests.put(
                        f"{SERVER_URL}/api/lists/{list_id}",
                        headers=headers,
                        json={"name": list_name, "items": items},
                        timeout=20,
                    )
                    action = "updated"
                else:
                    resp = requests.post(
                        f"{SERVER_URL}/api/lists",
                        headers=headers,
                        json={"name": list_name, "items": items},
                        timeout=20,
                    )
                    action = "created"

                if resp.status_code in (200, 201):
                    data = resp.json()
                    saved_id = data["id"]
                    saved_name = data["name"]
                    count = len(data.get("items", items))

                    def on_success():
                        self.active_list_id = saved_id
                        self.active_list_name = saved_name
                        self.log(f"Saved list '{saved_name}' {action} on server ({count} entries).")
                        current = self.list_count_var.get()
                        if "synced" not in current.lower():
                            self.list_count_var.set(f"{current} · synced to My Lists")

                    self.root.after(0, on_success)
                else:
                    detail = resp.json().get("detail", resp.text)
                    _schedule_log(self, f"Could not sync list to account: {detail}")
            except Exception as exc:
                _schedule_log(self, f"List sync error: {exc}")

        threading.Thread(target=worker, daemon=True).start()

    def browse_file(self):
        filename = filedialog.askopenfilename(
            title="Select an Input File",
            filetypes=(("Text files", "*.txt"), ("All files", "*.*")),
        )
        if filename:
            self.file_path_entry.delete(0, tk.END)
            self.file_path_entry.insert(0, filename)
            self.active_list_id = None
            self.active_list_name = self._default_list_name_from_path(filename)
            self.log(f"Selected file: {filename}")
            self._refresh_input_file_stats(notify=True)

    def log(self, message):
        from datetime import datetime

        if not hasattr(self, "log_area"):
            return
        line = f"{datetime.now().strftime('%H:%M:%S')} - {message}"
        try:
            self.log_area.insert(tk.END, line + "\n")
            self.log_area.see(tk.END)
        except tk.TclError:
            return
        if self.dashboard:
            self.dashboard.append_activity(line)
        self.root.update_idletasks()

    def set_ui_state(self, is_running):
        self.is_running = is_running
        state = tk.DISABLED if is_running else tk.NORMAL

        for btn in self.action_buttons:
            btn.config(state=state)
        for control in getattr(self, "primary_action_buttons", []):
            control.config(state=state)
        for widget in self.input_widgets:
            widget.config(state=state)

        self.stop_button.config(state=tk.NORMAL if is_running else tk.DISABLED)
        if hasattr(self, "primary_stop_button"):
            self.primary_stop_button.config(state=tk.NORMAL if is_running else tk.DISABLED)
        if not is_running and self.dashboard:
            self.dashboard.refresh_action_affordability()

    def open_admin_dialog(self):
        AdminBillingDialog(self.root, self)

    def open_add_credits(self):
        AddCreditsDialog(self.root, self)

    def current_credits(self) -> float:
        try:
            return float((self.user or {}).get("credits") or 0)
        except (TypeError, ValueError):
            return 0.0

    def action_rate(self, task_type: str) -> float:
        item = self.billing_rates.get(task_type) or {}
        try:
            return float(item.get("rate") or 0)
        except (TypeError, ValueError):
            return 0.0

    def is_billable(self, task_type: str) -> bool:
        item = self.billing_rates.get(task_type) or {}
        return bool(item.get("billable")) or self.action_rate(task_type) > 0

    def is_action_enabled(self, task_type: str) -> bool:
        item = self.billing_rates.get(task_type)
        if not item:
            return True
        return bool(item.get("enabled", True))

    def set_credits(self, credits) -> None:
        if self.user is None:
            return
        try:
            value = float(credits)
        except (TypeError, ValueError):
            return
        self.user["credits"] = value
        if self.dashboard:
            self.dashboard.apply_credits(value)

    def refresh_billing(self) -> None:
        def request():
            try:
                resp = requests.get(f"{SERVER_URL}/api/billing", headers=self.auth_headers(), timeout=20)
                if resp.status_code == 200:
                    data = resp.json()
                    self.root.after(0, lambda payload=data: self._apply_billing(payload))
            except requests.exceptions.RequestException:
                pass

        threading.Thread(target=request, daemon=True).start()

    def _apply_billing(self, payload: dict) -> None:
        rates = payload.get("rates") or []
        self.billing_rates = {item["task_type"]: item for item in rates}
        if "credits" in payload:
            self.set_credits(payload["credits"])
        if self.dashboard:
            self.dashboard.apply_billing_rates(self.billing_rates)

    def fetch_users(self):
        self.open_admin_dialog()

    def _validate_inputs(self, task_type):
        filepath = self.file_path_entry.get()
        password = self.password_entry.get()
        share_code = self.share_code_entry.get()
        amount = self.amount_entry.get()
        use_total_balance = self.amount_mode_var.get() == "total"

        if not all([filepath, password]):
            messagebox.showerror("Validation Error", "Please provide an input file and password.")
            return None

        if task_type in ["bet", "app_bonus", "claim_bonus"] and not share_code:
            messagebox.showerror("Validation Error", f"Share/Booking Code is required for '{task_type}'.")
            return None

        if task_type == "withdrawal" and not amount:
            messagebox.showerror("Validation Error", "Amount is required for withdrawal.")
            return None

        if not use_total_balance and task_type in ["bet", "virtual_bet", "app_bonus", "rollover", "claim"] and not amount:
            messagebox.showerror(
                "Validation Error",
                "Bet Amount is required when using 'Manual Input Choice'.",
            )
            return None

        dedupe_result = self._refresh_input_file_stats(notify=False)
        if dedupe_result is None:
            return None

        target_numbers = dedupe_result["target_numbers"]
        if not target_numbers:
            messagebox.showerror("Error", "Input file contains no entries.")
            return None

        if dedupe_result["removed_count"] > 0:
            messagebox.showinfo(
                "Duplicates Removed Before Submit",
                f"Removed {dedupe_result['removed_count']} duplicate(s) from the input file.\n"
                f"Submitting {dedupe_result['unique_count']} unique entries.",
            )
            self.log(
                f"Submitting clean list: {dedupe_result['unique_count']} entries "
                f"({dedupe_result['removed_count']} duplicate(s) removed)."
            )
        else:
            self.log(f"Submitting list: {dedupe_result['unique_count']} entries.")

        output_filename = ""
        if task_type == "save_token":
            output_filename = filedialog.asksaveasfilename(
                defaultextension=".txt",
                filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
                title="Save Tokens As...",
            )
            if not output_filename:
                self.log("Save token operation cancelled.")
                return None

        return {
            "task_type": task_type,
            "target_numbers": target_numbers,
            "target_password": password,
            "share_code": share_code,
            "amount": amount,
            "use_bonus": self.balance_mode_var.get() == "bonus",
            "use_total_balance": use_total_balance,
            "output_filename": output_filename,
            "bet_id": self.bet_id_entry.get().strip() if hasattr(self, "bet_id_entry") else "",
        }

    def start_job(self, task_type):
        if self.is_running:
            self.log("A task is already in progress.")
            return

        if not self.is_action_enabled(task_type):
            messagebox.showerror(
                "Action disabled",
                f"'{task_type}' is currently disabled by the server.",
            )
            return

        if self.is_billable(task_type):
            rate = self.action_rate(task_type)
            credits = self.current_credits()
            if credits < rate:
                messagebox.showerror(
                    "Credits required",
                    f"'{task_type}' is billable at {rate} credit(s) per successful action.\n"
                    f"Your balance is {credits}. Add credits before running this action.",
                )
                return

        payload = self._validate_inputs(task_type)
        if not payload:
            return

        self.set_ui_state(True)
        self.log(f"Starting '{task_type}' task on server...")
        if hasattr(self, "log_area"):
            self.log_area.delete(1.0, tk.END)
        if self.dashboard:
            self.dashboard.on_job_started()

        threading.Thread(target=self._submit_job, args=(payload,), daemon=True).start()

    def _submit_job(self, payload):
        try:
            resp = requests.post(
                f"{SERVER_URL}/api/start_task",
                json=payload,
                headers=self.auth_headers(),
                timeout=30,
            )
            if resp.status_code == 200:
                data = resp.json()
                self.current_job_id = data["job_id"]
                output_name = data.get("output_filename", "N/A")
                workers = data.get("connections")
                self.root.after(
                    0,
                    lambda name=output_name, count=workers: self.log(
                        f"Job started. Output: {name}"
                        + (f". Server connections: {count}" if count else "")
                    ),
                )
                self.root.after(0, self.monitor_job)
            elif resp.status_code in (401, 403):
                auth_detail = resp.json().get("detail", resp.text)
                self.root.after(0, lambda msg=auth_detail: messagebox.showerror("Auth Error", msg))
                self.root.after(0, lambda: self.set_ui_state(False))
            elif resp.status_code == 402:
                detail = resp.json().get("detail", resp.text) if resp.text else "Not enough credits for this action."
                self.root.after(0, lambda msg=detail: messagebox.showerror("Credits required", msg))
                self.root.after(0, lambda: self.set_ui_state(False))
                self.root.after(0, self.refresh_billing)
            elif resp.status_code == 423:
                detail = resp.json().get("detail", resp.text) if resp.text else "This action is currently disabled by the server."
                self.root.after(0, lambda msg=detail: messagebox.showerror("Action disabled", msg))
                self.root.after(0, lambda: self.set_ui_state(False))
                self.root.after(0, self.refresh_billing)
            else:
                detail = resp.json().get("detail", resp.text) if resp.text else "Unknown error"
                self.root.after(0, lambda msg=detail: messagebox.showerror("Error", f"Server error: {msg}"))
                self.root.after(0, lambda: self.set_ui_state(False))
        except requests.exceptions.Timeout:
            self.root.after(0, lambda: messagebox.showerror("Error", "Request timed out while starting task."))
            self.root.after(0, lambda: self.set_ui_state(False))
        except Exception as e:
            self.root.after(0, lambda msg=str(e): messagebox.showerror("Error", msg))
            self.root.after(0, lambda: self.set_ui_state(False))

    def monitor_job(self):
        if not self.current_job_id:
            return

        def fetch_status():
            try:
                resp = requests.get(
                    f"{SERVER_URL}/api/task_status/{self.current_job_id}",
                    headers=self.auth_headers(),
                    timeout=20,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    processed = data.get("processed", 0)
                    total = data.get("total", 0)
                    credits_remaining = data.get("credits_remaining")
                    credits_charged = data.get("credits_charged")
                    self.root.after(
                        0,
                        lambda logs=data["logs"], status=data["status"], p=processed, t=total, cr=credits_remaining, ch=credits_charged: self.update_logs(
                            logs, status, p, t, cr, ch
                        ),
                    )
                    if data["status"] == "running":
                        self.root.after(2000, self.monitor_job)
                elif resp.status_code == 404:
                    self.root.after(0, lambda: self.log("Job not found on server."))
                    self.root.after(0, lambda: self.set_ui_state(False))
                else:
                    self.root.after(0, lambda code=resp.status_code: self.log(f"Polling error: HTTP {code}"))
                    self.root.after(2000, self.monitor_job)
            except Exception as e:
                _schedule_log(self, f"Polling error: {e}")
                self.root.after(2000, self.monitor_job)

        threading.Thread(target=fetch_status, daemon=True).start()

    def update_logs(self, logs, status, processed=0, total=0, credits_remaining=None, credits_charged=None):
        self.log_area.delete(1.0, tk.END)
        for log_line in logs:
            self.log_area.insert(tk.END, log_line + "\n")
        self.log_area.see(tk.END)

        if credits_remaining is not None:
            self.set_credits(credits_remaining)

        if self.dashboard:
            self.dashboard.ingest_logs(logs, status, processed, total)
            if credits_charged is not None:
                self.dashboard.apply_job_billing(credits_charged, credits_remaining)

        if status in ["completed", "stopped"]:
            self.log_area.insert(tk.END, f"\n--- Job {status.upper()} ---\n")
            self.set_ui_state(False)
            self.current_job_id = None
            if self.dashboard:
                self.dashboard.on_job_finished(status)
            self.refresh_saved_outputs()
            self.refresh_billing()

    def stop_job(self):
        if not self.current_job_id:
            return

        job_id = self.current_job_id

        def send_stop():
            try:
                resp = requests.post(
                    f"{SERVER_URL}/api/stop_task/{job_id}",
                    headers=self.auth_headers(),
                    timeout=20,
                )
                if resp.status_code != 200:
                    self.root.after(
                        0,
                        lambda: messagebox.showerror("Error", f"Could not stop job: {resp.text}"),
                    )
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Error", str(e)))

        self.log("Cancellation signal sent. Stopping ongoing tasks...")
        self.stop_button.config(state=tk.DISABLED)
        threading.Thread(target=send_stop, daemon=True).start()


class OutputsDialog(tk.Toplevel):
    def __init__(self, master, app: ClientApp):
        super().__init__(master)
        self.app = app
        self.outputs_data = []
        identity = load_automation_identity()
        self.title(f"{identity.name} — Output Files")
        self.geometry("760x520")
        self.transient(master)
        self.grab_set()

        from client_theme import TOKENS, apply_theme, create_flat_button

        apply_theme(self)

        top = tk.Frame(self, bg=TOKENS["surface_1"], padx=10, pady=10)
        top.pack(fill="x")
        create_flat_button(top, "Refresh output list", self.refresh).pack(side="left")
        create_flat_button(top, "Open selected file", self.open_selected).pack(side="left", padx=6)
        create_flat_button(top, "Save selected file as...", self.save_selected_as).pack(side="left", padx=6)

        body = tk.Frame(self, bg=TOKENS["background"], padx=10, pady=6)
        body.pack(fill="both", expand=True)

        self.listbox = tk.Listbox(
            body,
            width=52,
            height=16,
            exportselection=False,
            bg=TOKENS["surface_elevated"],
            fg=TOKENS["text_primary"],
            selectbackground=TOKENS["accent_soft"],
            highlightthickness=0,
            bd=0,
        )
        self.listbox.pack(side="left", fill="y", padx=(0, 8))
        self.listbox.bind("<<ListboxSelect>>", self.show_selected)

        self.preview = scrolledtext.ScrolledText(
            body,
            wrap=tk.WORD,
            state=tk.DISABLED,
            bg=TOKENS["surface_elevated"],
            fg=TOKENS["text_primary"],
            font=TOKENS["font_mono"],
            relief="flat",
        )
        self.preview.pack(side="left", fill="both", expand=True)

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.refresh()

    def _on_close(self):
        self.destroy()

    def _is_alive(self):
        try:
            return self.winfo_exists()
        except tk.TclError:
            return False

    def refresh(self):
        def request():
            try:
                resp = requests.get(f"{SERVER_URL}/api/outputs", headers=self.app.auth_headers(), timeout=20)
                if resp.status_code == 200:
                    data = resp.json()
                    if self._is_alive():
                        self.after(0, lambda d=data: self._populate(d))
                else:
                    if self._is_alive():
                        _schedule_error(self, resp.text, parent=self)
            except Exception as exc:
                if self._is_alive():
                    _schedule_error(self, exc, parent=self)

        threading.Thread(target=request, daemon=True).start()
        if self.app.root.winfo_exists():
            self.app.refresh_saved_outputs()

    def _populate(self, outputs):
        if not self._is_alive():
            return
        try:
            self.outputs_data = outputs
            self.listbox.delete(0, tk.END)
            for item in outputs:
                self.listbox.insert(tk.END, self.app._format_output_label(item))
            self.preview.config(state=tk.NORMAL)
            self.preview.delete("1.0", tk.END)
            if outputs:
                self.preview.insert(tk.END, f"{len(outputs)} saved output file(s). Select one to preview.")
            else:
                self.preview.insert(tk.END, "No saved outputs yet.")
            self.preview.config(state=tk.DISABLED)
        except tk.TclError:
            return

    def _selected(self):
        idxs = self.listbox.curselection()
        if not idxs:
            messagebox.showinfo("Output Files", "Select an output file first.", parent=self)
            return None
        return self.outputs_data[idxs[0]]

    def show_selected(self, _event=None):
        idxs = self.listbox.curselection()
        if not idxs:
            return
        selected = self.outputs_data[idxs[0]]

        def request():
            try:
                resp = requests.get(
                    f"{SERVER_URL}/api/outputs/{selected['id']}",
                    headers=self.app.auth_headers(),
                    timeout=30,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if self._is_alive():
                        self.after(0, lambda d=data: self._render(d))
                else:
                    detail = resp.json().get("detail", resp.text)
                    if self._is_alive():
                        _schedule_error(self, detail, parent=self)
            except Exception as exc:
                if self._is_alive():
                    _schedule_error(self, exc, parent=self)

        threading.Thread(target=request, daemon=True).start()

    def _render(self, data):
        if not self._is_alive():
            return
        header = (
            f"File: {data['filename']}\n"
            f"Task: {data['task_type']} | Status: {data['status']} | "
            f"Progress: {data['processed']}/{data['total']}\n"
            f"{'-' * 60}\n"
        )
        self.preview.config(state=tk.NORMAL)
        self.preview.delete("1.0", tk.END)
        self.preview.insert(tk.END, header + data.get("content", ""))
        self.preview.config(state=tk.DISABLED)

    def open_selected(self):
        selected = self._selected()
        if not selected:
            return

        def request():
            try:
                resp = requests.get(
                    f"{SERVER_URL}/api/outputs/{selected['id']}",
                    headers=self.app.auth_headers(),
                    timeout=30,
                )
                if resp.status_code != 200:
                    if self._is_alive():
                        _schedule_error(self, resp.text, parent=self)
                    return
                data = resp.json()
                temp_dir = os.path.join(tempfile.gettempdir(), "odibets_outputs")
                os.makedirs(temp_dir, exist_ok=True)
                temp_path = os.path.join(temp_dir, data["filename"])
                with open(temp_path, "w", encoding="utf-8") as handle:
                    handle.write(data.get("content", ""))

                def open_file(path=temp_path):
                    if self._is_alive():
                        os.startfile(path)

                self.after(0, open_file)
            except Exception as exc:
                if self._is_alive():
                    _schedule_error(self, exc, parent=self)

        threading.Thread(target=request, daemon=True).start()

    def save_selected_as(self):
        selected = self._selected()
        if not selected:
            return

        def request():
            try:
                resp = requests.get(
                    f"{SERVER_URL}/api/outputs/{selected['id']}",
                    headers=self.app.auth_headers(),
                    timeout=30,
                )
                if resp.status_code != 200:
                    if self._is_alive():
                        _schedule_error(self, resp.text, parent=self)
                    return
                data = resp.json()

                def save_dialog(file_data=data):
                    if not self._is_alive():
                        return
                    path = filedialog.asksaveasfilename(
                        parent=self,
                        defaultextension=".txt",
                        initialfile=file_data["filename"],
                        filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
                    )
                    if path:
                        with open(path, "w", encoding="utf-8") as handle:
                            handle.write(file_data.get("content", ""))

                self.after(0, save_dialog)
            except Exception as exc:
                if self._is_alive():
                    _schedule_error(self, exc, parent=self)

        threading.Thread(target=request, daemon=True).start()


class ListsDialog(tk.Toplevel):
    def __init__(self, master, app: ClientApp):
        super().__init__(master)
        self.app = app
        self.title("My Saved Lists")
        self.geometry("520x420")
        self.transient(master)
        self.grab_set()

        top = tk.Frame(self, padx=10, pady=10)
        top.pack(fill="x")
        tk.Button(top, text="Refresh saved lists", command=self.refresh).pack(side="left")
        tk.Button(top, text="Create new list", command=self.create_list).pack(side="left", padx=6)

        self.listbox = tk.Listbox(self, height=12)
        self.listbox.pack(fill="both", expand=True, padx=10, pady=6)

        self.details = scrolledtext.ScrolledText(self, height=8, wrap=tk.WORD)
        self.details.pack(fill="both", expand=False, padx=10, pady=(0, 10))
        self.listbox.bind("<<ListboxSelect>>", self.show_selected)

        self.lists_data = []
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.refresh()

    def _is_alive(self):
        try:
            return self.winfo_exists()
        except tk.TclError:
            return False

    def refresh(self):
        def request():
            try:
                resp = requests.get(f"{SERVER_URL}/api/lists", headers=self.app.auth_headers(), timeout=20)
                if resp.status_code == 200:
                    data = resp.json()
                    if self._is_alive():
                        self.after(0, lambda d=data: self._populate(d))
                else:
                    if self._is_alive():
                        _schedule_error(self, resp.text, parent=self)
            except Exception as exc:
                if self._is_alive():
                    _schedule_error(self, exc, parent=self)

        threading.Thread(target=request, daemon=True).start()

    def _populate(self, lists):
        if not self._is_alive():
            return
        try:
            self.lists_data = lists
            self.listbox.delete(0, tk.END)
            for lst in lists:
                self.listbox.insert(tk.END, f"{lst['name']} ({len(lst['items'])} items)")
            self.details.delete("1.0", tk.END)
        except tk.TclError:
            return

    def show_selected(self, _event=None):
        idxs = self.listbox.curselection()
        if not idxs:
            return
        lst = self.lists_data[idxs[0]]
        self.details.delete("1.0", tk.END)
        for item in lst["items"]:
            self.details.insert(tk.END, item["value"] + "\n")

    def create_list(self):
        name = simpledialog.askstring("New List", "List name:", parent=self)
        if not name:
            return
        raw_items = simpledialog.askstring(
            "New List Items",
            "Enter items separated by commas or new lines:",
            parent=self,
        )
        if raw_items is None:
            return
        items = [part.strip() for part in raw_items.replace("\n", ",").split(",") if part.strip()]

        def request():
            try:
                resp = requests.post(
                    f"{SERVER_URL}/api/lists",
                    headers=self.app.auth_headers(),
                    json={"name": name, "items": items},
                    timeout=20,
                )
                if resp.status_code == 201:
                    if self._is_alive():
                        self.after(0, self.refresh)
                else:
                    detail = resp.json().get("detail", resp.text)
                    if self._is_alive():
                        _schedule_error(self, detail, parent=self)
            except Exception as exc:
                if self._is_alive():
                    _schedule_error(self, exc, parent=self)

        threading.Thread(target=request, daemon=True).start()


if __name__ == "__main__":
    root = tk.Tk()
    app = ClientApp(root)
    root.mainloop()
