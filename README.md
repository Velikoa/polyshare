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

**Keeping your watchlist in sync across devices:** the watchlist is encoded in the URL (`?w=NPN.JO,SOL.JO,…`).
After editing your list on one device, copy the URL from the address bar and re-add the shortcut on the other
device (or just bookmark the new URL). The server also keeps `watchlist.json` as a fallback.

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
