"""System telemetry poller.

Samples CPU, RAM, and battery stats at a configurable interval using
psutil. Returns cached values between polls to avoid blocking.
"""
import time
import psutil


class SystemMonitor:
    def __init__(self, poll_interval=2.0):
        self._interval = poll_interval
        self._last_poll = 0.0
        self._stats = {"cpu": 0.0, "ram": 0.0, "battery": 100, "plugged": True}
        psutil.cpu_percent(interval=None)  # prime (first call returns 0)

    def get_stats(self):
        now = time.time()
        if now - self._last_poll >= self._interval:
            self._stats["cpu"] = psutil.cpu_percent(interval=None)
            self._stats["ram"] = psutil.virtual_memory().percent
            bat = psutil.sensors_battery()
            if bat:
                self._stats["battery"] = bat.percent
                self._stats["plugged"] = bat.power_plugged
            self._last_poll = now
        return self._stats
