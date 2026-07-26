from __future__ import annotations

import ctypes
import logging
import math
import queue
import time
import tkinter as tk
from typing import Any

LOGGER = logging.getLogger(__name__)
TRANSPARENT = "#010101"


class CapsuleOverlay:
    def __init__(self, position: str = "bottom-center") -> None:
        self.position = position
        self.events: queue.Queue[tuple[str, dict[str, Any]]] = queue.Queue()
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.configure(bg=TRANSPARENT)
        try:
            self.root.wm_attributes("-transparentcolor", TRANSPARENT)
        except tk.TclError:
            self.root.attributes("-alpha", 0.98)
        self.width = 690
        self.height = 126
        self.canvas = tk.Canvas(
            self.root,
            width=self.width,
            height=self.height,
            bg=TRANSPARENT,
            highlightthickness=0,
        )
        self.canvas.pack()
        self.visible = False
        self._level_value = 0.0
        self._progress_value: float | None = None
        self._indeterminate = False
        self._spinner_phase = 0.0
        self._last_state = "idle"
        self._draw_base()
        self._apply_no_activate()
        self.root.after(35, self._pump)
        self.root.after(45, self._animate)

    def _rounded_rect(self, x1, y1, x2, y2, radius, **kwargs):
        points = [
            x1 + radius,
            y1,
            x2 - radius,
            y1,
            x2,
            y1,
            x2,
            y1 + radius,
            x2,
            y2 - radius,
            x2,
            y2,
            x2 - radius,
            y2,
            x1 + radius,
            y2,
            x1,
            y2,
            x1,
            y2 - radius,
            x1,
            y1 + radius,
            x1,
            y1,
        ]
        return self.canvas.create_polygon(
            points, smooth=True, splinesteps=28, **kwargs
        )

    def _draw_base(self) -> None:
        self.canvas.delete("all")
        self._rounded_rect(
            6,
            6,
            self.width - 6,
            self.height - 6,
            54,
            fill="#090f1c",
            outline="#2a3550",
            width=2,
            tags="shell",
        )
        self.canvas.create_oval(
            22,
            24,
            86,
            88,
            fill="#6d5dfc",
            outline="#9b90ff",
            width=2,
            tags="orb",
        )
        self.canvas.create_arc(
            16,
            18,
            92,
            94,
            start=30,
            extent=255,
            style=tk.ARC,
            outline="#cabfff",
            width=2,
            tags="spinner",
            state="hidden",
        )
        self.canvas.create_text(
            54,
            56,
            text="F",
            fill="white",
            font=("Segoe UI Variable Display", 20, "bold"),
        )
        self.canvas.create_text(
            108,
            39,
            text="Feria Dictation",
            fill="#f7f8ff",
            font=("Segoe UI Variable Display", 14, "bold"),
            anchor="w",
        )
        self.canvas.create_text(
            108,
            65,
            text="Preparado",
            fill="#9aa6bd",
            font=("Segoe UI", 10),
            anchor="w",
            tags="status",
        )
        self.canvas.create_text(
            108,
            84,
            text="Mantén F8 para hablar",
            fill="#58647a",
            font=("Segoe UI", 8),
            anchor="w",
            tags="detail",
        )
        self.bar_ids = []
        base_x = 475
        for index in range(20):
            x = base_x + index * 7
            height = 7 + (index % 4) * 2
            self.bar_ids.append(
                self.canvas.create_line(
                    x,
                    56 - height / 2,
                    x,
                    56 + height / 2,
                    fill="#59657e",
                    width=4,
                    capstyle=tk.ROUND,
                )
            )
        self.canvas.create_text(
            655,
            56,
            text="F8",
            fill="#dce2f0",
            font=("Consolas", 11, "bold"),
            anchor="e",
            tags="hotkey",
        )
        self._rounded_rect(
            108,
            101,
            656,
            107,
            3,
            fill="#1c2638",
            outline="",
            tags="progress_bg",
        )
        self._rounded_rect(
            108,
            101,
            108,
            107,
            3,
            fill="#8d7cff",
            outline="",
            tags="progress_fill",
        )

    def _apply_no_activate(self) -> None:
        if not hasattr(ctypes, "windll"):
            return
        try:
            hwnd = self.root.winfo_id()
            GWL_EXSTYLE = -20
            WS_EX_TOOLWINDOW = 0x00000080
            WS_EX_NOACTIVATE = 0x08000000
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(
                hwnd, GWL_EXSTYLE, style | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE
            )
        except Exception:
            LOGGER.exception("No se pudo aplicar WS_EX_NOACTIVATE al overlay")

    def _place(self) -> None:
        self.root.update_idletasks()
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        if self.position == "top-center":
            x = (screen_w - self.width) // 2
            y = 30
        elif self.position == "bottom-right":
            x = screen_w - self.width - 28
            y = screen_h - self.height - 72
        else:
            x = (screen_w - self.width) // 2
            y = screen_h - self.height - 72
        self.root.geometry(f"{self.width}x{self.height}+{x}+{y}")

    def post(self, event: str, **payload) -> None:
        self.events.put((event, payload))

    def _pump(self) -> None:
        try:
            while True:
                event, payload = self.events.get_nowait()
                if event == "show":
                    self._show(payload)
                elif event == "hide":
                    self._hide()
                elif event == "status":
                    self._status(payload)
                elif event == "level":
                    self._level_value = max(
                        0.0, min(float(payload.get("value", 0.0)), 1.0)
                    )
                elif event == "progress":
                    self._progress(payload)
                elif event == "hotkey":
                    self.canvas.itemconfigure(
                        "hotkey", text=str(payload.get("value", "")).upper()
                    )
                elif event == "position":
                    self.position = payload.get("value", self.position)
                    self._place()
        except queue.Empty:
            pass
        self.root.after(35, self._pump)

    def _show(self, payload: dict[str, Any]) -> None:
        self._place()
        self._status(payload)
        self.root.deiconify()
        self.root.lift()
        self.visible = True

    def _hide(self) -> None:
        self.root.withdraw()
        self.visible = False
        self._progress_value = None
        self._indeterminate = False

    def _status(self, payload: dict[str, Any]) -> None:
        text = str(payload.get("text", "Preparado"))
        detail = str(payload.get("detail", ""))
        state = str(payload.get("state", "idle"))
        self._last_state = state
        colors = {
            "idle": "#9aa6bd",
            "recording": "#ff7d90",
            "processing": "#ffc36e",
            "loading": "#b7aaff",
            "done": "#62e5b8",
            "error": "#ff7d90",
        }
        orb = {
            "idle": "#6d5dfc",
            "recording": "#fa5269",
            "processing": "#f2a84b",
            "loading": "#7d68ff",
            "done": "#33c995",
            "error": "#fa5269",
        }
        self.canvas.itemconfigure("status", text=text, fill=colors.get(state, "#9aa6bd"))
        self.canvas.itemconfigure("detail", text=detail, fill="#66738a")
        self.canvas.itemconfigure("orb", fill=orb.get(state, "#6d5dfc"))
        self.canvas.itemconfigure(
            "spinner", state="normal" if state in {"loading", "processing"} else "hidden"
        )

    def _progress(self, payload: dict[str, Any]) -> None:
        value = payload.get("value")
        self._indeterminate = bool(payload.get("indeterminate", value is None))
        if value is None:
            self._progress_value = None
        else:
            self._progress_value = max(0.0, min(float(value), 100.0))

    def _animate(self) -> None:
        self._spinner_phase = (self._spinner_phase + 14) % 360
        self.canvas.itemconfigure("spinner", start=self._spinner_phase)
        level = self._level_value
        now = time.monotonic()
        for index, item in enumerate(self.bar_ids):
            phase = abs((index % 10) - 4.5) / 4.5
            breathing = 0.0
            if self._last_state in {"loading", "processing"}:
                breathing = (math.sin(now * 7 + index * 0.55) + 1) * 0.12
            height = 7 + ((level + breathing) * 48 * (1 - phase * 0.42))
            x = 475 + index * 7
            self.canvas.coords(item, x, 56 - height / 2, x, 56 + height / 2)
            active = level > 0.035 or self._last_state in {"loading", "processing"}
            self.canvas.itemconfigure(item, fill="#9b8cff" if active else "#59657e")

        start_x = 108
        end_x = 656
        width = end_x - start_x
        if self._indeterminate:
            segment = width * 0.24
            travel = width + segment
            offset = ((now * 175) % travel) - segment
            x1 = max(start_x, start_x + offset)
            x2 = min(end_x, start_x + offset + segment)
        elif self._progress_value is not None:
            x1 = start_x
            x2 = start_x + width * (self._progress_value / 100.0)
        else:
            x1 = start_x
            x2 = start_x
        if x2 <= x1:
            self.canvas.coords("progress_fill", start_x, 101, start_x, 107)
        else:
            self.canvas.coords("progress_fill", x1, 101, x2, 107)
        self.root.after(45, self._animate)

    def run(self) -> None:
        self.root.mainloop()
