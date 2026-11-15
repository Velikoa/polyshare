# PolyShare

A personal share watchlist: live quote summary, 1W–10Y price charts, company description and
latest annual results with year-on-year movements. One URL, works on laptop and phone.

Built with **Streamlit** (Python) and **Yahoo Finance** data via `yfinance` — no API key needed.

---

## 1. Where it's hosted

**Streamlit Community Cloud** (free, no credit card). It gives you a permanent URL like
`https://polyshare.streamlit.app` that opens on any browser — laptop, iPhone, Android.

### Deploy (≈10 minutes, once)

1. Create a GitHub repository (e.g. `polyshare`) and push this folder to it:
   ```bash
   cd polyshare
   git init && git add . && git commit -m "PolyShare"
   git branch -M main
   git remote add origin https://github.com/<your-username>/polyshare.git
   git push -u origin main
   ```
2. Go to <https://share.streamlit.io>, sign in with GitHub, click **Create app → Deploy a public app from GitHub**.
3. Pick the `polyshare` repo, branch `main`, main file `app.py`.
   Under **Advanced settings**, choose Python 3.11 or 3.12.
   Optional: set a custom subdomain, e.g. `polyshare`.
4. Click **Deploy**. Your app is live at `https://<subdomain>.streamlit.app`.

Notes
- Free apps sleep after ~12 hours without visitors; the first open afterwards takes ~30 s to wake. Click the "wake up" button if prompted.
- Any `git push` to `main` redeploys automatically.
- Want it private? In the app's **Settings → Sharing** on share.streamlit.io, set it to "Only specific people" and add your email (free tier allows one private app).

### Alternatives if you prefer AWS
Since you hold the AWS SAA cert: the same code runs unchanged on an EC2 `t3.micro` (`pip install -r requirements.txt && streamlit run app.py --server.port 80`), on App Runner, or in a Lightsail container. Streamlit Cloud is simply the zero-ops option.

---

## 2. "Download" it to your laptop and phone

PolyShare is a web app, so you install it as a shortcut that opens full-screen like a native app.

**Laptop (Chrome / Edge)**
1. Open your app URL.
2. Click the **install icon** at the right of the address bar (or ⋮ menu → *Cast, save and share* → **Install page as app…** / *Apps → Install this site as an app*).
3. It appears in your Start menu / Applications folder and opens in its own window.

**iPhone / iPad (Safari)**
1. Open the URL in Safari.
2. Tap **Share** (square with arrow) → **Add to Home Screen** → **Add**.

**Android (Chrome)**
1. Open the URL in Chrome.
2. Tap **⋮** → **Add to Home screen** (or **Install app**) → **Add**.

---

## 2b. Keep your watchlist (one-time, 5 minutes) — **do this**

Streamlit Cloud wipes the app's disk whenever the app sleeps or redeploys, so a watchlist saved only on the
server is lost overnight. PolyShare therefore stores `watchlist.json` and `heps.json` in a **private GitHub
Gist** on your account. Once configured, your list survives restarts and is the same on laptop and phone.

1. **Create the gist.** Go to <https://gist.github.com> (signed in). Filename: `watchlist.json`.
   Content: `[]` (two square brackets). Click **Create secret gist**.
   Copy the long hex ID from the address bar: `https://gist.github.com/<you>/`**`a1b2c3d4…`**.
2. **Create a token.** GitHub → your avatar → **Settings → Developer settings → Personal access tokens →
   Fine-grained tokens → Generate new token**. Name it `polyshare`; expiration: 1 year (or custom, further out).
   Under **Permissions → Account permissions** set **Gists: Read and write**. No repository access needed.
   Generate, then copy the token (starts with `github_pat_`) — it's shown only once.
3. **Give them to the app.** On <https://share.streamlit.io> open your app → **⋮ → Settings → Secrets**, paste:
   ```toml
   GIST_ID = "a1b2c3d4…"
   GITHUB_TOKEN = "github_pat_…"
   ```
   Save. The app reboots; the sidebar should now show "✅ Watchlist saved to your private Gist".
4. Add your shares once more — this time they stick.

Running locally instead? Put the same two lines in `polyshare/.streamlit/secrets.toml` (already git-ignored).

Without these secrets the app still works, but changes only live in the URL (`?w=NPN.JO,SOL.JO,…`) and on the
server's temporary disk; the sidebar shows a warning to remind you.

---

## 3. Run locally (optional)

```bash
pip install -r requirements.txt
streamlit run app.py
```
Open <http://localhost:8501>. On the same Wi-Fi, your phone can open the "Network URL" that Streamlit prints.

---

## 4. Using the app

- **Watchlist chips** at the top — tap a share to load it.
- **Sidebar (› top-left)** — search by company name or ticker and add; ✕ to remove; ↻ to refresh data.
- **Ticker format:** JSE `NPN.JO`, `SOL.JO`, `SBK.JO`; LSE `.L`; ASX `.AX`; US bare (`AAPL`).
- **Quote card:** price, day move (R and %), open, day high/low, volume, previous close, previous high/low, previous volume.
- **Chart:** 1W, 1M, 3M, 6M, 1Y, 3Y, 5Y, 10Y with volume bars.
- **Latest annual results:** revenue, operating expenses, operating profit, profit for the year, basic & diluted EPS, each with YoY movement and %.
- **HEPS:** headline EPS is a JSE/SAICA measure that Yahoo doesn't publish. Capture it from the SENS results announcement in the *HEPS (manual entry)* expander; the app stores it in `heps.json` and shows the YoY movement.

## Data caveats
- JSE and LSE prices arrive in cents/pence; the app converts to ZAR/GBP.
- Prices are delayed 15–20 min on most exchanges. Yahoo quotes are free but unofficial; occasional gaps happen.
- Income-statement lines are Yahoo's standardised mapping of the published IFRS statements, so "operating expenses" may be grouped differently from the AFS face of the income statement.
