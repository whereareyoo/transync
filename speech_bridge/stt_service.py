from __future__ import annotations

from faster_whisper import WhisperModel
import numpy as np

# Быстрая английская модель: tiny.en
# Первый вызов может грузиться 5–10 секунд, дальше 1–3 сек на фразу.
_model = WhisperModel("tiny.en", device="cpu", compute_type="int8")

SAMPLE_RATE = 16000


def transcribe_pcm16_16k(pcm_bytes: bytes) -> str:
    """
    Вход: raw PCM16 mono 16 kHz (bytes)
    Выход: одна строка текста.
    """
    if not pcm_bytes:
        return ""

    # bytes -> float32 [-1, 1]
    arr = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0

    segments, _info = _model.transcribe(
        arr,
        beam_size=1,               # максимально быстро
        vad_filter=True,
        language="en",             # tiny.en = только английский
        condition_on_previous_text=False,
    )

    texts = [seg.text.strip() for seg in segments if seg.text.strip()]
    text = " ".join(texts)
    # нормализуем пробелы
    return " ".join(text.split())
