"""Adaptive low-pass filter for noisy input signals.

Implements the 1-Euro filter algorithm from:
    Casiez, Roussel, Vogel (2012) — "1€ Filter: A Simple Speed-Based
    Low-Pass Filter for Noisy Input in Interactive Systems"
"""
import math
import time


class OneEuroFilter:
    """Speed-adaptive low-pass filter. Reduces jitter at rest while
    allowing fast movements through with minimal latency.

    Args:
        min_cutoff: Base cutoff frequency. Lower values increase smoothing.
        beta: Speed coefficient. Higher values reduce lag during fast motion.
        d_cutoff: Cutoff frequency for the derivative estimator.
    """

    def __init__(self, min_cutoff=1.0, beta=0.007, d_cutoff=1.0):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self._x_prev = None
        self._dx_prev = 0.0
        self._t_prev = None

    def __call__(self, x, t=None):
        if t is None:
            t = time.perf_counter()

        if self._t_prev is None:
            self._x_prev = x
            self._t_prev = t
            return x

        dt = t - self._t_prev
        if dt <= 0:
            return self._x_prev

        dx = (x - self._x_prev) / dt
        a_d = self._alpha(self.d_cutoff, dt)
        dx_hat = a_d * dx + (1 - a_d) * self._dx_prev

        cutoff = self.min_cutoff + self.beta * abs(dx_hat)
        a = self._alpha(cutoff, dt)
        x_hat = a * x + (1 - a) * self._x_prev

        self._x_prev = x_hat
        self._dx_prev = dx_hat
        self._t_prev = t
        return x_hat

    @staticmethod
    def _alpha(cutoff, dt):
        tau = 1.0 / (2 * math.pi * cutoff)
        return 1.0 / (1.0 + tau / dt)

    def reset(self):
        self._x_prev = None
        self._dx_prev = 0.0
        self._t_prev = None
