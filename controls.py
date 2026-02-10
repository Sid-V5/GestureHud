"""Mouse control via Win32 SendInput.

Uses ctypes to inject input events at the lowest OS level,
avoiding focus-stealing side effects from higher-level libraries.
"""
import time
import ctypes
from ctypes import wintypes

MOUSEEVENTF_MOVE = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004
MOUSEEVENTF_RIGHTDOWN = 0x0008
MOUSEEVENTF_RIGHTUP = 0x0010
MOUSEEVENTF_WHEEL = 0x0800
MOUSEEVENTF_ABSOLUTE = 0x8000
INPUT_MOUSE = 0

user32 = ctypes.windll.user32


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]


class INPUT(ctypes.Structure):
    class _INPUT(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT)]
    _fields_ = [
        ("type", wintypes.DWORD),
        ("_input", _INPUT),
    ]


def _send(flags, x=0, y=0, data=0):
    mi = MOUSEINPUT(
        dx=x, dy=y, mouseData=data, dwFlags=flags, time=0,
        dwExtraInfo=ctypes.pointer(ctypes.c_ulong(0)))
    inp = INPUT(type=INPUT_MOUSE)
    inp._input.mi = mi
    user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))


class MouseController:
    """Translates normalized hand coordinates into system mouse events."""

    def __init__(self, screen_w, screen_h):
        self.screen_w = screen_w
        self.screen_h = screen_h
        self._last_left = 0.0
        self._last_right = 0.0
        self._click_cooldown = 0.4
        self._dragging = False
        self._last_scroll_y = None

    def move(self, nx, ny):
        x = max(0, min(int(nx * self.screen_w), self.screen_w - 1))
        y = max(0, min(int(ny * self.screen_h), self.screen_h - 1))
        user32.SetCursorPos(x, y)

    def left_click(self):
        now = time.time()
        if now - self._last_left > self._click_cooldown:
            _send(MOUSEEVENTF_LEFTDOWN)
            _send(MOUSEEVENTF_LEFTUP)
            self._last_left = now
            return True
        return False

    def right_click(self):
        now = time.time()
        if now - self._last_right > self._click_cooldown:
            _send(MOUSEEVENTF_RIGHTDOWN)
            _send(MOUSEEVENTF_RIGHTUP)
            self._last_right = now
            return True
        return False

    def start_drag(self):
        if not self._dragging:
            _send(MOUSEEVENTF_LEFTDOWN)
            self._dragging = True

    def stop_drag(self):
        if self._dragging:
            _send(MOUSEEVENTF_LEFTUP)
            self._dragging = False

    @property
    def is_dragging(self):
        return self._dragging

    def scroll(self, ny, sensitivity=15.0):
        if self._last_scroll_y is None:
            self._last_scroll_y = ny
            return
        delta = (self._last_scroll_y - ny) * sensitivity
        self._last_scroll_y = ny
        if abs(delta) > 0.3:
            _send(MOUSEEVENTF_WHEEL, data=int(delta * 120))

    def reset_scroll(self):
        self._last_scroll_y = None
