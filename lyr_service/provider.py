"""Strict, bounded LRCLIB retrieval and recognized-text matching."""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from .lyrics import comparison_text, contains_bengali, normalize_text

LRCLIB_ROOT = "https://lrclib.net/api"
MAX_RESULTS = 20
MAX_LYRICS_CHARACTERS = 250_000


@dataclass(frozen=True)
class LrcLibCandidate:
    record_id: int
    title: str
    artist: str
    album: str
    duration_seconds: float
    plain_lyrics: str
    synced_lyrics: str
    instrumental: bool = False


class LyricsProviderError(RuntimeError):
    pass


class LrcLibClient:
    def __init__(self, session: requests.Session | None = None) -> None:
        self.session = session or requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json",
                "User-Agent": "LyrOnline/1.0 (https://github.com/tajhatAti/Lyr)",
            }
        )
        retry = Retry(
            total=2,
            connect=2,
            read=2,
            status=2,
            backoff_factor=0.35,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
            respect_retry_after_header=True,
            raise_on_status=False,
        )
        self.session.mount("https://lrclib.net/", HTTPAdapter(max_retries=retry))

    def _get(self, path: str, params: dict[str, str]) -> list[dict[str, Any]]:
        response: requests.Response | None = None
        try:
            response = self.session.get(
                f"{LRCLIB_ROOT}/{path}",
                params=params,
                timeout=(4, 12),
                allow_redirects=False,
            )
            if 300 <= response.status_code < 400:
                raise LyricsProviderError(
                    "Lyrics provider returned an unexpected redirect."
                )
            if response.status_code == 404:
                return []
            if response.status_code == 429:
                raise LyricsProviderError("Lyrics provider is busy. Try again shortly.")
            if response.status_code >= 500:
                raise LyricsProviderError("Lyrics provider is temporarily unavailable.")
            if response.status_code >= 400:
                raise LyricsProviderError(
                    f"Lyrics provider rejected the request ({response.status_code})."
                )
            payload = response.json()
            if not isinstance(payload, list):
                raise LyricsProviderError(
                    "Lyrics provider returned an invalid response."
                )
            return [item for item in payload[:MAX_RESULTS] if isinstance(item, dict)]
        except requests.Timeout as exc:
            raise LyricsProviderError("Lyrics lookup timed out.") from exc
        except requests.RequestException as exc:
            raise LyricsProviderError(
                "Could not connect to the lyrics provider."
            ) from exc
        except ValueError as exc:
            raise LyricsProviderError("Lyrics provider returned invalid JSON.") from exc
        finally:
            if response is not None:
                response.close()

    @staticmethod
    def _candidate(item: dict[str, Any]) -> LrcLibCandidate | None:
        title = normalize_text(str(item.get("trackName") or ""))[:500]
        artist = normalize_text(str(item.get("artistName") or ""))[:500]
        synced = str(item.get("syncedLyrics") or "")[:MAX_LYRICS_CHARACTERS]
        plain = str(item.get("plainLyrics") or "")[:MAX_LYRICS_CHARACTERS]
        if not title or not artist or (not synced.strip() and not plain.strip()):
            return None
        try:
            record_id = int(item.get("id") or 0)
            duration = max(0.0, float(item.get("duration") or 0.0))
        except (TypeError, ValueError):
            return None
        return LrcLibCandidate(
            record_id=record_id,
            title=title,
            artist=artist,
            album=normalize_text(str(item.get("albumName") or ""))[:500],
            duration_seconds=duration,
            plain_lyrics=plain.strip(),
            synced_lyrics=synced.strip(),
            instrumental=bool(item.get("instrumental", False)),
        )

    def search_metadata(
        self,
        title: str,
        artist: str = "",
        duration_seconds: float = 0.0,
    ) -> tuple[LrcLibCandidate, ...]:
        clean_title = normalize_text(title)[:300]
        clean_artist = normalize_text(artist)[:300]
        if not clean_title:
            return ()
        params = {"track_name": clean_title}
        if clean_artist:
            params["artist_name"] = clean_artist
        if duration_seconds > 0:
            params["duration"] = str(round(duration_seconds))
        candidates = [self._candidate(item) for item in self._get("search", params)]
        return tuple(candidate for candidate in candidates if candidate is not None)

    def search_text(self, query: str) -> tuple[LrcLibCandidate, ...]:
        clean = normalize_text(query)[:500]
        if len(comparison_text(clean).split()) < 3:
            return ()
        candidates = [
            self._candidate(item) for item in self._get("search", {"q": clean})
        ]
        return tuple(candidate for candidate in candidates if candidate is not None)


def _name_similarity(left: str, right: str) -> float:
    left_clean = re.sub(r"\([^)]*\)|\[[^]]*]", " ", comparison_text(left))
    right_clean = re.sub(r"\([^)]*\)|\[[^]]*]", " ", comparison_text(right))
    return (
        SequenceMatcher(None, left_clean, right_clean).ratio()
        if left_clean and right_clean
        else 0.0
    )


def choose_metadata_candidate(
    candidates: tuple[LrcLibCandidate, ...],
    *,
    title: str,
    artist: str = "",
    duration_seconds: float = 0.0,
) -> tuple[LrcLibCandidate | None, float]:
    best: LrcLibCandidate | None = None
    best_score = 0.0
    bengali_expected = contains_bengali(f"{title} {artist}")
    for item in candidates:
        if not item.synced_lyrics or item.instrumental:
            continue
        title_score = _name_similarity(title, item.title)
        artist_score = _name_similarity(artist, item.artist) if artist.strip() else 0.65
        if title_score < 0.70 or (artist.strip() and artist_score < 0.42):
            continue
        if bengali_expected and not contains_bengali(item.synced_lyrics):
            continue
        duration_score = 0.65
        if duration_seconds > 0 and item.duration_seconds > 0:
            difference = abs(duration_seconds - item.duration_seconds)
            tolerance = max(8.0, duration_seconds * 0.08)
            if difference > max(20.0, duration_seconds * 0.15):
                continue
            duration_score = max(0.0, 1.0 - difference / tolerance)
        score = 0.58 * title_score + 0.24 * artist_score + 0.18 * duration_score
        if score > best_score:
            best, best_score = item, score
    return best, best_score


def transcript_phrases(transcript: str) -> tuple[str, ...]:
    lines = [normalize_text(line) for line in re.split(r"[\n।!?]+", transcript)]
    useful = [line for line in lines if 4 <= len(comparison_text(line).split()) <= 16]
    useful.sort(key=lambda line: (-len(comparison_text(line).split()), line))
    unique: list[str] = []
    for line in useful:
        normalized = comparison_text(line)
        if normalized and normalized not in {comparison_text(item) for item in unique}:
            unique.append(line)
        if len(unique) == 2:
            break
    return tuple(unique)


def choose_transcript_candidate(
    candidates: tuple[LrcLibCandidate, ...],
    *,
    transcript: str,
    duration_seconds: float,
    bengali_expected: bool,
) -> tuple[LrcLibCandidate | None, float]:
    evidence = set(comparison_text(transcript).split())
    if len(evidence) < 4:
        return None, 0.0
    best: LrcLibCandidate | None = None
    best_score = 0.0
    for item in candidates:
        if not item.synced_lyrics or item.instrumental:
            continue
        if bengali_expected and not contains_bengali(item.synced_lyrics):
            continue
        candidate_words = set(
            comparison_text(item.plain_lyrics or item.synced_lyrics).split()
        )
        if not candidate_words:
            continue
        overlap = len(evidence & candidate_words) / max(1, min(len(evidence), 80))
        duration_score = 0.5
        if duration_seconds > 0 and item.duration_seconds > 0:
            difference = abs(duration_seconds - item.duration_seconds)
            if difference > max(22.0, duration_seconds * 0.14):
                continue
            duration_score = max(
                0.0, 1.0 - difference / max(10.0, duration_seconds * 0.10)
            )
        score = 0.78 * overlap + 0.22 * duration_score
        if overlap >= 0.34 and score > best_score:
            best, best_score = item, score
    return best, best_score
