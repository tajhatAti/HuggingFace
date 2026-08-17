# Android integration contract

Target source: `tajhatAti/Lyr`, branch `arena/019ffc7c-lyr`.

## Intended behavior

1. Keep playback, MediaStore, overlay, settings, queue, LRC parser, corrections and caching native.
2. Keep the existing strict metadata lookup.
3. Remove the local Whisper dependency, model downloader, local WAV chunk inference and offline-AI claims.
4. When metadata lookup fails, upload the selected audio to Lyr Online.
5. Parse the structured result, save `synced_lyrics` through the existing private cache, and refresh Live Lyrics/overlay.
6. Show a clear network-required message when offline; do not silently fall back to a local model.

## Space endpoints

The public Gradio schema is available from:

```text
GET https://madarauchihagmailcom-my.hf.space/gradio_api/info
```

Named endpoints:

```text
/lookup_lyrics
/transcribe_song
```

The recommended Android implementation follows Gradio's upload + queued-call protocol rather than inventing an unrestricted custom proxy. The response's structured JSON object contains:

```json
{
  "ok": true,
  "source": "lrclib_metadata | lrclib_audio_match | whisper_ai",
  "title": "...",
  "artist": "...",
  "language": "bn | en | auto | unknown",
  "duration_seconds": 180.0,
  "plain_lyrics": "...",
  "synced_lyrics": "[00:12.00] ...",
  "lines": [{"start_ms": 12000, "end_ms": 15400, "text": "..."}],
  "provider_id": 123,
  "confidence": 0.91,
  "warnings": []
}
```

## Required Android source changes

- Add `OnlineLyricsService.kt` for HTTPS upload/call/status handling.
- Change `OnDeviceAiLyricsManager` into an online job coordinator or replace it with `OnlineAiLyricsManager` while retaining its observable job-state contract.
- Remove `dev.ffmpegkit-maintained:whisper-android` and the `arm64-v8a` restriction if no other native library needs it.
- Remove model download/delete controls and text.
- Keep the eight-minute policy, foreground data-sync notification, cancellation, durable result adoption, and regression tests.
- Update README privacy language: the song is uploaded ephemerally to the public owner's Hugging Face Space.

## Build

The existing `.github/workflows/build-apk.yml` on the Lyr branch already builds, tests, uploads `lyrics-overlay-debug-apk`, and attaches `app-debug.apk` to a prerelease. After Android integration is committed to that branch, the user can obtain the real APK from the successful Actions run.

This checkout is locked to the Hugging Face repository branch, so Android source cannot be pushed to the separate Lyr repository from this session. Open a new Arena Agent Mode session on `tajhatAti/Lyr` to apply and test the client changes without manually editing files.
