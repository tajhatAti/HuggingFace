"""Bounded online audio-fingerprint song identity discovery."""

from __future__ import annotations

import asyncio
import tempfile
import wave
from pathlib import Path
from typing import Any

import numpy as np
from shazamio import Shazam

from .provider import SongIdentity

FINGERPRINT_CLIP_SECONDS = 24
FINGERPRINT_START_FRACTIONS = (0.12, 0.42, 0.68)
FINGERPRINT_TIMEOUT_SECONDS = 35


class ShazamAudioIdentifier:
    """Identify a recording from compact fingerprints before full transcription."""

    async def _recognize(self, path: str) -> dict[str, Any]:
        result = await asyncio.wait_for(
            Shazam().recognize(path),
            timeout=FINGERPRINT_TIMEOUT_SECONDS,
        )
        return result if isinstance(result, dict) else {}

    @staticmethod
    def _write_clip(samples: np.ndarray, sample_rate: int, start: int) -> Path:
        clip_size = FINGERPRINT_CLIP_SECONDS * sample_rate
        clip = np.asarray(samples[start : start + clip_size], dtype=np.float32)
        if clip.size < sample_rate * 8:
            raise ValueError("Audio fingerprint clip is too short.")
        pcm = (np.clip(clip, -1.0, 1.0) * 32767.0).astype("<i2")
        handle = tempfile.NamedTemporaryFile(
            prefix="lyr-fingerprint-",
            suffix=".wav",
            delete=False,
        )
        path = Path(handle.name)
        handle.close()
        with wave.open(str(path), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(sample_rate)
            output.writeframes(pcm.tobytes())
        return path

    def identify(
        self,
        samples: np.ndarray,
        sample_rate: int,
        duration_seconds: float,
    ) -> SongIdentity | None:
        if sample_rate != 16_000 or duration_seconds < 8 or samples.size < sample_rate * 8:
            return None
        clip_size = min(samples.size, FINGERPRINT_CLIP_SECONDS * sample_rate)
        max_start = max(0, samples.size - clip_size)
        starts = sorted(
            {int(max_start * fraction) for fraction in FINGERPRINT_START_FRACTIONS}
        )
        for start in starts:
            path: Path | None = None
            try:
                path = self._write_clip(samples, sample_rate, start)
                result = asyncio.run(self._recognize(str(path)))
                track = result.get("track") or {}
                title = str(track.get("title") or "").strip()[:300]
                artist = str(track.get("subtitle") or "").strip()[:300]
                if title and artist:
                    return SongIdentity(
                        title=title,
                        artist=artist,
                        matched_words=100,
                        exact_words=100,
                    )
            except Exception:
                continue
            finally:
                if path is not None:
                    path.unlink(missing_ok=True)
        return None
