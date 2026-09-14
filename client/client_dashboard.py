"""Dark-themed automation operations dashboard for the Tkinter client."""

from __future__ import annotations

import math
import re
import threading
import tkinter as tk
from datetime import datetime
from tkinter import scrolledtext, ttk

import requests

from client_config import load_automation_identity, load_server_url
from client_theme import TOKENS, apply_theme, apply_ui_scale, create_card, create_flat_button, switch_theme, themed_entry

SERVER_URL = load_server_url()

NAV_SECTIONS = [
    ("overview", "Overview"),
    ("activity", "Activity"),
    ("logs", "Logs"),
    ("outputs", "Outputs"),
]

QUICK_ACTIONS = (
    ("Check balances", "balance"),
    ("Place bets", "bet"),
    ("Claim bonus", "claim_bonus"),
    ("Check streaks", "streak"),
    ("Withdrawal", "withdrawal"),
    ("Cashout", "cashout"),
    ("Virtual bet", "virtual_bet"),
    ("Rollover", "rollover"),
)

SHARE_CODE_ACTIONS = {"bet", "claim_bonus"}
AMOUNT_ACTIONS = {"bet", "virtual_bet", "rollover", "withdrawal"}
AMOUNT_OPTION_ACTIONS = {"bet", "virtual_bet", "rollover"}
BET_ID_ACTIONS = {"cashout"}

ACTION_HELP = {
    "balance": "Check the available balance for every account in the selected batch.",
    "bet": "Place the booking-code bet for each eligible account.",
    "claim_bonus": "Claim the configured bonus for eligible accounts.",
    "streak": "Check the available streak for every account in the selected batch.",
    "withdrawal": "Withdraw the entered amount for every account in the selected batch.",
    "cashout": "Cash out open bets. Bet ID is optional; leave it blank to cash out all eligible bets.",
    "virtual_bet": "Place the virtual arbitrage bet for each eligible account.",
    "rollover": "Split the batch across a balanced virtual market and place rollover bets.",
}

LEVEL_COLORS = {
    "success": TOKENS["success"],
    "danger": TOKENS["danger"],
    "warning": TOKENS["warning"],
    "info": TOKENS["info"],
}


def humanize_log_line(line: str) -> dict:
    text = line.strip()
    level = "info"
    title = "System update"

    upper = text.upper()
    if "SUCCESS" in upper:
        level = "success"
        title = "Operation succeeded"
    elif "FAILED" in upper:
        level = "danger"
        title = "Operation failed"
    elif "BILLING STOPPED" in upper:
        level = "warning"
        title = "Billing stopped"
    elif "BILLED" in upper:
        level = "info"
        title = "Credits charged"
    elif "PROGRESS:" in upper:
        level = "info"
        title = "Processing progress"
    elif "STOP SIGNAL" in upper or "STOPPING" in upper:
        level = "warning"
        title = "Run stopped"
    elif "INITIALIZED" in upper or "STARTED" in upper:
        level = "info"
        title = "Run started"
    elif "ERROR" in upper or "EXCEPTION" in upper:
        level = "danger"
        title = "Error detected"

    time_part = ""
    if " - " in text:
        time_part, text = text.split(" - ", 1)

    return {
        "time": time_part or datetime.now().strftime("%H:%M:%S"),
        "level": level,
        "title": title,
        "message": text.strip(),
    }


class DonutChart(tk.Canvas):
    def __init__(self, parent, size: int = 160, **kwargs):
        super().__init__(
            parent,
            width=size,
            height=size,
            bg=TOKENS["surface_2"],
            highlightthickness=0,
            **kwargs,
        )
        self.base_size = size
        self.size = size
        self.segments: list[tuple[float, str, str]] = []

    def set_scale(self, scale: float) -> None:
        size = max(132, round(self.base_size * scale))
        if size == self.size:
            return
        self.size = size
        self.configure(width=size, height=size)
        self._draw()

    def set_segments(self, segments: list[tuple[float, str, str]]) -> None:
        self.segments = [(max(value, 0), label, color) for value, label, color in segments if value > 0]
        self._draw()

    def _draw(self) -> None:
        self.delete("all")
        cx = cy = self.size / 2
        outer = self.size * 0.42
        inner = self.size * 0.28
        total = sum(value for value, _, _ in self.segments) or 1
        start = -math.pi / 2

        for value, _label, color in self.segments:
            extent = (value / total) * 2 * math.pi
            self.create_arc(
                cx - outer,
                cy - outer,
                cx + outer,
                cy + outer,
                start=math.degrees(start),
                extent=math.degrees(extent),
                style=tk.PIESLICE,
                outline="",
                fill=color,
            )
            start += extent

        self.create_oval(cx - inner, cy - inner, cx + inner, cy + inner, fill=TOKENS["surface_2"], outline="")
        self.create_text(cx, cy - 8, text=str(int(total)), fill=TOKENS["text_primary"], font=TOKENS["font_kpi"])
        self.create_text(cx, cy + 18, text="items", fill=TOKENS["text_muted"], font=TOKENS["font_ui_sm"])


class DashboardBuilder:
    def __init__(self, app):
        self.app = app
        self.identity = load_automation_identity()
        self.sections: dict[str, tk.Frame] = {}
        self.nav_buttons: dict[str, tk.Button] = {}
        self.stats_data: dict | None = None
        self.job_started_at: datetime | None = None
        self._connection_ok = False
        self._layout_mode: str | None = None
        self.current_section = "overview"
        self.theme_mode = "light"
        self.ui_scale = 1.0

    def build(self) -> None:
        root = self.app.root
        apply_theme(root, "light")
        root.configure(bg=TOKENS["background"])
        root.title(f"{self.identity.name} — Control Center")
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        window_width = int(screen_width * 0.80)
        window_height = int(screen_height * 0.80)
        window_x = max((screen_width - window_width) // 2, 0)
        window_y = max((screen_height - window_height) // 2, 0)
        root.geometry(f"{window_width}x{window_height}+{window_x}+{window_y}")
        root.minsize(min(900, window_width), min(650, window_height))

        shell = tk.Frame(root, bg=TOKENS["background"])
        shell.pack(fill="both", expand=True)

        self._build_top_nav(shell)
        self._build_header(shell)

        body = tk.Frame(shell, bg=TOKENS["background"], padx=12, pady=8)
        body.pack(fill="both", expand=True)

        self.content_host = tk.Frame(body, bg=TOKENS["background"])
        self.content_host.pack(fill="both", expand=True)

        self._build_overview()
        self._build_activity()
        self._build_logs()
        self._build_outputs()

        root.bind("<Configure>", self._on_root_configure, add="+")
        root.after_idle(lambda: self._apply_responsive_layout(root.winfo_width(), root.winfo_height()))

        self.show_section("overview")
        self.refresh_stats()
        self.refresh_connection()
        self.app.refresh_billing()
        self._schedule_connection_poll()
        self._schedule_stats_poll()

        self.app.dashboard = self

    def show_section(self, section_id: str) -> None:
        self.current_section = section_id
        for sid, frame in self.sections.items():
            frame.pack_forget()
        if section_id in self.sections:
            self.sections[section_id].pack(fill="both", expand=True)

        for sid, button in self.nav_buttons.items():
            if sid == section_id:
                button.configure(bg=TOKENS["accent_soft"], fg=TOKENS["text_primary"])
            else:
                button.configure(bg=TOKENS["surface_1"], fg=TOKENS["text_secondary"])

    def _on_root_configure(self, event) -> None:
        if event.widget is not self.app.root:
            return
        pending = getattr(self, "_resize_job", None)
        if pending:
            self.app.root.after_cancel(pending)
        self._resize_job = self.app.root.after(
            80, lambda width=event.width, height=event.height: self._apply_responsive_layout(width, height)
        )

    def _on_overview_mousewheel(self, event) -> None:
        if self.current_section != "overview" or not hasattr(self, "overview_canvas"):
            return
        self.overview_canvas.yview_scroll(int(-event.delta / 120), "units")

    def _apply_responsive_layout(self, width: int, height: int | None = None) -> None:
        """Adapt the desktop layout without rebuilding widgets or losing form state."""
        height = height or self.app.root.winfo_height()
        raw_scale = min(width / 1280, height / 800)
        scale = max(0.78, min(raw_scale, 1.25))
        scale = round(scale / 0.05) * 0.05
        mode = "wide" if width >= 1040 else "compact"
        action_columns = 4 if width >= 1100 else 2 if width >= 760 else 1
        signature = f"{mode}:{action_columns}:{scale:.2f}"
        if signature == self._layout_mode:
            return
        self._layout_mode = signature
        self.ui_scale = scale
        apply_ui_scale(self.app.root, scale)
        if hasattr(self, "scale_var"):
            self.scale_var.set(f"UI size: {round(scale * 100)}%")

        for button in self.optional_nav_buttons:
            if width >= 1320:
                button.pack(side="left", padx=4, before=self.logout_button)
            else:
                button.pack_forget()

        if mode == "wide":
            self.header_actions.grid(row=0, column=1, sticky="e", pady=0)
        else:
            self.header_actions.grid(row=1, column=0, sticky="w", pady=(10, 0))

        self.workspace_frame.columnconfigure(0, weight=1, minsize=0)
        self.workspace_frame.columnconfigure(1, weight=0, minsize=0)
        self.control_panel.grid(row=0, column=0, sticky="nsew", padx=0, pady=(0, 10))
        self.monitor_panel.grid(row=1, column=0, sticky="nsew", pady=0)

        for column in range(3):
            self.monitor_panel.columnconfigure(column, weight=0)
        for row in range(3):
            self.monitor_panel.rowconfigure(row, weight=0)
        for card in (self.progress_card, self.chart_card, self.recent_card):
            card.grid_forget()

        if mode == "wide":
            for column, weight in enumerate((3, 3, 3)):
                self.monitor_panel.columnconfigure(column, weight=weight, uniform="monitor")
            self.monitor_panel.rowconfigure(0, weight=1)
            self.progress_card.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
            self.chart_card.grid(row=0, column=1, sticky="nsew", padx=4)
            self.recent_card.grid(row=0, column=2, sticky="nsew", padx=(4, 0))
        else:
            self.monitor_panel.columnconfigure(0, weight=1, uniform="")
            for row, card in enumerate((self.progress_card, self.chart_card, self.recent_card)):
                self.monitor_panel.rowconfigure(row, weight=1)
                card.grid(row=row, column=0, sticky="nsew", pady=(0, 8 if row < 2 else 0))

        for column in range(4):
            self.action_grid.columnconfigure(column, weight=1 if column < action_columns else 0)
        for index, button in enumerate(self.action_button_order):
            button.configure(
                width=0,
                padx=max(5, round(7 * scale)),
                pady=max(4, round(5 * scale)),
            )
            gap = max(2, round(3 * scale))
            button.grid(row=index // action_columns, column=index % action_columns, padx=gap, pady=gap, sticky="ew")

        if hasattr(self, "donut"):
            self.donut.set_scale(scale)

        target_theme = "dark" if self.theme_mode == "light" else "light"
        prefix = "Switch to" if mode == "wide" else "Use"
        self.theme_button.configure(text=f"{prefix} {target_theme} mode")

        self.app.root.after_idle(
            lambda: self.overview_canvas.configure(scrollregion=self.overview_canvas.bbox("all"))
        )

    def _toggle_theme(self) -> None:
        self.theme_mode = "dark" if self.theme_mode == "light" else "light"
        switch_theme(self.app.root, self.theme_mode)
        apply_ui_scale(self.app.root, self.ui_scale)
        target_theme = "dark" if self.theme_mode == "light" else "light"
        prefix = "Switch to" if self._layout_mode and self._layout_mode.startswith("wide") else "Use"
        self.theme_button.configure(text=f"{prefix} {target_theme} mode")

        if hasattr(self, "donut"):
            self.donut.configure(bg=TOKENS["surface_2"])
            if self.stats_data:
                self.apply_stats(self.stats_data)
            else:
                self.donut._draw()
        if hasattr(self, "selected_task_type"):
            self._select_action(self.selected_task_type)
        self.set_run_status(self.status_var.get().lower().replace(" ", "_"))
        self.show_section(self.current_section)

    def _build_top_nav(self, parent) -> None:
        bar = tk.Frame(parent, bg=TOKENS["surface_1"], pady=8, padx=12)
        bar.pack(fill="x")
        bar.columnconfigure(1, weight=1)
        self.top_bar = bar

        brand = tk.Frame(bar, bg=TOKENS["surface_1"])
        brand.grid(row=0, column=0, sticky="w")
        tk.Label(
            brand,
            text="◆",
            bg=TOKENS["surface_1"],
            fg=TOKENS["accent_primary"],
            font=("Segoe UI", 16, "bold"),
        ).pack(side="left")
        tk.Label(
            brand,
            text=self.identity.name,
            bg=TOKENS["surface_1"],
            fg=TOKENS["text_primary"],
            font=("Segoe UI", 13, "bold"),
        ).pack(side="left", padx=(6, 0))

        nav = tk.Frame(bar, bg=TOKENS["surface_1"])
        nav.grid(row=0, column=1)
        self.nav_frame = nav
        for section_id, label in NAV_SECTIONS:
            btn = create_flat_button(nav, label, lambda s=section_id: self.show_section(s), variant="ghost")
            btn.pack(side="left", padx=4)
            self.nav_buttons[section_id] = btn

        right = tk.Frame(bar, bg=TOKENS["surface_1"])
        right.grid(row=0, column=2, sticky="e")
        self.nav_account_frame = right

        self.connection_var = tk.StringVar(value="Checking server…")
        self.connection_label = tk.Label(
            right,
            textvariable=self.connection_var,
            bg=TOKENS["surface_1"],
            fg=TOKENS["text_muted"],
            font=TOKENS["font_ui_sm"],
        )
        self.connection_label.pack(side="left", padx=(0, 12))

        self.theme_button = create_flat_button(right, "Switch to dark mode", self._toggle_theme, variant="secondary")
        self.theme_button.pack(side="left", padx=4)

        self.optional_nav_buttons: list[tk.Button] = []
        lists_button = create_flat_button(right, "Open saved lists", self.app.open_lists_dialog)
        lists_button.pack(side="left", padx=4)
        self.optional_nav_buttons.append(lists_button)
        if self.app.user.get("role") == "admin":
            admin_button = create_flat_button(right, "Billing & credits", self.app.open_admin_dialog)
            admin_button.pack(side="left", padx=4)
            self.optional_nav_buttons.append(admin_button)
        self.logout_button = create_flat_button(right, "Sign out", self.app.logout, variant="danger")
        self.logout_button.pack(side="left", padx=4)

    def _build_header(self, parent) -> None:
        header = tk.Frame(parent, bg=TOKENS["background"], padx=12, pady=0)
        header.pack(fill="x", pady=(10, 0))
        header.columnconfigure(0, weight=1)
        self.header_frame = header

        left = tk.Frame(header, bg=TOKENS["background"])
        left.grid(row=0, column=0, sticky="ew")
        self.header_identity = left

        self.header_title = tk.Label(
            left,
            text=f"{self.identity.dashboard_title}",
            bg=TOKENS["background"],
            fg=TOKENS["text_primary"],
            font=TOKENS["font_title"],
            anchor="w",
        )
        self.header_title.pack(anchor="w")

        tk.Label(
            left,
            text=self.identity.description,
            bg=TOKENS["background"],
            fg=TOKENS["text_secondary"],
            font=TOKENS["font_ui_sm"],
            anchor="w",
        ).pack(anchor="w", pady=(4, 0))

        meta = tk.Frame(left, bg=TOKENS["background"])
        meta.pack(anchor="w", pady=(8, 0))
        env_text = f"Environment: {self.identity.environment}"
        self.user_meta_var = tk.StringVar(value=self.app.user["email"])
        self.credits_var = tk.StringVar(value=self._credits_label(self.app.current_credits()))
        self.status_var = tk.StringVar(value="Idle")
        self.last_refresh_var = tk.StringVar(value="Stats not loaded yet")
        self.scale_var = tk.StringVar(value="UI size: 100%")

        
        tk.Label(meta, textvariable=self.user_meta_var, bg=TOKENS["background"], fg=TOKENS["text_muted"], font=TOKENS["font_ui_sm"]).pack(
            side="left", padx=(0, 16)
        )
        self.credits_label = tk.Label(
            meta,
            textvariable=self.credits_var,
            bg=TOKENS["accent_soft"],
            fg=TOKENS["text_primary"],
            font=("Segoe UI", 9, "bold"),
            padx=8,
            pady=2,
        )
        self.credits_label.pack(side="left", padx=(0, 8))
        create_flat_button(meta, "Add credits", self.app.open_add_credits, variant="primary").pack(
            side="left", padx=(0, 16)
        )
        tk.Label(meta, text="Status:", bg=TOKENS["background"], fg=TOKENS["text_muted"], font=TOKENS["font_ui_sm"]).pack(
            side="left"
        )
        self.status_label = tk.Label(
            meta, textvariable=self.status_var, bg=TOKENS["background"], fg=TOKENS["success"], font=TOKENS["font_ui_sm"]
        )
        self.status_label.pack(
            side="left", padx=(4, 16)
        )
        tk.Label(meta, textvariable=self.last_refresh_var, bg=TOKENS["background"], fg=TOKENS["text_muted"], font=TOKENS["font_ui_sm"]).pack(
            side="left"
        )
        

        actions = tk.Frame(header, bg=TOKENS["background"])
        actions.grid(row=0, column=1, sticky="e")
        self.header_actions = actions
        create_flat_button(actions, "Add credits", self.app.open_add_credits, variant="primary").pack(side="left", padx=4)
        create_flat_button(actions, "Refresh dashboard", self.refresh_stats, variant="secondary").pack(side="left", padx=4)
        create_flat_button(actions, "View activity", lambda: self.show_section("activity"), variant="primary").pack(side="left")

    def _section_frame(self, name: str) -> tk.Frame:
        frame = tk.Frame(self.content_host, bg=TOKENS["background"])
        self.sections[name] = frame
        return frame

    def _build_overview(self) -> None:
        section = self._section_frame("overview")
        canvas = tk.Canvas(section, bg=TOKENS["background"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(section, orient="vertical", command=canvas.yview)
        frame = tk.Frame(canvas, bg=TOKENS["background"])
        window_id = canvas.create_window((0, 0), window=frame, anchor="nw")
        frame.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(window_id, width=event.width))
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        canvas.bind_all("<MouseWheel>", self._on_overview_mousewheel, add="+")
        self.overview_canvas = canvas
        self.overview_body = frame
        self.primary_action_var = tk.StringVar(value=QUICK_ACTIONS[0][0])

        self.kpi_vars = {
            "total_runs": tk.StringVar(value="—"),
            "active_runs": tk.StringVar(value="—"),
            "completed_runs": tk.StringVar(value="—"),
            "credits": tk.StringVar(value=self._format_credits(self.app.current_credits())),
        }

        mid = tk.Frame(frame, bg=TOKENS["background"])
        mid.pack(fill="both", expand=True)
        mid.columnconfigure(0, weight=1, minsize=0)
        mid.columnconfigure(1, weight=0, minsize=0)
        mid.rowconfigure(0, weight=1)
        self.workspace_frame = mid

        control_panel = create_card(mid, padx=10, pady=9, highlight=True)
        control_panel.grid(row=0, column=0, sticky="nsew")
        self.control_panel = control_panel
        self._build_runs(control_panel)

        monitor_panel = tk.Frame(mid, bg=TOKENS["background"])
        monitor_panel.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        self.monitor_panel = monitor_panel

        progress_card = create_card(monitor_panel, padx=12, pady=10, highlight=True)
        progress_card.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        self.progress_card = progress_card

        tk.Label(
            progress_card,
            text="Current Run Progress",
            bg=TOKENS["surface_2"],
            fg=TOKENS["text_primary"],
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w")

        self.progress_pct_var = tk.StringVar(value="0%")
        self.progress_detail_var = tk.StringVar(value="No active run")
        self.progress_stage_var = tk.StringVar(value="Waiting for task")
        self.progress_elapsed_var = tk.StringVar(value="Elapsed: —")
        self.progress_rate_var = tk.StringVar(value="Rate: —")

        tk.Label(
            progress_card,
            textvariable=self.progress_pct_var,
            bg=TOKENS["surface_2"],
            fg=TOKENS["accent_primary"],
            font=("Segoe UI", 22, "bold"),
        ).pack(anchor="w", pady=(10, 4))
        tk.Label(
            progress_card,
            textvariable=self.progress_detail_var,
            bg=TOKENS["surface_2"],
            fg=TOKENS["text_secondary"],
            font=TOKENS["font_ui"],
        ).pack(anchor="w")
        tk.Label(
            progress_card,
            textvariable=self.progress_stage_var,
            bg=TOKENS["surface_2"],
            fg=TOKENS["text_muted"],
            font=TOKENS["font_ui_sm"],
        ).pack(anchor="w", pady=(2, 8))

        self.progress_bar = ttk.Progressbar(progress_card, style="Accent.Horizontal.TProgressbar", maximum=100)
        self.progress_bar.pack(fill="x", pady=(0, 10))
        self.progress_bar["value"] = 0

        stats_row = tk.Frame(progress_card, bg=TOKENS["surface_2"])
        stats_row.pack(fill="x")
        tk.Label(stats_row, textvariable=self.progress_elapsed_var, bg=TOKENS["surface_2"], fg=TOKENS["text_muted"], font=TOKENS["font_ui_sm"]).pack(
            side="left"
        )
        tk.Label(stats_row, textvariable=self.progress_rate_var, bg=TOKENS["surface_2"], fg=TOKENS["text_muted"], font=TOKENS["font_ui_sm"]).pack(
            side="right"
        )

        result_row = tk.Frame(progress_card, bg=TOKENS["surface_2"])
        result_row.pack(fill="x", pady=(12, 0))
        self.result_completed_var = tk.StringVar(value="0")
        self.result_stopped_var = tk.StringVar(value="0")
        for label, var, color in (
            ("Completed items", self.result_completed_var, TOKENS["success"]),
            ("Stopped / other", self.result_stopped_var, TOKENS["warning"]),
        ):
            box = tk.Frame(result_row, bg=TOKENS["surface_elevated"], padx=10, pady=8)
            box.pack(side="left", fill="x", expand=True, padx=(0, 8))
            tk.Label(box, text=label, bg=TOKENS["surface_elevated"], fg=TOKENS["text_muted"], font=TOKENS["font_ui_sm"]).pack(anchor="w")
            tk.Label(box, textvariable=var, bg=TOKENS["surface_elevated"], fg=color, font=("Segoe UI", 16, "bold")).pack(anchor="w")

        chart_card = create_card(monitor_panel, padx=12, pady=10)
        chart_card.grid(row=0, column=1, sticky="nsew", padx=4)
        self.chart_card = chart_card

        tk.Label(
            chart_card,
            text="Run Outcome Distribution",
            bg=TOKENS["surface_2"],
            fg=TOKENS["text_primary"],
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w")

        chart_body = tk.Frame(chart_card, bg=TOKENS["surface_2"])
        chart_body.pack(fill="both", expand=True, pady=10)
        self.donut = DonutChart(chart_body, size=170)
        self.donut.pack(side="left")

        legend = tk.Frame(chart_body, bg=TOKENS["surface_2"])
        legend.pack(side="left", fill="y", padx=12)
        self.legend_labels: list[tk.Label] = []
        for color, label in (
            (TOKENS["success"], "Completed"),
            (TOKENS["warning"], "Stopped"),
            (TOKENS["accent_primary"], "Running"),
        ):
            row = tk.Frame(legend, bg=TOKENS["surface_2"])
            row.pack(anchor="w", pady=4)
            tk.Label(row, text="●", bg=TOKENS["surface_2"], fg=color, font=TOKENS["font_ui"]).pack(side="left")
            lbl = tk.Label(row, text=f"{label}: 0", bg=TOKENS["surface_2"], fg=TOKENS["text_secondary"], font=TOKENS["font_ui_sm"])
            lbl.pack(side="left", padx=(4, 0))
            self.legend_labels.append(lbl)

        recent_card = create_card(monitor_panel, padx=11, pady=9)
        recent_card.grid(row=0, column=2, sticky="nsew", padx=(4, 0))
        self.recent_card = recent_card
        tk.Label(
            recent_card,
            text="Recent Activity",
            bg=TOKENS["surface_2"],
            fg=TOKENS["text_primary"],
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w")

        self.recent_activity = tk.Listbox(
            recent_card,
            height=4,
            bg=TOKENS["surface_elevated"],
            fg=TOKENS["text_primary"],
            selectbackground=TOKENS["accent_soft"],
            highlightthickness=0,
            bd=0,
            font=TOKENS["font_ui_sm"],
        )
        self.recent_activity.pack(fill="both", expand=True, pady=(8, 0))

    def _build_runs(self, parent: tk.Frame) -> None:
        """Build the operational controls directly inside the dashboard workspace."""
        scroll_body = parent

        tk.Label(
            scroll_body, text="Create a run", bg=TOKENS["surface_2"], fg=TOKENS["text_primary"],
            font=("Segoe UI", 14, "bold"),
        ).pack(anchor="w")
        tk.Label(
            scroll_body, text="Choose a task and complete only the details it requires.",
            bg=TOKENS["surface_2"], fg=TOKENS["text_secondary"], font=TOKENS["font_ui_sm"],
        ).pack(anchor="w", pady=(2, 8))

        details_wrap = tk.Frame(scroll_body, bg=TOKENS["surface_2"])
        details_wrap.pack(fill="x", pady=(0, 6))
        details_wrap.columnconfigure(0, weight=1)
        details_wrap.columnconfigure(1, weight=8)
        details_wrap.columnconfigure(2, weight=1)
        self.required_fields_wrap = details_wrap

        input_card = create_card(details_wrap, padx=10, pady=8)
        input_card.grid(row=0, column=1, sticky="ew")
        self.required_fields_frame = input_card
        self.action_requirement_var = tk.StringVar()
        tk.Label(
            input_card, text="2  Required details", bg=TOKENS["surface_2"],
            fg=TOKENS["text_primary"], font=("Segoe UI", 11, "bold"),
        ).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 4))
        tk.Label(
            input_card, textvariable=self.action_requirement_var, bg=TOKENS["surface_2"],
            fg=TOKENS["info"], font=TOKENS["font_ui_sm"], wraplength=420, justify="left",
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(0, 10))

        def label(text, row):
            field_label = tk.Label(
                input_card,
                text=text,
                bg=TOKENS["surface_2"],
                fg=TOKENS["text_secondary"],
                font=TOKENS["font_ui"],
            )
            field_label.grid(row=row, column=0, sticky="w", pady=3)
            return field_label

        label("Input file", 2)
        self.app.file_path_entry = themed_entry(input_card, width=30)
        self.app.file_path_entry.grid(row=2, column=1, padx=8, sticky="ew")
        self.app.browse_button = create_flat_button(input_card, "Browse files", self.app.browse_file)
        self.app.browse_button.grid(row=2, column=2, sticky="w")
        self.app.load_list_button = create_flat_button(input_card, "Use saved list", self.app.load_from_saved_list)
        self.app.load_list_button.grid(row=2, column=3, sticky="w", padx=(6, 0))

        self.app.list_count_var = tk.StringVar(value="Entries: —")
        tk.Label(
            input_card,
            textvariable=self.app.list_count_var,
            bg=TOKENS["surface_2"],
            fg=TOKENS["info"],
            font=TOKENS["font_ui_sm"],
        ).grid(row=3, column=1, columnspan=3, sticky="w", padx=8, pady=(2, 8))

        label("Password", 4)
        self.app.password_entry = themed_entry(input_card, width=30, show="*")
        self.app.password_entry.grid(row=4, column=1, padx=8, columnspan=3, sticky="ew")

        self.share_code_label = label("Share / booking code", 5)
        self.app.share_code_entry = themed_entry(input_card, width=30)
        self.app.share_code_entry.grid(row=5, column=1, padx=8, columnspan=3, sticky="ew")

        self.amount_label = label("Amount", 6)
        self.app.amount_entry = themed_entry(input_card, width=12)
        self.app.amount_entry.grid(row=6, column=1, padx=8, sticky="w")
        input_card.columnconfigure(1, weight=1)

        self.bet_id_label = label("Bet ID (optional)", 7)
        self.app.bet_id_entry = themed_entry(input_card, width=30)
        self.app.bet_id_entry.grid(row=7, column=1, padx=8, columnspan=3, sticky="ew")

        self.option_card = create_card(input_card, padx=10, pady=8, highlight=True)
        self.option_card.grid(row=8, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        tk.Label(
            self.option_card,
            text="Amount and balance options",
            bg=TOKENS["surface_2"],
            fg=TOKENS["text_primary"],
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", pady=(0, 8))

        self.app.balance_mode_var = tk.StringVar(value="actual")
        bal_row = tk.Frame(self.option_card, bg=TOKENS["surface_2"])
        bal_row.pack(anchor="w", pady=2)
        tk.Label(bal_row, text="Balance Source:", bg=TOKENS["surface_2"], fg=TOKENS["text_secondary"], width=16, anchor="w").pack(
            side="left"
        )
        for text, value in (("Actual Balance", "actual"), ("Bonus Balance", "bonus")):
            tk.Radiobutton(
                bal_row,
                text=text,
                variable=self.app.balance_mode_var,
                value=value,
                bg=TOKENS["surface_2"],
                fg=TOKENS["text_primary"],
                selectcolor=TOKENS["surface_elevated"],
                activebackground=TOKENS["surface_2"],
            ).pack(side="left", padx=6)

        self.app.amount_mode_var = tk.StringVar(value="manual")
        amt_row = tk.Frame(self.option_card, bg=TOKENS["surface_2"])
        amt_row.pack(anchor="w", pady=2)
        tk.Label(amt_row, text="Amount Type:", bg=TOKENS["surface_2"], fg=TOKENS["text_secondary"], width=16, anchor="w").pack(
            side="left"
        )
        for text, value in (("Manual Input", "manual"), ("Use Total Balance", "total")):
            tk.Radiobutton(
                amt_row,
                text=text,
                variable=self.app.amount_mode_var,
                value=value,
                bg=TOKENS["surface_2"],
                fg=TOKENS["text_primary"],
                selectcolor=TOKENS["surface_elevated"],
                activebackground=TOKENS["surface_2"],
            ).pack(side="left", padx=6)

        actions_card = create_card(scroll_body, padx=10, pady=8)
        actions_card.pack(fill="x", before=details_wrap, pady=(0, 6))
        tk.Label(
            actions_card,
            text="1  Choose an action",
            bg=TOKENS["surface_2"],
            fg=TOKENS["text_primary"],
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", pady=(0, 10))

        grid = tk.Frame(actions_card, bg=TOKENS["surface_2"])
        grid.pack(fill="x")
        self.action_grid = grid
        for column in range(4):
            grid.columnconfigure(column, weight=1)

        defs = [
            (label.title(), task_type, "primary" if index < 2 else "secondary")
            for index, (label, task_type) in enumerate(QUICK_ACTIONS)
        ]
        self.app.action_buttons = []
        self.action_button_map: dict[str, tk.Button] = {}
        self.action_button_order: list[tk.Button] = []
        self.action_base_labels: dict[str, str] = {}
        for idx, (text, task_type, variant) in enumerate(defs):
            btn = create_flat_button(
                grid,
                text,
                lambda t=task_type: self._select_action(t),
                variant=variant,
                width=18,
            )
            btn.grid(row=idx // 4, column=idx % 4, padx=2, pady=2, sticky="ew")
            self.app.action_buttons.append(btn)
            self.action_button_order.append(btn)
            self.action_button_map[task_type] = btn
            self.action_base_labels[task_type] = text

        self.app.input_widgets = [
            self.app.browse_button,
            self.app.load_list_button,
            self.app.file_path_entry,
            self.app.password_entry,
            self.app.share_code_entry,
            self.app.amount_entry,
            self.app.bet_id_entry,
        ]

        run_card = create_card(scroll_body, padx=10, pady=8, highlight=True)
        run_card.pack(fill="x")
        self.run_card = run_card
        tk.Label(
            run_card, text="3  Start run", bg=TOKENS["surface_2"], fg=TOKENS["text_primary"],
            font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w", pady=(0, 8))
        run_actions = tk.Frame(run_card, bg=TOKENS["surface_2"])
        run_actions.pack(fill="x")
        self.primary_run_button = create_flat_button(
            run_actions, "Run check balances", self._start_selected_action, variant="primary"
        )
        self.primary_run_button.pack(side="left", fill="x", expand=True)
        self.primary_stop_button = create_flat_button(run_actions, "Stop active run", self.app.stop_job, variant="danger")
        self.primary_stop_button.configure(state=tk.DISABLED)
        self.primary_stop_button.pack(side="left", padx=(8, 0))
        self.app.stop_button = self.primary_stop_button
        self.app.primary_action_buttons = [self.primary_run_button]
        self.app.primary_stop_button = self.primary_stop_button
        self._select_action("balance")

    def _build_activity(self) -> None:
        frame = self._section_frame("activity")
        card = create_card(frame, padx=12, pady=12, highlight=True)
        card.pack(fill="both", expand=True)

        top = tk.Frame(card, bg=TOKENS["surface_2"])
        top.pack(fill="x")
        tk.Label(
            top,
            text=f"{self.identity.name} Activity",
            bg=TOKENS["surface_2"],
            fg=TOKENS["text_primary"],
            font=("Segoe UI", 11, "bold"),
        ).pack(side="left")
        create_flat_button(top, "Open technical logs", lambda: self.show_section("logs"), variant="ghost").pack(side="right")

        columns = ("time", "level", "title", "message")
        self.activity_tree = ttk.Treeview(card, columns=columns, show="headings", height=22, style="Dark.Treeview")
        for col, heading, width in (
            ("time", "Time", 80),
            ("level", "Level", 80),
            ("title", "Event", 160),
            ("message", "Details", 620),
        ):
            self.activity_tree.heading(col, text=heading)
            self.activity_tree.column(col, width=width, anchor="w")
        self.activity_tree.pack(fill="both", expand=True, pady=(10, 0))

    def _build_logs(self) -> None:
        frame = self._section_frame("logs")
        card = create_card(frame, padx=12, pady=12)
        card.pack(fill="both", expand=True)

        top = tk.Frame(card, bg=TOKENS["surface_2"])
        top.pack(fill="x")
        tk.Label(
            top,
            text="Raw Server Logs",
            bg=TOKENS["surface_2"],
            fg=TOKENS["text_primary"],
            font=("Segoe UI", 11, "bold"),
        ).pack(side="left")
        create_flat_button(top, "Open activity view", lambda: self.show_section("activity"), variant="ghost").pack(side="right")

        self.app.log_area = scrolledtext.ScrolledText(
            card,
            wrap=tk.WORD,
            bg=TOKENS["surface_elevated"],
            fg=TOKENS["text_primary"],
            insertbackground=TOKENS["text_primary"],
            font=TOKENS["font_mono"],
            relief="flat",
            highlightthickness=1,
            highlightbackground=TOKENS["border_subtle"],
        )
        self.app.log_area.pack(fill="both", expand=True, pady=(10, 0))

    def _build_outputs(self) -> None:
        frame = self._section_frame("outputs")
        card = create_card(frame, padx=12, pady=12, highlight=True)
        card.pack(fill="both", expand=True)

        top = tk.Frame(card, bg=TOKENS["surface_2"])
        top.pack(fill="x")
        tk.Label(
            top,
            text="Saved Output Files",
            bg=TOKENS["surface_2"],
            fg=TOKENS["text_primary"],
            font=("Segoe UI", 11, "bold"),
        ).pack(side="left")
        create_flat_button(top, "Refresh output files", self.app.refresh_saved_outputs).pack(side="right", padx=4)
        create_flat_button(top, "Open output manager", self.app.open_outputs_dashboard, variant="ghost").pack(side="right")

        body = tk.Frame(card, bg=TOKENS["surface_2"])
        body.pack(fill="both", expand=True, pady=(10, 0))

        self.app.outputs_listbox = tk.Listbox(
            body,
            height=14,
            width=52,
            exportselection=False,
            bg=TOKENS["surface_elevated"],
            fg=TOKENS["text_primary"],
            selectbackground=TOKENS["accent_soft"],
            highlightthickness=0,
            bd=0,
            font=TOKENS["font_ui_sm"],
        )
        self.app.outputs_listbox.pack(side="left", fill="y", padx=(0, 8))
        self.app.outputs_listbox.bind("<<ListboxSelect>>", self.app._show_selected_output)

        self.app.outputs_preview = scrolledtext.ScrolledText(
            body,
            wrap=tk.WORD,
            state=tk.DISABLED,
            bg=TOKENS["surface_elevated"],
            fg=TOKENS["text_primary"],
            font=TOKENS["font_mono"],
            relief="flat",
        )
        self.app.outputs_preview.pack(side="left", fill="both", expand=True)

        btns = tk.Frame(card, bg=TOKENS["surface_2"])
        btns.pack(fill="x", pady=(10, 0))
        create_flat_button(btns, "Open selected file", self.app.open_selected_output).pack(side="left")
        create_flat_button(btns, "Save selected file as...", self.app.save_selected_output_as).pack(side="left", padx=6)

        self.app.saved_outputs = []
        self.app.refresh_saved_outputs()

    def append_activity(self, line: str) -> None:
        if not hasattr(self, "activity_tree"):
            return
        item = humanize_log_line(line)
        self.activity_tree.insert(
            "",
            0,
            values=(item["time"], item["level"].upper(), item["title"], item["message"]),
        )
        children = self.activity_tree.get_children()
        if len(children) > 300:
            self.activity_tree.delete(children[-1])

        if hasattr(self, "recent_activity"):
            summary = f"{item['time']}  {item['title']}: {item['message'][:90]}"
            self.recent_activity.insert(0, summary)
            if self.recent_activity.size() > 8:
                self.recent_activity.delete(tk.END)

    def set_run_status(self, status: str) -> None:
        colors = {
            "running": TOKENS["accent_primary"],
            "completed": TOKENS["success"],
            "stopped": TOKENS["warning"],
            "idle": TOKENS["text_muted"],
        }
        label = status.replace("_", " ").title()
        self.status_var.set(label)
        if hasattr(self, "status_label"):
            self.status_label.configure(fg=colors.get(status, TOKENS["text_secondary"]))
        self.app.root.update_idletasks()

    def _start_selected_action(self) -> None:
        self.app.start_job(getattr(self, "selected_task_type", "balance"))

    def _select_action(self, task_type: str) -> None:
        """Keep common setup visible and reveal only the selected action's extras."""
        self.selected_task_type = task_type
        label = next((name for name, value in QUICK_ACTIONS if value == task_type), "Check balances")
        self.primary_action_var.set(label)

        requires_share_code = task_type in SHARE_CODE_ACTIONS
        requires_amount = task_type in AMOUNT_ACTIONS
        requires_amount_options = task_type in AMOUNT_OPTION_ACTIONS
        requires_bet_id = task_type in BET_ID_ACTIONS
        required_extras = []
        if requires_share_code:
            required_extras.append("booking code")
        if requires_amount:
            required_extras.append("amount")
        if requires_bet_id:
            required_extras.append("optional bet ID")
        requirement = f" Additional details: {', '.join(required_extras)}." if required_extras else " No additional details required."
        billing_note = self._billing_help(task_type)
        availability_note = "" if self.app.is_action_enabled(task_type) else " This action is currently disabled by the server."
        self.action_requirement_var.set(f"{ACTION_HELP.get(task_type, '')}{requirement}{billing_note}{availability_note}")
        self.share_code_label.configure(text="Share / booking code *")
        self.amount_label.configure(text="Amount *")
        self.bet_id_label.configure(text="Bet ID (optional)")
        run_label = f"Run {label.lower()}"
        if self.app.is_billable(task_type):
            run_label = f"{run_label} · {self._format_credits(self.app.action_rate(task_type))} cr each"
        self.primary_run_button.configure(text=run_label)
        self.refresh_action_affordability()

        for widget in (self.share_code_label, self.app.share_code_entry):
            (widget.grid if requires_share_code else widget.grid_remove)()
        for widget in (self.amount_label, self.app.amount_entry):
            (widget.grid if requires_amount else widget.grid_remove)()
        for widget in (self.bet_id_label, self.app.bet_id_entry):
            (widget.grid if requires_bet_id else widget.grid_remove)()

        if requires_amount_options:
            self.option_card.grid()
        else:
            self.option_card.grid_remove()

        self._style_action_buttons()

    def _style_action_buttons(self) -> None:
        selected = getattr(self, "selected_task_type", "balance")
        running = bool(self.app.is_running)
        for action, button in getattr(self, "action_button_map", {}).items():
            enabled = self.app.is_action_enabled(action)
            is_selected = action == selected
            base = self.action_base_labels.get(action, action)
            item = (self.app.billing_rates or {}).get(action) or {}
            label = base
            if item.get("billable") or float(item.get("rate") or 0) > 0:
                label = f"{base}  ·  {self._format_credits(item.get('rate'))} cr"
            if not enabled:
                label = f"{base}  ·  off"
            button.configure(
                text=label,
                state=tk.DISABLED if running or not enabled else tk.NORMAL,
                bg=TOKENS["accent_primary"] if is_selected and enabled else TOKENS["surface_elevated"],
                fg=TOKENS["on_accent"] if is_selected and enabled else TOKENS["text_muted"] if not enabled else TOKENS["text_secondary"],
                highlightbackground=TOKENS["focus_ring"] if is_selected and enabled else TOKENS["surface_elevated"],
                highlightthickness=1,
            )

    def _format_credits(self, value) -> str:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return "0"
        if number.is_integer():
            return str(int(number))
        return f"{number:.4f}".rstrip("0").rstrip(".")

    def _credits_label(self, value) -> str:
        return f"Credits: {self._format_credits(value)}"

    def _billing_help(self, task_type: str) -> str:
        if not self.app.is_billable(task_type):
            return " This action is free."
        rate = self.app.action_rate(task_type)
        credits = self.app.current_credits()
        affordable = int(credits // rate) if rate else 0
        return (
            f" Billable: {self._format_credits(rate)} credit(s) per successful action. "
            f"Current balance covers about {affordable} success(es)."
        )

    def apply_credits(self, credits) -> None:
        formatted = self._format_credits(credits)
        if hasattr(self, "credits_var"):
            self.credits_var.set(self._credits_label(credits))
        if hasattr(self, "kpi_vars") and "credits" in self.kpi_vars:
            self.kpi_vars["credits"].set(formatted)
        self.refresh_action_affordability()
        if not self.app.is_running and hasattr(self, "selected_task_type") and hasattr(self, "action_requirement_var"):
            self._select_action(self.selected_task_type)

    def apply_billing_rates(self, rates: dict) -> None:
        self.app.billing_rates = rates
        if hasattr(self, "selected_task_type"):
            self._select_action(self.selected_task_type)
        else:
            self._style_action_buttons()
            self.refresh_action_affordability()

    def apply_job_billing(self, charged, remaining) -> None:
        if remaining is not None:
            formatted = self._format_credits(remaining)
            if hasattr(self, "credits_var"):
                self.credits_var.set(self._credits_label(remaining))
            if hasattr(self, "kpi_vars") and "credits" in self.kpi_vars:
                self.kpi_vars["credits"].set(formatted)
        if charged is not None and hasattr(self, "progress_rate_var"):
            current = self.progress_rate_var.get()
            billed = f"Billed: {self._format_credits(charged)} cr"
            if "Billed:" in current:
                self.progress_rate_var.set(billed)
            else:
                self.progress_rate_var.set(f"{current}  •  {billed}" if current else billed)

    def refresh_action_affordability(self) -> None:
        if self.app.is_running:
            return
        task_type = getattr(self, "selected_task_type", "balance")
        can_run = self.app.is_action_enabled(task_type)
        if can_run and self.app.is_billable(task_type):
            can_run = self.app.current_credits() >= self.app.action_rate(task_type)
        if hasattr(self, "primary_run_button"):
            self.primary_run_button.configure(state=tk.NORMAL if can_run else tk.DISABLED)
        self._style_action_buttons()

    def update_progress(self, processed: int, total: int, status: str = "running", stage: str = "Processing items") -> None:
        total = max(total, 0)
        processed = max(min(processed, total), 0) if total else processed
        pct = int((processed / total) * 100) if total else 0

        self.progress_bar["value"] = pct
        self.progress_pct_var.set(f"{pct}% complete")
        if total:
            self.progress_detail_var.set(f"{processed} of {total} items")
        else:
            self.progress_detail_var.set("No active batch")
        self.progress_stage_var.set(f"Current stage: {stage}")

        elapsed_text = "Elapsed: —"
        rate_text = "Rate: —"
        if self.job_started_at and processed > 0:
            elapsed_sec = max((datetime.now() - self.job_started_at).total_seconds(), 1)
            elapsed_text = f"Elapsed: {int(elapsed_sec // 60)}m {int(elapsed_sec % 60)}s"
            rate = processed / elapsed_sec
            rate_text = f"Rate: {rate:.2f} items/s"
            if total and processed < total and rate > 0:
                remaining = (total - processed) / rate
                self.progress_stage_var.set(f"{stage} • ETA ~{int(remaining // 60)}m {int(remaining % 60)}s")

        self.progress_elapsed_var.set(elapsed_text)
        self.progress_rate_var.set(rate_text)
        self.set_run_status(status)

    def apply_stats(self, stats: dict) -> None:
        self.stats_data = stats
        self.kpi_vars["total_runs"].set(str(stats.get("total_runs", 0)))
        self.kpi_vars["active_runs"].set(str(stats.get("active_runs", 0)))
        self.kpi_vars["completed_runs"].set(str(stats.get("completed_runs", 0)))

        completed = stats.get("completed_runs", 0)
        stopped = stats.get("stopped_runs", 0)
        active = stats.get("active_runs", 0)
        self.result_completed_var.set(str(stats.get("items_processed", 0)))
        self.result_stopped_var.set(str(max(stats.get("items_total", 0) - stats.get("items_processed", 0), 0)))

        segments = [
            (completed, "Completed", TOKENS["success"]),
            (stopped, "Stopped", TOKENS["warning"]),
            (active, "Running", TOKENS["accent_primary"]),
        ]
        self.donut.set_segments(segments)
        legend_values = [completed, stopped, active]
        legend_names = ["Completed", "Stopped", "Running"]
        for lbl, name, value in zip(self.legend_labels, legend_names, legend_values):
            lbl.config(text=f"{name}: {value}")

        last_run = stats.get("last_run_at")
        if last_run:
            ts = last_run[:16].replace("T", " ")
            self.last_refresh_var.set(f"Last run: {ts} • Refreshed {datetime.now().strftime('%H:%M:%S')}")
        else:
            self.last_refresh_var.set(f"Refreshed {datetime.now().strftime('%H:%M:%S')}")
        if stats.get("credits") is not None:
            self.app.set_credits(stats["credits"])

    def refresh_stats(self) -> None:
        def request():
            try:
                resp = requests.get(f"{SERVER_URL}/api/dashboard/stats", headers=self.app.auth_headers(), timeout=20)
                if resp.status_code == 200:
                    data = resp.json()
                    self.app.root.after(0, lambda d=data: self.apply_stats(d))
                elif resp.status_code in (401, 403):
                    self.app.root.after(0, lambda: self.connection_var.set("Session expired"))
                else:
                    self.app.root.after(0, lambda: self.last_refresh_var.set("Could not refresh stats"))
            except requests.exceptions.RequestException:
                self.app.root.after(0, lambda: self.last_refresh_var.set("Stats unavailable (offline)"))

        threading.Thread(target=request, daemon=True).start()

    def refresh_connection(self) -> None:
        def request():
            try:
                resp = requests.get(f"{SERVER_URL}/auth/me", headers=self.app.auth_headers(), timeout=10)
                if resp.status_code == 200:
                    data = resp.json()
                    self.app.root.after(0, lambda payload=data: self._set_connection(True, payload))
                else:
                    self.app.root.after(0, lambda: self._set_connection(False))
            except requests.exceptions.RequestException:
                self.app.root.after(0, lambda: self._set_connection(False))

        threading.Thread(target=request, daemon=True).start()

    def _set_connection(self, ok: bool, user_payload: dict | None = None) -> None:
        self._connection_ok = ok
        if ok:
            self.connection_var.set("● Server connected")
            if user_payload and "credits" in user_payload:
                self.app.set_credits(user_payload["credits"])
        else:
            self.connection_var.set("● Server offline")

    def _schedule_connection_poll(self) -> None:
        self.refresh_connection()
        self.app.refresh_billing()
        self.app.root.after(30000, self._schedule_connection_poll)

    def _schedule_stats_poll(self) -> None:
        if not self.app.is_running:
            self.refresh_stats()
        self.app.root.after(45000, self._schedule_stats_poll)

    def on_job_started(self) -> None:
        self.job_started_at = datetime.now()
        self.set_run_status("running")
        self.update_progress(0, 0, status="running", stage="Initializing run")
        self.show_section("overview")

    def on_job_finished(self, status: str) -> None:
        self.job_started_at = None
        self.set_run_status(status)
        self.refresh_stats()

    def ingest_logs(self, logs: list[str], status: str, processed: int, total: int) -> None:
        stage = "Processing items"
        for line in reversed(logs):
            if "Progress:" in line:
                match = re.search(r"Progress:\s*(\d+)\/(\d+)", line)
                if match:
                    processed = int(match.group(1))
                    total = int(match.group(2))
                break
            if "initialized" in line.lower():
                stage = "Run initialized"
            if "Stop signal" in line:
                stage = "Stopping run"

        if status in ("completed", "stopped"):
            stage = "Run finished"

        self.update_progress(processed, total, status=status if status == "running" else status, stage=stage)

        if hasattr(self, "activity_tree"):
            self.activity_tree.delete(*self.activity_tree.get_children())
        for line in logs[-120:]:
            self.append_activity(line)
