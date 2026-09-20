"""Virtual try-on via Google Gemini image generation (nano-banana).

Uses the REST API directly (no SDK needed): sends the person photo and the
garment photo to the image model with an instruction to dress the person in
the garment, and saves the returned image.

Requires GEMINI_API_KEY in .env (https://aistudio.google.com/apikey) on a
project with billing enabled — image generation has no free tier.
"""

# Drip Lab — built by Rishabh Bhardwaj.
# Personal, non-commercial use only. See LICENSE.

import base64
import json
import mimetypes
import os
import urllib.error
import urllib.request

MODEL = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-image")
API_URL = ("https://generativelanguage.googleapis.com/v1beta/models/"
           f"{MODEL}:generateContent")

# Bump when the prompt changes so earlier cached results are regenerated.
CACHE_VERSION = "gemini-v2"

GARMENT_PART = {
    "tops": "top (the upper-body clothing)",
    "bottoms": "trousers, shorts or skirt (the lower-body clothing)",
    "dresses": "outfit",
}

PROMPT = """Virtual try-on. You receive two images.

IMAGE 1 is the customer. Keep EVERYTHING about them exactly as it is: face,
hair, skin tone, glasses, body shape and size, pose, arm positions, camera
angle, framing, lighting and background.

IMAGE 2 is a shop photo of this garment: {name}. It may show a fashion model.
Use IMAGE 2 ONLY as a reference for the garment's design, colour, pattern,
fabric and cut. Never copy the model's face, head, hair, body, pose, hands
or legs, and never copy any accessories (sunglasses, bags, jewellery, belts)
or other clothing items from IMAGE 2.

Replace only the customer's {part} with this garment, fitted naturally to
THEIR body and posture with realistic folds, shadows and lighting that match
IMAGE 1. Keep all their other clothing as it is.

Keep exactly the same crop as IMAGE 1: if IMAGE 1 only shows the head and
shoulders, the result only shows the head and shoulders, with the garment
visible where the body is in frame. Do not extend the picture, zoom out or
invent body parts that are outside IMAGE 1. The result must look like the
same photo of the same person, just wearing the new garment."""

# Aspect ratios the image model can output.
ASPECT_RATIOS = ["1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4", "9:16",
                 "16:9", "21:9"]


def _aspect_ratio(path):
    """Closest supported aspect ratio to the photo, so the output keeps its shape."""
    try:
        from PIL import Image
        with Image.open(path) as im:
            w, h = im.size
    except Exception:
        return None
    target = w / h
    return min(ASPECT_RATIOS,
               key=lambda r: abs(int(r.split(":")[0]) / int(r.split(":")[1]) - target))


class TryOnError(Exception):
    """Raised when generation failed; message is user-facing."""


def _b64_part(path):
    mime = mimetypes.guess_type(str(path))[0] or "image/jpeg"
    with open(path, "rb") as f:
        data = base64.b64encode(f.read()).decode()
    return {"inline_data": {"mime_type": mime, "data": data}}


def run_tryon(person_path, garment_path, out_path, category="", description=""):
    """Generate a try-on image; writes the result to out_path."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise TryOnError(
            "GEMINI_API_KEY is not set. Get a key at "
            "https://aistudio.google.com/apikey (billing must be enabled), "
            "put it in a .env file in this folder and restart the app."
        )

    generation = {"responseModalities": ["IMAGE"]}
    ratio = _aspect_ratio(person_path)
    if ratio:
        generation["imageConfig"] = {"aspectRatio": ratio}
    prompt = PROMPT.format(name=description or "the garment",
                           part=GARMENT_PART.get(category, "clothing"))
    body = {
        "contents": [{
            "parts": [
                {"text": prompt},
                {"text": "IMAGE 1 (the customer):"},
                _b64_part(person_path),
                {"text": "IMAGE 2 (the garment reference):"},
                _b64_part(garment_path),
            ],
        }],
        "generationConfig": generation,
    }

    req = urllib.request.Request(
        API_URL,
        data=json.dumps(body).encode(),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:500]
        try:
            detail = json.loads(detail)["error"]["message"]
        except Exception:
            pass
        if e.code == 400 and "API key" in str(detail):
            raise TryOnError("Invalid GEMINI_API_KEY — check your .env file.")
        if e.code == 429:
            raise TryOnError(
                "Gemini refused: no image-generation quota on this API key. "
                "As of late 2026 Google requires billing to be enabled for "
                "image models (aistudio.google.com → your key → Set up "
                "billing, ~$0.04/image) — or use the free tryon-kolors app "
                "instead. If you do have billing, this is a temporary rate "
                "limit; wait a minute and retry."
            )
        raise TryOnError(f"Gemini API error {e.code}: {detail}")
    except urllib.error.URLError as e:
        raise TryOnError(f"Could not reach the Gemini API: {e.reason}")

    # Find the returned image part
    try:
        parts = payload["candidates"][0]["content"]["parts"]
    except (KeyError, IndexError):
        feedback = payload.get("promptFeedback", {})
        if feedback.get("blockReason"):
            raise TryOnError(
                f"Gemini refused this image pair ({feedback['blockReason']}). "
                "Try a different photo or product."
            )
        raise TryOnError(f"Unexpected Gemini response: {str(payload)[:300]}")

    for part in parts:
        blob = part.get("inline_data") or part.get("inlineData")
        if blob and blob.get("data"):
            with open(out_path, "wb") as f:
                f.write(base64.b64decode(blob["data"]))
            return out_path

    text = " ".join(p.get("text", "") for p in parts)[:300]
    raise TryOnError(f"Gemini returned no image. It said: {text}")
