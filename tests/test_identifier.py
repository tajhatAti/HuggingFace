from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any

try:
    import numpy as np

    from lyr_service.identifier import ShazamAudioIdentifier
except ModuleNotFoundError as dependency_error:
    np = None  # type: ignore[assignment]
    ShazamAudioIdentifier = None  # type: ignore[assignment,misc]
    IDENTIFIER_DEPENDENCY_ERROR = dependency_error
else:
    IDENTIFIER_DEPENDENCY_ERROR = None


@unittest.skipIf(
    ShazamAudioIdentifier is None,
    f"optional fingerprint test dependencies are unavailable: {IDENTIFIER_DEPENDENCY_ERROR}",
)
class IdentifierTests(unittest.TestCase):
    def test_bounded_wav_is_parsed_and_removed(self):
        observed_paths: list[Path] = []
        observed_sizes: list[int] = []
        identifier = ShazamAudioIdentifier()

        async def fake_recognize(path: str) -> dict[str, Any]:
            clip = Path(path)
            observed_paths.append(clip)
            observed_sizes.append(clip.stat().st_size)
            return {"track": {"title": "Matir Roud", "subtitle": "Aftermath"}}

        identifier._recognize = fake_recognize  # type: ignore[method-assign]
        samples = np.zeros(30 * 16_000, dtype=np.float32)
        identity = identifier.identify(samples, 16_000, 30.0)

        self.assertIsNotNone(identity)
        assert identity is not None
        self.assertEqual(identity.title, "Matir Roud")
        self.assertEqual(identity.artist, "Aftermath")
        self.assertEqual(len(observed_paths), 1)
        self.assertLessEqual(observed_sizes[0], 24 * 16_000 * 2 + 100)
        self.assertFalse(observed_paths[0].exists())

    def test_short_or_wrong_rate_audio_never_leaves_the_process(self):
        identifier = ShazamAudioIdentifier()
        self.assertIsNone(
            identifier.identify(np.zeros(7 * 16_000, dtype=np.float32), 16_000, 7.0)
        )
        self.assertIsNone(
            identifier.identify(np.zeros(10 * 8_000, dtype=np.float32), 8_000, 10.0)
        )


if __name__ == "__main__":
    unittest.main()
