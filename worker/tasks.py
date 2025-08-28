import os, subprocess, shutil, tempfile, json, time, pathlib
from celery import Celery
from loguru import logger
from shared.storage import upload_file
from shared.tusd import fetch_tus_file

REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_URL = os.getenv("ELEVENLABS_TRANSCRIBE_URL", "")
ELEVENLABS_LANG = os.getenv("ELEVENLABS_LANGUAGE", "auto")
ELEVENLABS_OUTFMT = os.getenv("ELEVENLABS_OUTPUT_FORMAT", "srt")

celery = Celery(__name__, broker=REDIS_URL, backend=REDIS_URL)

def run(cmd):
    logger.info("RUN: {}", " ".join(cmd))
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{p.stdout}")
    return p.stdout

@celery.task(name="tasks.split_task")
def split_task(tus_url: str):
    local, fname = fetch_tus_file(tus_url)
    logger.info(f"Downloaded {fname} to {local}")
    wav = tempfile.NamedTemporaryFile(delete=False, suffix=".wav").name
    run(["ffmpeg", "-y", "-i", local, "-ac", "2", "-ar", "44100", wav])
    outdir = tempfile.mkdtemp()
    run(["python", "-m", "demucs.separate", "-o", outdir, "--two-stems", "vocals", wav])
    demucs_root = pathlib.Path(outdir)
    candidates = list(demucs_root.rglob("*.wav"))
    urls = {}
    for c in candidates:
        key = f"demucs/{int(time.time())}_{c.name}"
        url = upload_file(str(c), key)
        urls[c.stem] = {"key": key, "url": url}
    try:
        os.remove(local)
    except: pass
    shutil.rmtree(outdir, ignore_errors=True)
    return {"filename": fname, "results": urls}

@celery.task(name="tasks.merge_task")
def merge_task(video_tus_url: str, audio_tus_url: str, offset_sec: float = 0.0):
    vlocal, vname = fetch_tus_file(video_tus_url)
    alocal, aname = fetch_tus_file(audio_tus_url)
    out = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4").name
    try:
        cmd = ["ffmpeg", "-y", "-i", vlocal, "-i", alocal]
        if offset_sec and abs(offset_sec) > 0.0001:
            cmd = ["ffmpeg", "-y", "-i", vlocal, "-itsoffset", str(offset_sec), "-i", alocal]
        cmd += ["-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-shortest", out]
        run(cmd)
    except Exception as e:
        enc = "h264_nvenc"
        try:
            run(["ffmpeg", "-hide_banner", "-encoders"])
        except:
            enc = "libx264"
        run(["ffmpeg", "-y", "-i", vlocal, "-i", alocal, "-map", "0:v:0", "-map", "1:a:0", "-c:v", enc, "-c:a", "aac", "-shortest", out])
    key = f"merged/{int(time.time())}_{os.path.splitext(os.path.basename(vname))[0]}_merged.mp4"
    url = upload_file(out, key)
    return {"video": vname, "audio": aname, "result": {"key": key, "url": url}}

@celery.task(name="tasks.transcribe_task")
def transcribe_task(tus_url: str, target_languages=None):
    local, fname = fetch_tus_file(tus_url)
    wav = tempfile.NamedTemporaryFile(delete=False, suffix=".wav").name
    run(["ffmpeg", "-y", "-i", local, "-ac", "1", "-ar", "16000", wav])
    if not ELEVENLABS_API_KEY or not ELEVENLABS_URL or ELEVENLABS_URL == "REPLACE_ME":
        key = f"audio/{int(time.time())}_{os.path.splitext(fname)[0]}.wav"
        url = upload_file(wav, key)
        return {"warning": "Set ELEVENLABS_API_KEY and ELEVENLABS_TRANSCRIBE_URL to enable transcription.", "audio_url": url}
    import requests
    headers = {"xi-api-key": ELEVENLABS_API_KEY}
    files = {"file": (os.path.basename(wav), open(wav, "rb"), "audio/wav")}
    data = {"language": ELEVENLABS_LANG, "output_format": ELEVENLABS_OUTFMT}
    r = requests.post(ELEVENLABS_URL, headers=headers, files=files, data=data)
    if r.status_code >= 300:
        raise RuntimeError(f"Transcription failed: {r.status_code} {r.text}")
    srt_path = tempfile.NamedTemporaryFile(delete=False, suffix=".srt").name
    with open(srt_path, "wb") as f:
        f.write(r.content)
    key = f"transcripts/{int(time.time())}_{os.path.splitext(fname)[0]}.srt"
    url = upload_file(srt_path, key)
    return {"filename": fname, "srt": {"key": key, "url": url}}

@celery.task(name="tasks.rename_task")
def rename_task(keys, pattern, start_index: int = 1, pad: int = 2, dryRun: bool = False):
    import boto3
    from shared.storage import s3, RESULTS_BUCKET
    out = []
    idx = start_index
    for key in keys:
        base = os.path.splitext(os.path.basename(key))[0]
        ext = os.path.splitext(key)[1]
        newname = pattern.replace("{index}", str(idx).zfill(pad)).replace("{basename}", base).replace("{ext}", ext)
        newkey = os.path.join(os.path.dirname(key), newname).replace("\\", "/")
        out.append({"from": key, "to": newkey})
        idx += 1
    if dryRun:
        return {"dryRun": True, "mapping": out}
    for m in out:
        copy_source = {"Bucket": RESULTS_BUCKET, "Key": m["from"]}
        s3.copy(copy_source, RESULTS_BUCKET, m["to"])
        s3.delete_object(Bucket=RESULTS_BUCKET, Key=m["from"])
    return {"dryRun": False, "mapping": out}
