# Android client and online integration

The complete Android project now lives in this repository at [`android/`](../android). It was based on the functional `tajhatAti/Lyr` branch `arena/019ffc7c-lyr`, then converted from local Whisper to the live Lyr Online backend.

## Preserved native features

Playback, MediaStore scanning, queue management, synchronized/live lyrics, floating overlay, LRC parsing and editing, timing corrections, Bengali script checks, same-folder LRC support, and saved lyric caches remain native Android features. Only song extraction/transcription moved online.

## Online-only pipeline

`OnlineLyricsClient.kt` uses the public Gradio queued API at the fixed HTTPS Space:

```text
https://madarauchihagmailcom-my.hf.space
```

For each Smart Lyrics request it:

1. calls `/lookup_lyrics` with title, artist, and duration;
2. immediately returns a strict synchronized LRCLIB match when available;
3. otherwise uploads the selected audio through `/gradio_api/upload`;
4. calls `/transcribe_song`; the server previews three regions, detects language, identifies title/artist and searches again before any full-song pass;
5. forces Bengali decoding after automatic `bn` detection, preventing avoidable Banglish output;
6. validates that the structured result is successful and contains parseable LRC;
7. returns it through the existing `OnDeviceAiLyricsManager` listener/state contract, allowing the player and editor to adopt the result without architectural regressions.

The legacy manager class name and some result enum names are intentionally retained for source compatibility. The implementation does not decode audio, download model weights, load native Whisper, or run local AI. Known pasted lyrics can still be aligned to server-provided timing using a small deterministic Kotlin text/timing algorithm.

## Privacy and bounds

- Internet is required.
- When metadata does not produce a trustworthy match, the song is uploaded ephemerally to the owner's Hugging Face Space.
- No model is stored on the phone.
- Upload size is capped at 16 GB; song duration remains capped at eight minutes for bounded song processing.
- The client uses HTTPS only, bounded timeouts, one job at a time, cancellation, and limited retries while a sleeping Space wakes.
- The backend searches LRCLIB before starting quota-free CPU transcription.

## Build and APK

From the repository root:

```bash
cd android
./gradlew clean testDebugUnitTest assembleDebug
```

Output:

```text
android/app/build/outputs/apk/debug/app-debug.apk
```

A push that changes `android/**` triggers `.github/workflows/build-android-apk.yml`. It runs the same tests/build, uploads the `lyr-online-debug-apk` Actions artifact for 30 days, and attaches `app-debug.apk` to a GitHub prerelease tagged `lyr-online-<run number>`.

To install manually, download the APK on the Android phone, allow installation from that browser or file manager when Android asks, then open the APK. Android 7.0 (API 24) or newer is supported. Existing installs made from a differently signed build may need to be uninstalled first.

## Backend response

The structured output consumed by Android includes:

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

The authoritative live schema remains available at:

```text
GET https://madarauchihagmailcom-my.hf.space/gradio_api/info
```
