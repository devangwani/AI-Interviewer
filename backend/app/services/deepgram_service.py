from deepgram import DeepgramClient, LiveTranscriptionEvents, LiveOptions
from app.core.config import settings

_client: DeepgramClient | None = None


def get_deepgram_client() -> DeepgramClient:
    global _client
    if _client is None:
        _client = DeepgramClient(settings.DEEPGRAM_API_KEY)
    return _client


def build_live_options() -> LiveOptions:
    """Raw PCM / linear16 options — kept for the legacy /stream endpoint."""
    return LiveOptions(
        model="nova-2",
        language="en-US",
        smart_format=True,
        interim_results=True,
        utterance_end_ms=1000,
        vad_events=True,
        encoding="linear16",
        sample_rate=16000,
        channels=1,
    )


def build_live_options_webm() -> LiveOptions:
    """Options for WebM/Opus audio from MediaRecorder.
    No encoding/sample_rate hints — Deepgram reads them from the container header."""
    return LiveOptions(
        model="nova-2",
        language="en-US",
        smart_format=True,
        interim_results=True,
        utterance_end_ms=1000,
        vad_events=True,
    )


async def transcribe_audio_bytes(audio_bytes: bytes) -> str:
    """One-shot transcription for pre-recorded audio chunks."""
    client = get_deepgram_client()
    response = await client.listen.asyncrest.v("1").transcribe_file(
        {"buffer": audio_bytes, "mimetype": "audio/wav"},
        {"model": "nova-2", "smart_format": True, "language": "en-US"},
    )
    try:
        return response["results"]["channels"][0]["alternatives"][0]["transcript"]
    except (KeyError, IndexError):
        return ""
