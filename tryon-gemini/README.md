# Drip Lab: Gemini edition ⭐ (recommended)

Live fashion search across 6 UK stores, plus AI virtual try-on powered by
**Google Gemini**. Fast (about 10–15 seconds per try-on), no queue, and
reliable. Each try-on costs about **3p (≈ $0.04)** on your own Google account.

> Want a free version instead? See [`../tryon-kolors`](../tryon-kolors/README.md).
> It works, but has daily limits and queues.

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

Open a terminal **in this folder** (`tryon-gemini`). On Windows, the easiest way is
to open the folder in File Explorer, click the address bar, type `cmd` and press
Enter. Or use `cd`, and **add `/d` if the folder is on another drive**:

```bash
cd /d D:\TryOn\tryon-gemini
```

(Without `/d`, Command Prompt stays on drive C and you'll get
*"Could not import module main"*.) Then run:

```bash
pip install -r requirements.txt
```

This installs FastAPI, Uvicorn and Pillow. It takes about a minute.

## 3. Get your Gemini API key (once)

1. Go to **https://aistudio.google.com/apikey** and sign in with a Google
   account.
2. Click **Create API key** and copy it.
3. On the same page, click **Set up billing** next to the key's project and
   add a payment method.
   **This is required.** Google's free tier does not include image generation,
   so without billing every try-on is refused with a "quota" error.
4. **Recommended:** in Google Cloud Console → *Billing → Budgets & alerts*,
   create a small monthly budget (e.g. £5) with email alerts, so you always
   know what you're spending.

### Add the key to the app

Make a copy of `.env.example` named `.env`, in this folder:

- **Windows (Command Prompt):** `copy .env.example .env`
- **Windows (PowerShell):** `Copy-Item .env.example .env`
- **Mac / Linux:** `cp .env.example .env`

Open `.env` in any text editor (Notepad works) and paste your key after the `=`:

```
GEMINI_API_KEY=paste-your-key-here
```

Save the file.

> 🔒 **Keep `.env` private.** It's your key, and anyone who has it can spend
> your money. Never share it, email it or upload it; the `.gitignore` in this
> folder stops Git from uploading it.

## 4. Run it

In a terminal in this folder:

```bash
python -m uvicorn main:app --port 8001
```

Open **http://localhost:8001** in your browser.

To stop the app, press **Ctrl + C** in the terminal. Run the same command to
start it again next time; steps 1–3 are one-time setup.

## 5. How to use it

1. **Pick Women or Men** under the search bar.
2. **Search** for anything: *"black t-shirt"*, *"linen shirt"*,
   *"floral midi dress"*, *"blue jeans"*. Results arrive live from
   Zara, H&M, boohoo, M&S, River Island and Seasalt. The first search takes
   about 8–10 seconds; repeats are instant.
3. **Narrow it down** with the type chips (T-shirts, Shirts, Jeans…) or the
   **Filters** button (stores, max price, sort by price).
4. **Add your photo** in the *Try-on photo* box on the left. You only do this
   once; it's remembered until you click *Change photo*.
5. Click **Try it on** on any product. In about 10–15 seconds you'll see
   yourself wearing it.
6. Every try-on is saved under **"Fits you've tried"**. Click one to view it
   again, **Save it** to download, **Cop it →** to open the shop page, or
   **Clear all** to delete them.

### Getting the best try-on

| ✅ Do | ❌ Avoid |
|---|---|
| Full-body photo, head to feet | Webcam or head-and-shoulders selfies |
| Portrait (tall) photo | Landscape (wide) photos |
| Standing, facing the camera, arms visible | Sitting, turned sideways, heavy coats |
| The original photo from your camera roll | Screenshots (low quality, extra icons) |

A mirror selfie is perfect. The app warns you if your photo looks like a
close-up. The AI can only dress the body it can see: with a head-and-shoulders
photo, you'll only see the garment's collar.

## Costs

- About **3p per try-on**, charged by Google to your own billing account.
- **Free:** searching, browsing, filters, and repeating a try-on you've already
  done (results are cached, so the same photo + item never costs twice).
- Check your spending at https://aistudio.google.com/apikey → the usage
  (bar-chart) icon next to your key.

## Troubleshooting

| Message / problem | Fix |
|---|---|
| "GEMINI_API_KEY is not set" | `.env` is missing or misnamed. It must be called exactly `.env` (not `.env.txt`) and sit in this folder. Restart the app afterwards. |
| "Invalid GEMINI_API_KEY" | Copy the key again from https://aistudio.google.com/apikey, save `.env`, restart. |
| "No image-generation quota" / 429 | Billing isn't enabled on the key's project (step 3). If it is, you hit the per-minute limit; wait a minute and retry. |
| "Gemini refused this image pair" | A safety filter was triggered; try a different photo or product. |
| The result pastes my face onto the model | Your photo is a close-up. Use a full-body portrait photo. |
| A store shows an error or 0 results | That store changed its website. The other stores still work. |
| `python` or `pip` "not recognised" | Reinstall Python with *"Add python.exe to PATH"* ticked, or use `py -m pip …` and `py -m uvicorn …` on Windows. |
| *"Could not import module main"* | The terminal isn't in the app folder. Check the prompt shows `...\tryon-gemini>`; on Windows use `cd /d <folder>` to switch drive as well. |
| "Address already in use" | The app is already running in another terminal; use that, or run with `--port 8002`. |

## What's in this folder

```
tryon-gemini/
├── main.py            web server and API
├── scraper.py         live search across the 6 stores
├── tryon.py           sends your photo + the garment to Gemini
├── static/            the website (HTML, CSS, JavaScript)
├── requirements.txt   Python packages
├── .env.example       template for your key (copy to .env)
└── .gitignore         keeps .env and your photos out of Git
```

Created while running: `uploads/` (your photo), `tryon_results/` (your
try-ons) and `garment_cache/` (product images). They stay on your computer.

## Privacy

Your photo stays on your computer. It's sent only to Google's Gemini API when
you click *Try it on*. Only upload photos of yourself or of people who have
agreed.
