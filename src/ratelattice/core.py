from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from threading import RLock
from time import monotonic, time


@dataclass(frozen=True)
class Decision:
    allowed: bool
    retry_after: float = 0.0
    remaining: float = 0.0
    blocked_by: tuple[str, ...] = ()


class TokenBucket:
    """A thread-safe token bucket with an injectable clock for tests."""

    def __init__(self, capacity: float, refill_per_second: float) -> None:
        if capacity <= 0 or refill_per_second <= 0:
            raise ValueError("capacity and refill_per_second must be positive")
        self.capacity = float(capacity)
        self.refill_per_second = float(refill_per_second)
        self._tokens = self.capacity
        self._updated = monotonic()
        self._lock = RLock()

    @property
    def tokens(self) -> float:
        """Return stored tokens without refilling the bucket."""

        with self._lock:
            return self._tokens

    def _preview(self, cost: float, now: float) -> Decision:
        elapsed = max(0.0, now - self._updated)
        available = min(self.capacity, self._tokens + elapsed * self.refill_per_second)
        if available >= cost:
            return Decision(True, remaining=available - cost)
        wait = (cost - available) / self.refill_per_second
        return Decision(False, retry_after=wait, remaining=available)

    def preview(self, cost: float = 1.0, now: float | None = None) -> Decision:
        """Inspect a request without consuming tokens."""

        if cost <= 0:
            raise ValueError("cost must be positive")
        current = monotonic() if now is None else now
        with self._lock:
            return self._preview(cost, current)

    def allow(self, cost: float = 1.0, now: float | None = None) -> Decision:
        if cost <= 0:
            raise ValueError("cost must be positive")
        current = monotonic() if now is None else now
        with self._lock:
            decision = self._preview(cost, current)
            elapsed = max(0.0, current - self._updated)
            self._tokens = min(self.capacity, self._tokens + elapsed * self.refill_per_second)
            self._updated = current
            if decision.allowed:
                self._tokens -= cost
                return Decision(True, remaining=self._tokens)
            return Decision(False, retry_after=decision.retry_after, remaining=self._tokens)

    def reset(self) -> None:
        """Restore the bucket to full capacity."""

        with self._lock:
            self._tokens = self.capacity
            self._updated = monotonic()


class RateLattice:
    """Evaluate several independent limits as one inspectable decision."""

    def __init__(self, limits: dict[str, TokenBucket] | None = None) -> None:
        self.limits = dict(limits or {})
        self._lock = RLock()

    def add(self, name: str, limit: TokenBucket) -> None:
        if not name:
            raise ValueError("limit name must not be empty")
        self.limits[name] = limit

    def allow(self, cost: float = 1.0, now: float | None = None) -> Decision:
        if cost <= 0:
            raise ValueError("cost must be positive")
        current = monotonic() if now is None else now
        with self._lock:
            # Preview every bucket first. A rejected request must not consume
            # capacity from limits checked earlier in the same request.
            decisions = {name: limit.preview(cost, now=current) for name, limit in self.limits.items()}
            blocked = tuple(sorted(name for name, decision in decisions.items() if not decision.allowed))
            if blocked:
                return Decision(
                    False,
                    retry_after=max(decisions[name].retry_after for name in blocked),
                    remaining=min((decision.remaining for decision in decisions.values()), default=0.0),
                    blocked_by=blocked,
                )
            for limit in self.limits.values():
                limit.allow(cost, now=current)
            remaining = min((decision.remaining for decision in decisions.values()), default=0.0)
            return Decision(True, remaining=remaining)

    def reset(self) -> None:
        """Restore every configured limit to full capacity."""

        with self._lock:
            for limit in self.limits.values():
                limit.reset()


def parse_retry_after(value: str | int | float | None, now: float | None = None) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return max(0.0, float(value))
    try:
        return max(0.0, float(value.strip()))
    except ValueError:
        try:
            parsed: datetime = parsedate_to_datetime(value)
        except (TypeError, ValueError, IndexError):
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return max(0.0, parsed.timestamp() - (time() if now is None else now))


def combine_delays(*delays: float | None) -> float:
    """Choose the most conservative non-negative delay from local/remote signals."""

    return max((max(0.0, delay) for delay in delays if delay is not None), default=0.0)
