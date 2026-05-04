import json
import sys
import time
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Callable, Optional

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
    def __init__(self, parent: tk.Widget, bg: str, radius: int = 16, pad: int = 20, fixed_height: Optional[int] = None):
        super().__init__(parent, bg=parent.cget("bg"))
        self.bg_color = bg
        self.radius = radius
        self.pad = pad

        self.canvas = tk.Canvas(self, bg=parent.cget("bg"), highlightthickness=0, bd=0)
        if fixed_height is not None:
            self.canvas.configure(height=max(10, fixed_height))
        self.canvas.pack(fill="both", expand=True)

        self.inner = tk.Frame(self.canvas, bg=bg)
        self.inner_win = self.canvas.create_window(0, 0, anchor="nw", window=self.inner)

        self.canvas.bind("<Configure>", self._on_resize)

    def _on_resize(self, event: tk.Event) -> None:
        self.canvas.delete("shape")
        draw_rounded_rect(self.canvas, 0, 0, event.width, event.height, self.radius, self.bg_color)
        self.canvas.itemconfigure(self.inner_win, width=max(1, event.width - self.pad * 2), height=max(1, event.height - self.pad * 2))
        self.canvas.coords(self.inner_win, self.pad, self.pad)


class TitleBarButton(tk.Canvas):
    def __init__(self, parent: tk.Widget, kind: str, command: Callable[[], None]):
        super().__init__(
            parent,
            width=42,
            height=28,
            bg=parent.cget("bg"),
            bd=0,
            highlightthickness=0,
            cursor="hand2",
            takefocus=0,
        )
        self.kind = kind
        self.command = command
        self.hovered = False
        self.pressed = False

        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.redraw()

    def palette(self) -> tuple[str, str, str]:
        if self.kind == "close":
            if self.pressed:
                return "#d1242f", "#d1242f", "#ffffff"
            if self.hovered:
                return "#ea4a5a", "#ea4a5a", "#ffffff"
            return "#f8d6da", "#f3c2c8", "#a40e26"

        if self.pressed:
            return "#dce2ea", "#c9d1db", "#2f363d"
        if self.hovered:
            return "#e8edf3", "#d4dbe4", "#2f363d"
        return "#f4f6f9", "#dde3ea", "#57606a"

    def redraw(self) -> None:
        bg, border, icon = self.palette()
        self.delete("all")
        self.create_rectangle(4, 4, 38, 24, fill=bg, outline=border, width=1)
        if self.kind == "close":
            self.create_line(17, 11, 25, 19, fill=icon, width=2, capstyle=tk.ROUND)
            self.create_line(25, 11, 17, 19, fill=icon, width=2, capstyle=tk.ROUND)
        else:
            self.create_line(16, 17, 26, 17, fill=icon, width=2, capstyle=tk.ROUND)

    def _on_enter(self, _event: tk.Event) -> None:
        self.hovered = True
        self.redraw()

    def _on_leave(self, _event: tk.Event) -> None:
        self.hovered = False
        self.pressed = False
        self.redraw()

    def _on_press(self, _event: tk.Event) -> None:
        self.pressed = True
        self.redraw()

    def _on_release(self, event: tk.Event) -> None:
        was_pressed = self.pressed
        self.pressed = False
        self.redraw()
        inside = 0 <= event.x <= self.winfo_width() and 0 <= event.y <= self.winfo_height()
        if was_pressed and inside:
            self.command()


class RestReminderApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.enable_hidpi_support()
        self.root.title("Rest Reminder")
        self.root.minsize(1040, 700)
        startup_w, startup_h = self.pick_startup_size()
        startup_x, startup_y = self.calculate_center_position(startup_w, startup_h)
        self.root.geometry(f"{startup_w}x{startup_h}+{startup_x}+{startup_y}")
        self.root.configure(bg="#dde2e8")
        self.use_borderless_window = False
        self.root.option_add("*Font", "{Microsoft YaHei UI} 12")

        self.config = self.load_config()

        self.running = False
        self.small_interval_seconds = 0
        self.big_interval_seconds = 0
        self.last_small_ts = time.time()
        self.last_big_ts = time.time()
        self.after_id: Optional[str] = None
        self.stopwatch_after_id: Optional[str] = None
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
        self.stopwatch_var = tk.StringVar(value="00:00:00")
        self.stopwatch_running = False
        self.stopwatch_elapsed = 0.0
        self.stopwatch_started_ts = 0.0
        self.stopwatch_start_btn: Optional[tk.Button] = None
        self.stopwatch_pause_btn: Optional[tk.Button] = None
        self.did_initial_map_center = False
        self.native_chrome_applied = False
        self.native_style_attempts = 0
        self.icon_photo_ref: Optional[tk.PhotoImage] = None

        self.style = ttk.Style()
        self.setup_styles()
        self.apply_window_icon()
        self.build_ui()
        self.root.after(0, self.finish_startup_window_setup)
        self.root.bind("<Map>", self.restore_custom_window)
        self.root.protocol("WM_DELETE_WINDOW", self.on_root_close)

    def finish_startup_window_setup(self) -> None:
        self.apply_native_window_colors()
        self.center_window()
        self.root.after(30, self.apply_native_window_colors)
        self.root.after(40, self.center_window)

    def get_work_area(self) -> tuple[int, int, int, int]:
        if sys.platform != "win32":
            return (0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight())
        try:
            from ctypes import windll, wintypes

            rect = wintypes.RECT()
            SPI_GETWORKAREA = 0x0030
            ok = windll.user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, rect, 0)
            if ok and rect.right > rect.left and rect.bottom > rect.top:
                return (rect.left, rect.top, rect.right, rect.bottom)
        except Exception:
            pass
        return (0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight())

    def pick_startup_size(self) -> tuple[int, int]:
        left, top, right, bottom = self.get_work_area()
        available_w = max(1, right - left)
        available_h = max(1, bottom - top)

        target_w = min(1480, int(available_w * 0.93))
        target_h = min(940, int(available_h * 0.93))
        startup_w = max(1040, target_w)
        startup_h = max(700, target_h)
        return (min(startup_w, available_w), min(startup_h, available_h))

    def calculate_center_position(self, width: int, height: int) -> tuple[int, int]:
        left, top, right, bottom = self.get_work_area()
        available_w = max(1, right - left)
        available_h = max(1, bottom - top)
        x = left + max(0, (available_w - width) // 2)
        y = top + max(0, (available_h - height) // 2)
        return (x, y)

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
        left, top, right, bottom = self.get_work_area()
        available_w = max(1, right - left)
        available_h = max(1, bottom - top)
        min_w, min_h = self.root.minsize()

        width = max(self.root.winfo_width(), self.root.winfo_reqwidth(), min_w)
        height = max(self.root.winfo_height(), self.root.winfo_reqheight(), min_h)
        width = min(width, available_w)
        height = min(height, available_h)

        x, y = self.calculate_center_position(width, height)
        self.root.geometry(f"{width}x{height}+{x}+{y}")

    def get_window_hwnd(self) -> int:
        hwnd = self.root.winfo_id()
        if sys.platform != "win32":
            return hwnd
        try:
            from ctypes import windll

            GA_ROOT = 2
            root_hwnd = windll.user32.GetAncestor(hwnd, GA_ROOT)
            if root_hwnd:
                return root_hwnd
            parent_hwnd = windll.user32.GetParent(hwnd)
            if parent_hwnd:
                return parent_hwnd
        except Exception:
            pass
        return hwnd

    def start_drag(self, event: tk.Event) -> None:
        if self.use_borderless_window and sys.platform == "win32":
            try:
                from ctypes import windll

                WM_NCLBUTTONDOWN = 0x00A1
                HTCAPTION = 2
                windll.user32.ReleaseCapture()
                windll.user32.SendMessageW(self.get_window_hwnd(), WM_NCLBUTTONDOWN, HTCAPTION, 0)
                return
            except Exception:
                pass
        self.drag_start_x = event.x_root
        self.drag_start_y = event.y_root
        self.drag_win_x = self.root.winfo_x()
        self.drag_win_y = self.root.winfo_y()

    def do_drag(self, event: tk.Event) -> None:
        if self.use_borderless_window and sys.platform == "win32":
            return
        new_x = self.drag_win_x + (event.x_root - self.drag_start_x)
        new_y = self.drag_win_y + (event.y_root - self.drag_start_y)
        self.root.geometry(f"+{new_x}+{new_y}")

    def minimize_custom_window(self) -> None:
        if self.use_borderless_window:
            try:
                from ctypes import windll

                SW_MINIMIZE = 6
                windll.user32.ShowWindow(self.get_window_hwnd(), SW_MINIMIZE)
            except Exception:
                self.root.iconify()
            return
        self.root.iconify()

    def restore_custom_window(self, _event: tk.Event) -> None:
        if self.root.state() != "normal":
            return
        self.apply_native_window_colors()
        if not self.did_initial_map_center:
            self.did_initial_map_center = True
            self.root.after(20, self.center_window)

    def apply_native_window_colors(self) -> None:
        if sys.platform != "win32":
            return
        try:
            from ctypes import byref, c_uint, windll

            hwnd = self.get_window_hwnd()
            DWMWA_BORDER_COLOR = 34
            DWMWA_CAPTION_COLOR = 35
            DWMWA_TEXT_COLOR = 36

            def rgb_to_colorref(hex_color: str) -> int:
                rgb = hex_color.lstrip("#")
                r = int(rgb[0:2], 16)
                g = int(rgb[2:4], 16)
                b = int(rgb[4:6], 16)
                return r | (g << 8) | (b << 16)

            border = c_uint(rgb_to_colorref("#dde2e8"))
            caption = c_uint(rgb_to_colorref("#dde2e8"))
            text = c_uint(rgb_to_colorref("#1f2328"))

            windll.dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_BORDER_COLOR, byref(border), 4)
            windll.dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_CAPTION_COLOR, byref(caption), 4)
            windll.dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_TEXT_COLOR, byref(text), 4)
        except Exception:
            pass

    def ensure_native_borderless_style(self) -> None:
        self.apply_native_borderless_style()
        if not self.use_borderless_window or self.native_chrome_applied:
            return
        if self.native_style_attempts >= 8:
            return
        self.native_style_attempts += 1
        self.root.after(40, self.ensure_native_borderless_style)

    def apply_native_borderless_style(self) -> None:
        if sys.platform != "win32" or not self.use_borderless_window:
            return
        try:
            from ctypes import byref, c_int, windll

            hwnd = self.get_window_hwnd()
            GWL_STYLE = -16
            GWL_EXSTYLE = -20
            WS_OVERLAPPEDWINDOW = 0x00CF0000
            WS_POPUP = 0x80000000
            WS_MINIMIZEBOX = 0x00020000
            WS_MAXIMIZEBOX = 0x00010000
            WS_SYSMENU = 0x00080000
            WS_VISIBLE = 0x10000000
            WS_EX_WINDOWEDGE = 0x00000100
            WS_EX_CLIENTEDGE = 0x00000200
            WS_EX_DLGMODALFRAME = 0x00000001
            WS_EX_STATICEDGE = 0x00020000
            SWP_NOSIZE = 0x0001
            SWP_NOMOVE = 0x0002
            SWP_NOZORDER = 0x0004
            SWP_FRAMECHANGED = 0x0020
            SWP_NOOWNERZORDER = 0x0200
            DWMWA_NCRENDERING_POLICY = 2
            DWMNCRP_DISABLED = 1

            style = windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
            ex_style = windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            new_style = (style & ~WS_OVERLAPPEDWINDOW) | WS_POPUP | WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_SYSMENU | WS_VISIBLE
            new_ex_style = ex_style & ~(WS_EX_WINDOWEDGE | WS_EX_CLIENTEDGE | WS_EX_DLGMODALFRAME | WS_EX_STATICEDGE)
            if new_style != style or new_ex_style != ex_style or not self.native_chrome_applied:
                windll.user32.SetWindowLongW(hwnd, GWL_STYLE, new_style)
                windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_ex_style)
                windll.user32.SetWindowPos(
                    hwnd,
                    0,
                    0,
                    0,
                    0,
                    0,
                    SWP_NOSIZE | SWP_NOMOVE | SWP_NOZORDER | SWP_NOOWNERZORDER | SWP_FRAMECHANGED,
                )
                policy = c_int(DWMNCRP_DISABLED)
                try:
                    windll.dwmapi.DwmSetWindowAttribute(hwnd, DWMWA_NCRENDERING_POLICY, byref(policy), 4)
                except Exception:
                    pass
            current_style = windll.user32.GetWindowLongW(hwnd, GWL_STYLE)
            current_ex_style = windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            chrome_bits = 0x00C00000 | 0x00040000 | 0x00800000 | 0x00400000
            edge_bits = WS_EX_WINDOWEDGE | WS_EX_CLIENTEDGE | WS_EX_DLGMODALFRAME | WS_EX_STATICEDGE
            self.native_chrome_applied = (current_style & chrome_bits) == 0 and (current_ex_style & edge_bits) == 0
        except Exception:
            pass

    def apply_taskbar_style(self) -> None:
        if sys.platform != "win32" or not self.use_borderless_window:
            return
        try:
            from ctypes import windll

            hwnd = self.get_window_hwnd()
            GWL_EXSTYLE = -20
            WS_EX_APPWINDOW = 0x00040000
            WS_EX_TOOLWINDOW = 0x00000080

            ex_style = windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ex_style = (ex_style | WS_EX_APPWINDOW) & ~WS_EX_TOOLWINDOW
            windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style)
        except Exception:
            pass

    def find_icon_source(self) -> Optional[Path]:
        base = Path(__file__).resolve().parent
        candidates = [
            "app.normalized.ico",
            "app.png",
            "icon.png",
            "rest_reminder.png",
            "app.ico",
            "icon.ico",
            "rest_reminder.ico",
        ]
        found: list[Path] = []
        for name in candidates:
            path = base / name
            if path.exists() and path.is_file():
                found.append(path)
        if not found:
            return None
        return max(found, key=lambda p: p.stat().st_mtime)

    def build_normalized_icon(self, source: Path) -> Optional[Path]:
        try:
            from PIL import Image
        except ImportError:
            return source if source.suffix.lower() == ".ico" else None

        try:
            with Image.open(source) as image:
                frame = image.convert("RGBA")
                try:
                    frame_count = image.n_frames
                except (AttributeError, OSError):
                    frame_count = 1

                best_area = frame.width * frame.height
                for index in range(1, frame_count):
                    image.seek(index)
                    candidate = image.convert("RGBA")
                    area = candidate.width * candidate.height
                    if area > best_area:
                        frame = candidate
                        best_area = area

                alpha_bbox = frame.getchannel("A").getbbox()
                if alpha_bbox is not None:
                    frame = frame.crop(alpha_bbox)

                if hasattr(Image, "Resampling"):
                    resample = Image.Resampling.LANCZOS
                else:
                    resample = Image.LANCZOS

                canvas_size = 512
                target_fill = 0.92
                max_side = max(frame.width, frame.height)
                if max_side <= 0:
                    return source if source.suffix.lower() == ".ico" else None
                scale = (canvas_size * target_fill) / max_side
                target_w = max(1, int(round(frame.width * scale)))
                target_h = max(1, int(round(frame.height * scale)))

                resized = frame.resize((target_w, target_h), resample)
                normalized = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
                offset_x = (canvas_size - target_w) // 2
                offset_y = (canvas_size - target_h) // 2
                normalized.paste(resized, (offset_x, offset_y), resized)

                target = source.with_name("app.normalized.ico")
                normalized.save(
                    target,
                    format="ICO",
                    sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)],
                )
                return target
        except OSError:
            return source if source.suffix.lower() == ".ico" else None

    def apply_window_icon(self) -> None:
        source = self.find_icon_source()
        if source is None:
            return

        icon_path = self.build_normalized_icon(source)
        if icon_path is None:
            return

        if icon_path.suffix.lower() == ".ico":
            self.root.iconbitmap(default=str(icon_path))
            return

        self.icon_photo_ref = tk.PhotoImage(file=str(icon_path))
        self.root.iconphoto(True, self.icon_photo_ref)

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

        self.style.configure(
            "MiniPrimary.TButton",
            foreground="#ffffff",
            background="#0b5cad",
            borderwidth=0,
            padding=(14, 8),
            font=("Microsoft YaHei UI", 11, "bold"),
        )
        self.style.map(
            "MiniPrimary.TButton",
            background=[("active", "#0f6bc9"), ("pressed", "#084787")],
        )

        self.style.configure(
            "MiniSecondary.TButton",
            foreground="#263238",
            background="#e7eaed",
            borderwidth=0,
            padding=(14, 8),
            font=("Microsoft YaHei UI", 11),
        )
        self.style.map(
            "MiniSecondary.TButton",
            background=[("active", "#d8dee4"), ("pressed", "#c7d0d9")],
        )

        self.style.configure(
            "MiniGhost.TButton",
            foreground="#0e639c",
            background="#f0f4f8",
            borderwidth=0,
            padding=(14, 8),
            font=("Microsoft YaHei UI", 11),
        )
        self.style.map(
            "MiniGhost.TButton",
            background=[("active", "#e5edf7"), ("pressed", "#d5e2f0")],
        )

    def build_ui(self) -> None:
        root_wrap = tk.Frame(self.root, bg="#dde2e8", padx=0, pady=0)
        root_wrap.pack(fill="both", expand=True)

        app_surface = tk.Frame(root_wrap, bg="#eef1f5")
        app_surface.pack(fill="both", expand=True)

        content = tk.Frame(app_surface, bg="#eef1f5", padx=36, pady=30)
        content.pack(fill="both", expand=True)

        header = tk.Frame(content, bg="#eef1f5")
        header.pack(fill="x", pady=(0, 22))

        tk.Label(
            header,
            text="Rest Reminder",
            bg="#eef1f5",
            fg="#1f2328",
            font=("Segoe UI", 36, "bold"),
        ).pack(anchor="w")

        body = tk.Frame(content, bg="#eef1f5")
        body.pack(fill="both", expand=True)

        left = RoundedCard(body, bg="#ffffff", radius=18, pad=22)
        left.pack(side="left", fill="both", expand=True)

        right = RoundedCard(body, bg="#f8fafc", radius=18, pad=18)
        right.configure(width=430)
        right.pack(side="left", fill="both", padx=(20, 0))

        self.build_setting_row(left.inner, 0, "小提醒间隔（分钟）", self.small_var)
        self.build_setting_row(left.inner, 1, "大提醒间隔（分钟）", self.big_var)
        self.build_setting_row(left.inner, 2, "强制休息时长（秒）", self.break_var)

        btn_row = tk.Frame(left.inner, bg="#ffffff")
        btn_row.grid(row=3, column=0, columnspan=2, sticky="w", pady=(24, 10))

        ttk.Button(btn_row, text="启动提醒", command=self.start, style="Primary.TButton").pack(side="left", padx=(0, 10))
        ttk.Button(btn_row, text="停止提醒", command=self.stop, style="Secondary.TButton").pack(side="left", padx=(0, 10))
        ttk.Button(btn_row, text="立即测试", command=self.test_now, style="Ghost.TButton").pack(side="left")

        status_card = RoundedCard(left.inner, bg="#f6f8fa", radius=14, pad=14, fixed_height=104)
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
        self.build_stat_card(right.inner, "副时钟", self.stopwatch_var, "#1a7f37")

        tk.Label(
            right.inner,
            text="计时控制",
            bg="#f8fafc",
            fg="#57606a",
            font=("Microsoft YaHei UI", 12, "bold"),
        ).pack(anchor="w", pady=(14, 4))

        stopwatch_btn_row = tk.Frame(right.inner, bg="#f8fafc")
        stopwatch_btn_row.pack(anchor="w", pady=(0, 0))
        self.stopwatch_start_btn = tk.Button(
            stopwatch_btn_row,
            text="开启",
            command=self.start_stopwatch,
            bg="#0b5cad",
            fg="#ffffff",
            activebackground="#0f6bc9",
            activeforeground="#ffffff",
            relief="flat",
            borderwidth=0,
            padx=16,
            pady=9,
            font=("Microsoft YaHei UI", 11, "bold"),
            cursor="hand2",
        )
        self.stopwatch_start_btn.pack(side="left", padx=(0, 8))
        self.stopwatch_pause_btn = tk.Button(
            stopwatch_btn_row,
            text="暂停",
            command=self.pause_stopwatch,
            bg="#e7eaed",
            fg="#263238",
            activebackground="#d8dee4",
            activeforeground="#263238",
            relief="flat",
            borderwidth=0,
            padx=16,
            pady=9,
            font=("Microsoft YaHei UI", 11),
            cursor="hand2",
        )
        self.stopwatch_pause_btn.pack(side="left", padx=(0, 8))
        tk.Button(
            stopwatch_btn_row,
            text="清除",
            command=self.clear_stopwatch,
            bg="#f0f4f8",
            fg="#0e639c",
            activebackground="#e5edf7",
            activeforeground="#0e639c",
            relief="flat",
            borderwidth=0,
            padx=16,
            pady=9,
            font=("Microsoft YaHei UI", 11),
            cursor="hand2",
        ).pack(side="left")
        self.refresh_stopwatch_controls()

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
        card = RoundedCard(parent, bg="#ffffff", radius=14, pad=12, fixed_height=132)
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
            font=("Consolas", 32, "bold"),
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

    def format_elapsed(self, seconds: int) -> str:
        safe = max(0, seconds)
        hours = safe // 3600
        minutes = (safe % 3600) // 60
        remain = safe % 60
        return f"{hours:02d}:{minutes:02d}:{remain:02d}"

    def current_stopwatch_seconds(self, now: Optional[float] = None) -> int:
        if not self.stopwatch_running:
            return int(self.stopwatch_elapsed)
        current = time.time() if now is None else now
        return int(self.stopwatch_elapsed + (current - self.stopwatch_started_ts))

    def update_stopwatch(self) -> None:
        self.stopwatch_var.set(self.format_elapsed(self.current_stopwatch_seconds()))
        if self.stopwatch_running:
            self.stopwatch_after_id = self.root.after(200, self.update_stopwatch)
        else:
            self.stopwatch_after_id = None

    def refresh_stopwatch_controls(self) -> None:
        if self.stopwatch_start_btn is None or self.stopwatch_pause_btn is None:
            return
        if self.stopwatch_running:
            self.stopwatch_start_btn.configure(state="disabled", bg="#89afd8", fg="#eaf1f8", cursor="arrow")
            self.stopwatch_pause_btn.configure(state="normal", bg="#e7eaed", fg="#263238", cursor="hand2")
            return
        self.stopwatch_start_btn.configure(state="normal", bg="#0b5cad", fg="#ffffff", cursor="hand2")
        self.stopwatch_pause_btn.configure(state="disabled", bg="#dbe1e8", fg="#7a838b", cursor="arrow")

    def start_stopwatch(self) -> None:
        if self.stopwatch_running:
            return
        self.stopwatch_running = True
        self.stopwatch_started_ts = time.time()
        if self.stopwatch_after_id is not None:
            self.root.after_cancel(self.stopwatch_after_id)
        self.update_stopwatch()
        self.refresh_stopwatch_controls()

    def pause_stopwatch(self) -> None:
        if not self.stopwatch_running:
            return
        now = time.time()
        self.stopwatch_elapsed += now - self.stopwatch_started_ts
        self.stopwatch_running = False
        if self.stopwatch_after_id is not None:
            self.root.after_cancel(self.stopwatch_after_id)
            self.stopwatch_after_id = None
        self.stopwatch_var.set(self.format_elapsed(int(self.stopwatch_elapsed)))
        self.refresh_stopwatch_controls()

    def clear_stopwatch(self) -> None:
        if self.stopwatch_running:
            self.pause_stopwatch()
        self.stopwatch_elapsed = 0.0
        self.stopwatch_started_ts = 0.0
        self.stopwatch_var.set("00:00:00")
        self.refresh_stopwatch_controls()

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

        if self.big_break_window is not None and self.big_break_window.winfo_exists():
            self.after_id = self.root.after(1000, self.tick)
            return

        if now - self.last_big_ts >= self.big_interval_seconds:
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
        win.bind("<Destroy>", self._on_big_window_destroy)
        win.protocol("WM_DELETE_WINDOW", lambda: self.close_big_reminder(win))

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

    def _on_big_window_destroy(self, event: tk.Event) -> None:
        if event.widget is self.big_break_window:
            self.big_break_window = None

    def close_big_reminder(self, win: tk.Toplevel) -> None:
        if not win.winfo_exists():
            return
        win.destroy()
        self._clear_big_window_reference()
        if self.running:
            now = time.time()
            self.last_small_ts = now
            self.last_big_ts = now
            self.update_dashboard(now)

    def on_root_close(self) -> None:
        if self.after_id is not None:
            self.root.after_cancel(self.after_id)
            self.after_id = None
        if self.stopwatch_after_id is not None:
            self.root.after_cancel(self.stopwatch_after_id)
            self.stopwatch_after_id = None
        self.root.destroy()

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
