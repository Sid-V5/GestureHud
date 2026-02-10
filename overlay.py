"""Transparent HUD overlay rendered with Pygame.

Creates a fullscreen borderless window with Win32 click-through transparency
(WS_EX_LAYERED + WS_EX_TRANSPARENT). Draws hand skeleton wireframe, cursor
reticle with rotating arcs, system telemetry bars, and status indicators.
"""
import os
import math
import time
import pygame
import ctypes

# Win32 constants
GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000
WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_NOACTIVATE = 0x08000000
LWA_COLORKEY = 0x00000001
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001
SWP_NOACTIVATE = 0x0010
SWP_SHOWWINDOW = 0x0040
SW_SHOWNOACTIVATE = 4
HWND_TOPMOST = -1

OVERLAY_STYLE = (WS_EX_LAYERED | WS_EX_TRANSPARENT | WS_EX_TOPMOST
                 | WS_EX_TOOLWINDOW | WS_EX_NOACTIVATE)

user32 = ctypes.windll.user32

# Color palette
TKEY = (255, 0, 255)
CYAN = (0, 220, 255)
CYAN_DIM = (0, 80, 110)
CYAN_BRIGHT = (80, 255, 255)
RED = (255, 50, 50)
RED_DIM = (150, 30, 30)
ORANGE = (255, 160, 40)
GREEN = (50, 255, 100)
GREEN_DIM = (20, 120, 50)
YELLOW = (255, 255, 80)

# MediaPipe hand bone connections
_HAND_CONNECTIONS = [
    (0, 1), (1, 2), (2, 3), (3, 4),       # thumb
    (0, 5), (5, 6), (6, 7), (7, 8),       # index
    (0, 9), (9, 10), (10, 11), (11, 12),  # middle
    (0, 13), (13, 14), (14, 15), (15, 16),# ring
    (0, 17), (17, 18), (18, 19), (19, 20),# pinky
    (5, 9), (9, 13), (13, 17),            # palm
]
_FINGERTIPS = {4, 8, 12, 16, 20}


def _setup_window(hwnd, colorkey):
    """Apply Win32 styles to make a Pygame window into a click-through overlay."""
    style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
    user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | OVERLAY_STYLE)
    r, g, b = colorkey
    user32.SetLayeredWindowAttributes(hwnd, r | (g << 8) | (b << 16), 0, LWA_COLORKEY)
    user32.ShowWindow(hwnd, SW_SHOWNOACTIVATE)
    user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                        SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW)


class HUDOverlay:
    def __init__(self, screen_w, screen_h):
        self.W = screen_w
        self.H = screen_h

        os.environ["SDL_VIDEO_WINDOW_POS"] = "0,0"
        pygame.init()
        pygame.font.init()

        self.screen = pygame.display.set_mode((screen_w, screen_h), pygame.NOFRAME)
        pygame.display.set_caption("GestureHUD")
        self._hwnd = pygame.display.get_wm_info()["window"]
        _setup_window(self._hwnd, TKEY)

        self.f12 = pygame.font.SysFont("Consolas", 12)
        self.f14 = pygame.font.SysFont("Consolas", 14)
        self.f18 = pygame.font.SysFont("Consolas", 18)
        self.f24 = pygame.font.SysFont("Consolas", 24)
        self.f32 = pygame.font.SysFont("Consolas", 32, bold=True)
        self.clock = pygame.time.Clock()

        self._t = 0.0
        self._ring_angle = 0.0
        self._click_flash = 0.0
        self._click_color = CYAN
        self._hud_visible = True
        self._scan_offset = 0.0

        self._boot_start = time.time()
        self._boot_done = False
        self._boot_duration = 1.2

    @property
    def hud_visible(self):
        return self._hud_visible

    def toggle_visibility(self):
        self._hud_visible = not self._hud_visible

    def force_topmost(self):
        """Re-apply all overlay window properties to survive focus changes."""
        style = user32.GetWindowLongW(self._hwnd, GWL_EXSTYLE)
        if (style & OVERLAY_STYLE) != OVERLAY_STYLE:
            user32.SetWindowLongW(self._hwnd, GWL_EXSTYLE, style | OVERLAY_STYLE)
            r, g, b = TKEY
            user32.SetLayeredWindowAttributes(
                self._hwnd, r | (g << 8) | (b << 16), 0, LWA_COLORKEY)
        user32.ShowWindow(self._hwnd, SW_SHOWNOACTIVATE)
        user32.SetWindowPos(self._hwnd, HWND_TOPMOST, 0, 0, 0, 0,
                            SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_SHOWWINDOW)

    def handle_events(self):
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                return False
            if ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                return False
        return True

    def begin_frame(self):
        self.screen.fill(TKEY)
        self._t += 0.03
        self._scan_offset = (self._scan_offset + 0.5) % self.H
        if self._click_flash > 0:
            self._click_flash -= 0.08
        self.force_topmost()

    def draw_boot_sequence(self):
        if self._boot_done:
            return True
        progress = min(1.0, (time.time() - self._boot_start) / self._boot_duration)
        cx, cy = self.W // 2, self.H // 2

        title = self.f32.render("GestureHUD", True, CYAN_BRIGHT)
        self.screen.blit(title, (cx - title.get_width() // 2, cy - 60))
        sub = self.f14.render("GESTURE CONTROL INTERFACE", True, CYAN_DIM)
        self.screen.blit(sub, (cx - sub.get_width() // 2, cy - 22))

        bw, bh = 280, 3
        bx, by = cx - bw // 2, cy + 10
        pygame.draw.rect(self.screen, CYAN_DIM, (bx, by, bw, bh), 1)
        fw = int(bw * progress)
        if fw > 0:
            pygame.draw.rect(self.screen, CYAN, (bx, by, fw, bh))
            pygame.draw.rect(self.screen, CYAN_BRIGHT, (bx + fw - 2, by, 2, bh))

        pct = self.f12.render(f"{int(progress * 100)}%", True, CYAN)
        self.screen.blit(pct, (cx - pct.get_width() // 2, by + 10))

        if progress >= 1.0:
            self._boot_done = True
        return self._boot_done

    # -- Cursor --

    def draw_cursor(self, nx, ny, state="idle"):
        if not self._hud_visible:
            return
        x, y = int(nx * self.W), int(ny * self.H)

        if state in ("left_click", "right_click"):
            self._click_flash = 1.0
            self._click_color = RED if state == "left_click" else ORANGE

        if self._click_flash > 0:
            color = ring_color = self._click_color
        elif state == "drag":
            color = ring_color = YELLOW
        elif state == "scroll":
            color = ring_color = GREEN
        else:
            color = ring_color = CYAN

        # Outer rotating arcs
        self._ring_angle += 1.5 if state == "idle" else 6.0
        r_out = 26
        angle = math.radians(self._ring_angle)
        for seg in range(4):
            start = angle + seg * (math.pi / 2)
            pts = [(x + math.cos(start + s / 9 * math.radians(50)) * r_out,
                     y + math.sin(start + s / 9 * math.radians(50)) * r_out)
                    for s in range(10)]
            pygame.draw.lines(self.screen, ring_color, False, pts, 2)

        # Inner counter-rotating arcs
        angle2 = math.radians(-self._ring_angle * 0.7)
        for seg in range(3):
            start = angle2 + seg * (2 * math.pi / 3)
            pts = [(x + math.cos(start + s / 7 * math.radians(40)) * 16,
                     y + math.sin(start + s / 7 * math.radians(40)) * 16)
                    for s in range(8)]
            pygame.draw.lines(self.screen, CYAN_DIM, False, pts, 1)

        # Crosshair ticks
        gap, length = r_out + 5, 10
        for dx, dy in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
            pygame.draw.line(self.screen, ring_color,
                             (x + dx * gap, y + dy * gap),
                             (x + dx * (gap + length), y + dy * (gap + length)), 1)

        # Center dot with pulse
        pulse = 1.0 + 0.3 * math.sin(self._t * 4)
        pygame.draw.circle(self.screen, color, (x, y), max(2, int(3 * pulse)))

        # Click flash ring
        if self._click_flash > 0:
            flash_r = int(r_out + 15 * (1.0 - self._click_flash))
            pygame.draw.circle(self.screen, self._click_color, (x, y), flash_r, 2)

    # -- Hand skeleton --

    def draw_hand_skeleton(self, landmarks):
        if not self._hud_visible or not landmarks or len(landmarks) < 21:
            return
        pts = [(int(x * self.W), int(y * self.H)) for x, y in landmarks]

        for a, b in _HAND_CONNECTIONS:
            pygame.draw.line(self.screen, CYAN_DIM, pts[a], pts[b], 1)

        for i, pt in enumerate(pts):
            if i in _FINGERTIPS:
                pygame.draw.circle(self.screen, CYAN_BRIGHT, pt, 4)
                pygame.draw.circle(self.screen, CYAN, pt, 4, 1)
            elif i == 0:
                pygame.draw.circle(self.screen, CYAN, pt, 3)
            else:
                pygame.draw.circle(self.screen, CYAN_DIM, pt, 2)

        # Pinch proximity line (thumb → index)
        self._draw_pinch_line(landmarks, pts, 4, 8, left=True)
        self._draw_pinch_line(landmarks, pts, 4, 12, left=False)

    def _draw_pinch_line(self, lm, pts, a, b, left=True):
        dx = lm[a][0] - lm[b][0]
        dy = lm[a][1] - lm[b][1]
        dist = math.sqrt(dx * dx + dy * dy)
        if dist < 0.05:
            color = RED if left else ORANGE
        elif dist < 0.10:
            color = ORANGE if left else YELLOW
        else:
            if not left:
                return  # only show right-click line when close
            color = CYAN_DIM
        pygame.draw.line(self.screen, color, pts[a], pts[b], 1)
        pygame.draw.circle(self.screen, color, pts[a], 6, 1)
        pygame.draw.circle(self.screen, color, pts[b], 6, 1)

    # -- HUD elements --

    def draw_corner_brackets(self):
        if not self._hud_visible:
            return
        blen, margin = 40, 15
        for cx, cy, dx, dy in [
            (margin, margin, 1, 1),
            (self.W - margin, margin, -1, 1),
            (margin, self.H - margin, 1, -1),
            (self.W - margin, self.H - margin, -1, -1),
        ]:
            pygame.draw.line(self.screen, CYAN_DIM, (cx, cy), (cx + dx * blen, cy), 1)
            pygame.draw.line(self.screen, CYAN_DIM, (cx, cy), (cx, cy + dy * blen), 1)

    def draw_scan_line(self):
        if not self._hud_visible:
            return
        pygame.draw.line(self.screen, CYAN_DIM, (0, int(self._scan_offset)),
                         (self.W, int(self._scan_offset)), 1)

    def draw_telemetry(self, stats, tracker_fps=0.0, render_fps=0.0):
        if not self._hud_visible:
            return

        # System bars (bottom-left)
        bx, by = 22, self.H - 130
        lbl = self.f12.render("TELEMETRY", True, CYAN_DIM)
        self.screen.blit(lbl, (bx, by - 18))
        pygame.draw.line(self.screen, CYAN_DIM, (bx, by - 3), (bx + 100, by - 3), 1)

        self._draw_bar(bx, by, "CPU", stats.get("cpu", 0))
        self._draw_bar(bx, by + 26, "RAM", stats.get("ram", 0))
        bat = stats.get("battery", 100)
        plugged = stats.get("plugged", False)
        bat_label = "BAT +" if plugged else "BAT"
        self._draw_bar(bx, by + 52, bat_label, bat, invert=True)

        # Clock (top-right)
        ts = self.f24.render(time.strftime("%H:%M:%S"), True, CYAN)
        self.screen.blit(ts, (self.W - ts.get_width() - 22, 18))
        ds = self.f12.render(time.strftime("%d %b %Y").upper(), True, CYAN_DIM)
        self.screen.blit(ds, (self.W - ds.get_width() - 22, 48))
        status = self.f12.render("ONLINE", True, GREEN_DIM)
        self.screen.blit(status, (self.W - status.get_width() - 22, 64))

        # FPS (top-left)
        rc = GREEN if render_fps >= 55 else (YELLOW if render_fps >= 30 else RED)
        tc = GREEN if tracker_fps >= 25 else (YELLOW if tracker_fps >= 15 else RED)
        self.screen.blit(self.f12.render(f"RENDER {render_fps:.0f}", True, rc), (22, 18))
        self.screen.blit(self.f12.render(f"TRACK  {tracker_fps:.0f}", True, tc), (22, 34))

    def draw_gesture_indicator(self, gesture, nx=0.0, ny=0.0):
        if not self._hud_visible or not gesture:
            return
        surf = self.f12.render(gesture, True, CYAN_BRIGHT)
        self.screen.blit(surf, (int(nx * self.W) - surf.get_width() // 2,
                                int(ny * self.H) - 48))

    def draw_hand_status(self, num):
        if not self._hud_visible:
            return
        if num > 0:
            txt = f"TRACKING: {num} HAND{'S' if num != 1 else ''}"
            c = CYAN_DIM
        else:
            txt, c = "NO TARGET", RED_DIM
        self.screen.blit(self.f12.render(txt, True, c), (22, 52))

    def draw_mode_indicator(self, mode):
        if not self._hud_visible or mode in ("IDLE", "MOVE"):
            return
        surf = self.f14.render(f"[ {mode} ]", True, YELLOW)
        self.screen.blit(surf, (self.W - surf.get_width() - 22, self.H - 35))

    def _draw_bar(self, x, y, label, val, invert=False):
        if invert:
            color = RED if val < 20 else (YELLOW if val < 40 else GREEN)
        else:
            color = RED if val > 80 else (YELLOW if val > 50 else CYAN)
        self.screen.blit(self.f12.render(label, True, CYAN_DIM), (x, y))
        bx, bw, bh = x + 50, 100, 10
        pygame.draw.rect(self.screen, CYAN_DIM, (bx, y + 2, bw, bh), 1)
        fw = max(0, int(bw * val / 100.0))
        if fw > 0:
            pygame.draw.rect(self.screen, color, (bx + 1, y + 3, fw - 2, bh - 2))
        self.screen.blit(self.f12.render(f"{val:.0f}%", True, color), (bx + bw + 6, y))

    def end_frame(self):
        pygame.display.flip()
        self.clock.tick(60)
        return self.clock.get_fps()

    def quit(self):
        pygame.quit()
