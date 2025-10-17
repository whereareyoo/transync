# main.py (фрагмент)
from fastapi import FastAPI, Query
from fastapi.responses import Response, PlainTextResponse, HTMLResponse
import os, subprocess, shutil, tempfile

app = FastAPI(title="Speech Bridge", version="0.1")

MODEL_EN = "models/piper/en_US-amy-medium.onnx"
TMP_DIR = os.path.join(os.getcwd(), "_tmp")  # локальная папка для временных файлов
os.makedirs(TMP_DIR, exist_ok=True)

@app.get("/health")
def health():
    return {"status": "ok", "piper": shutil.which("piper") is not None}

@app.get("/speak2")
def speak2(text: str = Query(..., min_length=1)):
    if not shutil.which("piper"):
        return PlainTextResponse("piper not found in PATH (check venv)", status_code=500)

    # создаём временный файл В НАШЕЙ ПАПКЕ, а не в системном TEMP
    fd, tmp_wav = tempfile.mkstemp(prefix="tts_", suffix=".wav", dir=TMP_DIR)
    os.close(fd)  # сразу закроем дескриптор, чтобы Piper мог писать

    try:
        # пишем напрямую в файл (без stdout)
        cmd = ["piper", "--model", MODEL_EN, "--output_file", tmp_wav]
        proc = subprocess.run(cmd, input=(text + "\n").encode("utf-8"),
                              capture_output=True)
        if proc.returncode != 0:
            err = proc.stderr.decode("utf-8", errors="ignore")
            return PlainTextResponse(f"Piper error (code {proc.returncode}): {err}", status_code=500)

        # читаем байты и отдаем как единый WAV
        with open(tmp_wav, "rb") as f:
            data = f.read()
        if not data.startswith(b"RIFF"):
            return PlainTextResponse("Generated file is not WAV/RIFF", status_code=500)

        return Response(
            content=data,
            media_type="audio/wav",
            headers={
                "Content-Length": str(len(data)),
                "Content-Disposition": 'inline; filename="tts.wav"',
            },
        )
    finally:
        # подчистим временный файл
        try:
            os.remove(tmp_wav)
        except OSError:
            pass

@app.get("/test", response_class=HTMLResponse)
def test(text: str = "Hello from Piper"):
    # Страница с плеером — вручную нажми Play
    from urllib.parse import quote
    return f"""
    <html><body style="font-family:sans-serif">
      <h3>TTS test</h3>
      <audio controls src="/speak2?text={quote(text)}"></audio>
    </body></html>
    """
