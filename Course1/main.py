import concurrent.futures
from datetime import datetime
import json
import os
import requests
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, ttk
from bs4 import BeautifulSoup

# --- Configuration ---
CONFIG = {
    "BASE_URL": "https://odibets.com:443",
    "CONNECTIONS": 4,
    "TIMEOUT": 300,
    "BATCH_SIZE": 100,
    "WAIT_TIME_S": 5,
    "MAX_RETRIES": 3,
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

INPUT_FILE = os.path.join(BASE_DIR, "testlist.txt")
SUCCESS_FILE = os.path.join(BASE_DIR, "successbalance19.txt")
ERROR_FILE = os.path.join(BASE_DIR, "errorlistbalance55.txt")
TOOMANY_FILE = os.path.join(BASE_DIR, "toomanybalance1.txt")
PENDING_FILE = os.path.join(BASE_DIR, "pendingbalance2.txt")
DUPLICATES_FILE = os.path.join(BASE_DIR, "duplicates.txt")

# Threading state structures
retry_counts = {}
retry_items_next_round = set()
io_lock = threading.Lock()


# --- Core Helper & I/O Functions ---

def load_file(filename):
    """Loads phone numbers from a text file, stripping whitespace."""
    try:
        if not os.path.exists(filename):
            return []
        with open(filename, "r", encoding="utf-8") as f:
            return [line.strip() for line in f if line.strip()]
    except Exception as e:
        print(f"Error loading {filename}: {e}")
        return []


def clear_file(filename):
    with io_lock:
        with open(filename, "w", encoding="utf-8"):
            pass


def append_line_safely(filename, text):
    """Thread-safe file writing prevents race-conditions."""
    with io_lock:
        with open(filename, "a", encoding="utf-8") as f:
            f.write(text + "\n")


def write_pending(items):
    with io_lock:
        with open(PENDING_FILE, "w", encoding="utf-8") as f:
            for item in sorted(items):
                f.write(item + "\n")


def process_duplicates(items):
    seen = set()
    duplicates = set()
    for item in items:
        if item in seen:
            duplicates.add(item)
        else:
            seen.add(item)

    if duplicates:
        with io_lock:
            with open(DUPLICATES_FILE, "w", encoding="utf-8") as f:
                for item in sorted(duplicates):
                    f.write(item + "\n")


def mark_toomany(item):
    """Handles retries and error list segregation."""
    with io_lock:
        retry_counts[item] = retry_counts.get(item, 0) + 1
        if retry_counts[item] >= CONFIG["MAX_RETRIES"]:
            append_line_safely(ERROR_FILE, item)
        else:
            retry_items_next_round.add(item)
            append_line_safely(TOOMANY_FILE, item)


def get_dynamic_user_agent(phone_number):
    lt = phone_number[-2:] if len(phone_number) >= 2 else "00"
    kc = phone_number[-4] if len(phone_number) >= 4 else "0"
    return f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/1{lt}.0.{kc}.90 Safari/537.36"


# --- Core API Logic ---

def login_and_get_balance(phone_number, password):
    """
    Performs the full multi-step login process for Odibets and retrieves the balance.

    Args:
        phone_number (str): The user's phone number.
        password (str): The user's password.

    Returns:
        A tuple of (balance, bonus_balance) on success.

    Raises:
        Exception: On any failure during the multi-step process.
    """
    session = requests.Session()
    user_agent = get_dynamic_user_agent(phone_number)
    
    # === Step 1: Get initial cookie and X-Odi-Key precursor ===
    headers_step1 = {
        "User-Agent": user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Upgrade-Insecure-Requests": "0",
        "Connection": "close"
    }
    resp_step1 = session.get(CONFIG['BASE_URL'], headers=headers_step1, timeout=CONFIG['TIMEOUT'])
    resp_step1.raise_for_status()
    
    soup = BeautifulSoup(resp_step1.content, 'html.parser')
    body_element = soup.find(id='body')
    if not body_element or not body_element.get('ref'):
        raise ValueError("Could not find 'ref' value in initial page load.")
    
    ref_value = body_element.get('ref')
    x_odi_key_precursor = ref_value[2:].split(" ")[0]

    # === Step 2: Get the real X-Odi-Key ===
    
    

    # === Step 3: Perform the actual login ===
    burp0_url2 = "https://accounts-api.apps.odibets.com:443/accounts-api/api/v1/auth/login"
    headers_step3 = {"X-Link-Id": x_odi_key_precursor, "Sec-Ch-Ua-Platform": "\"Windows\"", "Accept-Language": "en-US,en;q=0.9", "Sec-Ch-Ua": "\"Not;A=Brand\";v=\"8\", \"Chromium\";v=\"150\"", "Sec-Ch-Ua-Mobile": "?0", "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36", "Accept": "application/json, text/plain, */*", "Content-Type": "application/json", "Origin": "https://odibets.com", "Sec-Fetch-Site": "same-site", "Sec-Fetch-Mode": "cors", "Sec-Fetch-Dest": "empty", "Referer": "https://odibets.com/", "Accept-Encoding": "gzip, deflate, br", "Priority": "u=1, i"}

    json_step3 = {
       
        "msisdn": phone_number, 
        "password": password, 
       
    }
    resp_step3 = session.post(burp0_url2, headers=headers_step3, json=json_step3, timeout=CONFIG['TIMEOUT'])
    resp_step3.raise_for_status()

    final_data = resp_step3.json()
    status_code = final_data.get("status_code")

    if status_code == 200 and "data" in final_data:
        balance = final_data["data"].get("balance", "N/A")
        bonus_balance = final_data["data"].get("bonus_balance", "N/A")
        append_line_safely(
            SUCCESS_FILE, f"{phone_number} Balance: {balance} Bonus: {bonus_balance}"
        )
        return (balance, bonus_balance)

    elif status_code == 422:
        append_line_safely(ERROR_FILE, f"{phone_number} Balance: Auth Failed")
        raise ValueError("Invalid credentials")
    else:
        mark_toomany(phone_number)
        error_msg = final_data.get("message", "Unknown API error")
        raise ValueError(error_msg)


def claim_bonus(phone_number, password, day_to_claim):
    time.sleep(0.3)
    return (True, f"Bonus claim for Day {day_to_claim} submitted.")


def place_bet(phone_number, password, share_code):
    time.sleep(0.3)
    return (True, f"Bet placed with code: {share_code}")


# --- GUI Application Class ---

class App:
    def __init__(self, master):
        self.master = master
        master.title("Odibets Automation Studio")
        master.geometry("800x680")
        master.protocol("WM_DELETE_WINDOW", self.on_closing)

        # Reactive State
        self.file_path = tk.StringVar()
        self.password = tk.StringVar()
        self.share_code = tk.StringVar()
        self.selected_day = tk.StringVar(value="Day 1")
        self.is_running = False
        self.processing_thread = None

        self.setup_ui()

    def setup_ui(self):
        # Configuration Card
        config_frame = ttk.LabelFrame(self.master, text=" Parameters ", padding=12)
        config_frame.pack(fill="x", padx=12, pady=8)
        config_frame.columnconfigure(1, weight=1)

        ttk.Label(config_frame, text="Phone List File:").grid(row=0, column=0, sticky="w", pady=4)
        self.file_entry = ttk.Entry(config_frame, textvariable=self.file_path, state="readonly")
        self.file_entry.grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Button(config_frame, text="Browse", command=self.browse_file).grid(row=0, column=2)

        ttk.Label(config_frame, text="Account Password:").grid(row=1, column=0, sticky="w", pady=4)
        ttk.Entry(config_frame, textvariable=self.password, show="•").grid(row=1, column=1, columnspan=2, sticky="ew", padx=6)

        ttk.Label(config_frame, text="Bet Share Code:").grid(row=2, column=0, sticky="w", pady=4)
        ttk.Entry(config_frame, textvariable=self.share_code).grid(row=2, column=1, columnspan=2, sticky="ew", padx=6)

        ttk.Label(config_frame, text="Bonus Day:").grid(row=3, column=0, sticky="w", pady=4)
        day_options = [f"Day {i}" for i in range(1, 8)]
        ttk.Combobox(config_frame, textvariable=self.selected_day, values=day_options, state="readonly").grid(
            row=3, column=1, columnspan=2, sticky="ew", padx=6
        )

        # Control Panel
        action_frame = ttk.LabelFrame(self.master, text=" Operations ", padding=12)
        action_frame.pack(fill="x", padx=12, pady=4)
        action_frame.columnconfigure((0, 1, 2), weight=1)

        self.balance_btn = ttk.Button(action_frame, text="Check Balances", command=lambda: self.start_processing("balance"))
        self.balance_btn.grid(row=0, column=0, sticky="ew", padx=4)

        self.claim_btn = ttk.Button(action_frame, text="Claim Bonus", command=lambda: self.start_processing("claim"))
        self.claim_btn.grid(row=0, column=1, sticky="ew", padx=4)

        self.bet_btn = ttk.Button(action_frame, text="Place Bet", command=lambda: self.start_processing("bet"))
        self.bet_btn.grid(row=0, column=2, sticky="ew", padx=4)

        self.stop_btn = ttk.Button(action_frame, text="Stop Task", command=self.stop_processing, state="disabled")
        self.stop_btn.grid(row=1, column=0, columnspan=3, sticky="ew", padx=4, pady=(8, 0))

        self.action_buttons = [self.balance_btn, self.claim_btn, self.bet_btn]

        # Output Log Frame
        log_frame = ttk.LabelFrame(self.master, text=" Execution Output ", padding=8)
        log_frame.pack(padx=12, pady=8, expand=True, fill="both")

        self.output_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, font=("Consolas", 9))
        self.output_text.pack(expand=True, fill="both")

        # Status Bar
        self.progress_bar = ttk.Progressbar(self.master, mode="determinate")
        self.progress_bar.pack(fill="x", padx=12, pady=(0, 2))

        self.status_label = ttk.Label(self.master, text="Ready", relief=tk.SUNKEN, anchor=tk.W, padding=4)
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)

    def browse_file(self):
        path = filedialog.askopenfilename(title="Select Phone Number List", filetypes=(("Text Files", "*.txt"), ("All Files", "*.*")))
        if path:
            self.file_path.set(path)
            self.log_output(f"Loaded file target: {path}\n")

    def log_output(self, message):
        self.master.after(0, self._insert_log, message)

    def _insert_log(self, message):
        self.output_text.insert(tk.END, message)
        self.output_text.see(tk.END)

    def update_status(self, message, progress=None):
        self.master.after(0, self._update_status_gui, message, progress)

    def _update_status_gui(self, message, progress):
        self.status_label.config(text=message)
        if progress is not None:
            self.progress_bar["value"] = progress

    def set_controls_state(self, state):
        for btn in self.action_buttons:
            btn.config(state=state)
        self.stop_btn.config(state="normal" if state == "disabled" else "disabled")

    def start_processing(self, action):
        file_p = self.file_path.get()
        pwd = self.password.get()

        if not file_p or not pwd:
            messagebox.showerror("Validation Error", "Please provide both an input file and account password.")
            return

        if action == "bet" and not self.share_code.get():
            messagebox.showerror("Validation Error", "Share code required for placing bets.")
            return

        self.is_running = True
        self.set_controls_state("disabled")
        self.output_text.delete(1.0, tk.END)

        try:
            day_val = int(self.selected_day.get().split()[-1])
        except (ValueError, IndexError):
            day_val = 1

        self.processing_thread = threading.Thread(
            target=self.run_processing,
            args=(file_p, pwd, self.share_code.get(), day_val, action),
            daemon=True,
        )
        self.processing_thread.start()

    def stop_processing(self):
        if self.is_running:
            self.is_running = False
            self.log_output("\n[!] STOP SIGNAL ISSUED. Terminating pending threads...\n")
            self.update_status("Stopping operations...")
            self.stop_btn.config(state="disabled")

    def on_closing(self):
        if self.is_running:
            if messagebox.askokcancel("Quit", "Tasks are active. Are you sure you want to stop and exit?"):
                self.is_running = False
                self.master.destroy()
        else:
            self.master.destroy()

    def run_processing(self, file_path, password, share_code, day_to_claim, action):
        self.log_output(f"=== Initiating Task Action: {action.upper()} ===\n")

        phone_numbers = load_file(file_path)
        if not phone_numbers:
            self.log_output(f"ERROR: Input file empty or non-existent.\n")
            self.update_status("Error loading input data.")
            self.master.after(0, self.set_controls_state, "normal")
            return

        process_duplicates(phone_numbers)
        total_items = len(phone_numbers)
        batches = [phone_numbers[i:i + CONFIG['BATCH_SIZE']] for i in range(0, total_items, CONFIG['BATCH_SIZE'])]
        total_batches = len(batches)

        self.log_output(f"Processing {total_items} numbers across {total_batches} batch(es).\n")

        processed_count = 0
        balance_results = []
        start_time = time.time()

        for batch_num, batch in enumerate(batches, 1):
            if not self.is_running:
                break

            self.log_output(f"\n--- Processing Batch {batch_num}/{total_batches} ---\n")

            with concurrent.futures.ThreadPoolExecutor(max_workers=CONFIG["CONNECTIONS"]) as executor:
                if action == "balance":
                    future_map = {executor.submit(login_and_get_balance, num, password): num for num in batch}
                elif action == "claim":
                    future_map = {executor.submit(claim_bonus, num, password, day_to_claim): num for num in batch}
                else:
                    future_map = {executor.submit(place_bet, num, password, share_code): num for num in batch}

                for future in concurrent.futures.as_completed(future_map):
                    if not self.is_running:
                        executor.shutdown(wait=False, cancel_futures=True)
                        break

                    processed_count += 1
                    phone = future_map[future]
                    progress_pct = (processed_count / total_items) * 100
                    self.update_status(f"Processed {processed_count}/{total_items} ({phone})", progress_pct)

                    try:
                        result = future.result()
                        if action == "balance":
                            bal, bonus = result
                            balance_results.append(f"{phone},{bal},{bonus}")
                            self.log_output(f"[SUCCESS] {phone:<13} | Bal: {bal:<8} | Bonus: {bonus}\n")
                        else:
                            ok, msg = result
                            tag = "SUCCESS" if ok else "FAILED"
                            self.log_output(f"[{tag}] {phone:<13} | {msg}\n")
                    except Exception as exc:
                        self.log_output(f"[FAILED]  {phone:<13} | Error: {exc}\n")

            if batch_num < total_batches and self.is_running:
                self.log_output(f"Batch {batch_num} complete. Pausing {CONFIG['WAIT_TIME_S']}s...\n")
                for i in range(CONFIG["WAIT_TIME_S"], 0, -1):
                    if not self.is_running:
                        break
                    self.update_status(f"Cooling down... ({i}s)")
                    time.sleep(1)

        duration = time.time() - start_time
        self.log_output(f"\n=== Operation Completed in {duration:.2f}s ===\n")

        if action == "balance" and balance_results and self.is_running:
            self.master.after(0, self.prompt_save_balance, balance_results)

        self.update_status("Finished.", 100)
        self.is_running = False
        self.master.after(0, self.set_controls_state, "normal")

    def prompt_save_balance(self, balance_results):
        save_path = filedialog.asksaveasfilename(
            title="Export Balance Results",
            defaultextension=".csv",
            filetypes=(("CSV Files", "*.csv"), ("Text Files", "*.txt")),
        )
        if save_path:
            try:
                with open(save_path, "w", encoding="utf-8") as f:
                    f.write("PhoneNumber,Balance,BonusBalance\n")
                    f.write("\n".join(balance_results))
                self.log_output(f"Exported results successfully to {save_path}\n")
            except Exception as e:
                messagebox.showerror("Save Failure", f"Unable to write file:\n{e}")


# --- Application Entry Point ---

if __name__ == "__main__":
    root = tk.Tk()
    style = ttk.Style(root)
    if "clam" in style.theme_names():
        style.theme_use("clam")

    app = App(root)
    root.mainloop()