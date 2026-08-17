"""Bounded audio decoding and resampling for user-provided songs."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from gradio.processing_utils import audio_from_file

from .domain import AudioData

MAX_AUDIO_BYTES = 80_000_000
MAX_AUDIO_SECONDS = 8 * 60
TARGET_SAMPLE_RATE = 16_000


def _to_float_mono(data: np.ndarray) -> np.ndarray:
    values = np.asarray(data)
    if values.ndim == 2:
        values = values.astype(np.float32).mean(axis=1)
    if values.ndim != 1:
        raise ValueError("Audio channels could not be decoded.")
    if np.issubdtype(values.dtype, np.integer):
        limit = max(abs(np.iinfo(values.dtype).min), np.iinfo(values.dtype).max)
        values = values.astype(np.float32) / float(limit)
    else:
        values = values.astype(np.float32)
    if values.size == 0:
        raise ValueError("The audio file is empty.")
    if not np.isfinite(values).all():
        raise ValueError("The audio contains invalid samples.")
    peak = float(np.max(np.abs(values)))
    if peak > 1.0:
        values = values / peak
    return values


def _resample(values: np.ndarray, source_rate: int, target_rate: int) -> np.ndarray:
    if source_rate == target_rate:
        return values
    target_size = max(1, round(values.size * target_rate / source_rate))
    old_positions = np.linspace(0.0, 1.0, num=values.size, endpoint=False)
    new_positions = np.linspace(0.0, 1.0, num=target_size, endpoint=False)
    return np.interp(new_positions, old_positions, values).astype(np.float32)


def load_audio(path_value: str) -> AudioData:
    path = Path(path_value or "")
    if not path.is_file():
        raise ValueError("Choose an MP3, M4A, WAV, FLAC, OGG, or AAC song first.")
    size = path.stat().st_size
    if size <= 0:
        raise ValueError("The audio file is empty.")
    if size > MAX_AUDIO_BYTES:
        raise ValueError(
            f"Audio must be smaller than {MAX_AUDIO_BYTES // 1_000_000} MB."
        )
    sample_rate, raw = audio_from_file(str(path))
    if sample_rate <= 0:
        raise ValueError("The audio sample rate is invalid.")
    values = _to_float_mono(raw)
    duration = values.size / float(sample_rate)
    if duration < 1.0:
        raise ValueError("Audio must be at least one second long.")
    if duration > MAX_AUDIO_SECONDS:
        raise ValueError(f"Audio must be {MAX_AUDIO_SECONDS // 60} minutes or shorter.")
    resampled = _resample(values, sample_rate, TARGET_SAMPLE_RATE)
    return AudioData(resampled, TARGET_SAMPLE_RATE, duration, path.name[:240])
