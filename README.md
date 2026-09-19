# Drip Lab 🛍️ — live fashion search + AI virtual try-on

Search six UK fashion retailers at once (**Zara, H&M, boohoo, M&S, River Island,
Seasalt**; women's and men's), then see any item **on your own photo** before
you buy it.

It runs entirely on your own computer. You bring your own API key, and nothing
is hosted anywhere.

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
