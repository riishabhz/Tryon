# Drip Lab 🛍️ — live fashion search + AI virtual try-on

Search six UK fashion retailers at once (**Zara, H&M, boohoo, M&S, River Island,
Seasalt**; women's and men's), then see any item **on your own photo** before
you buy it.

It runs entirely on your own computer. You bring your own API key, and nothing
is hosted anywhere.

---

## See it in action

Real results from the app's **Fit check** view: the shop's product photo on the
left, and the same item tried on a real photo (the author's, on Regent Street) on
the right.

### Gemini edition

| M&S Supersoft Quarter Zip Knitted Polo | Retro Colour Block Jacket |
|---|---|
| ![Gemini try-on: knitted polo](docs/images/gemini-knitted-polo.webp) | ![Gemini try-on: colour block jacket](docs/images/gemini-colour-block-jacket.webp) |

### Free edition (Hugging Face)

| M&S Supersoft Quarter Zip Knitted Polo | Men's Balnoon Organic Cotton Check Overshirt |
|---|---|
| ![Free try-on: knitted polo](docs/images/free-knitted-polo.webp) | ![Free try-on: check overshirt](docs/images/free-check-overshirt.webp) |

**What the examples show:** both editions keep your face, the scene and your
other clothes (the jeans and trainers are untouched). Gemini fits the garment
closely to your body and pose. The free edition gets the colour and pattern
right, but the fit is looser, bits of your original outfit can show through
(see the cuffs on the polo), and it may change your arm position (the raised
hand on the overshirt comes from the product photo).

### How a try-on works

1. **You upload one photo** of yourself, ideally full-body and standing. It's
   saved on your computer and reused for every try-on.
2. **You click "Try it on"** on any product in the search results.
3. **The app picks the best garment picture.** Where the store has one, it uses
   a photo of the garment on its own, with no model (M&S cut-outs, Zara
   flat-lays), so the AI has no other person to copy.
4. **Your photo and the garment go to the AI you chose:**
   - **Gemini** is told to keep your face, body, pose, framing and background,
     replace only that garment, and never copy the shop model or their
     accessories. The output keeps your photo's shape.
   - **The free models** re-dress the upper or lower body. The app then pastes
     only the new clothing back onto your original photo, so your face, hair
     and background stay exactly as they were (when IDM-VTON handles the
     request, which is the usual case).
5. **The result appears** next to the product photo, gets saved to "Fits you've
   tried", and can be downloaded. Trying the same item again is instant and
   free, because results are cached.

---

## Two versions: pick one

The website is the same in both. They differ only in the AI that does the
try-on.

| | [`tryon-gemini/`](tryon-gemini/README.md) ⭐ recommended | [`tryon-kolors/`](tryon-kolors/README.md) |
|---|---|---|
| **AI engine** | Google Gemini image model | Free open-source models on Hugging Face (Kolors, IDM-VTON, CatVTON, Leffa) |
| **Cost** | About **3p (≈ $0.04) per try-on** | **Free** |
| **Speed** | ~10–15 seconds | 30 seconds – 2 minutes (shared queue) |
| **Daily limit** | Only your billing budget | **Roughly 5–10 try-ons/day** without an account; **a few dozen** with a free Hugging Face token |
| **Reliability** | High | The free services are sometimes busy, out of quota or offline |
| **Quality** | Keeps your face, pose and background; works with most photos | Good with a clear full-body photo; struggles with close-ups |
| **Needs** | A Google API key **with billing enabled** | Nothing (an HF token is optional) |

### Which should I use?

- **Just want to try it for free?** Use **`tryon-kolors`**. It works, but the
  free GPU allowance runs out after a handful of try-ons a day, and you may
  wait in a queue. When it runs out, the app says so; wait a while or switch
  to Gemini.
- **Want it fast and reliable?** Use **`tryon-gemini`**. A few pounds of
  Google credit covers about 100 try-ons, with no queue and no daily cap.

You can install both and switch whenever you like. They run on different ports
(8001 and 8000).

## Quick start

1. Install **Python 3.11** from https://www.python.org/downloads/ (on Windows,
   tick **"Add python.exe to PATH"** during setup).
2. Open the folder of the version you picked and follow its README:
   - [tryon-gemini/README.md](tryon-gemini/README.md)
   - [tryon-kolors/README.md](tryon-kolors/README.md)

In short:

```bash
cd tryon-gemini
pip install -r requirements.txt
python -m uvicorn main:app --port 8001
```

Then open **http://localhost:8001** in your browser.

## Features

- **Live search across 6 stores at once.** Type *"black t-shirt"*, *"linen
  shirt"* or *"floral midi dress"*.
- **Women / Men toggle**, clothing-type chips (T-shirts, Shirts, Jeans,
  Dresses…) and a **Filters** panel (stores, max price, sort by price).
- **Understands the query.** *"black mens t-shirt"* sets Men, T-shirts and the
  colour black for you.
- **Virtual try-on.** Upload one photo, click **Try it on** on any product, and
  see yourself wearing it. Every try-on is kept in **"Fits you've tried"**,
  which has a **Clear all** button.
- **Back-button friendly.** Open a product in the shop, come back, and your
  results and scroll position are still there.

## Privacy and your API key

- Your key lives only in a `.env` file on your computer. **Never share that
  file or upload it to GitHub**; the included `.gitignore` keeps it out of Git.
- Your photo stays on your computer and is sent only to the try-on AI you chose
  (Google, or a Hugging Face Space). Only upload photos of yourself or of
  people who have agreed.

## Disclaimer

A personal, educational project, **not affiliated with or endorsed by** any of
the retailers. Product data and images belong to the retailers; they're fetched
live for personal use and never redistributed. Stores change their websites,
so a store can stop working at any time; the others carry on, and the app shows
which store failed. The free engine's models are licensed for **non-commercial
use only**.
