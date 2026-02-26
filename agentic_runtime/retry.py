from __future__ import annotations

import asyncio
import random
from abc import ABC, abstractmethod
from typing import Any, Optional


class IRetryPolicy(ABC):
    @abstractmethod
    async def run(self, op: Any) -> Any:
        raise NotImplementedError


class ExponentialBackoffRetryPolicy(IRetryPolicy):
    def __init__(self, max_attempts: int = 3, base_delay_seconds: float = 0.05, multiplier: float = 2.0, jitter: bool = False) -> None:
        self.max_attempts = max_attempts
        self.base_delay_seconds = base_delay_seconds
        self.multiplier = multiplier
        self.jitter = jitter

    async def run(self, op: Any) -> Any:
        last_exc: Optional[Exception] = None
        delay = self.base_delay_seconds
        for attempt in range(1, self.max_attempts + 1):
            try:
                return await op()
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if attempt >= self.max_attempts:
                    raise
                sleep_for = delay * (random.uniform(0.8, 1.2) if self.jitter else 1.0)
                await asyncio.sleep(sleep_for)
                delay *= self.multiplier
        if last_exc:
            raise last_exc
        raise RuntimeError("Retry policy exited unexpectedly.")
