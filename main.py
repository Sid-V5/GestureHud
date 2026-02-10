"""Application entry point.

Initializes the hand tracker, overlay, mouse controller, and telemetry
modules, then runs the main render loop at 60 fps. Gesture-to-action
mapping is handled here.

Usage:
    python main.py          # default (CPU inference)
    python main.py --gpu    # request GPU delegate
"""
import sys
import time
import ctypes

from tracker import HandTracker
from overlay import HUDOverlay
from controls import MouseController
from telemetry import SystemMonitor


def get_screen_size():
    u32 = ctypes.windll.user32
    u32.SetProcessDPIAware()
    return u32.GetSystemMetrics(0), u32.GetSystemMetrics(1)


def main():
    use_gpu = "--gpu" in sys.argv
    screen_w, screen_h = get_screen_size()
    print(f"Screen: {screen_w}x{screen_h} | Mode: {'GPU' if use_gpu else 'CPU'}")

    tracker = HandTracker(use_gpu=use_gpu)
    hud = HUDOverlay(screen_w, screen_h)
    mouse = MouseController(screen_w, screen_h)
    telemetry = SystemMonitor(poll_interval=2.0)

    tracker.start()
    print("Tracker started. Press ESC to quit.")

    render_fps = 0.0
    hud_toggle_cooldown = 0.0

    while True:
        if not hud.handle_events():
            break

        hud.begin_frame()

        if not hud.draw_boot_sequence():
            render_fps = hud.end_frame()
            continue

        state = tracker.get_state()
        stats = telemetry.get_stats()
        primary = state.primary
        secondary = state.secondary

        gesture_label = ""
        mode = "IDLE"

        if primary.detected:
            mouse.move(primary.x, primary.y)

            if primary.click_left:
                mouse.left_click()
                hud.force_topmost()
                gesture_label = "L-CLICK"
                mode = "CLICK"
            elif primary.click_right:
                mouse.right_click()
                hud.force_topmost()
                gesture_label = "R-CLICK"
                mode = "CLICK"
            elif primary.is_peace:
                mouse.scroll(primary.y)
                gesture_label = "SCROLL"
                mode = "SCROLL"
            elif primary.is_fist:
                mouse.start_drag()
                gesture_label = "DRAG"
                mode = "DRAG"
            elif primary.is_open_palm:
                mouse.stop_drag()
                mouse.reset_scroll()
                gesture_label = "OPEN"
                mode = "IDLE"
            else:
                mouse.stop_drag()
                mode = "MOVE"

            # Two-hand HUD toggle
            if secondary.detected and secondary.click_left:
                now = time.time()
                if now - hud_toggle_cooldown > 1.0:
                    hud.toggle_visibility()
                    hud_toggle_cooldown = now
        else:
            mouse.stop_drag()
            mouse.reset_scroll()

        if mode != "SCROLL":
            mouse.reset_scroll()

        # Determine cursor visual state
        cursor_state = "idle"
        if mode == "CLICK":
            cursor_state = "left_click" if "L-" in gesture_label else "right_click"
        elif mode == "DRAG":
            cursor_state = "drag"
        elif mode == "SCROLL":
            cursor_state = "scroll"

        # Render
        if primary.detected:
            hud.draw_hand_skeleton(primary.landmarks)
            hud.draw_cursor(primary.x, primary.y, cursor_state)
            hud.draw_gesture_indicator(gesture_label, primary.x, primary.y)
        if secondary.detected:
            hud.draw_hand_skeleton(secondary.landmarks)

        hud.draw_corner_brackets()
        hud.draw_scan_line()
        hud.draw_telemetry(stats, tracker_fps=state.fps, render_fps=render_fps)
        hud.draw_hand_status(state.num_hands)
        hud.draw_mode_indicator(mode)

        render_fps = hud.end_frame()

    print("Shutting down...")
    tracker.stop()
    mouse.stop_drag()
    hud.quit()


if __name__ == "__main__":
    main()
