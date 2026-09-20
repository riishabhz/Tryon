"""Virtual try-on via free Hugging Face Spaces (Kolors-first, with fallbacks).

The official Kwai-Kolors/Kolors-Virtual-Try-On Space currently has its
programmatic API DISABLED by Kuaishou (0 exposed endpoints — verified), so
this module tries it first in case they re-enable it, then automatically
falls back through other free, actively-running try-on Spaces:

    1. Kwai-Kolors/Kolors-Virtual-Try-On  (API disabled as of Aug 2026)
    2. yisol/IDM-VTON                     (works, auto-masking)
    3. zhengchong/CatVTON                 (works, needs cloth type)
    4. franciszzj/Leffa                   (works, needs garment type)

All of these run on HF "ZeroGPU" hardware with a per-user free quota.
Setting HF_TOKEN in .env (free account) raises your quota significantly.

Each provider function takes (person_path, garment_path, category,
description) and returns the path of the generated image that gradio_client
downloaded locally. IDM-VTON also returns its mask preview, which is used to
paste only the re-dressed area back onto the original photo (_composite).
"""

# Drip Lab — built by Rishabh Bhardwaj.
# Personal, non-commercial use only. See LICENSE.

import inspect
import os
import shutil

from gradio_client import Client, handle_file
from PIL import Image, ImageChops, ImageDraw, ImageFilter

# Bump when the pipeline changes so earlier cached results are regenerated.
CACHE_VERSION = "hf-v2"


def _client(space):
    """Create a gradio client; the token kwarg was renamed across versions
    (hf_token in 1.x, token in 2.x)."""
    token = os.getenv("HF_TOKEN") or None
    params = inspect.signature(Client.__init__).parameters
    kwarg = "token" if "token" in params else "hf_token"
    return Client(space, **{kwarg: token})


class TryOnError(Exception):
    """Raised when every provider failed; message is user-facing."""


def _friendly(err_text):
    low = err_text.lower()
    if "quota" in low or "gpu" in low and "exceeded" in low:
        return ("free GPU quota exceeded — wait a few minutes, or add a free "
                "HF_TOKEN in .env to get a bigger quota")
    if "queue" in low and "full" in low:
        return "queue is full right now"
    return err_text[:200]


# ---------------------------------------------------------------------------
# Providers
# ---------------------------------------------------------------------------

def _kolors(person, garment, category, description):
    client = _client("Kwai-Kolors/Kolors-Virtual-Try-On")
    result = client.predict(
        person_img=handle_file(person),
        garment_img=handle_file(garment),
        seed=0,
        randomize_seed=True,
        api_name="/tryon",
    )
    return result[0] if isinstance(result, (list, tuple)) else result


def _idm_vton(person, garment, category, description):
    client = _client("yisol/IDM-VTON")
    result = client.predict(
        dict={"background": handle_file(person), "layers": [],
              "composite": None},
        garm_img=handle_file(garment),
        garment_des=description or "a garment",
        is_checked=True,        # auto-generate mask
        is_checked_crop=False,
        denoise_steps=30,
        seed=42,
        api_name="/tryon",
    )
    # returns (output image, preview of the person with the edited area grey)
    if isinstance(result, (list, tuple)) and len(result) > 1:
        return {"image": result[0], "mask_preview": result[1]}
    return result


def _catvton(person, garment, category, description):
    cloth_type = {"tops": "upper", "bottoms": "lower"}.get(category, "overall")
    client = _client("zhengchong/CatVTON")
    result = client.predict(
        person_image={"background": handle_file(person), "layers": [],
                      "composite": None},
        cloth_image=handle_file(garment),
        cloth_type=cloth_type,
        num_inference_steps=50,
        guidance_scale=2.5,
        seed=42,
        show_type="result only",
        api_name="/submit_function",
    )
    return result if isinstance(result, str) else result[0]


def _leffa(person, garment, category, description):
    garment_type = {"tops": "upper_body",
                    "bottoms": "lower_body"}.get(category, "dresses")
    client = _client("franciszzj/Leffa")
    result = client.predict(
        src_image_path=handle_file(person),
        ref_image_path=handle_file(garment),
        ref_acceleration=False,
        step=30,
        scale=2.5,
        seed=42,
        vt_model_type="viton_hd",
        vt_garment_type=garment_type,
        vt_repaint=False,
        api_name="/leffa_predict_vt",
    )
    # returns (generated image, mask, densepose)
    return result[0] if isinstance(result, (list, tuple)) else result


PROVIDERS = [
    ("Kolors (official)", _kolors),
    ("IDM-VTON", _idm_vton),
    ("CatVTON", _catvton),
    ("Leffa", _leffa),
]


def _composite(person_path, generated_path, preview_path, out_path):
    """Paste only the re-dressed area back onto the untouched original photo.

    The free models work at a fixed 768x1024 and re-draw the whole picture, so
    small faces lose their likeness and the photo gets stretched. IDM-VTON's
    preview marks the area it edited in flat grey; everything outside it is
    taken from the original, at its original size and shape.
    """
    original = Image.open(person_path).convert("RGB")
    size = original.size
    generated = Image.open(generated_path).convert("RGB").resize(size, Image.LANCZOS)

    preview = Image.open(preview_path).convert("RGB")
    grey = [band.point(lambda v: 255 if 120 <= v <= 135 else 0)
            for band in preview.split()]
    mask = ImageChops.multiply(ImageChops.multiply(grey[0], grey[1]), grey[2])
    # Drop stray grey pixels. Don't grow the area: at this scale a face can be
    # only ~40px wide and sits right against the edited block.
    mask = mask.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(3))

    _protect_head(mask)

    coverage = sum(mask.histogram()[128:]) / (mask.width * mask.height)
    if coverage < 0.01:
        generated.save(out_path)   # no usable mask: fall back to the full result
        return
    mask = mask.resize(size, Image.BILINEAR)
    mask = mask.filter(ImageFilter.GaussianBlur(1))
    Image.composite(generated, original, mask).save(out_path)


def _protect_head(mask):
    """Keep the whole head (hair and jaw too) from the original photo.

    IDM-VTON's edit block covers the hair and leaves only a face-shaped gap in
    its top rows, so the re-drawn hair and jaw change how the person looks.
    Find that gap (non-edited pixels with edited pixels on both sides) and
    clear a larger oval around it.
    """
    core = mask.filter(ImageFilter.MinFilter(21)).getbbox()   # ignore grey specks
    if not core:
        return
    bx0, by0, bx1, by1 = core
    left, right = max(0, bx0 - 15), min(mask.width, bx1 + 15)
    xs, ys = [], []
    for y in range(max(0, by0 - 15), by0 + int((by1 - by0) * 0.3)):
        row = [mask.getpixel((x, y)) > 127 for x in range(left, right)]
        if True not in row:
            continue
        first, last = row.index(True), len(row) - 1 - row[::-1].index(True)
        for i in range(first, last):
            if not row[i]:
                xs.append(left + i)
                ys.append(y)
    if len(xs) < 50:
        return
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    w, h = x1 - x0, y1 - y0
    if w > (bx1 - bx0) * 0.5:                  # too wide to be a face
        return
    ImageDraw.Draw(mask).ellipse(
        (x0 - 0.35 * w, y0 - 0.6 * h, x1 + 0.35 * w, y1), fill=0)


def _extract_path(value):
    """gradio_client may return a str path or a dict like {'image': {'path':…}}."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("path", "image", "value"):
            if key in value:
                return _extract_path(value[key])
    raise TryOnError(f"Unexpected result format from Space: {type(value)}")


def run_tryon(person_path, garment_path, out_path, category="", description=""):
    """Generate a try-on image; writes the result to out_path.

    Tries each provider Space in order until one succeeds.
    Raises TryOnError with a readable summary if all fail.
    """
    failures = []
    for name, fn in PROVIDERS:
        try:
            result = fn(person_path, garment_path, category, description)
            if isinstance(result, dict) and "mask_preview" in result:
                _composite(person_path, _extract_path(result["image"]),
                           _extract_path(result["mask_preview"]), out_path)
            else:
                shutil.copyfile(_extract_path(result), out_path)
            return out_path
        except TryOnError:
            raise
        except Exception as e:
            failures.append(f"{name}: {_friendly(str(e))}")
    raise TryOnError(
        "All free try-on Spaces failed — " + " | ".join(failures)
    )
