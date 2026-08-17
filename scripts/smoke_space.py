"""End-to-end smoke test for the deployed upload, queue, Whisper, and LRC path."""

from __future__ import annotations

import json
import time
from typing import Any

import requests
from huggingface_hub import HfApi

SPACE_ID = "madarauchihagmailcom/My"
SPACE_URL = "https://madarauchihagmailcom-my.hf.space"
# Public-domain 2:55 vocal recording of Bangladesh's national anthem from Wikimedia Commons.
TEST_AUDIO_URL = (
    "https://commons.wikimedia.org/wiki/Special:Redirect/file/"
    "Amar_Sonar_Bangla_-_official_vocal_music_of_the_"
    "National_anthem_of_Bangladesh.ogg"
)
USER_AGENT = "Lyr-Deployment-Smoke/1.0"


class SmokeTestError(RuntimeError):
    """The public Android-facing workflow did not complete successfully."""


def wait_for_space(
    api: HfApi,
    *,
    repo_id: str = SPACE_ID,
    timeout_seconds: int = 720,
) -> str:
    """Wait for the currently mirrored revision to become the running revision."""

    deadline = time.monotonic() + timeout_seconds
    last = "unknown"
    while time.monotonic() < deadline:
        target_sha = api.repo_info(repo_id=repo_id, repo_type="space").sha
        runtime = api.get_space_runtime(repo_id=repo_id)
        raw = runtime.raw or {}
        running_sha = str(raw.get("sha") or "")
        last = f"stage={runtime.stage}, target={target_sha}, running={running_sha}"
        if runtime.stage == "RUNNING" and running_sha == target_sha:
            return target_sha
        time.sleep(10)
    raise SmokeTestError(f"Space did not reach its mirrored revision: {last}")


def _request(method: str, url: str, **kwargs: Any) -> requests.Response:
    headers = {"User-Agent": USER_AGENT, **kwargs.pop("headers", {})}
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = requests.request(
                method,
                url,
                headers=headers,
                timeout=kwargs.pop("timeout", (30, 360)),
                **kwargs,
            )
            if response.status_code not in {429, 500, 502, 503, 504}:
                response.raise_for_status()
                return response
            last_error = SmokeTestError(
                f"{method} {url} returned HTTP {response.status_code}"
            )
        except requests.RequestException as exc:
            last_error = exc
        if attempt < 2:
            time.sleep((attempt + 1) * 8)
    raise SmokeTestError(f"Request failed after retries: {last_error}")


def _upload_audio(audio: bytes) -> str:
    response = _request(
        "POST",
        f"{SPACE_URL}/gradio_api/upload",
        files={"files": ("amar-sonar-bangla-public-domain.ogg", audio, "audio/ogg")},
    )
    payload = response.json()
    if not isinstance(payload, list) or not payload:
        raise SmokeTestError(f"Upload returned an invalid payload: {payload!r}")
    first = payload[0]
    if isinstance(first, dict):
        path = str(first.get("path") or "")
    else:
        path = str(first)
    if not path:
        raise SmokeTestError("Upload did not return a server file path.")
    return path


def _start_transcription(path: str) -> str:
    response = _request(
        "POST",
        f"{SPACE_URL}/gradio_api/call/v2/transcribe_song",
        headers={"Content-Type": "application/json"},
        data=json.dumps(
            {
                "audio_path": {
                    "path": path,
                    "meta": {"_type": "gradio.FileData"},
                },
                "title": "",
                "artist": "",
                "language_label": "Auto detect",
            }
        ).encode(),
    )
    event_id = str(response.json().get("event_id") or "")
    if not event_id:
        raise SmokeTestError("Transcription call did not return an event ID.")
    return event_id


def _await_transcription(event_id: str) -> tuple[str, dict[str, Any]]:
    response = _request(
        "GET",
        f"{SPACE_URL}/gradio_api/call/transcribe_song/{event_id}",
        headers={"Accept": "text/event-stream"},
        stream=True,
        timeout=(30, 900),
    )
    event = ""
    for raw_line in response.iter_lines(decode_unicode=True):
        line = raw_line or ""
        if line.startswith("event:"):
            event = line.partition(":")[2].strip()
        elif line.startswith("data:") and event == "error":
            raise SmokeTestError("Gradio reported an error event.")
        elif line.startswith("data:") and event == "complete":
            outputs = json.loads(line.partition(":")[2].strip())
            if not isinstance(outputs, list) or len(outputs) < 4:
                raise SmokeTestError(
                    "Completion payload did not contain endpoint outputs."
                )
            lrc = str(outputs[1] or "").strip()
            structured = outputs[3] if isinstance(outputs[3], dict) else {}
            return lrc, structured
    raise SmokeTestError("Transcription stream ended without a completion event.")


def run_deployed_smoke_test(api: HfApi) -> dict[str, Any]:
    revision = wait_for_space(api)
    audio_response = _request("GET", TEST_AUDIO_URL, timeout=(30, 90))
    if not 10_000 <= len(audio_response.content) <= 5_000_000:
        raise SmokeTestError("Public-domain test audio had an unexpected size.")
    path = _upload_audio(audio_response.content)
    event_id = _start_transcription(path)
    lrc, structured = _await_transcription(event_id)
    if not structured.get("ok") or not lrc or "[" not in lrc:
        raise SmokeTestError(
            "Full transcription did not return successful synchronized lyrics: "
            f"{structured!r}"
        )
    if structured.get("language") != "bn" or not any(
        "\u0980" <= character <= "\u09ff" for character in lrc
    ):
        diagnostics = {
            "language": structured.get("language"),
            "source": structured.get("source"),
            "title": structured.get("title"),
            "artist": structured.get("artist"),
            "warnings": structured.get("warnings"),
            "lrc_excerpt": lrc[:240],
        }
        raise SmokeTestError(
            "Auto detection did not return native Bengali-script synchronized lyrics: "
            f"{json.dumps(diagnostics, ensure_ascii=False)}"
        )
    title = str(structured.get("title") or "")
    artist = str(structured.get("artist") or "")
    if "amar sonar bangla" not in title.casefold() or artist.casefold().startswith(
        "unknown"
    ):
        raise SmokeTestError(
            "Online identity refill did not recover Amar Sonar Bangla and its artist: "
            f"title={title!r}, artist={artist!r}, "
            f"warnings={structured.get('warnings')!r}."
        )
    bengali_characters = sum(
        "\u0980" <= character <= "\u09ff" for character in lrc
    )
    replacement_characters = lrc.count("\ufffd")
    line_count = len(structured.get("lines") or [])
    if (
        bengali_characters < 40
        or line_count < 5
        or replacement_characters > max(2, bengali_characters // 20)
    ):
        raise SmokeTestError(
            "Bengali transcription did not contain enough usable native-script lyrics: "
            f"Bengali characters={bengali_characters}, lines={line_count}, "
            f"replacement characters={replacement_characters}."
        )
    result = {
        "revision": revision,
        "source": structured.get("source"),
        "language": structured.get("language"),
        "title": structured.get("title"),
        "artist": structured.get("artist"),
        "lines": line_count,
        "bengali_characters": bengali_characters,
        "audio_bytes": len(audio_response.content),
        "warnings": structured.get("warnings"),
        "lrc_excerpt": lrc[:360],
    }
    print(f"Deployed upload/transcription smoke passed: {json.dumps(result)}")
    return result
