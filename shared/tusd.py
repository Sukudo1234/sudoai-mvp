import os, re, requests, tempfile, base64

TUSD_INTERNAL_URL = os.getenv("TUSD_INTERNAL_URL", "http://tusd:1080")

def _id_from_tus_url(tus_url: str) -> str:
    m = re.search(r"/files/([^/?]+)", tus_url)
    if not m:
        raise ValueError("Invalid tus URL, expected /files/<id>: " + tus_url)
    return m.group(1)

def fetch_tus_file(tus_url: str):
    """Download a tus upload to a temp file.
    Returns (local_path, original_filename)."""
    upload_id = _id_from_tus_url(tus_url)
    h = requests.head(f"{TUSD_INTERNAL_URL}/files/{upload_id}")
    filename = "upload.bin"
    meta = h.headers.get("Upload-Metadata", "")
    for pair in meta.split(","):
        if not pair.strip():
            continue
        sp = pair.strip().split(" ")
        if len(sp) != 2:
            continue
        k, b64v = sp
        if k.lower() == "filename":
            try:
                filename = base64.b64decode(b64v).decode("utf-8")
            except Exception:
                pass
    r = requests.get(f"{TUSD_INTERNAL_URL}/files/{upload_id}", stream=True)
    r.raise_for_status()
    suffix = os.path.splitext(filename)[1] or ".bin"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    for chunk in r.iter_content(chunk_size=1024*1024):
        if chunk:
            tmp.write(chunk)
    tmp.close()
    return tmp.name, filename
