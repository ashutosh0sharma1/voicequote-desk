import csv
import hashlib
import io
import json
import os
import sqlite3
import subprocess
import sys
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ConfigDict, StrictInt
from engine import CATALOG, analyze, apply_resolutions

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
DATA.mkdir(exist_ok=True)
(DATA / "uploads").mkdir(exist_ok=True)
DB = Path(os.environ.get("VOICEQUOTE_DB", DATA / "quotes.sqlite3"))
ASR_LOCK = threading.Lock()
app = FastAPI(title="VoiceQuote Desk", version="1.0.0")

@contextmanager
def connect():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    try:
        with db:
            yield db
    finally:
        db.close()

def initialize():
    with connect() as db:
        db.execute("CREATE TABLE IF NOT EXISTS analyses(id TEXT PRIMARY KEY, transcript TEXT NOT NULL, source TEXT NOT NULL, audio_asset TEXT, result TEXT NOT NULL, created_at TEXT NOT NULL)")
        db.execute("CREATE TABLE IF NOT EXISTS quotes(id TEXT PRIMARY KEY, request_id TEXT UNIQUE NOT NULL, payload_hash TEXT NOT NULL, analysis_id TEXT NOT NULL, original_transcript TEXT NOT NULL, source TEXT NOT NULL, audio_asset TEXT, validated_fields TEXT NOT NULL, resolutions TEXT NOT NULL, created_at TEXT NOT NULL)")
initialize()

def now():
    return datetime.now(timezone.utc).isoformat()

def cached_model():
    cache = Path.home() / ".cache/huggingface/hub/models--Systran--faster-whisper-small/snapshots"
    return next((p for p in cache.glob("*") if (p / "model.bin").is_file() and (p / "config.json").is_file()), None)

def create_analysis(text, source, asset=None, asr=None):
    try:
        result = analyze(text)
    except ValueError as e:
        raise HTTPException(422, str(e))
    item = {"id": uuid.uuid4().hex, "transcript": text, "source": source, "audio_asset": asset,
            "result": result, "created_at": now(), "asr": asr}
    with connect() as db:
        db.execute("INSERT INTO analyses VALUES (?,?,?,?,?,?)", (item["id"], text, source, asset, json.dumps(result), item["created_at"]))
    return item

class TranscriptIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    transcript: str = Field(min_length=1, max_length=10000)

class Resolution(BaseModel):
    model_config = ConfigDict(extra="forbid")
    index: StrictInt
    product_id: str
    quantity: StrictInt = Field(ge=1, le=1000)

class SaveIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    analysis_id: str
    request_id: str = Field(min_length=8, max_length=100)
    resolutions: list[Resolution] = Field(default_factory=list, max_length=50)

@app.get("/api/health")
def health():
    return {"status": "ok", "offline": True, "model_cached": cached_model() is not None, "catalog": "synthetic fixture", "database": "SQLite"}

@app.get("/api/catalog")
def catalog():
    return {"items": CATALOG, "currency": "GBP", "notice": "Synthetic fixture catalog. No supplier or client integration. Tax and delivery excluded."}

@app.get("/api/cases")
def cases():
    return json.loads((BASE / "fixtures.json").read_text())

@app.post("/api/analyze")
def transcript(body: TranscriptIn):
    return create_analysis(body.transcript, "typed transcript")

@app.post("/api/audio")
def audio(file: UploadFile = File(...)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".wav", ".mp3", ".m4a", ".flac", ".ogg"}:
        raise HTTPException(422, "Use WAV, MP3, M4A, FLAC or OGG audio.")
    content = file.file.read(15 * 1024 * 1024 + 1)
    if not content or len(content) > 15 * 1024 * 1024:
        raise HTTPException(422, "Choose a nonempty audio file smaller than 15 MB.")
    model = cached_model()
    if model is None:
        raise HTTPException(503, "Cached offline model unavailable. Use transcript input; no model will be downloaded.")
    if not ASR_LOCK.acquire(blocking=False):
        raise HTTPException(409, "Another local transcription is running. Try again when it finishes.")
    asset = uuid.uuid4().hex + suffix
    path = DATA / "uploads" / asset
    try:
        path.write_bytes(content)
        run = subprocess.run([sys.executable, str(BASE / "asr_worker.py"), str(model), str(path)], capture_output=True, text=True, timeout=75, cwd=BASE)
        if run.returncode:
            path.unlink(missing_ok=True)
            raise HTTPException(422, "Offline transcription failed. Check the audio format and 90-second limit; transcript mode is available.")
        result = json.loads(run.stdout.strip().splitlines()[-1])
        return create_analysis(result["transcript"], "offline audio transcription", asset, result)
    except subprocess.TimeoutExpired:
        path.unlink(missing_ok=True)
        raise HTTPException(503, "Local transcription exceeded 75 seconds and was stopped. Use transcript input or a shorter clip.")
    finally:
        ASR_LOCK.release()

def quote_dict(row):
    result = dict(row)
    result.pop("payload_hash", None)
    result["validated_fields"] = json.loads(result["validated_fields"])
    result["resolutions"] = json.loads(result["resolutions"])
    return result

@app.post("/api/quotes")
def save_quote(body: SaveIn):
    payload = body.model_dump()
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        previous = db.execute("SELECT * FROM quotes WHERE request_id=?", (body.request_id,)).fetchone()
        if previous:
            if previous["payload_hash"] != digest:
                raise HTTPException(409, "This save key was already used for different data.")
            return {"quote": quote_dict(previous), "replayed": True}
        row = db.execute("SELECT * FROM analyses WHERE id=?", (body.analysis_id,)).fetchone()
        if row is None:
            raise HTTPException(404, "Analysis not found.")
        try:
            reviewed = apply_resolutions(json.loads(row["result"]), payload["resolutions"])
        except ValueError as e:
            raise HTTPException(422, str(e))
        qid = "VQ-" + uuid.uuid4().hex[:8].upper()
        db.execute("INSERT INTO quotes VALUES (?,?,?,?,?,?,?,?,?,?)", (qid, body.request_id, digest, body.analysis_id, row["transcript"], row["source"], row["audio_asset"], json.dumps(reviewed), json.dumps(payload["resolutions"]), now()))
        saved = db.execute("SELECT * FROM quotes WHERE id=?", (qid,)).fetchone()
    return {"quote": quote_dict(saved), "replayed": False}

@app.get("/api/quotes")
def quotes():
    with connect() as db:
        rows = db.execute("SELECT * FROM quotes ORDER BY created_at DESC LIMIT 100").fetchall()
    return {"quotes": [quote_dict(row) for row in rows]}

@app.get("/api/quotes/{quote_id}/csv")
def export(quote_id: str):
    with connect() as db:
        row = db.execute("SELECT * FROM quotes WHERE id=?", (quote_id,)).fetchone()
    if row is None:
        raise HTTPException(404, "Quote not found.")
    quote = quote_dict(row)
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(["quote_id", "created_at_utc", "source", "original_transcript", "product_id", "item", "quantity", "unit_price_gbp", "line_total_gbp", "status", "review_notes"])
    def safe(value):
        text = "" if value is None else str(value)
        return "'" + text if text.startswith(("=", "+", "-", "@", "\t", "\r")) else text
    for line in quote["validated_fields"]["lines"]:
        writer.writerow([safe(v) for v in [quote_id, quote["created_at"], quote["source"], quote["original_transcript"], line["product_id"], line["name"], line["quantity"], line["unit_price"], line["subtotal"], line["status"], "; ".join(line["issues"])]])
    return Response(buffer.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{quote_id}.csv"'})

@app.get("/")
def home():
    return FileResponse(BASE / "static/index.html")

app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
app.mount("/samples", StaticFiles(directory=BASE / "samples"), name="samples")
