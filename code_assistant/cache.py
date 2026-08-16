"""Small bounded in-process TTL cache for public GitHub metadata and source text."""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Generic, Hashable, TypeVar


KeyT = TypeVar("KeyT", bound=Hashable)
ValueT = TypeVar("ValueT")


@dataclass(frozen=True)
class CacheStats:
    entries: int
    hits: int
    misses: int
    evictions: int


@dataclass
class _Entry(Generic[ValueT]):
    value: ValueT
    expires_at: float


class TTLCache(Generic[KeyT, ValueT]):
    """Thread-safe least-recently-used cache with monotonic expiration."""

    def __init__(self, max_entries: int = 256, ttl_seconds: float = 300.0) -> None:
        if max_entries < 1:
            raise ValueError("max_entries must be positive")
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self.max_entries = int(max_entries)
        self.ttl_seconds = float(ttl_seconds)
        self._items: OrderedDict[KeyT, _Entry[ValueT]] = OrderedDict()
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0
        self._evictions = 0

    def get(self, key: KeyT) -> ValueT | None:
        now = time.monotonic()
        with self._lock:
            entry = self._items.get(key)
            if entry is None:
                self._misses += 1
                return None
            if entry.expires_at <= now:
                del self._items[key]
                self._misses += 1
                self._evictions += 1
                return None
            self._items.move_to_end(key)
            self._hits += 1
            return entry.value

    def set(self, key: KeyT, value: ValueT, ttl_seconds: float | None = None) -> None:
        ttl = self.ttl_seconds if ttl_seconds is None else float(ttl_seconds)
        if ttl <= 0:
            return
        with self._lock:
            self._items[key] = _Entry(value=value, expires_at=time.monotonic() + ttl)
            self._items.move_to_end(key)
            while len(self._items) > self.max_entries:
                self._items.popitem(last=False)
                self._evictions += 1

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    def stats(self) -> CacheStats:
        with self._lock:
            return CacheStats(
                entries=len(self._items),
                hits=self._hits,
                misses=self._misses,
                evictions=self._evictions,
            )

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)
