import json
import sys
import time
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Optional

try:
    import winsound
except ImportError:
    winsound = None


CONFIG_PATH = Path(__file__).with_name("config.json")
DEFAULT_CONFIG = {
    "small_interval_minutes": 20,
    "big_interval_minutes": 120,
    "forced_break_seconds": 60,
}


def draw_rounded_rect(canvas: tk.Canvas, x1: int, y1: int, x2: int, y2: int, radius: int, color: str) -> None:
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
    canvas.create_polygon(points, smooth=True, splinesteps=32, fill=color, outline=color)


class RoundedCard(tk.Frame):
    def __init__(self, parent: tk.Widget, bg: str, radius: int = 16, pad: int = 20):
        super().__init__(parent, bg=parent.cget("bg"))
        self.bg_color = bg
        self.radius = radius
        self.pad = pad

        self.canvas = tk.Canvas(self, bg=parent.cget("bg"), highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)

        self.inner = tk.Frame(self.canvas, bg=bg)
        self.inner_win = self.canvas.create_window(0, 0, anchor="nw", window=self.inner)

        self.canvas.bind("<Configure>", self._on_resize)

    def _on_resize(self, event: tk.Event) -> None:
        self.canvas.delete("shape")
        draw_rounded_rect(self.canvas, 0, 0, event.width, event.height, self.radius, self.bg_color)
        self.canvas.itemconfigure(self.inner_win, width=max(1, event.width - self.pad * 2), height=max(1, event.height - self.pad * 2))
        self.canvas.coords(self.inner_win, self.pad, self.pad)


class RestReminderApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.enable_hidpi_support()
        self.root.title("Rest Reminder")
        self.root.geometry("1260x800")
        self.root.minsize(1120, 720)
        self.root.configure(bg="#dde2e8")
        self.root.overrideredirect(True)
        self.root.option_add("*Font", "{Microsoft YaHei UI} 12")

        self.config = self.load_config()

        self.running = False
        self.small_interval_seconds = 0
        self.big_interval_seconds = 0
        self.last_small_ts = time.time()
        self.last_big_ts = time.time()
        self.after_id: Optional[str] = None
        self.big_break_window: Optional[tk.Toplevel] = None
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.drag_win_x = 0
        self.drag_win_y = 0

        self.small_var = tk.StringVar(value=str(self.config["small_interval_minutes"]))
        self.big_var = tk.StringVar(value=str(self.config["big_interval_minutes"]))
        self.break_var = tk.StringVar(value=str(self.config["forced_break_seconds"]))
        self.status_var = tk.StringVar(value="未启动")
        self.next_small_var = tk.StringVar(value="--:--")
        self.next_big_var = tk.StringVar(value="--:--")

        self.style = ttk.Style()
        self.setup_styles()
        self.build_ui()
        self.center_window()
        self.root.bind("<Map>", self.restore_custom_window)

    def enable_hidpi_support(self) -> None:
        if sys.platform != "win32":
            return
        try:
            from ctypes import windll

            windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            try:
                from ctypes import windll

                windll.user32.SetProcessDPIAware()
            except Exception:
                pass

    def center_window(self) -> None:
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        x = max(0, (self.root.winfo_screenwidth() - width) // 2)
        y = max(0, (self.root.winfo_screenheight() - height) // 2)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def start_drag(self, event: tk.Event) -> None:
        self.drag_start_x = event.x_root
        self.drag_start_y = event.y_root
        self.drag_win_x = self.root.winfo_x()
        self.drag_win_y = self.root.winfo_y()

    def do_drag(self, event: tk.Event) -> None:
        new_x = self.drag_win_x + (event.x_root - self.drag_start_x)
        new_y = self.drag_win_y + (event.y_root - self.drag_start_y)
        self.root.geometry(f"+{new_x}+{new_y}")

    def minimize_custom_window(self) -> None:
        self.root.overrideredirect(False)
        self.root.iconify()

    def restore_custom_window(self, _event: tk.Event) -> None:
        self.root.overrideredirect(True)

    def setup_styles(self) -> None:
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass

        self.style.configure(
            "Primary.TButton",
            foreground="#ffffff",
            background="#0b5cad",
            borderwidth=0,
            padding=(18, 12),
            font=("Microsoft YaHei UI", 12, "bold"),
        )
        self.style.map(
            "Primary.TButton",
            background=[("active", "#0f6bc9"), ("pressed", "#084787")],
        )

        self.style.configure(
            "Secondary.TButton",
            foreground="#263238",
            background="#e7eaed",
            borderwidth=0,
            padding=(18, 12),
            font=("Microsoft YaHei UI", 12),
        )
        self.style.map(
            "Secondary.TButton",
            background=[("active", "#d8dee4"), ("pressed", "#c7d0d9")],
        )

        self.style.configure(
            "Ghost.TButton",
            foreground="#0e639c",
            background="#f0f4f8",
            borderwidth=0,
            padding=(18, 12),
            font=("Microsoft YaHei UI", 12),
        )
        self.style.map(
            "Ghost.TButton",
            background=[("active", "#e5edf7"), ("pressed", "#d5e2f0")],
        )

    def build_ui(self) -> None:
        root_wrap = tk.Frame(self.root, bg="#dde2e8", padx=1, pady=1)
        root_wrap.pack(fill="both", expand=True)

        app_surface = tk.Frame(root_wrap, bg="#eef1f5")
        app_surface.pack(fill="both", expand=True)

        title_bar = tk.Frame(app_surface, bg="#e5e9ef", height=44)
        title_bar.pack(fill="x")
        title_bar.pack_propagate(False)

        title_label = tk.Label(
            title_bar,
            text="  Rest Reminder",
            bg="#e5e9ef",
            fg="#1f2328",
            font=("Segoe UI", 11, "bold"),
            anchor="w",
        )
        title_label.pack(side="left", fill="y")

        title_btns = tk.Frame(title_bar, bg="#e5e9ef")
        title_btns.pack(side="right", fill="y")

        min_btn = tk.Button(
            title_btns,
            text="-",
            command=self.minimize_custom_window,
            bg="#e5e9ef",
            fg="#444",
            activebackground="#d8dee6",
            activeforeground="#111",
            relief="flat",
            borderwidth=0,
            width=4,
            font=("Segoe UI", 11, "bold"),
        )
        min_btn.pack(side="left", fill="y")

        close_btn = tk.Button(
            title_btns,
            text="✕",
            command=self.root.destroy,
            bg="#e5e9ef",
            fg="#444",
            activebackground="#c42b1c",
            activeforeground="#ffffff",
            relief="flat",
            borderwidth=0,
            width=4,
            font=("Segoe UI", 10, "bold"),
        )
        close_btn.pack(side="left", fill="y")

        for widget in (title_bar, title_label):
            widget.bind("<ButtonPress-1>", self.start_drag)
            widget.bind("<B1-Motion>", self.do_drag)

        content = tk.Frame(app_surface, bg="#eef1f5", padx=30, pady=26)
        content.pack(fill="both", expand=True)

        header = tk.Frame(content, bg="#eef1f5")
        header.pack(fill="x", pady=(0, 18))

        tk.Label(
            header,
            text="Rest Reminder",
            bg="#eef1f5",
            fg="#1f2328",
            font=("Segoe UI", 34, "bold"),
        ).pack(anchor="w")

        body = tk.Frame(content, bg="#eef1f5")
        body.pack(fill="both", expand=True)

        left = RoundedCard(body, bg="#ffffff", radius=18, pad=22)
        left.pack(side="left", fill="both", expand=True)

        right = RoundedCard(body, bg="#f8fafc", radius=18, pad=22)
        right.pack(side="left", fill="y", padx=(18, 0))

        self.build_setting_row(left.inner, 0, "小提醒间隔（分钟）", self.small_var)
        self.build_setting_row(left.inner, 1, "大提醒间隔（分钟）", self.big_var)
        self.build_setting_row(left.inner, 2, "强制休息时长（秒）", self.break_var)

        btn_row = tk.Frame(left.inner, bg="#ffffff")
        btn_row.grid(row=3, column=0, columnspan=2, sticky="w", pady=(24, 10))

        ttk.Button(btn_row, text="启动提醒", command=self.start, style="Primary.TButton").pack(side="left", padx=(0, 10))
        ttk.Button(btn_row, text="停止提醒", command=self.stop, style="Secondary.TButton").pack(side="left", padx=(0, 10))
        ttk.Button(btn_row, text="立即测试", command=self.test_now, style="Ghost.TButton").pack(side="left")

        status_card = RoundedCard(left.inner, bg="#f6f8fa", radius=14, pad=14)
        status_card.grid(row=4, column=0, columnspan=2, sticky="ew", pady=(14, 0))
        left.inner.grid_columnconfigure(0, weight=1)

        tk.Label(
            status_card.inner,
            textvariable=self.status_var,
            bg="#f6f8fa",
            fg="#1f2328",
            font=("Microsoft YaHei UI", 18, "bold"),
        ).pack(anchor="w")

        self.build_stat_card(right.inner, "下次小提醒", self.next_small_var, "#0969da")
        self.build_stat_card(right.inner, "下次强提醒", self.next_big_var, "#bc4c00")

        tk.Label(
            right.inner,
            text="建议：每次小提醒离屏 20 秒，强提醒时至少站起来活动 1 分钟。",
            justify="left",
            bg="#f8fafc",
            fg="#57606a",
            font=("Microsoft YaHei UI", 12),
            wraplength=300,
        ).pack(anchor="w", pady=(16, 0))

    def build_setting_row(self, parent: tk.Frame, row: int, label: str, variable: tk.StringVar) -> None:
        tk.Label(
            parent,
            text=label,
            fg="#24292f",
            bg="#ffffff",
            font=("Microsoft YaHei UI", 14),
        ).grid(row=row, column=0, sticky="w", pady=9)

        tk.Entry(
            parent,
            textvariable=variable,
            width=9,
            bg="#f6f8fa",
            fg="#1f2328",
            insertbackground="#1f2328",
            relief="flat",
            font=("Segoe UI", 15),
            justify="center",
            highlightthickness=1,
            highlightbackground="#d0d7de",
            highlightcolor="#0969da",
        ).grid(row=row, column=1, sticky="e", pady=9, padx=(14, 0), ipady=8)

    def build_stat_card(self, parent: tk.Frame, title: str, value_var: tk.StringVar, accent: str) -> None:
        card = RoundedCard(parent, bg="#ffffff", radius=14, pad=14)
        card.pack(fill="x", pady=(12, 0))

        tk.Label(
            card.inner,
            text=title,
            bg="#ffffff",
            fg="#57606a",
            font=("Microsoft YaHei UI", 12),
        ).pack(anchor="w")
        tk.Label(
            card.inner,
            textvariable=value_var,
            bg="#ffffff",
            fg=accent,
            font=("Consolas", 34, "bold"),
        ).pack(anchor="w", pady=(4, 0))

    def load_config(self) -> dict:
        if not CONFIG_PATH.exists():
            return DEFAULT_CONFIG.copy()
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            return {
                "small_interval_minutes": int(data.get("small_interval_minutes", 20)),
                "big_interval_minutes": int(data.get("big_interval_minutes", 120)),
                "forced_break_seconds": int(data.get("forced_break_seconds", 60)),
            }
        except Exception:
            return DEFAULT_CONFIG.copy()

    def save_config(self) -> None:
        CONFIG_PATH.write_text(
            json.dumps(
                {
                    "small_interval_minutes": self.small_interval_seconds // 60,
                    "big_interval_minutes": self.big_interval_seconds // 60,
                    "forced_break_seconds": int(self.break_var.get()),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def read_positive_int(self, value: str, field_name: str) -> int:
        try:
            number = int(value)
            if number <= 0:
                raise ValueError
            return number
        except ValueError as exc:
            raise ValueError(f"{field_name} 需要是大于 0 的整数") from exc

    def format_countdown(self, seconds: int) -> str:
        safe = max(0, seconds)
        minutes = safe // 60
        remain = safe % 60
        return f"{minutes:02d}:{remain:02d}"

    def update_dashboard(self, now: Optional[float] = None) -> None:
        if not self.running:
            self.next_small_var.set("--:--")
            self.next_big_var.set("--:--")
            return

        current = time.time() if now is None else now
        small_left = int(self.small_interval_seconds - (current - self.last_small_ts))
        big_left = int(self.big_interval_seconds - (current - self.last_big_ts))
        self.next_small_var.set(self.format_countdown(small_left))
        self.next_big_var.set(self.format_countdown(big_left))

    def beep(self) -> None:
        if winsound is None:
            return
        try:
            winsound.MessageBeep()
        except RuntimeError:
            pass

    def start(self) -> None:
        try:
            small_minutes = self.read_positive_int(self.small_var.get(), "小提醒间隔")
            big_minutes = self.read_positive_int(self.big_var.get(), "大提醒间隔")
            self.read_positive_int(self.break_var.get(), "强制休息时长")
        except ValueError as err:
            messagebox.showerror("参数错误", str(err), parent=self.root)
            return

        if big_minutes <= small_minutes:
            messagebox.showerror("参数错误", "大提醒间隔应大于小提醒间隔", parent=self.root)
            return

        self.small_interval_seconds = small_minutes * 60
        self.big_interval_seconds = big_minutes * 60
        self.last_small_ts = time.time()
        self.last_big_ts = time.time()
        self.running = True
        self.status_var.set("运行中")
        self.update_dashboard()
        self.save_config()

        if self.after_id is not None:
            self.root.after_cancel(self.after_id)
        self.after_id = self.root.after(1000, self.tick)

    def stop(self) -> None:
        self.running = False
        if self.after_id is not None:
            self.root.after_cancel(self.after_id)
            self.after_id = None
        self.status_var.set("已停止")
        self.next_small_var.set("--:--")
        self.next_big_var.set("--:--")

    def tick(self) -> None:
        if not self.running:
            return

        now = time.time()
        self.update_dashboard(now)

        if now - self.last_big_ts >= self.big_interval_seconds:
            self.last_big_ts = now
            self.last_small_ts = now
            self.show_big_reminder()
        elif now - self.last_small_ts >= self.small_interval_seconds:
            self.last_small_ts = now
            self.show_small_reminder()

        self.after_id = self.root.after(1000, self.tick)

    def show_small_reminder(self) -> None:
        self.beep()
        messagebox.showinfo(
            "眼睛休息提醒",
            "看看远处 20 秒，活动肩颈，喝口水。",
            parent=self.root,
        )

    def show_small_test_reminder(self) -> None:
        self.beep()
        popup = tk.Toplevel(self.root)
        popup.title("眼睛休息提醒")
        popup.attributes("-topmost", True)
        popup.configure(bg="#eef1f5")
        popup.resizable(False, False)
        popup.transient(self.root)

        width = 520
        height = 250
        x = (popup.winfo_screenwidth() - width) // 2 - 200
        y = (popup.winfo_screenheight() - height) // 2 - 120
        popup.geometry(f"{width}x{height}+{x}+{y}")

        card = RoundedCard(popup, bg="#ffffff", radius=16, pad=18)
        card.pack(fill="both", expand=True, padx=14, pady=14)

        tk.Label(
            card.inner,
            text="眼睛休息提醒",
            bg="#ffffff",
            fg="#1f2328",
            font=("Microsoft YaHei UI", 20, "bold"),
        ).pack(anchor="w")
        tk.Label(
            card.inner,
            text="看看远处 20 秒，活动肩颈，喝口水。",
            bg="#ffffff",
            fg="#57606a",
            font=("Microsoft YaHei UI", 13),
            justify="left",
        ).pack(anchor="w", pady=(10, 0))

    def show_big_reminder(self) -> None:
        if self.big_break_window is not None and self.big_break_window.winfo_exists():
            return

        self.beep()
        forced_seconds = self.read_positive_int(self.break_var.get(), "强制休息时长")

        win = tk.Toplevel(self.root)
        win.title("强制休息")
        win.attributes("-topmost", True)
        win.configure(bg="#eef1f5")
        win.resizable(False, False)
        win.transient(self.root)

        self.big_break_window = win
        win.bind("<Destroy>", lambda _e: self._clear_big_window_reference())

        width = 880
        height = 530
        x = (win.winfo_screenwidth() - width) // 2
        y = (win.winfo_screenheight() - height) // 2
        win.geometry(f"{width}x{height}+{x}+{y}")
        win.grab_set()

        box = RoundedCard(win, bg="#ffffff", radius=20, pad=28)
        box.pack(fill="both", expand=True, padx=20, pady=20)

        countdown = tk.StringVar(value=self.format_countdown(forced_seconds))

        tk.Label(
            box.inner,
            text="休息一下，重置状态",
            bg="#ffffff",
            fg="#1f2328",
            font=("Segoe UI", 34, "bold"),
        ).pack(pady=(10, 10))
        tk.Label(
            box.inner,
            text="请离开屏幕，走动、拉伸、补水",
            bg="#ffffff",
            fg="#57606a",
            font=("Microsoft YaHei UI", 18),
        ).pack()
        tk.Label(
            box.inner,
            textvariable=countdown,
            bg="#ffffff",
            fg="#0969da",
            font=("Consolas", 78, "bold"),
        ).pack(pady=20)
        tk.Label(
            box.inner,
            text="可直接点击窗口右上角关闭。",
            bg="#ffffff",
            fg="#6e7781",
            font=("Microsoft YaHei UI", 13),
        ).pack()

        def step(remain: int) -> None:
            if not win.winfo_exists():
                return
            countdown.set(self.format_countdown(remain))
            if remain <= 0:
                self.beep()
                return
            win.after(1000, lambda: step(remain - 1))

        step(forced_seconds)

    def _clear_big_window_reference(self) -> None:
        self.big_break_window = None

    def test_now(self) -> None:
        self.status_var.set("测试中")
        self.show_small_test_reminder()
        self.show_big_reminder()


def main() -> None:
    root = tk.Tk()
    app = RestReminderApp(root)
    root.mainloop()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
