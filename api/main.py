import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from celery.result import AsyncResult
from dotenv import load_dotenv
from loguru import logger

load_dotenv()

app = FastAPI(title="sudo.ai MVP API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

TUSD_PUBLIC_URL = os.getenv("TUSD_PUBLIC_URL", "http://localhost:8080")

from celery import Celery
celery = Celery(__name__, broker=os.getenv("REDIS_URL", "redis://redis:6379/0"))
celery.conf.result_backend = os.getenv("REDIS_URL", "redis://redis:6379/0")

class SplitReq(BaseModel):
    tus_url: str = Field(..., description="Full tus upload URL (Location)")

class MergeReq(BaseModel):
    video_tus_url: str
    audio_tus_url: str
    offset_sec: float = 0.0

class TranscribeReq(BaseModel):
    tus_url: str
    target_languages: list[str] = Field(default_factory=lambda: ["original"])

class RenameReq(BaseModel):
    keys: list[str]
    pattern: str
    start_index: int = 1
    pad: int = 2
    dryRun: bool = False

@app.get("/health")
def health():
    return {"ok": True}

@app.get("/uploads/tus")
def get_tus():
    ep = TUSD_PUBLIC_URL or "http://localhost:8080"
    if not ep.endswith("/files"):
        ep = ep.rstrip("/") + "/files"
    return {"tus_endpoint": ep}


@app.post("/split")
def split(req: SplitReq):
    r = celery.send_task("tasks.split_task", args=[req.tus_url])
    return {"task_id": r.id}

@app.post("/merge")
def merge(req: MergeReq):
    r = celery.send_task("tasks.merge_task", args=[req.video_tus_url, req.audio_tus_url, req.offset_sec])
    return {"task_id": r.id}

@app.post("/transcribe")
def transcribe(req: TranscribeReq):
    r = celery.send_task("tasks.transcribe_task", args=[req.tus_url, req.target_languages])
    return {"task_id": r.id}

@app.post("/rename")
def rename(req: RenameReq):
    r = celery.send_task("tasks.rename_task", args=[req.keys, req.pattern, req.start_index, req.pad, req.dryRun])
    return {"task_id": r.id}

@app.get("/jobs/{task_id}")
def job(task_id: str):
    res = AsyncResult(task_id, app=celery)
    out = {"task_id": task_id, "state": res.state}
    if res.state == "SUCCESS":
        out["result"] = res.result
    elif res.state == "FAILURE":
        out["error"] = str(res.info)
    return out
