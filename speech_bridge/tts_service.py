from __future__ import annotations
from pathlib import Path
import subprocess
import sys
import tempfile

BASE_DIR = Path(__file__).parent
MODELS_DIR = BASE_DIR / "models" / "piper"

MODEL_BY_LANG = {
    "en": MODELS_DIR / "en_US-amy-medium.onnx",
    "ru": MODELS_DIR / "ru_RU-irina-medium.onnx",
}

def _piper_exe() -> str:
    # запускаем piper из текущего venv/интерпретатора
    # На Windows обычно есть .venv\Scripts\piper.exe, но надёжнее так:
    scripts = Path(sys.executable).parent
    exe = scripts / "piper.exe"
    return str(exe)

def synthesize_wav(text: str, lang: str = "en") -> str:
    text = (text or "").strip()
    if not text:
        raise ValueError("Empty text")

    lang = (lang or "en").lower()
    model_path = MODEL_BY_LANG.get(lang, MODEL_BY_LANG["en"])
    if not model_path.exists():
        raise FileNotFoundError(f"Model not found: {model_path}")

    # временный wav-файл
    fd, out_path = tempfile.mkstemp(suffix=".wav")
    # fd закрываем, piper сам запишет файл по пути
    try:
        import os
        os.close(fd)
    except Exception:
        pass

    cmd = [
        _piper_exe(),
        "--model", str(model_path),
        "--output_file", out_path,
    ]

    # Piper читает текст из stdin
    proc = subprocess.run(
        cmd,
        input=text,
        text=True,
        capture_output=True,
    )

    if proc.returncode != 0:
        # удалим пустой/битый файл, если создался
        try:
            Path(out_path).unlink(missing_ok=True)
        except Exception:
            pass
        raise RuntimeError(f"Piper CLI error:\n{proc.stderr or proc.stdout}")

    return out_path
