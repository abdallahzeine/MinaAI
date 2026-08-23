# Reference Voice for Voice-Cloning TTS Engines

This directory holds reference voice assets for cloning-based TTS engines.

## Assets

- `reference.wav` — Optional WAV file containing the target voice sample to clone.
- `reference.txt` — Optional verbatim transcript of `reference.wav`.

Defaults:

```
Backend/assets/reference.wav
Backend/assets/reference.txt
```

Non-cloning TTS engines ignore these files.

## Override via Environment Variables

If your concrete TTS provider supports voice cloning reference overrides, you can set:

```
TTS_REF_AUDIO=C:\path\to\your_voice.wav
TTS_REF_TEXT=ويدقق النظر في القرآن الكريم ...
# OR
TTS_REF_TEXT_FILE=C:\path\to\transcript.txt
```

## Plugging in a TTS Engine

1. Create a provider subclassing `BaseTTSProvider` in `Backend/main/core/`.
2. Implement `ensure_loaded()`, `is_available()`, and `synthesize()`.
3. Register it using `register_provider("backend_name", YourProviderClass)`.
4. Set `TTS_BACKEND=backend_name` in `Backend/.env`.
