"""Drip Lab — live fashion search with virtual try-on.

Run locally:
    uvicorn main:app --port 8000
Then open http://localhost:8000

With DRIPLAB_MULTIUSER=1 (set by the Dockerfile for hosting), every visitor
gets a private photo and gallery, identified by a random ID their browser
sends in the X-Session-Id header. Locally everything belongs to one user.
"""

import hashlib
import json
import mimetypes
import os
import re
import shutil
import threading
import time
import urllib.request
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

BASE_DIR = Path(__file__).parent


def _load_env():
    """Tiny .env loader (KEY=value lines) so no python-dotenv dep is needed."""
    env_file = BASE_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip())


_load_env()

import scraper  # noqa: E402
import tryon    # noqa: E402
UPLOADS = BASE_DIR / "uploads"
GARMENTS = BASE_DIR / "garment_cache"
RESULTS = BASE_DIR / "tryon_results"
for d in (UPLOADS, GARMENTS, RESULTS, BASE_DIR / "static"):
    d.mkdir(exist_ok=True)

MULTIUSER = os.getenv("DRIPLAB_MULTIUSER") == "1"
LOCAL_SESSION = "local"
SESSION_MAX_AGE = 24 * 3600   # hosted: forget visitors' photos after a day

app = FastAPI(title="Drip Lab")

# In-memory try-on jobs: job_id -> {status, result_url, error, product_name, sid}
JOBS = {}
JOBS_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# Sessions: whose photo and gallery a request belongs to
# ---------------------------------------------------------------------------

def session_id(request):
    if not MULTIUSER:
        return LOCAL_SESSION
    sid = request.headers.get("x-session-id", "")
    if not re.fullmatch(r"[0-9a-f]{32}", sid):
        raise HTTPException(400, "Missing session. Reload the page.")
    return sid


def uploads_dir(sid):
    d = UPLOADS / sid
    d.mkdir(exist_ok=True)
    return d


def results_dir(sid):
    d = RESULTS / sid
    d.mkdir(exist_ok=True)
    return d


def _migrate_single_user_files():
    """Move files from before sessions existed into the local session."""
    if MULTIUSER:
        return
    for p in list(UPLOADS.glob("model.*")):
        shutil.move(str(p), uploads_dir(LOCAL_SESSION) / p.name)
    old_index = RESULTS / "index.json"
    pngs = list(RESULTS.glob("*.png"))
    if not pngs and not old_index.exists():
        return
    target = results_dir(LOCAL_SESSION)
    for p in pngs:
        shutil.move(str(p), target / p.name)
    if old_index.exists():
        entries = json.loads(old_index.read_text(encoding="utf-8") or "[]")
        for e in entries:
            e["result_url"] = e.get("result_url", "").replace(
                "/tryon_results/", f"/tryon_results/{LOCAL_SESSION}/", 1)
        (target / "index.json").write_text(json.dumps(entries, indent=2),
                                           encoding="utf-8")
        old_index.unlink()


def _forget_old_sessions():
    """Hosted only: delete visitors' photos and try-ons after a day."""
    while True:
        cutoff = time.time() - SESSION_MAX_AGE
        for root in (UPLOADS, RESULTS):
            for d in root.iterdir():
                if d.is_dir() and d.stat().st_mtime < cutoff:
                    shutil.rmtree(d, ignore_errors=True)
        time.sleep(3600)


_migrate_single_user_files()
if MULTIUSER:
    threading.Thread(target=_forget_old_sessions, daemon=True).start()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def current_photo(sid):
    """Return the path of this session's uploaded photo, or None."""
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        p = UPLOADS / sid / f"model{ext}"
        if p.exists():
            return p
    return None


def download_garment(url):
    """Download a garment image to the local cache; returns the file path."""
    key = hashlib.sha256(url.encode()).hexdigest()[:16]
    for ext in (".jpg", ".png", ".webp"):
        p = GARMENTS / f"{key}{ext}"
        if p.exists():
            return p
    req = urllib.request.Request(url, headers={
        "User-Agent": scraper.HEADERS["User-Agent"],
        "Accept": "image/*,*/*;q=0.8",
        "Referer": url,
    })
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = resp.read()
        ctype = resp.headers.get("Content-Type", "")
    ext = ".png" if "png" in ctype else ".webp" if "webp" in ctype else ".jpg"
    path = GARMENTS / f"{key}{ext}"
    path.write_bytes(data)
    return path


def load_results_index(sid):
    index = RESULTS / sid / "index.json"
    if index.exists():
        try:
            return json.loads(index.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
    return []


def save_results_index(sid, entries):
    (results_dir(sid) / "index.json").write_text(json.dumps(entries, indent=2),
                                                 encoding="utf-8")


def tryon_cache_key(photo_path, garment_url):
    h = hashlib.sha256()
    h.update(photo_path.read_bytes())
    h.update(garment_url.encode())
    h.update(getattr(tryon, "CACHE_VERSION", "").encode())
    return h.hexdigest()[:20]


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

@app.get("/api/search")
def api_search(q: str = "", type: str = "auto", gender: str = "women",
               stores: str = "", max: int = 12):
    store_keys = [s.strip() for s in stores.split(",") if s.strip()] or None
    return scraper.search(query=q, ctype=type, gender=gender,
                          stores=store_keys, max_per_store=min(max, 24))


@app.get("/api/stores")
def api_stores():
    return [{"key": k, "name": name} for k, name in scraper.STORES.items()]


@app.get("/api/types")
def api_types(gender: str = "women"):
    return scraper.available_types(gender)


# ---------------------------------------------------------------------------
# Model photo
# ---------------------------------------------------------------------------

@app.get("/api/photo")
def api_photo_status(request: Request):
    sid = session_id(request)
    p = current_photo(sid)
    if not p:
        return {"exists": False}
    return {"exists": True,
            "url": f"/uploads/{sid}/{p.name}?t={int(p.stat().st_mtime)}"}


@app.post("/api/photo")
async def api_photo_upload(request: Request, file: UploadFile = File(...)):
    sid = session_id(request)
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp"):
        raise HTTPException(400, "Please upload a JPG, PNG or WEBP image.")
    data = await file.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(400, "Image too large (max 15 MB).")
    # Remove any previous photo so current_photo() is unambiguous
    folder = uploads_dir(sid)
    for old_ext in (".jpg", ".jpeg", ".png", ".webp"):
        old = folder / f"model{old_ext}"
        if old.exists():
            old.unlink()
    path = folder / f"model{ext}"
    path.write_bytes(data)
    return {"exists": True,
            "url": f"/uploads/{sid}/{path.name}?t={int(time.time())}"}


# ---------------------------------------------------------------------------
# Try-on
# ---------------------------------------------------------------------------

class TryOnRequest(BaseModel):
    image_url: str
    product_name: str = ""
    product_url: str = ""
    category: str = ""


def _run_tryon_job(job_id, sid, photo_path, garment_url, product_name,
                   product_url, category):
    try:
        with JOBS_LOCK:
            JOBS[job_id]["status"] = "running"
        garment_path = download_garment(garment_url)
        cache_key = tryon_cache_key(photo_path, garment_url)
        out_path = results_dir(sid) / f"{cache_key}.png"

        if not out_path.exists():
            tryon.run_tryon(str(photo_path), str(garment_path), str(out_path),
                            category=category, description=product_name)

        entry = {
            "key": cache_key,
            "result_url": f"/tryon_results/{sid}/{out_path.name}",
            "garment_url": garment_url,
            "product_name": product_name,
            "product_url": product_url,
            "created": time.time(),
        }
        index = load_results_index(sid)
        index = [e for e in index if e.get("key") != cache_key]
        index.insert(0, entry)
        save_results_index(sid, index[:100])

        with JOBS_LOCK:
            JOBS[job_id].update(status="done",
                                result_url=entry["result_url"])
    except tryon.TryOnError as e:
        with JOBS_LOCK:
            JOBS[job_id].update(status="error", error=str(e))
    except Exception as e:
        with JOBS_LOCK:
            JOBS[job_id].update(status="error", error=f"Unexpected error: {e}")


@app.post("/api/tryon")
def api_tryon_start(req: TryOnRequest, request: Request):
    sid = session_id(request)
    photo = current_photo(sid)
    if not photo:
        raise HTTPException(400, "Upload a model photo first.")
    if not req.image_url:
        raise HTTPException(400, "This product has no image to try on.")

    # Instant hit if we already generated this combination
    cache_key = tryon_cache_key(photo, req.image_url)
    cached = RESULTS / sid / f"{cache_key}.png"
    if cached.exists():
        job_id = uuid.uuid4().hex[:12]
        with JOBS_LOCK:
            JOBS[job_id] = {"status": "done", "sid": sid,
                            "result_url": f"/tryon_results/{sid}/{cached.name}",
                            "product_name": req.product_name}
        return {"job_id": job_id, "cached": True}

    with JOBS_LOCK:
        busy = any(j["sid"] == sid and j["status"] in ("queued", "running")
                   for j in JOBS.values())
        if MULTIUSER and busy:
            raise HTTPException(429, "One try-on at a time — wait for the "
                                     "current one to finish.")
        job_id = uuid.uuid4().hex[:12]
        JOBS[job_id] = {"status": "queued", "sid": sid,
                        "product_name": req.product_name}
    t = threading.Thread(
        target=_run_tryon_job,
        args=(job_id, sid, photo, req.image_url, req.product_name,
              req.product_url, req.category),
        daemon=True,
    )
    t.start()
    return {"job_id": job_id, "cached": False}


@app.get("/api/tryon/{job_id}")
def api_tryon_status(job_id: str, request: Request):
    sid = session_id(request)
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job or job.get("sid") != sid:
        raise HTTPException(404, "Unknown job.")
    return {k: v for k, v in job.items() if k != "sid"}


@app.get("/api/tryons")
def api_tryon_gallery(request: Request):
    return load_results_index(session_id(request))


@app.delete("/api/tryons")
def api_tryon_clear(request: Request):
    """Delete this session's saved try-on images and empty its gallery."""
    sid = session_id(request)
    removed = 0
    for image in (RESULTS / sid).glob("*.png"):
        image.unlink()
        removed += 1
    save_results_index(sid, [])
    return {"removed": removed}


# ---------------------------------------------------------------------------
# Image proxy (retailer CDNs often block hotlinking / CORS)
# ---------------------------------------------------------------------------

@app.get("/api/image-proxy")
def api_image_proxy(url: str):
    if not url.startswith(("http://", "https://")):
        raise HTTPException(400, "Invalid URL.")
    try:
        path = download_garment(url)
    except Exception as e:
        raise HTTPException(502, f"Could not fetch image: {e}")
    media_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    return Response(path.read_bytes(), media_type=media_type,
                    headers={"Cache-Control": "public, max-age=86400"})


# ---------------------------------------------------------------------------
# Static files & pages
# ---------------------------------------------------------------------------

app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOADS), name="uploads")
app.mount("/tryon_results", StaticFiles(directory=RESULTS), name="tryon_results")


@app.get("/")
def index():
    return FileResponse(BASE_DIR / "static" / "index.html")
