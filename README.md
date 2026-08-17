---
title: Lyr Online
emoji: 🎵
colorFrom: purple
colorTo: pink
sdk: gradio
app_file: app.py
python_version: 3.12.12
pinned: false
license: apache-2.0
models:
  - Systran/faster-whisper-small
---

# Lyr Online

A minimal online song-to-synced-lyrics backend and mobile web interface for the Android project [`tajhatAti/Lyr`](https://github.com/tajhatAti/Lyr).

The former GitHub repository explorer has been removed. This Space now does one job:

1. accept one song;
2. prefer a strict synchronized LRCLIB result when title/artist metadata identifies it safely;
3. otherwise listen with multilingual int8 Faster-Whisper on the 16 GB CPU;
4. use recognized lyric evidence for one final strict synchronized lookup;
5. fall back to an editable AI-generated LRC with explicit cue endings;
6. return plain lyrics, synchronized LRC, structured app data, and a downloadable `.lrc` file.

## Reviewed Lyr branches

The implementation was designed after reviewing both public branches on 2026-08-17:

- `main` — four early Python/Telegram files; it is not the Android product and contains exposed credentials that must be revoked.
- `arena/019ffc7c-lyr` — the real native Kotlin music player, floating overlay, LRCLIB retrieval, local Whisper pipeline, LRC parser, regression tests, and successful APK workflow.

The online architecture intentionally preserves the stronger branch's retrieval-first strategy and Lyr-compatible empty timestamp markers while moving heavy transcription from the phone to this Space.

## User flow

- **Known title:** enter title/artist and use **Find by name only**. This is fast and uses no transcription compute.
- **Unknown or unreliable metadata:** upload MP3/M4A/WAV/FLAC/OGG/AAC and use **Extract synced lyrics**.
- **বাংলা:** choose বাংলা to force Bengali transcription without translation.
- Download the `.lrc`, copy plain lyrics, or consume the structured API result.

This is deliberately online-only. There is no local model download and no offline AI fallback.

## Android app and APK

The complete native app is in [`android/`](android). It keeps Lyr's music player, synchronized and floating lyrics, Bengali handling, LRC timing/editor, local saved lyrics, and automatic lyrics flow. Smart Lyrics now performs strict online lookup first and securely uploads audio to this Space only when transcription is needed.

Every push changing `android/**` runs `.github/workflows/build-android-apk.yml`. A successful run provides:

- the `lyr-online-debug-apk` Actions artifact; and
- `app-debug.apk` attached to a GitHub prerelease tagged `lyr-online-<run number>`.

See [`docs/ANDROID_INTEGRATION.md`](docs/ANDROID_INTEGRATION.md) for architecture, privacy behavior, local build instructions, and installation guidance.

## Public Gradio API

- `/lookup_lyrics(title, artist, duration_seconds)`
- `/transcribe_song(audio_path, title, artist, language_label)`

The Android client should call lookup first and upload audio only when lookup has no trustworthy result. See [`docs/ANDROID_INTEGRATION.md`](docs/ANDROID_INTEGRATION.md).

## Bounds

| Resource | Bound |
|---|---:|
| Audio size | 16 GB |
| Audio duration | 8 minutes |
| CPU inference concurrency | 1 |
| Queue size | 8 |
| LRCLIB results per request | 20 |
| Recognized-text follow-up queries | 2 |
| LRC output retention | 2 hours / 80 files |
| GPU quota required | No |

Audio is decoded ephemerally through bounded 16 kHz mono FFmpeg output and is not published. Large source files stay on ephemeral disk instead of expanding at their original sample rate in RAM. Generated LRC files receive randomized names and expire. Singing transcription is inherently less reliable than speech recognition; accompaniment, reverb, language, and vocal clarity affect accuracy.

## Local tests

```bash
python -m venv .venv
.venv/bin/pip install "gradio>=6.24,<7" "requests>=2.32,<3" "ruff>=0.11,<1"
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/ruff check app.py lyr_service tests scripts
python -m compileall -q app.py lyr_service scripts tests
```

## Deployment

Every push to `arena/01a00b5b-huggingface` is validated and mirrored to `madarauchihagmailcom/My` by `.github/workflows/sync-to-huggingface.yml`. The workflow preserves the Space registration, runs transcription on its free 16 GB host CPU, and requires a real audio-to-LRC smoke test after syncing.

## Security

- No Telegram token, GitHub token, visitor credential, shell, tunnel, proxy, or remote-management function.
- Network calls are limited to the fixed HTTPS LRCLIB API plus Hugging Face model retrieval managed by Transformers.
- Upload size/duration and provider response sizes are bounded.
- Lyrics lookup/transcription is for audio the user is allowed to process.

See [`SECURITY.md`](SECURITY.md) and [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).
