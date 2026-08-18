"""Lyr Online — minimal retrieval-first song-to-synced-lyrics Space."""

from __future__ import annotations

import logging
import os
import re
import time
import traceback
import uuid
from pathlib import Path

import gradio as gr
import spaces
from faster_whisper import WhisperModel

from lyr_service.audio import MAX_AUDIO_BYTES, MAX_AUDIO_SECONDS, load_audio
from lyr_service.domain import LyricsDocument
from lyr_service.identifier import ShazamAudioIdentifier
from lyr_service.provider import LrcLibClient
from lyr_service.recognizer import CpuWhisperRecognizer, LANGUAGE_CODES
from lyr_service.service import LyricsService, LyricsServiceError

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s :: %(message)s"
)
log = logging.getLogger("lyr-online")

MODEL_ID = os.getenv(
    "WHISPER_CPU_MODEL_ID",
    "dropbox-dash/faster-whisper-large-v3-turbo",
)
CPU_THREADS = max(1, min(8, os.cpu_count() or 2))
CPU_MODEL = None
CPU_RECOGNIZER = None
AUDIO_IDENTIFIER = ShazamAudioIdentifier()
MODEL_ERROR = ""
OUTPUT_ROOT = Path(os.getenv("LYR_OUTPUT_DIRECTORY", "/tmp/lyr-online"))
OUTPUT_TTL_SECONDS = 2 * 60 * 60
MAX_OUTPUT_FILES = 80
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")

try:
    log.info("Loading quota-free CPU Whisper %s with %s threads", MODEL_ID, CPU_THREADS)
    CPU_MODEL = WhisperModel(
        MODEL_ID,
        device="cpu",
        compute_type="int8",
        cpu_threads=CPU_THREADS,
        num_workers=1,
    )
    CPU_RECOGNIZER = CpuWhisperRecognizer(CPU_MODEL)
    log.info("CPU Whisper is ready")
except Exception as exc:  # noqa: BLE001 - model runtimes raise heterogeneous errors.
    MODEL_ERROR = f"{type(exc).__name__}: {exc}"
    log.error("CPU Whisper loading failed: %s", MODEL_ERROR)
    log.debug(traceback.format_exc())


@spaces.GPU(duration=1)
def _zero_gpu_registration_marker() -> str:
    """Keep the granted Space hardware valid; production endpoints never call this."""

    return "GPU capability registered; lyrics transcription uses quota-free CPU."


def _cleanup_outputs() -> None:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True, mode=0o700)
    now = time.time()
    files = sorted(
        (item for item in OUTPUT_ROOT.iterdir() if item.is_file()),
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    for index, item in enumerate(files):
        try:
            if (
                index >= MAX_OUTPUT_FILES
                or now - item.stat().st_mtime > OUTPUT_TTL_SECONDS
            ):
                item.unlink(missing_ok=True)
        except OSError:
            continue


def _save_lrc(document: LyricsDocument) -> str:
    _cleanup_outputs()
    stem = (
        _SAFE_NAME.sub("-", f"{document.artist}-{document.title}").strip("-._")[:120]
        or "lyrics"
    )
    destination = OUTPUT_ROOT / f"{stem}-{uuid.uuid4().hex[:8]}.lrc"
    destination.write_text(document.synced_lyrics, encoding="utf-8")
    try:
        destination.chmod(0o600)
    except OSError:
        pass
    return str(destination)


def _source_label(source: str) -> str:
    return {
        "lrclib_metadata": "exact LRCLIB match",
        "lrclib_audio_match": "audio-verified LRCLIB match",
        "whisper_ai": "Whisper AI transcription",
    }.get(source, source)


def _document_outputs(document: LyricsDocument):
    warning_text = ""
    if document.warnings:
        warning_text = "\n\n" + "\n".join(
            f"- {warning}" for warning in document.warnings
        )
    status = (
        f"## ✅ Lyrics ready\n\n**{document.title}** · {document.artist}<br>"
        f"Source: **{_source_label(document.source)}** · {len(document.lines)} synced lines"
        f"{warning_text}"
    )
    payload = {"ok": True, **document.to_dict()}
    return (
        status,
        document.synced_lyrics,
        document.plain_lyrics,
        payload,
        _save_lrc(document),
    )


def _error_outputs(message: str):
    clean = str(message).replace("`", "'")[:1_000]
    return (
        f"## Could not finish\n\n{clean}",
        "",
        "",
        {"ok": False, "error": clean},
        None,
    )


def lookup_lyrics_ui(title: str, artist: str, duration_seconds: float):
    """Find a strict synchronized match without starting transcription."""

    try:
        document = LyricsService(provider=LrcLibClient()).lookup(
            title,
            artist,
            max(0.0, float(duration_seconds or 0.0)),
        )
        return _document_outputs(document)
    except (LyricsServiceError, ValueError) as exc:
        return _error_outputs(str(exc))
    except Exception:
        log.exception("Unexpected lyrics lookup error")
        return _error_outputs("Unexpected online lookup error. Try again shortly.")


def transcribe_song_ui(audio_path: str, title: str, artist: str, language_label: str):
    """Prefer exact retrieval, then transcribe on quota-free CPU Whisper."""

    try:
        audio = load_audio(audio_path)
        document = LyricsService(
            provider=LrcLibClient(),
            recognizer=CPU_RECOGNIZER,
            identifier=AUDIO_IDENTIFIER,
        ).transcribe(
            audio,
            title=title or "",
            artist=artist or "",
            language_label=language_label or "Auto detect",
        )
        return _document_outputs(document)
    except (LyricsServiceError, ValueError) as exc:
        return _error_outputs(str(exc))
    except Exception:
        log.exception("Unexpected song transcription error")
        return _error_outputs("Unexpected AI processing error. Try another audio file.")


MODEL_STATUS = (
    f"Quota-free CPU Whisper ready · `{MODEL_ID}` · {CPU_THREADS} threads"
    if CPU_RECOGNIZER is not None
    else "CPU AI is temporarily unavailable; synchronized title lookup remains online."
)

CSS = """
:root { --ink:#f8fafc; --muted:#a8b3c7; --line:rgba(255,255,255,.11); --accent:#a78bfa; }
body { background:#090a0f !important; }
.gradio-container { max-width:860px !important; margin:auto !important; padding:18px 14px 70px !important; color:var(--ink) !important; }
#hero { padding:34px 30px !important; border:1px solid var(--line) !important; border-radius:26px !important; background:radial-gradient(circle at 90% 0,rgba(167,139,250,.18),transparent 36%),#11131b !important; }
#hero h1 { margin:6px 0 10px; font-size:clamp(38px,8vw,64px); letter-spacing:-.055em; line-height:.95; }
#hero p { color:var(--muted); max-width:650px; line-height:1.65; }
.kicker { color:#c4b5fd; font-size:12px; font-weight:900; letter-spacing:.17em; text-transform:uppercase; }
#work { margin-top:14px; padding:20px !important; border:1px solid var(--line) !important; border-radius:24px !important; background:#10121a !important; }
#extract, #lookup { min-height:52px !important; border:0 !important; border-radius:14px !important; font-weight:850 !important; }
#extract { color:#0b0713 !important; background:linear-gradient(110deg,#c4b5fd,#f0abfc) !important; }
#lookup { background:#1d2030 !important; }
textarea { font-family:ui-monospace,SFMono-Regular,Menlo,monospace !important; }
footer { display:none !important; }
@media(max-width:640px){ .gradio-container{padding:8px 8px 64px!important} #hero{padding:24px 18px!important;border-radius:20px!important} #work{padding:14px!important;border-radius:20px!important} button{min-height:50px!important} }
"""

with gr.Blocks(title="Lyr Online", analytics_enabled=False) as demo:
    gr.HTML(
        """<section id="hero"><div class="kicker">Online song → synced lyrics</div>
<h1>Lyr Online.</h1>
<p>Upload one song. Lyr detects its language, searches verified synchronized lyrics using AI evidence and a bounded recording fingerprint, then listens to the full song only when retrieval fails. Unusable mixed-script বাংলা output is rejected.</p></section>"""
    )
    with gr.Column(elem_id="work"):
        gr.Markdown("### 1 · Choose a song")
        audio_input = gr.Audio(
            label="MP3 · M4A · WAV · FLAC · OGG · AAC",
            type="filepath",
            sources=["upload"],
        )
        with gr.Row():
            title_input = gr.Textbox(
                label="Song title · optional",
                placeholder="Name improves instant matching",
            )
            artist_input = gr.Textbox(
                label="Artist · optional", placeholder="Artist name"
            )
        with gr.Row():
            language_input = gr.Dropdown(
                choices=list(LANGUAGE_CODES),
                value="Auto detect",
                label="Lyrics language",
            )
            duration_input = gr.Number(
                label="Duration seconds · only for name lookup",
                value=0,
                minimum=0,
                precision=1,
            )
        gr.Markdown(
            f"Online only · maximum **{MAX_AUDIO_SECONDS // 60} minutes / {MAX_AUDIO_BYTES // 1_000_000_000} GB** · large files are decoded memory-safely · audio is processed ephemerally · {MODEL_STATUS}"
        )
        with gr.Row():
            extract_button = gr.Button("2 · Extract synced lyrics", elem_id="extract")
            lookup_button = gr.Button("Find by name only", elem_id="lookup")

        status_output = gr.Markdown("### Ready\n\nChoose a song, then extract.")
        with gr.Tabs():
            with gr.Tab("Synced LRC"):
                lrc_output = gr.Textbox(
                    label="Timestamped lyrics", lines=18, interactive=False
                )
            with gr.Tab("Plain lyrics"):
                plain_output = gr.Textbox(label="Lyrics", lines=18, interactive=False)
            with gr.Tab("App/API data"):
                json_output = gr.JSON(label="Structured result")
        lrc_download = gr.File(label="Download .lrc", interactive=False)

    # Hidden and never called by the app/UI. Its only purpose is to preserve the Space's granted
    # ZeroGPU hardware registration while all real lyric work remains quota-free on CPU.
    gpu_marker_button = gr.Button(visible=False)
    gpu_marker_output = gr.Textbox(visible=False)
    gpu_marker_button.click(
        fn=_zero_gpu_registration_marker,
        inputs=[],
        outputs=[gpu_marker_output],
        api_name=False,
    )

    outputs = [status_output, lrc_output, plain_output, json_output, lrc_download]
    extract_button.click(
        fn=transcribe_song_ui,
        inputs=[audio_input, title_input, artist_input, language_input],
        outputs=outputs,
        api_name="transcribe_song",
    )
    lookup_button.click(
        fn=lookup_lyrics_ui,
        inputs=[title_input, artist_input, duration_input],
        outputs=outputs,
        api_name="lookup_lyrics",
    )


demo.queue(default_concurrency_limit=1, max_size=8)

if __name__ == "__main__":
    demo.launch(
        show_error=False,
        max_file_size=MAX_AUDIO_BYTES,
        theme=gr.themes.Base(primary_hue="violet", neutral_hue="slate"),
        css=CSS,
    )
