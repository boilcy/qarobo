from pathlib import Path

import httpx

client = httpx.Client(base_url="http://localhost:8000/")
model_id = "suronek/Kokoro-82M-v1.1-zh-ONNX"
voice_id = "af_heart"
res = client.post(
    "v1/audio/speech",
    json={
        "model": model_id,
        "voice": voice_id,
        "input": "Hello, world!",
        "response_format": "mp3",
        "speed": 1,
    },
).raise_for_status()
with Path("output.mp3").open("wb") as f:
    f.write(res.read())
