# speech_bridge/main.py
import os
import base64
import json
import traceback
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Body, Query
from fastapi.responses import HTMLResponse, FileResponse, PlainTextResponse
from starlette.background import BackgroundTask
from starlette.routing import Route, WebSocketRoute

from mt_service import translate as mt_translate
from tts_service import synthesize_wav
from stt_service import transcribe_pcm16_16k

from typing import Dict, Set, Any
from fastapi import Request
from urllib.parse import quote

app = FastAPI(title="Speech Bridge — STT → MT → TTS (demo)")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/debug/routes")
def debug_routes():
    http_routes = [r.path for r in app.router.routes if isinstance(r, Route)]
    ws_routes = [r.path for r in app.router.routes if isinstance(r, WebSocketRoute)]
    return {"http": http_routes, "ws": ws_routes}


@app.post("/translate")
def translate_endpoint(
    text: str = Body(..., embed=True),
    src: str = Body("en"),
    tgt: str = Body("ru"),
):
    return {"translated": mt_translate(text, src, tgt)}

@app.post("/process")
def process(
    audio_b64: str = Body(...),
    src: str = Body("en"),
    tgt: str = Body("ru"),
):
    try:
        pcm = base64.b64decode(audio_b64)

        # STT — у тебя возвращает СТРОКУ
        original = transcribe_pcm16_16k(pcm).strip()

        if not original:
            return {
                "ok": False,
                "error": "STT empty",
                "original": "",
                "translated": ""
            }

        # MT
        translated = mt_translate(original, src, tgt)

        return {
            "ok": True,
            "original": original,
            "translated": translated
        }

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        print(tb)
        return PlainTextResponse(tb, status_code=500)


@app.get("/speak")
def speak(text: str = Query(...), lang: str = Query("en")):
    try:
        path = synthesize_wav(text, lang=lang)
        return FileResponse(
            path,
            media_type="audio/wav",
            filename="tts.wav",
            background=BackgroundTask(lambda: os.remove(path))
        )
    except Exception as e:
        return PlainTextResponse(str(e), status_code=500)


@app.get("/stt_demo", response_class=HTMLResponse)
def stt_demo():
    return r"""
    <!doctype html>
<html>
<head>
<meta charset="utf-8"/>
<title>Speech Bridge Demo</title>
<style>
  body{font-family:system-ui,sans-serif;margin:24px}
  #log{white-space:pre-wrap;border:1px solid #ccc;padding:12px;border-radius:8px;min-height:180px}
  button{padding:10px 16px;margin-right:8px}
  label{margin-left:10px}
  select{margin-left:6px}
  .row{margin:12px 0}
</style>
</head>
<body>
  <h2>Speech Bridge: STT → MT → TTS (stable demo)</h2>
  <p>Start → скажи фразу → Stop → увидишь текст и услышишь перевод.</p>

  <div class="row">
    <button id="startBtn">Start</button>
    <button id="stopBtn" disabled>Stop</button>

    <label>STT:
      <select id="sttSel">
        <option value="en" selected>en</option>
        <option value="ru">ru</option>
      </select>
    </label>

    <label>Translate:
      <select id="srcSel">
        <option value="en" selected>en</option>
        <option value="ru">ru</option>
      </select>
      →
      <select id="tgtSel">
        <option value="ru" selected>ru</option>
        <option value="en">en</option>
      </select>
    </label>
  </div>

  <div id="log"></div>

<script>
let ac=null, proc=null, srcNode=null, mic=null;
let chunks = [];
const audioEl = new Audio();
audioEl.autoplay = true;

function log(s){
  const el=document.getElementById("log");
  el.textContent += s + "\n";
  el.scrollTop = el.scrollHeight;
}

function downsampleTo16k(float32Audio, inRate){
  if (inRate === 16000) return float32Audio;
  const ratio = inRate / 16000;
  const newLen = Math.round(float32Audio.length / ratio);
  const result = new Float32Array(newLen);
  let offRes = 0, offBuf = 0;
  while (offRes < newLen){
    const nextOffBuf = Math.round((offRes + 1) * ratio);
    let accum=0, count=0;
    for (let i=offBuf; i<nextOffBuf && i<float32Audio.length; i++){
      accum += float32Audio[i]; count++;
    }
    result[offRes++] = accum / (count || 1);
    offBuf = nextOffBuf;
  }
  return result;
}

function floatToInt16(float32){
  const out = new Int16Array(float32.length);
  for (let i=0;i<float32.length;i++){
    let s = Math.max(-1, Math.min(1, float32[i]));
    out[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
  }
  return out;
}

function mergeInt16(chunks){
  const total = chunks.reduce((a,b)=>a+b.length, 0);
  const merged = new Int16Array(total);
  let off=0;
  for (const c of chunks){ merged.set(c, off); off += c.length; }
  return merged;
}

async function int16ToBase64(int16arr){
  const blob = new Blob([int16arr.buffer], {type:"application/octet-stream"});
  return await new Promise((resolve, reject)=>{
    const fr = new FileReader();
    fr.onload = () => {
      const s = fr.result;
      resolve(s.substring(s.indexOf(",")+1));
    };
    fr.onerror = reject;
    fr.readAsDataURL(blob);
  });
}

async function start(){
  document.getElementById("startBtn").disabled = true;
  document.getElementById("stopBtn").disabled = false;
  document.getElementById("log").textContent = "";
  chunks = [];

  ac = new (window.AudioContext||window.webkitAudioContext)({sampleRate:48000});
  mic = await navigator.mediaDevices.getUserMedia({audio:true});
  srcNode = ac.createMediaStreamSource(mic);

  const bufSize = 4096;
  proc = ac.createScriptProcessor(bufSize, 1, 1);
  srcNode.connect(proc);
  proc.connect(ac.destination);

  proc.onaudioprocess = (e)=>{
    const input = e.inputBuffer.getChannelData(0);
    const down = downsampleTo16k(input, ac.sampleRate);
    const pcm16 = floatToInt16(down);
    chunks.push(pcm16);
  };

  log("[recording] speak now…");
}

async function stop(){
  document.getElementById("startBtn").disabled = false;
  document.getElementById("stopBtn").disabled = true;

  try{ proc && proc.disconnect(); }catch(e){}
  try{ srcNode && srcNode.disconnect(); }catch(e){}
  try{ mic && mic.getTracks().forEach(t=>t.stop()); }catch(e){}
  try{ ac && ac.close(); }catch(e){}

  if (chunks.length === 0){
    log("No audio captured");
    return;
  }

  const merged = mergeInt16(chunks);
  chunks = [];

  log(`[client] sending audio bytes=${merged.byteLength}`);

  const b64 = await int16ToBase64(merged);

  const stt = document.getElementById("sttSel").value;
  const src = document.getElementById("srcSel").value;
  const tgt = document.getElementById("tgtSel").value;

  // 1) STT + MT on server
  const r = await fetch("/process", {
    method: "POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify({audio_b64: b64, stt_lang: stt, src: src, tgt: tgt})
  });
  const j = await r.json();

  if(!j.ok){
    log("ERR: " + (j.error || "process failed"));
    return;
  }

  log("✓ STT: " + j.original);
  log("→ MT: " + j.translated);

  // 2) TTS
  const url = `/speak?lang=${encodeURIComponent(tgt)}&text=${encodeURIComponent(j.translated)}`;
  log("⏳ speaking…");
  const rr = await fetch(url);
  if(!rr.ok){
    log("TTS error: " + await rr.text());
    return;
  }
  const blob = await rr.blob();
  const objUrl = URL.createObjectURL(blob);

  audioEl.pause();
  audioEl.src = objUrl;
  await audioEl.play();

  setTimeout(()=>URL.revokeObjectURL(objUrl), 30000);
  log("🔊 done");
}

document.getElementById("startBtn").onclick = start;
document.getElementById("stopBtn").onclick = stop;
</script>
</body>
</html>
    """


@app.websocket("/ws/stt")
async def ws_stt(ws: WebSocket):
    """
    Принимаем PCM16@16k mono (base64) чанками.
    Можно прислать cfg: {type:"cfg", language:"en"/"ru"} чтобы зафиксировать язык.
    На flush: распознаём всё накопленное и отдаём одну финальную строку.
    """
    await ws.accept()
    print("[ws] connected")

    buf = bytearray()
    language = None

    try:
        while True:
            raw = await ws.receive_text()

            # cfg
            if raw.startswith('{"type":"cfg"'):
                try:
                    obj = json.loads(raw)
                    language = obj.get("language") or None
                except Exception:
                    language = None
                await ws.send_text('{"type":"ack","msg":"cfg_set"}')
                continue

            # audio_chunk
            if raw.startswith('{"type":"audio_chunk"'):
                key = '"pcm_base64":"'
                i = raw.find(key)
                if i != -1:
                    j = raw.find('"', i + len(key))
                    b64 = raw[i + len(key):j]
                    chunk = base64.b64decode(b64)
                    buf.extend(chunk)
                    print(f"[ws] got audio_chunk bytes={len(chunk)} total_buf={len(buf)}")
                continue

            # flush
            if raw == '{"type":"flush"}':
                print(f"[ws] flush buf={len(buf)} bytes")
                text_out = ""
                if buf:
                    segs = transcribe_pcm16_16k(bytes(buf), language=language)
                    buf.clear()
                    # transcribe_pcm16_16k возвращает список сегментов (text,start,end)
                    if segs:
                        text_out = segs[-1][0]  # последняя фраза
                        print("[ws] final:", text_out)

                await ws.send_text(json.dumps({"type": "final_text", "text": text_out}))
                await ws.send_text('{"type":"ack","msg":"flushed"}')
                continue

    except WebSocketDisconnect:
        print("[ws] closed")
