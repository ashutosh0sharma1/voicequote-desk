"""One bounded offline ASR process; never downloads or uses a cloud provider."""
import json
import os
import sys
os.environ["HF_HUB_OFFLINE"] = "1"
os.environ["TRANSFORMERS_OFFLINE"] = "1"
from faster_whisper import WhisperModel

if __name__ == "__main__":
    model = WhisperModel(sys.argv[1], device="cpu", compute_type="int8", local_files_only=True, cpu_threads=4)
    segments, info = model.transcribe(sys.argv[2], language="en", beam_size=3, vad_filter=False)
    if info.duration > 90:
        raise ValueError("Audio must be at most 90 seconds.")
    rows = [{"start": round(s.start, 2), "end": round(s.end, 2), "text": s.text.strip()} for s in segments]
    print(json.dumps({"transcript": " ".join(s["text"] for s in rows), "segments": rows,
                      "duration": round(info.duration, 2), "model": "faster-whisper-small / CPU int8", "offline": True}))
