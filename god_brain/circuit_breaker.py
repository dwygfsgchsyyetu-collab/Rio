# Lightweight circuit breaker for protecting fragile integrations
import time
import threading
from typing import Callable

class CircuitOpen(Exception):
    pass

class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 30.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failures = 0
        self.state = 'CLOSED'  # CLOSED, OPEN, HALF
        self.opened_at = None
        self.lock = threading.Lock()

    def record_success(self):
        with self.lock:
            self.failures = 0
            self.state = 'CLOSED'
            self.opened_at = None

    def record_failure(self):
        with self.lock:
            self.failures += 1
            if self.failures >= self.failure_threshold:
                self.state = 'OPEN'
                self.opened_at = time.time()

    def allow(self) -> bool:
        with self.lock:
            if self.state == 'OPEN':
                if (time.time() - (self.opened_at or 0)) > self.recovery_timeout:
                    self.state = 'HALF'
                    return True
                return False
            return True

    def __call__(self, func: Callable):
        def wrapped(*args, **kwargs):
            if not self.allow():
                raise CircuitOpen('Circuit is open')
            try:
                res = func(*args, **kwargs)
                self.record_success()
                return res
            except Exception as e:
                self.record_failure()
                raise
        return wrapped
