"""Bounded, memory-safe audio decoding and resampling for uploaded songs."""

from __future__ import annotations

import subprocess
from pathlib import Path

import numpy as np

from .domain import AudioData

# The owner's Space has 16 GB RAM and 50 GB ephemeral storage. Uploads may use
# the full 16 GB requested ceiling, while FFmpeg decodes directly to bounded
# 16 kHz mono PCM instead of expanding source-rate audio in memory.
MAX_AUDIO_BYTES = 16_000_000_000
MAX_AUDIO_SECONDS = 8 * 60
TARGET_SAMPLE_RATE = 16_000
_DECODE_TIMEOUT_SECONDS = 240
_PROBE_TIMEOUT_SECONDS = 45


def _to_float_mono(data: np.ndarray) -> np.ndarray:
    """Normalize a decoded array for focused tests and utility callers."""

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
    """Resample a bounded array; production uploads use FFmpeg."""

    if source_rate == target_rate:
        return values
    target_size = max(1, round(values.size * target_rate / source_rate))
    old_positions = np.linspace(0.0, 1.0, num=values.size, endpoint=False)
    new_positions = np.linspace(0.0, 1.0, num=target_size, endpoint=False)
    return np.interp(new_positions, old_positions, values).astype(np.float32)


def _probe_duration(path: Path) -> float:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            check=False,
            text=True,
            timeout=_PROBE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("The audio file could not be inspected safely.") from exc
    if result.returncode != 0:
        raise ValueError("The audio format could not be decoded.")
    try:
        duration = float(result.stdout.strip())
    except (TypeError, ValueError) as exc:
        raise ValueError("The audio duration could not be determined.") from exc
    if not np.isfinite(duration) or duration < 1.0:
        raise ValueError("Audio must be at least one second long.")
    if duration > MAX_AUDIO_SECONDS:
        raise ValueError(f"Audio must be {MAX_AUDIO_SECONDS // 60} minutes or shorter.")
    return duration


def _decode_bounded_pcm(path: Path) -> np.ndarray:
    command = [
        "ffmpeg",
        "-nostdin",
        "-v",
        "error",
        "-i",
        str(path),
        "-map",
        "0:a:0",
        "-vn",
        "-ac",
        "1",
        "-ar",
        str(TARGET_SAMPLE_RATE),
        "-t",
        str(MAX_AUDIO_SECONDS),
        "-f",
        "f32le",
        "pipe:1",
    ]
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            check=False,
            timeout=_DECODE_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError("The audio file took too long to decode safely.") from exc
    if result.returncode != 0:
        raise ValueError("The audio format could not be decoded.")
    if not result.stdout or len(result.stdout) % np.dtype(np.float32).itemsize:
        raise ValueError("The audio file did not contain usable samples.")
    values = np.frombuffer(result.stdout, dtype="<f4").astype(np.float32, copy=True)
    if values.size == 0 or not np.isfinite(values).all():
        raise ValueError("The audio contains invalid samples.")
    peak = float(np.max(np.abs(values)))
    if peak > 1.0:
        values /= peak
    return values


def load_audio(path_value: str) -> AudioData:
    path = Path(path_value or "")
    if not path.is_file():
        raise ValueError("Choose an MP3, M4A, WAV, FLAC, OGG, or AAC song first.")
    size = path.stat().st_size
    if size <= 0:
        raise ValueError("The audio file is empty.")
    if size > MAX_AUDIO_BYTES:
        raise ValueError(
            f"Audio must be {MAX_AUDIO_BYTES // 1_000_000_000} GB or smaller."
        )

    duration = _probe_duration(path)
    values = _decode_bounded_pcm(path)
    expected_samples = max(1, round(duration * TARGET_SAMPLE_RATE))
    # Clamp imprecise container padding with a small timestamp tolerance.
    max_samples = expected_samples + TARGET_SAMPLE_RATE
    if values.size > max_samples:
        values = values[:max_samples].copy()
    decoded_duration = values.size / float(TARGET_SAMPLE_RATE)
    if decoded_duration < 1.0:
        raise ValueError("Audio must be at least one second long.")
    return AudioData(
        values,
        TARGET_SAMPLE_RATE,
        min(duration, decoded_duration),
        path.name[:240],
    )
