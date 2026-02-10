"""Hand tracking module with gesture recognition.

Runs MediaPipe Hands in a background thread and exposes a thread-safe
snapshot of the current hand state (position, gestures, click events).

Pinch detection uses a hysteresis state machine with filtered distance
measurements to fire edge-triggered click events reliably.
"""
import threading
import time
import math
import cv2
import mediapipe as mp
from dataclasses import dataclass, field
from collections import deque

from filter import OneEuroFilter


@dataclass
class HandState:
    x: float = 0.0
    y: float = 0.0
    click_left: bool = False
    click_right: bool = False
    is_fist: bool = False
    is_peace: bool = False
    is_open_palm: bool = False
    velocity: float = 0.0
    detected: bool = False
    landmarks: list = field(default_factory=list)


@dataclass
class TrackerState:
    primary: HandState = field(default_factory=HandState)
    secondary: HandState = field(default_factory=HandState)
    num_hands: int = 0
    fps: float = 0.0


class HandTracker:
    """Threaded hand tracker with gesture classification.

    Gestures detected:
        - Left click: index-to-thumb pinch (edge-triggered)
        - Right click: middle-to-thumb pinch (edge-triggered)
        - Fist: all fingers curled (sustained)
        - Peace / V-sign: index + middle extended (sustained)
        - Open palm: all fingers extended (sustained)
    """

    # Pinch detection thresholds (applied to filtered distance ratios)
    PINCH_ENTER = 0.28
    PINCH_EXIT = 0.50
    DEBOUNCE = 4        # consecutive qualifying frames before firing
    COOLDOWN = 0.45     # minimum seconds between clicks
    Z_WEIGHT = 0.5      # depth axis weight in 3D distance

    def __init__(self, use_gpu=False):
        self.mp_hands = mp.solutions.hands
        self.hands = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=2,
            model_complexity=0,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.6,
        )
        self.state = TrackerState()
        self.lock = threading.Lock()

        # Cursor smoothing (per hand)
        self._filt_x = [OneEuroFilter(1.5, 0.01), OneEuroFilter(1.5, 0.01)]
        self._filt_y = [OneEuroFilter(1.5, 0.01), OneEuroFilter(1.5, 0.01)]

        # Pinch distance smoothing — aggressive to suppress jitter
        self._filt_d_idx = [OneEuroFilter(0.5, 0.003), OneEuroFilter(0.5, 0.003)]
        self._filt_d_mid = [OneEuroFilter(0.5, 0.003), OneEuroFilter(0.5, 0.003)]

        # Velocity computation
        self._prev_x = [0.5, 0.5]
        self._prev_y = [0.5, 0.5]
        self._prev_t = [time.perf_counter()] * 2

        # Pinch state machines (per hand)
        self._idx_state = ["open", "open"]
        self._mid_state = ["open", "open"]
        self._idx_count = [0, 0]
        self._mid_count = [0, 0]
        self._idx_exit = [0, 0]
        self._mid_exit = [0, 0]
        self._last_lclick = [0.0, 0.0]
        self._last_rclick = [0.0, 0.0]

        # Fist detection requires sustained frames
        self._fist_cnt = [0, 0]

        self._ftimes = deque(maxlen=30)
        self.cap = None
        self._running = False
        self._thread = None

    # -- Lifecycle --

    def start(self):
        """Open the webcam and begin tracking in a background thread."""
        self.cap = cv2.VideoCapture(0)
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        self.cap.set(cv2.CAP_PROP_FPS, 30)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        if not self.cap.isOpened():
            raise RuntimeError("Cannot open webcam")
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        """Signal the tracking thread to exit and release the webcam."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2)
        if self.cap:
            self.cap.release()

    def get_state(self) -> TrackerState:
        """Return a thread-safe snapshot of the current tracker state."""
        with self.lock:
            return TrackerState(
                primary=HandState(**vars(self.state.primary)),
                secondary=HandState(**vars(self.state.secondary)),
                num_hands=self.state.num_hands,
                fps=self.state.fps,
            )

    # -- Internal --

    def _loop(self):
        while self._running:
            t0 = time.perf_counter()
            ret, frame = self.cap.read()
            if not ret:
                continue

            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            results = self.hands.process(rgb)

            ns = TrackerState()
            if results.multi_hand_landmarks:
                hands = []
                for i, hlm in enumerate(results.multi_hand_landmarks):
                    if i >= 2:
                        break
                    hands.append(self._process(hlm, i, t0))
                ns.num_hands = len(hands)
                if len(hands) >= 1:
                    ns.primary = hands[0]
                if len(hands) >= 2:
                    ns.secondary = hands[1]

            dt = time.perf_counter() - t0
            self._ftimes.append(dt)
            avg = sum(self._ftimes) / len(self._ftimes)
            ns.fps = 1.0 / avg if avg > 0 else 0

            with self.lock:
                self.state = ns

    def _dist3d(self, a, b):
        """Weighted 3D euclidean distance between two landmarks."""
        dx = a.x - b.x
        dy = a.y - b.y
        dz = (a.z - b.z) * self.Z_WEIGHT
        return math.sqrt(dx * dx + dy * dy + dz * dz)

    def _process(self, landmarks, i, now):
        lm = landmarks.landmark
        hs = HandState(detected=True)

        hs.landmarks = [(l.x, l.y) for l in lm]

        # Cursor position (index fingertip, filtered)
        hs.x = max(0.0, min(1.0, self._filt_x[i](lm[8].x, now)))
        hs.y = max(0.0, min(1.0, self._filt_y[i](lm[8].y, now)))

        # Cursor velocity
        dt = now - self._prev_t[i]
        if dt > 0:
            hs.velocity = math.hypot(
                hs.x - self._prev_x[i], hs.y - self._prev_y[i]) / dt
        self._prev_x[i], self._prev_y[i], self._prev_t[i] = hs.x, hs.y, now

        # Hand scale for distance normalization
        hand_size = self._dist3d(lm[0], lm[5])
        if hand_size < 0.01:
            hand_size = 0.1

        # Finger-to-thumb distances (3D, normalized)
        thumb = lm[4]
        d_idx = self._filt_d_idx[i](self._dist3d(lm[8], thumb) / hand_size, now)
        d_mid = self._filt_d_mid[i](self._dist3d(lm[12], thumb) / hand_size, now)

        # Finger extension detection
        tips = [8, 12, 16, 20]
        pips = [6, 10, 14, 18]
        ext = []
        for t, p in zip(tips, pips):
            tip_d = math.hypot(lm[t].x - lm[0].x, lm[t].y - lm[0].y)
            pip_d = math.hypot(lm[p].x - lm[0].x, lm[p].y - lm[0].y)
            ext.append(tip_d > pip_d * 1.05)

        idx_ext, mid_ext, ring_ext, pinky_ext = ext

        # Extension-based isolation: pinch is suppressed during a fist
        # (at least one of ring/pinky must be extended)
        can_pinch = ring_ext or pinky_ext

        # Pinch state machines (edge-triggered — fire on transition only)
        hs.click_left = self._pinch(i, "idx", d_idx, can_pinch, now)
        hs.click_right = self._pinch(i, "mid", d_mid, can_pinch, now)

        # Sustained gesture classification
        hs.is_peace = idx_ext and mid_ext and not ring_ext and not pinky_ext
        hs.is_open_palm = idx_ext and mid_ext and ring_ext and pinky_ext

        all_curled = not any(ext)
        self._fist_cnt[i] = min(self._fist_cnt[i] + 1, 20) if all_curled else 0
        hs.is_fist = self._fist_cnt[i] >= 8

        return hs

    def _pinch(self, i, which, dist, qualified, now):
        """Hysteresis state machine for pinch detection.

        Returns True on the single frame a pinch is first detected
        (edge trigger). The debounce counter hard-resets on any frame
        where conditions are not met, preventing jitter from accumulating.
        """
        if which == "idx":
            state_arr = self._idx_state
            count_arr = self._idx_count
            exit_arr = self._idx_exit
            time_arr = self._last_lclick
        else:
            state_arr = self._mid_state
            count_arr = self._mid_count
            exit_arr = self._mid_exit
            time_arr = self._last_rclick

        click = False

        if state_arr[i] == "open":
            if (dist < self.PINCH_ENTER
                    and qualified
                    and (now - time_arr[i]) > self.COOLDOWN):
                count_arr[i] += 1
            else:
                count_arr[i] = 0

            if count_arr[i] >= self.DEBOUNCE:
                state_arr[i] = "pinched"
                count_arr[i] = 0
                time_arr[i] = now
                click = True

        elif state_arr[i] == "pinched":
            if dist > self.PINCH_EXIT:
                exit_arr[i] += 1
            else:
                exit_arr[i] = 0

            if exit_arr[i] >= 3:
                state_arr[i] = "open"
                exit_arr[i] = 0

        return click
