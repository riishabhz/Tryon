# Drip Lab: free edition (Hugging Face)

Live fashion search across 6 UK stores, plus **free** AI virtual try-on using
open-source models hosted on Hugging Face.

> ⚠️ **It's free, but limited.** It works, but the free GPUs have a small daily
> allowance and are shared with everyone, so expect queues and the occasional
> "quota exceeded". For fast, reliable try-ons, use the
> **[Gemini edition](../tryon-gemini/README.md)** (about 3p per try-on).
> Searching and browsing are unlimited in both versions; only the try-on is
> limited.

---

## Free limits: what to expect

The try-on runs on Hugging Face **ZeroGPU** Spaces: free GPUs that Hugging Face
shares among all visitors, with a daily allowance per person.

| | Without an account | With a free Hugging Face token |
|---|---|---|
| Try-ons per day (approx.) | **~5–10** | **a few dozen** |
| Time per try-on | 30 s – 2 min (queue + generation) | 30 s – 2 min |
| When the allowance runs out | "Free GPU quota exceeded"; it refills over minutes to hours | Same, but it takes much longer to run out |

Also:

- **Busy times mean longer queues.** The app waits up to 6 minutes before
  giving up.
- **The free Spaces are run by volunteers and researchers.** Any of them can be
  down, sleeping or overloaded. The app automatically tries four in turn:
  Kolors (whose API is currently disabled by its owner, so it's skipped
  quickly) → **IDM-VTON** → **CatVTON** → **Leffa**.
- **The models need a clear, full-body photo.** Close-ups and selfies give poor
  results.
- **Hugging Face doesn't publish the exact numbers** and changes them over time,
  so treat the figures above as a rough guide.
- **The models are licensed for non-commercial use only.**

**In short:** great for trying the project out, but if you run out or want
consistent results, switch to the Gemini edition.

---

## 1. Install Python (once)

1. Download **Python 3.11** from https://www.python.org/downloads/
2. **Windows:** in the installer, tick **"Add python.exe to PATH"**, then click
   *Install Now*.
3. Check it works. Open a terminal (Windows: *Command Prompt* or
   *PowerShell*; Mac: *Terminal*) and run:

   ```bash
   python --version
   ```

   You should see `Python 3.11.x`. (On Mac, use `python3` wherever this guide
   says `python`.)

## 2. Install the app (once)

Open a terminal **in this folder** (`tryon-kolors`). On Windows, the easiest way is
to open the folder in File Explorer, click the address bar, type `cmd` and press
Enter. Or use `cd`, and **add `/d` if the folder is on another drive**:

```bash
cd /d D:\TryOn\tryon-kolors
```

(Without `/d`, Command Prompt stays on drive C and you'll get
*"Could not import module main"*.) Then run:

```bash
pip install -r requirements.txt
```

## 3. Optional: add a free Hugging Face token (recommended)

It's free and raises your daily try-on allowance several times over.

1. Create a free account at https://huggingface.co/join
2. Go to https://huggingface.co/settings/tokens → **Create new token** → type
   **Read** → copy it (it starts with `hf_`).
3. Make a copy of `.env.example` named `.env`, in this folder:
   - **Windows (Command Prompt):** `copy .env.example .env`
   - **Windows (PowerShell):** `Copy-Item .env.example .env`
   - **Mac / Linux:** `cp .env.example .env`
4. Open `.env` in any text editor and paste the token after the `=`:

   ```
   HF_TOKEN=hf_your_token_here
   ```

> 🔒 Keep `.env` private and never upload it; the `.gitignore` keeps it out of
> Git.

Skip this step and the app still works, with the smaller anonymous allowance.

## 4. Run it

In a terminal in this folder:

```bash
python -m uvicorn main:app --port 8000
```

Open **http://localhost:8000** in your browser.

To stop the app, press **Ctrl + C** in the terminal. Run the same command to
start it again next time.

## 5. How to use it

1. **Pick Women or Men** under the search bar.
2. **Search** for anything: *"black t-shirt"*, *"linen shirt"*,
   *"floral midi dress"*, *"blue jeans"*. Results arrive live from
   Zara, H&M, boohoo, M&S, River Island and Seasalt. The first search takes
   about 8–10 seconds; repeats are instant.
3. **Narrow it down** with the type chips or the **Filters** button (stores,
   max price, sort by price).
4. **Add your photo** in the *Try-on photo* box on the left. You only do this
   once; it's remembered until you click *Change photo*.
5. Click **Try it on**. The button shows *Queued…* and then *Fitting…* with a
   timer; free try-ons take 30 seconds to 2 minutes.
6. Results are saved under **"Fits you've tried"**, with **Clear all** to
   delete them. Repeating a try-on you've already done is instant and doesn't
   use your allowance.

### Getting the best try-on

| ✅ Do | ❌ Avoid |
|---|---|
| Full-body photo, head to feet | Webcam or head-and-shoulders selfies |
| Portrait (tall) photo | Landscape (wide) photos |
| Standing, facing the camera, arms visible | Sitting, turned sideways, heavy coats |
| Plain background, good light | Busy scenes, dark photos |

A mirror selfie is perfect. Products shown as garment-only photos (many M&S
and Zara items) give the best results.

## Troubleshooting

| Message / problem | Fix |
|---|---|
| "Free GPU quota exceeded" | Your daily allowance is used up. Wait 10–60 minutes, add an `HF_TOKEN` (step 3), or use the Gemini edition. |
| "All free try-on Spaces failed" | All four free services are busy or down right now. Try later, or use the Gemini edition. |
| "Timed out after 6 minutes" | The queue is very long. Try again later. |
| Poor or distorted result | Use a clearer full-body photo, or a product with a plain garment photo. |
| A store shows an error or 0 results | That store changed its website. The other stores still work. |
| `python` or `pip` "not recognised" | Reinstall Python with *"Add python.exe to PATH"* ticked, or use `py -m pip …` and `py -m uvicorn …` on Windows. |
| *"Could not import module main"* | The terminal isn't in the app folder. Check the prompt shows `...\tryon-kolors>`; on Windows use `cd /d <folder>` to switch drive as well. |
| "Address already in use" | The app is already running in another terminal; use that, or run with `--port 8002`. |

## What's in this folder

```
tryon-kolors/
├── main.py            web server and API
├── scraper.py         live search across the 6 stores
├── tryon.py           sends your photo + the garment to the free HF Spaces
├── static/            the website (HTML, CSS, JavaScript)
├── requirements.txt   Python packages
├── .env.example       template for your optional HF token (copy to .env)
└── .gitignore         keeps .env and your photos out of Git
```

Created while running: `uploads/` (your photo), `tryon_results/` (your
try-ons) and `garment_cache/` (product images). They stay on your computer.

## Privacy

Your photo stays on your computer. It's sent only to the public Hugging Face
Space that generates the try-on. Don't upload photos you wouldn't want
processed by a public service, and only upload photos of yourself or of people
who have agreed.
