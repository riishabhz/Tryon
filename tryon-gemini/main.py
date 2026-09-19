"""Gift Dashboard — dynamic shopping site with virtual try-on.

Run:
    uvicorn main:app --port 8000
Then open http://localhost:8000
"""

import hashlib
import json
import mimetypes
import os
import threading
import time
import urllib.request
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile, File
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

RESULTS_INDEX = RESULTS / "index.json"

app = FastAPI(title="Gift Dashboard Try-On")

# In-memory try-on jobs: job_id -> {status, result_url, error, product_name}
JOBS = {}
JOBS_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def current_photo():
    """Return the path of the uploaded model photo, or None."""
    for ext in (".jpg", ".jpeg", ".png", ".webp"):
        p = UPLOADS / f"model{ext}"
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


def load_results_index():
    if RESULTS_INDEX.exists():
        try:
            return json.loads(RESULTS_INDEX.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
    return []


def save_results_index(entries):
    RESULTS_INDEX.write_text(json.dumps(entries, indent=2), encoding="utf-8")


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
def api_photo_status():
    p = current_photo()
    if not p:
        return {"exists": False}
    return {"exists": True, "url": f"/uploads/{p.name}?t={int(p.stat().st_mtime)}"}


@app.post("/api/photo")
async def api_photo_upload(file: UploadFile = File(...)):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp"):
        raise HTTPException(400, "Please upload a JPG, PNG or WEBP image.")
    data = await file.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(400, "Image too large (max 15 MB).")
    # Remove any previous photo so current_photo() is unambiguous
    for old_ext in (".jpg", ".jpeg", ".png", ".webp"):
        old = UPLOADS / f"model{old_ext}"
        if old.exists():
            old.unlink()
    path = UPLOADS / f"model{ext}"
    path.write_bytes(data)
    return {"exists": True, "url": f"/uploads/{path.name}?t={int(time.time())}"}


# ---------------------------------------------------------------------------
# Try-on
# ---------------------------------------------------------------------------

class TryOnRequest(BaseModel):
    image_url: str
    product_name: str = ""
    product_url: str = ""
    category: str = ""


def _run_tryon_job(job_id, photo_path, garment_url, product_name, product_url,
                   category):
    try:
        with JOBS_LOCK:
            JOBS[job_id]["status"] = "running"
        garment_path = download_garment(garment_url)
        cache_key = tryon_cache_key(photo_path, garment_url)
        out_path = RESULTS / f"{cache_key}.png"

        if not out_path.exists():
            tryon.run_tryon(str(photo_path), str(garment_path), str(out_path),
                            category=category, description=product_name)

        entry = {
            "key": cache_key,
            "result_url": f"/tryon_results/{out_path.name}",
            "garment_url": garment_url,
            "product_name": product_name,
            "product_url": product_url,
            "created": time.time(),
        }
        index = load_results_index()
        index = [e for e in index if e.get("key") != cache_key]
        index.insert(0, entry)
        save_results_index(index[:100])

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
def api_tryon_start(req: TryOnRequest):
    photo = current_photo()
    if not photo:
        raise HTTPException(400, "Upload a model photo first.")
    if not req.image_url:
        raise HTTPException(400, "This product has no image to try on.")

    # Instant hit if we already generated this combination
    cache_key = tryon_cache_key(photo, req.image_url)
    cached = RESULTS / f"{cache_key}.png"
    if cached.exists():
        job_id = uuid.uuid4().hex[:12]
        with JOBS_LOCK:
            JOBS[job_id] = {"status": "done",
                            "result_url": f"/tryon_results/{cached.name}",
                            "product_name": req.product_name}
        return {"job_id": job_id, "cached": True}

    job_id = uuid.uuid4().hex[:12]
    with JOBS_LOCK:
        JOBS[job_id] = {"status": "queued", "product_name": req.product_name}
    t = threading.Thread(
        target=_run_tryon_job,
        args=(job_id, photo, req.image_url, req.product_name, req.product_url,
              req.category),
        daemon=True,
    )
    t.start()
    return {"job_id": job_id, "cached": False}


@app.get("/api/tryon/{job_id}")
def api_tryon_status(job_id: str):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        raise HTTPException(404, "Unknown job.")
    return job


@app.get("/api/tryons")
def api_tryon_gallery():
    return load_results_index()


@app.delete("/api/tryons")
def api_tryon_clear():
    """Delete every saved try-on image and empty the gallery."""
    removed = 0
    for image in RESULTS.glob("*.png"):
        image.unlink()
        removed += 1
    save_results_index([])
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
