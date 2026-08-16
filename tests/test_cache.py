from __future__ import annotations

import time
import unittest

from code_assistant.cache import TTLCache


class TTLCacheTests(unittest.TestCase):
    def test_get_set_and_stats(self):
        cache: TTLCache[str, str] = TTLCache(max_entries=2, ttl_seconds=10)
        self.assertIsNone(cache.get("missing"))
        cache.set("key", "value")
        self.assertEqual(cache.get("key"), "value")
        stats = cache.stats()
        self.assertEqual(stats.entries, 1)
        self.assertEqual(stats.hits, 1)
        self.assertEqual(stats.misses, 1)

    def test_lru_eviction(self):
        cache: TTLCache[str, int] = TTLCache(max_entries=2, ttl_seconds=10)
        cache.set("a", 1)
        cache.set("b", 2)
        self.assertEqual(cache.get("a"), 1)
        cache.set("c", 3)
        self.assertIsNone(cache.get("b"))
        self.assertEqual(cache.get("a"), 1)
        self.assertEqual(cache.get("c"), 3)
        self.assertGreaterEqual(cache.stats().evictions, 1)

    def test_expiration(self):
        cache: TTLCache[str, int] = TTLCache(max_entries=2, ttl_seconds=0.01)
        cache.set("a", 1)
        time.sleep(0.02)
        self.assertIsNone(cache.get("a"))
        self.assertEqual(len(cache), 0)

    def test_rejects_invalid_configuration(self):
        with self.assertRaises(ValueError):
            TTLCache(max_entries=0)
        with self.assertRaises(ValueError):
            TTLCache(ttl_seconds=0)


if __name__ == "__main__":
    unittest.main()
