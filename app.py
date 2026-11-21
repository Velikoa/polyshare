"""
PolyShare — a personal share watchlist with live quotes, charts and fundamentals.

Data source: Yahoo Finance via the `yfinance` package (no API key required).
Ticker conventions: JSE = SYMBOL.JO (e.g. NPN.JO), LSE = .L, ASX = .AX, US = bare symbol.
"""
from __future__ import annotations

import html
import json
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

# --------------------------------------------------------------------------- #
# Page setup & theme
# --------------------------------------------------------------------------- #
st.set_page_config(
    page_title="PolyShare",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"] { font-family: 'Inter', -apple-system, system-ui, sans-serif; }
.block-container { padding-top: 3.2rem; padding-bottom: 3rem; max-width: 1200px; }
#MainMenu, footer { visibility: hidden; }

.ps-brand { display:flex; align-items:center; gap:.7rem; margin-bottom:.5rem; }
.ps-logo { width:54px; height:54px; border-radius:15px; flex-shrink:0;
  background: linear-gradient(135deg,#6EE7B7 0%,#3B82F6 60%,#8B5CF6 100%);
  display:flex; align-items:center; justify-content:center; font-weight:800; color:#0B1220; font-size:26px; }
/* "p." prefix needed: Streamlit's own paragraph style otherwise wins and pins the title at 16px */
.ps-brand p.ps-title { font-size:32px; font-weight:800; letter-spacing:-0.02em; margin:0; line-height:1.1; }
.ps-sub { color:#8B96A8; font-size:.85rem; margin-top:.1rem; }

/* Summary + market tables */
.ps-scroll { overflow-x:auto; -webkit-overflow-scrolling:touch; }
table.ps-sum { width:100%; border-collapse:collapse; font-size:.92rem; white-space:nowrap; margin:0; border:none; }
table.ps-sum th { text-align:right; color:#8B96A8; font-weight:500; font-size:.72rem;
  text-transform:uppercase; letter-spacing:.06em; padding:.45rem .6rem; border:none;
  border-bottom:1px solid rgba(255,255,255,.08); }
table.ps-sum td { text-align:right; padding:.6rem .6rem; border:none; border-bottom:1px solid rgba(255,255,255,.05);
  font-variant-numeric: tabular-nums; }
table.ps-sum tr:last-child td { border-bottom:none; }
table.ps-sum th:first-child, table.ps-sum td:first-child { text-align:left; position:sticky; left:0;
  background:#0F1728; z-index:1; }
table.ps-sum .tk { font-weight:700; }
table.ps-sum .cc { color:#8B96A8; font-size:.7rem; font-weight:500; margin-left:.25rem; }
table.ps-sum .nm { color:#8B96A8; font-size:.75rem; max-width:170px; overflow:hidden; text-overflow:ellipsis; }
table.ps-sum .px { font-weight:700; }
table.ps-sum td.err { text-align:left; color:#F87171; font-size:.8rem; }
@media (max-width: 640px) {
  table.ps-sum { font-size:.85rem; }
  table.ps-sum th, table.ps-sum td { padding:.5rem .45rem; }
  table.ps-sum .nm { max-width:105px; }
}

.ps-card { background: linear-gradient(180deg, rgba(255,255,255,.04), rgba(255,255,255,.015));
  border:1px solid rgba(255,255,255,.08); border-radius:16px; padding:1.1rem 1.25rem; margin-bottom:1rem; }
.ps-name { font-size:1.35rem; font-weight:700; margin:0; }
.ps-meta { color:#8B96A8; font-size:.8rem; }
.ps-price { font-size:2.6rem; font-weight:800; letter-spacing:-0.03em; line-height:1.1; }
.ps-chg { font-size:1.05rem; font-weight:600; }
.up { color:#34D399; } .down { color:#F87171; } .flat { color:#8B96A8; }

.ps-grid { display:grid; grid-template-columns: repeat(auto-fit, minmax(150px,1fr)); gap:.6rem; }
.ps-tile { background:rgba(255,255,255,.035); border:1px solid rgba(255,255,255,.07);
  border-radius:12px; padding:.65rem .8rem; }
.ps-tile .k { color:#8B96A8; font-size:.72rem; text-transform:uppercase; letter-spacing:.06em; }
.ps-tile .v { font-size:1.05rem; font-weight:600; margin-top:.15rem; }
.ps-tile .s { font-size:.75rem; color:#8B96A8; }

.ps-section { font-size:.78rem; text-transform:uppercase; letter-spacing:.1em; color:#8B96A8;
  font-weight:600; margin:1.1rem 0 .5rem 0; }
.ps-desc { color:#C9D1DE; line-height:1.55; font-size:.95rem; }

table.ps-fin { width:100%; border-collapse:collapse; font-size:.92rem; }
table.ps-fin th { text-align:left; color:#8B96A8; font-weight:500; font-size:.75rem;
  text-transform:uppercase; letter-spacing:.06em; padding:.45rem .5rem; border-bottom:1px solid rgba(255,255,255,.08); }
table.ps-fin td { padding:.55rem .5rem; border-bottom:1px solid rgba(255,255,255,.05); }
table.ps-fin td.num { text-align:right; font-variant-numeric: tabular-nums; }
.ps-note { color:#8B96A8; font-size:.78rem; margin-top:.5rem; }

div[data-testid="stPills"] button { border-radius: 999px !important; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

# --------------------------------------------------------------------------- #
# Persistence
#   Preferred: a private GitHub Gist (survives app restarts, shared across devices).
#     Set in Streamlit secrets:  GIST_ID = "..."   GITHUB_TOKEN = "github_pat_..."
#   Fallback: URL query param ?w=... plus a JSON file next to app.py (lost on redeploy).
# --------------------------------------------------------------------------- #
DEFAULT_WATCHLIST = ["NPN.JO", "SOL.JO", "SBK.JO", "AGL.JO", "AAPL", "MSFT"]
WL_NAME, HEPS_NAME = "watchlist.json", "heps.json"


def _gist_cfg():
    try:
        gid, tok = st.secrets["GIST_ID"], st.secrets["GITHUB_TOKEN"]
        return (gid, tok) if gid and tok else None
    except Exception:
        return None


def _gh_headers(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"}


@st.cache_data(ttl=600, show_spinner=False)
def _gist_files(gid: str, tok: str) -> dict:
    r = requests.get(f"https://api.github.com/gists/{gid}", headers=_gh_headers(tok), timeout=10)
    r.raise_for_status()
    return {name: f.get("content", "") for name, f in r.json().get("files", {}).items()}


def _gist_put(gid: str, tok: str, name: str, content: str) -> None:
    r = requests.patch(f"https://api.github.com/gists/{gid}", headers=_gh_headers(tok),
                       json={"files": {name: {"content": content}}}, timeout=10)
    r.raise_for_status()
    _gist_files.clear()


def store_load(name: str, default):
    """Read a JSON document from the gist, else from local disk, else default."""
    cfg = _gist_cfg()
    if cfg:
        try:
            raw = _gist_files(*cfg).get(name)
            if raw:
                return json.loads(raw)
        except Exception as e:
            st.session_state["store_error"] = f"Gist read failed: {e}"
    try:
        return json.loads(Path(__file__).with_name(name).read_text())
    except Exception:
        return default


def store_save(name: str, data) -> bool:
    """Write a JSON document to the gist (if configured) and to local disk. Returns True if durable."""
    payload = json.dumps(data, indent=2)
    durable = False
    cfg = _gist_cfg()
    if cfg:
        try:
            _gist_put(*cfg, name, payload)
            durable = True
        except Exception as e:
            st.session_state["store_error"] = f"Gist write failed: {e}"
    try:
        Path(__file__).with_name(name).write_text(payload)
    except Exception:
        pass
    return durable


def _load_watchlist() -> list[str]:
    if _gist_cfg():
        data = store_load(WL_NAME, None)
        if isinstance(data, list) and data:
            return [str(s).upper() for s in data]
    q = st.query_params.get("w")
    if q:
        return [s.strip().upper() for s in q.split(",") if s.strip()]
    data = store_load(WL_NAME, None)
    if isinstance(data, list) and data:
        return [str(s).upper() for s in data]
    return DEFAULT_WATCHLIST.copy()


def _save_watchlist(wl: list[str]) -> None:
    st.query_params["w"] = ",".join(wl)
    store_save(WL_NAME, wl)


SUMMARY = "__summary__"          # the "Summary" tab in the selector row
LOCAL_TZ = ZoneInfo("Africa/Johannesburg")
REFRESH_SECONDS = 60              # summary + quote card re-fetch while the page is open

# Market updates table: (label, Yahoo symbol, unit shown under the label, decimals)
MARKETS = [
    ("Gold", "GC=F", "USD per ounce", 2),
    ("Crude oil (Brent)", "BZ=F", "USD per barrel", 2),
    ("USD / ZAR", "USDZAR=X", "Rand per US$1", 4),
    ("EUR / ZAR", "EURZAR=X", "Rand per €1", 4),
    ("Bitcoin", "BTC-USD", "USD per bitcoin", 2),
]

if "watchlist" not in st.session_state:
    st.session_state.watchlist = _load_watchlist()
if "selected" not in st.session_state:
    st.session_state.selected = SUMMARY   # always open on the Summary page

# --------------------------------------------------------------------------- #
# Data layer (cached)
# --------------------------------------------------------------------------- #
PERIODS = {
    "1W": ("7d", "60m"),
    "1M": ("1mo", "1d"),
    "3M": ("3mo", "1d"),
    "6M": ("6mo", "1d"),
    "1Y": ("1y", "1d"),
    "3Y": ("3y", "1wk"),
    "5Y": ("5y", "1wk"),
    "10Y": ("10y", "1wk"),
}


def _fetch_quote(symbol: str) -> dict:
    """Live quote (fast_info) + last trade time (1-min bars) + previous-session figures (daily bars).
    Uncached so it can run in worker threads; use get_quote / get_quotes from the UI."""
    t = yf.Ticker(symbol)

    # --- live quote fields -------------------------------------------------
    fi = {}
    try:
        f = t.fast_info
        fi = {k: _f(getattr(f, k, None)) for k in
              ("last_price", "open", "day_high", "day_low", "last_volume", "previous_close")}
        fi["currency"] = getattr(f, "currency", "") or ""
        fi["exchange"] = getattr(f, "exchange", "") or ""
    except Exception:
        pass

    # --- today's intraday bars: last trade time + fallbacks -----------------
    intra = pd.DataFrame()
    try:
        intra = t.history(period="1d", interval="1m", auto_adjust=False).dropna(subset=["Close"])
    except Exception:
        pass

    # --- daily bars: previous session --------------------------------------
    daily = t.history(period="10d", interval="1d", auto_adjust=False).dropna(subset=["Close"])
    if daily.empty and intra.empty:
        raise ValueError(f"No price data for {symbol}")

    if not intra.empty:
        as_of = intra.index[-1]
        agg = {"open": float(intra["Open"].iloc[0]), "high": float(intra["High"].max()),
               "low": float(intra["Low"].min()), "volume": float(intra["Volume"].sum()),
               "last": float(intra["Close"].iloc[-1])}
    else:
        as_of = daily.index[-1]
        row = daily.iloc[-1]
        agg = {"open": float(row["Open"]), "high": float(row["High"]), "low": float(row["Low"]),
               "volume": float(row["Volume"]), "last": float(row["Close"])}

    # previous session = last daily bar strictly before the trade date
    trade_date = as_of.date()
    before = daily[[d.date() < trade_date for d in daily.index]]
    prev = before.iloc[-1] if not before.empty else None

    def pick(key_fi, key_agg):
        v = fi.get(key_fi)
        return v if v is not None else agg[key_agg]

    prev_close = fi.get("previous_close")
    if prev_close is None and prev is not None:
        prev_close = float(prev["Close"])

    return {
        "symbol": symbol,
        "last": pick("last_price", "last"),
        "currency": fi.get("currency", ""),
        "exchange": fi.get("exchange", ""),
        "as_of": as_of.to_pydatetime(),
        "open": pick("open", "open"),
        "high": pick("day_high", "high"),
        "low": pick("day_low", "low"),
        "volume": pick("last_volume", "volume"),
        "prev_close": prev_close if prev_close is not None else agg["last"],
        "prev_high": float(prev["High"]) if prev is not None else None,
        "prev_low": float(prev["Low"]) if prev is not None else None,
        "prev_volume": float(prev["Volume"]) if prev is not None else None,
        "prev_date": prev.name.to_pydatetime() if prev is not None else None,
    }


@st.cache_data(ttl=30, show_spinner=False)
def get_quote(symbol: str) -> dict:
    return _fetch_quote(symbol)


def _run_parallel(fn, symbols, workers: int = 6) -> dict:
    """Call fn(symbol) for each symbol in a small thread pool. Failures come back as {"error": "..."}."""
    out = {}
    if not symbols:
        return out
    with ThreadPoolExecutor(max_workers=min(workers, len(symbols))) as ex:
        futs = {ex.submit(fn, s): s for s in symbols}
        for fut in as_completed(futs):
            s = futs[fut]
            try:
                out[s] = fut.result()
            except Exception as e:
                out[s] = {"error": str(e) or type(e).__name__}
    return out


@st.cache_data(ttl=30, show_spinner=False)
def get_quotes(symbols: tuple[str, ...]) -> dict:
    """Quotes for many symbols at once (Summary page) — fetched in parallel."""
    return _run_parallel(_fetch_quote, symbols)


@st.cache_data(ttl=3600, show_spinner=False)
def get_names(symbols: tuple[str, ...]) -> dict:
    res = _run_parallel(_fetch_profile, symbols)
    return {s: (r.get("name") or s) if "error" not in r else s for s, r in res.items()}


@st.cache_data(ttl=300, show_spinner=False)
def get_history(symbol: str, period_key: str) -> pd.DataFrame:
    period, interval = PERIODS[period_key]
    df = yf.Ticker(symbol).history(period=period, interval=interval, auto_adjust=False)
    return df.dropna(subset=["Close"])


@st.cache_data(ttl=3600, show_spinner=False)
def get_daily(symbol: str) -> pd.DataFrame:
    """~11.5 years of daily bars: feeds the 30-day / 1-year averages (even on the 10Y chart,
    whose first point needs a year of history before it) and the 1-year high/low."""
    start = (pd.Timestamp.today() - pd.DateOffset(years=11, months=6)).strftime("%Y-%m-%d")
    df = yf.Ticker(symbol).history(start=start, interval="1d", auto_adjust=False)
    return df.dropna(subset=["Close"])


def _fetch_profile(symbol: str) -> dict:
    try:
        info = yf.Ticker(symbol).info or {}
    except Exception:
        info = {}
    return {
        "name": info.get("longName") or info.get("shortName") or symbol,
        "summary": info.get("longBusinessSummary") or "",
        "sector": info.get("sector") or "",
        "industry": info.get("industry") or "",
        "website": info.get("website") or "",
        "country": info.get("country") or "",
        "employees": info.get("fullTimeEmployees"),
        "fin_currency": info.get("financialCurrency") or "",
    }


@st.cache_data(ttl=3600, show_spinner=False)
def get_profile(symbol: str) -> dict:
    return _fetch_profile(symbol)


FIN_ROWS = [
    ("Total revenue", ["Total Revenue", "Operating Revenue"]),
    ("Operating expenses", ["Operating Expense", "Total Operating Expenses"]),
    ("Operating profit", ["Operating Income", "EBIT"]),
    ("Profit for the year", ["Net Income", "Net Income Common Stockholders"]),
    ("Basic EPS", ["Basic EPS"]),
    ("Diluted EPS", ["Diluted EPS"]),
]


@st.cache_data(ttl=3600, show_spinner=False)
def get_financials(symbol: str) -> dict | None:
    try:
        inc = yf.Ticker(symbol).income_stmt
    except Exception:
        return None
    if inc is None or inc.empty or inc.shape[1] < 1:
        return None
    inc = inc.sort_index(axis=1, ascending=False)
    cur_col, prev_col = inc.columns[0], (inc.columns[1] if inc.shape[1] > 1 else None)
    rows = []
    for label, keys in FIN_ROWS:
        key = next((k for k in keys if k in inc.index), None)
        if key is None:
            continue
        cur = inc.loc[key, cur_col]
        prev = inc.loc[key, prev_col] if prev_col is not None else None
        rows.append({"label": label, "current": _f(cur), "previous": _f(prev)})
    return {
        "fy_end": pd.Timestamp(cur_col).strftime("%d %b %Y"),
        "prev_fy_end": pd.Timestamp(prev_col).strftime("%d %b %Y") if prev_col is not None else None,
        "rows": rows,
    }


def _f(v):
    try:
        v = float(v)
        return None if math.isnan(v) else v
    except Exception:
        return None


@st.cache_data(ttl=3600, show_spinner=False)
def search_symbols(query: str) -> list[dict]:
    try:
        res = yf.Search(query, max_results=8).quotes
    except Exception:
        return []
    out = []
    for q in res:
        if q.get("quoteType") not in ("EQUITY", "ETF"):
            continue
        out.append({
            "symbol": q.get("symbol"),
            "name": q.get("longname") or q.get("shortname") or "",
            "exch": q.get("exchDisp") or q.get("exchange") or "",
        })
    return out


# --------------------------------------------------------------------------- #
# Formatting helpers
# --------------------------------------------------------------------------- #
def norm_currency(ccy: str, value: float | None):
    """Yahoo quotes JSE shares in ZAc (cents) and LSE in GBp (pence). Show in major units."""
    if value is None:
        return ccy, None
    if ccy == "ZAc":
        return "ZAR", value / 100
    if ccy in ("GBp", "GBX"):
        return "GBP", value / 100
    return ccy, value


def fmt_price(v: float | None, ccy: str = "") -> str:
    if v is None:
        return "—"
    return f"{ccy} {v:,.2f}".strip()


def fmt_int(v: float | None) -> str:
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return "—"
    return f"{v:,.0f}"


def fmt_big(v: float | None, ccy: str = "") -> str:
    if v is None:
        return "—"
    a = abs(v)
    for div, suf in ((1e12, "tn"), (1e9, "bn"), (1e6, "m"), (1e3, "k")):
        if a >= div:
            return f"{ccy} {v/div:,.2f}{suf}".strip()
    return f"{ccy} {v:,.2f}".strip()


def yoy(cur: float | None, prev: float | None):
    """Returns (abs change, % change) with sensible handling of sign flips."""
    if cur is None or prev is None:
        return None, None
    chg = cur - prev
    pct = None if prev == 0 else chg / abs(prev) * 100
    return chg, pct


def css_dir(v: float | None) -> str:
    if v is None or v == 0:
        return "flat"
    return "up" if v > 0 else "down"


def arrow(v: float | None) -> str:
    if v is None or v == 0:
        return "•"
    return "▲" if v > 0 else "▼"


def to_local(dt) -> datetime | None:
    """Show times in South African time regardless of the server's (UTC) clock or the exchange's zone."""
    if dt is None:
        return None
    if getattr(dt, "tzinfo", None) is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(LOCAL_TZ)


def _utc_index(idx: pd.DatetimeIndex) -> pd.DatetimeIndex:
    return idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")


def one_year_range(symbol: str, qd: dict):
    """52-week high/low (intraday highs/lows) with dates, in the quote's raw units (e.g. ZAc).
    Today's live high/low is included because JSE daily bars only post after the close."""
    hi = lo = hi_d = lo_d = None
    try:
        daily = get_daily(symbol)
    except Exception:
        daily = pd.DataFrame()
    if not daily.empty:
        since = pd.Timestamp.now(tz=daily.index.tz) - pd.Timedelta(days=365)
        yr = daily[daily.index > since]
        highs = yr["High"][yr["High"] > 0]
        lows = yr["Low"][yr["Low"] > 0]          # Yahoo occasionally reports a 0 low on JSE bars
        if not highs.empty:
            hi, hi_d = float(highs.max()), highs.idxmax().to_pydatetime()
        if not lows.empty:
            lo, lo_d = float(lows.min()), lows.idxmin().to_pydatetime()
    if qd.get("high") and (hi is None or qd["high"] > hi):
        hi, hi_d = qd["high"], qd["as_of"]
    if qd.get("low") and (lo is None or qd["low"] < lo):
        lo, lo_d = qd["low"], qd["as_of"]
    return hi, hi_d, lo, lo_d


def moving_averages(daily: pd.DataFrame, scale: float) -> pd.DataFrame:
    """30-day average = last 30 trading sessions; 1-year average = last 365 calendar days.
    The 1-year line is only drawn once a full year of history exists."""
    close = daily["Close"] * scale
    ma30 = close.rolling(30, min_periods=30).mean()
    ma1y = close.rolling("365D").mean()
    ma1y[close.index < close.index[0] + pd.Timedelta(days=364)] = float("nan")
    return pd.DataFrame({"ma30": ma30, "ma1y": ma1y})


def _sum_row_label(sym: str, ccy: str, name: str) -> str:
    cc = f"<span class='cc'>{ccy}</span>" if ccy else ""
    nm = f"<div class='nm'>{html.escape(name)}</div>" if name and name != sym else ""
    return f"<td><div class='tk'>{html.escape(sym)}{cc}</div>{nm}</td>"


def watchlist_table(symbols, quotes: dict, names: dict) -> str:
    head = ("<tr><th>Share</th><th>Price</th><th>Day high</th><th>Day low</th><th>Prev. close</th>"
            "<th>Prev. high</th><th>Prev. low</th><th>Volume today</th><th>Prev. volume</th></tr>")
    rows = ""
    for s in symbols:
        q = quotes.get(s) or {"error": "no data"}
        name = names.get(s, s)
        if "error" in q:
            rows += ("<tr>" + _sum_row_label(s, "", name) +
                     f"<td colspan='8' class='err'>Couldn't load: {html.escape(q['error'][:90])}</td></tr>")
            continue
        ccy, last = norm_currency(q["currency"], q["last"])
        n = lambda v: norm_currency(q["currency"], v)[1]
        prev_close = n(q["prev_close"])
        d = css_dir(None if last is None or prev_close is None else last - prev_close)
        rows += (
            "<tr>" + _sum_row_label(s, ccy, name) +
            f"<td class='px {d}'>{fmt_price(last)}</td>"
            f"<td>{fmt_price(n(q['high']))}</td><td>{fmt_price(n(q['low']))}</td>"
            f"<td>{fmt_price(prev_close)}</td>"
            f"<td>{fmt_price(n(q['prev_high']))}</td><td>{fmt_price(n(q['prev_low']))}</td>"
            f"<td>{fmt_int(q['volume'])}</td><td>{fmt_int(q['prev_volume'])}</td></tr>"
        )
    return (f"<div class='ps-card ps-scroll'><table class='ps-sum'><thead>{head}</thead>"
            f"<tbody>{rows}</tbody></table></div>")


def market_table(quotes: dict) -> str:
    head = "<tr><th>Market</th><th>Price</th><th>Change</th><th>Change %</th><th>Last update</th></tr>"
    rows = ""
    for label, sym, unit, dp in MARKETS:
        q = quotes.get(sym) or {"error": "no data"}
        lab = (f"<td><div class='tk'>{label}</div><div class='nm'>{unit}</div></td>")
        if "error" in q:
            rows += f"<tr>{lab}<td colspan='4' class='err'>Couldn't load: {html.escape(q['error'][:90])}</td></tr>"
            continue
        last, prev = q["last"], q["prev_close"]
        chg = (last - prev) if (last is not None and prev) else None
        pct = (chg / prev * 100) if chg is not None else None
        d = css_dir(chg)
        when = to_local(q["as_of"])
        rows += (
            f"<tr>{lab}<td class='px'>{'—' if last is None else f'{last:,.{dp}f}'}</td>"
            f"<td class='{d}'>{'—' if chg is None else f'{arrow(chg)} {chg:+,.{dp}f}'}</td>"
            f"<td class='{d}'>{'—' if pct is None else f'{pct:+.2f}%'}</td>"
            f"<td>{when.strftime('%a %H:%M') if when else '—'}</td></tr>"
        )
    return (f"<div class='ps-card ps-scroll'><table class='ps-sum'><thead>{head}</thead>"
            f"<tbody>{rows}</tbody></table></div>")


# --------------------------------------------------------------------------- #
# Header
# --------------------------------------------------------------------------- #
st.markdown(
    """
    <div class="ps-brand">
      <div class="ps-logo">P</div>
      <div><p class="ps-title">PolyShare</p>
      <div class="ps-sub">Your watchlist · live quotes · fundamentals</div></div>
    </div>
    """,
    unsafe_allow_html=True,
)

# --------------------------------------------------------------------------- #
# Sidebar: manage watchlist
# --------------------------------------------------------------------------- #
with st.sidebar:
    st.markdown("### Manage watchlist")
    st.caption("JSE tickers end in **.JO** (e.g. NPN.JO), LSE **.L**, ASX **.AX**. US tickers are bare (AAPL).")

    q = st.text_input("Search a company or ticker", placeholder="e.g. Naspers or NPN.JO")
    if q:
        hits = search_symbols(q)
        if hits:
            labels = [f"{h['symbol']} — {h['name']} ({h['exch']})" for h in hits]
            pick = st.selectbox("Results", labels, label_visibility="collapsed")
            if st.button("➕ Add to watchlist", width="stretch"):
                sym = pick.split(" — ")[0].upper()
                if sym not in st.session_state.watchlist:
                    st.session_state.watchlist.append(sym)
                    _save_watchlist(st.session_state.watchlist)
                st.session_state.selected = sym
                st.rerun()
        else:
            direct = q.strip().upper()
            st.caption("No search results — add the exact ticker instead:")
            if st.button(f"➕ Add {direct}", width="stretch"):
                if direct not in st.session_state.watchlist:
                    st.session_state.watchlist.append(direct)
                    _save_watchlist(st.session_state.watchlist)
                st.session_state.selected = direct
                st.rerun()

    st.divider()
    st.markdown("**Remove**")
    for sym in list(st.session_state.watchlist):
        c1, c2 = st.columns([4, 1])
        c1.write(sym)
        if c2.button("✕", key=f"rm_{sym}", help=f"Remove {sym}"):
            st.session_state.watchlist.remove(sym)
            _save_watchlist(st.session_state.watchlist)
            if st.session_state.selected == sym:
                st.session_state.selected = SUMMARY
            st.rerun()

    st.divider()
    if st.button("↻ Refresh data", width="stretch"):
        st.cache_data.clear()
        st.rerun()
    if _gist_cfg():
        if st.session_state.get("store_error"):
            st.error(st.session_state["store_error"])
        else:
            st.caption("✅ Watchlist saved to your private Gist — synced across devices.")
    else:
        st.warning("Storage not configured: changes are lost when the app restarts. "
                   "See README → 'Keep your watchlist'.")

# --------------------------------------------------------------------------- #
# Watchlist selector
# --------------------------------------------------------------------------- #
wl = st.session_state.watchlist
if st.session_state.selected != SUMMARY and st.session_state.selected not in wl:
    st.session_state.selected = SUMMARY

chosen = st.pills(
    "Watchlist",
    [SUMMARY] + wl,
    selection_mode="single",
    default=st.session_state.selected,
    format_func=lambda o: "📊 Summary" if o == SUMMARY else o,
    label_visibility="collapsed",
)
if chosen and chosen != st.session_state.selected:
    st.session_state.selected = chosen
sym = st.session_state.selected


def footer() -> None:
    st.markdown(
        "<div class='ps-note' style='margin-top:1.5rem'>Prices may be delayed by 15–20 minutes depending on the exchange. "
        "Data: Yahoo Finance via yfinance. Not investment advice.</div>",
        unsafe_allow_html=True,
    )


# --------------------------------------------------------------------------- #
# Summary page (opens by default)
# --------------------------------------------------------------------------- #
@st.fragment(run_every=REFRESH_SECONDS)
def summary_page(symbols: tuple[str, ...]) -> None:
    """Re-runs itself every minute while open, like the quote card."""
    market_syms = tuple(m[1] for m in MARKETS)
    with st.spinner("Fetching prices…"):
        quotes = get_quotes(symbols + market_syms)
        names = get_names(symbols) if symbols else {}
    updated = datetime.now(LOCAL_TZ).strftime("%H:%M:%S")

    st.markdown('<div class="ps-section">Watchlist summary</div>', unsafe_allow_html=True)
    if symbols:
        st.markdown(watchlist_table(symbols, quotes, names), unsafe_allow_html=True)
    else:
        st.info("Your watchlist is empty. Open the sidebar (top-left ›) to add shares.")

    st.markdown('<div class="ps-section">Market updates</div>', unsafe_allow_html=True)
    st.markdown(market_table(quotes), unsafe_allow_html=True)
    st.markdown(
        f"<div class='ps-note'>Refreshed {updated} (SA time) · updates every minute · "
        "tap a share above for its chart and details. Previous = previous trading session; "
        "change on the market rows is against the previous close.</div>",
        unsafe_allow_html=True,
    )


if sym == SUMMARY:
    summary_page(tuple(wl))
    footer()
    st.stop()

# --------------------------------------------------------------------------- #
# Quote summary
# --------------------------------------------------------------------------- #
try:
    with st.spinner(f"Fetching {sym}…"):
        qd = get_quote(sym)
        prof = get_profile(sym)
except Exception as e:
    st.error(f"Couldn't load **{sym}**: {e}. Check the ticker (JSE shares need the `.JO` suffix).")
    st.stop()

@st.fragment(run_every=REFRESH_SECONDS)
def quote_card(sym: str, prof: dict) -> None:
    """Re-runs itself every minute while the page is open, so prices stay fresh on a phone."""
    try:
        qd = get_quote(sym)
    except Exception as e:
        st.error(f"Couldn't refresh {sym}: {e}")
        return
    updated = datetime.now(LOCAL_TZ).strftime("%H:%M:%S")
    yr_hi, yr_hi_d, yr_lo, yr_lo_d = one_year_range(sym, qd)
    _, yr_hi = norm_currency(qd["currency"], yr_hi)
    _, yr_lo = norm_currency(qd["currency"], yr_lo)
    yr_hi_s = yr_hi_d.strftime("%d %b %Y") if yr_hi_d else "last 12 months"
    yr_lo_s = yr_lo_d.strftime("%d %b %Y") if yr_lo_d else "last 12 months"
    ccy, last = norm_currency(qd["currency"], qd["last"])
    _, open_ = norm_currency(qd["currency"], qd["open"])
    _, high = norm_currency(qd["currency"], qd["high"])
    _, low = norm_currency(qd["currency"], qd["low"])
    _, prev_close = norm_currency(qd["currency"], qd["prev_close"])
    _, prev_high = norm_currency(qd["currency"], qd["prev_high"])
    _, prev_low = norm_currency(qd["currency"], qd["prev_low"])
    chg = last - prev_close
    pct = (chg / prev_close * 100) if prev_close else 0.0
    d = css_dir(chg)
    prev_date = qd["prev_date"].strftime("%a %d %b") if qd["prev_date"] else "prev. session"

    meta_bits = [b for b in (qd["exchange"], prof["sector"], prof["industry"]) if b]
    st.markdown(
        f"""
        <div class="ps-card">
          <p class="ps-name">{prof['name']} <span class="ps-meta">· {sym}</span></p>
          <div class="ps-meta">{' · '.join(meta_bits)} · last trade {qd['as_of'].strftime('%a %d %b %Y %H:%M %Z').strip()} · refreshed {updated}</div>
          <div style="display:flex;align-items:baseline;gap:1rem;flex-wrap:wrap;margin-top:.6rem;">
            <div class="ps-price">{fmt_price(last, ccy)}</div>
            <div class="ps-chg {d}">{arrow(chg)} {chg:+,.2f} ({pct:+.2f}%) today</div>
          </div>
          <div class="ps-grid" style="margin-top:1rem;">
            <div class="ps-tile"><div class="k">Open</div><div class="v">{fmt_price(open_, '')}</div></div>
            <div class="ps-tile"><div class="k">Day high</div><div class="v up">{fmt_price(high, '')}</div></div>
            <div class="ps-tile"><div class="k">Day low</div><div class="v down">{fmt_price(low, '')}</div></div>
            <div class="ps-tile"><div class="k">Volume today</div><div class="v">{fmt_int(qd['volume'])}</div></div>
            <div class="ps-tile"><div class="k">Prev. close</div><div class="v">{fmt_price(prev_close, '')}</div><div class="s">{prev_date}</div></div>
            <div class="ps-tile"><div class="k">Prev. high / low</div><div class="v">{fmt_price(prev_high, '')} / {fmt_price(prev_low, '')}</div><div class="s">{prev_date}</div></div>
            <div class="ps-tile"><div class="k">Prev. volume</div><div class="v">{fmt_int(qd['prev_volume'])}</div><div class="s">{prev_date}</div></div>
            <div class="ps-tile"><div class="k">1-year high</div><div class="v up">{fmt_price(yr_hi, '')}</div><div class="s">{yr_hi_s}</div></div>
            <div class="ps-tile"><div class="k">1-year low</div><div class="v down">{fmt_price(yr_lo, '')}</div><div class="s">{yr_lo_s}</div></div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )



quote_card(sym, prof)
ccy, _ = norm_currency(qd["currency"], qd["last"])

# --------------------------------------------------------------------------- #
# Price chart
# --------------------------------------------------------------------------- #
st.markdown('<div class="ps-section">Price history</div>', unsafe_allow_html=True)
period = st.pills("Period", list(PERIODS), default="6M", label_visibility="collapsed")
period = period or "6M"

try:
    hist = get_history(sym, period)
except Exception:
    hist = pd.DataFrame()

if hist.empty:
    st.warning("No history available for this period.")
else:
    _, closes = norm_currency(qd["currency"], 1.0)
    scale = closes  # 0.01 for ZAc/GBp, else 1
    y = hist["Close"] * scale
    first, lastp = float(y.iloc[0]), float(y.iloc[-1])
    pchg = lastp - first
    ppct = pchg / first * 100 if first else 0
    color = "#34D399" if pchg >= 0 else "#F87171"
    rgba = "rgba(52,211,153,.15)" if pchg >= 0 else "rgba(248,113,113,.15)"

    # Rolling averages are always computed from DAILY closes, then laid over whatever bar size the
    # chart uses (hourly for 1W, daily for 1M–1Y, weekly for 3Y+).
    ma = pd.DataFrame()
    try:
        daily = get_daily(sym)
        if not daily.empty:
            ma = moving_averages(daily, scale)
    except Exception:
        pass
    if not ma.empty:
        if period == "1W":   # step each day's average across that day's hourly bars
            m = ma.copy()
            m.index = _utc_index(m.index)
            ma = m.reindex(_utc_index(hist.index), method="ffill")
            ma.index = hist.index
        else:
            ma = ma[_utc_index(ma.index) >= _utc_index(hist.index[:1])[0]]

    lo_vals, hi_vals = [float(y.min())], [float(y.max())]
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=hist.index, y=y, mode="lines", name="Price",
        line=dict(color=color, width=2.2), fill="tozeroy", fillcolor=rgba,
        hovertemplate=ccy + " %{y:,.2f}",
    ))
    for col, label, lcolor, dash in (("ma30", "30-day avg", "#FBBF24", "solid"),
                                     ("ma1y", "1-year avg", "#A78BFA", "dash")):
        if ma.empty or ma[col].dropna().empty:
            continue
        fig.add_trace(go.Scatter(
            x=ma.index, y=ma[col], mode="lines", name=label, connectgaps=False,
            line=dict(color=lcolor, width=1.6, dash=dash),
            hovertemplate=ccy + " %{y:,.2f}",
        ))
        lo_vals.append(float(ma[col].min()))
        hi_vals.append(float(ma[col].max()))
    fig.add_trace(go.Bar(
        x=hist.index, y=hist["Volume"], name="Volume", yaxis="y2", showlegend=False,
        marker_color="rgba(139,150,168,.35)", hovertemplate="%{y:,.0f}",
    ))
    fig.update_layout(
        height=440, margin=dict(l=10, r=10, t=30, b=10),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", color="#C9D1DE"),
        hovermode="x unified", showlegend=True,
        legend=dict(orientation="h", yanchor="top", y=-0.08, xanchor="left", x=0,
                    bgcolor="rgba(0,0,0,0)", font=dict(size=12)),
        title=dict(text=f"{period}: {pchg:+,.2f} ({ppct:+.2f}%)", font=dict(size=14, color=color), x=0),
        xaxis=dict(showgrid=False, rangeslider=dict(visible=False),
                   hoverformat="%d %b %Y %H:%M" if period == "1W" else "%d %b %Y"),
        yaxis=dict(title=ccy, gridcolor="rgba(255,255,255,.06)", zeroline=False,
                   range=[min(lo_vals) * 0.97, max(hi_vals) * 1.02]),
        yaxis2=dict(overlaying="y", side="right", showgrid=False, showticklabels=False,
                    range=[0, float(hist["Volume"].max()) * 4]),
    )
    if period == "1W":
        fig.update_xaxes(rangebreaks=[dict(bounds=["sat", "mon"])])
    st.plotly_chart(fig, width="stretch", config={"displayModeBar": False})

# --------------------------------------------------------------------------- #
# Company description
# --------------------------------------------------------------------------- #
st.markdown('<div class="ps-section">About the company</div>', unsafe_allow_html=True)
if prof["summary"]:
    extra = []
    if prof["country"]:
        extra.append(prof["country"])
    if prof["employees"]:
        extra.append(f"{prof['employees']:,} employees")
    if prof["website"]:
        extra.append(f"<a href='{prof['website']}' target='_blank'>{prof['website'].replace('https://','').replace('http://','')}</a>")
    st.markdown(
        f"<div class='ps-card'><div class='ps-desc'>{prof['summary']}</div>"
        f"<div class='ps-note'>{' · '.join(extra)}</div></div>",
        unsafe_allow_html=True,
    )
else:
    st.caption("No company description available from the data provider.")

# --------------------------------------------------------------------------- #
# Financial summary (latest annual financial statements)
# --------------------------------------------------------------------------- #
st.markdown('<div class="ps-section">Latest annual results</div>', unsafe_allow_html=True)
fin = get_financials(sym)
if not fin or not fin["rows"]:
    st.caption("Annual financial statements not available from the data provider for this share.")
else:
    fccy = prof["fin_currency"] or ccy
    rows_html = ""
    for r in fin["rows"]:
        is_eps = "EPS" in r["label"]
        cur_s = fmt_price(r["current"], fccy) if is_eps else fmt_big(r["current"], fccy)
        prev_s = fmt_price(r["previous"], fccy) if is_eps else fmt_big(r["previous"], fccy)
        chg_v, chg_p = yoy(r["current"], r["previous"])
        chg_s = ("—" if chg_v is None else
                 (f"{chg_v:+,.2f}" if is_eps else fmt_big(chg_v).replace(" ", "")))
        if chg_v is not None and not is_eps and chg_v > 0:
            chg_s = "+" + chg_s
        pct_s = "—" if chg_p is None else f"{chg_p:+.1f}%"
        # Opex: rising cost is "bad"; everything else: rising is "good"
        good_up = r["label"] != "Operating expenses"
        cls = css_dir(chg_v) if good_up else css_dir(-chg_v if chg_v is not None else None)
        rows_html += (
            f"<tr><td>{r['label']}</td><td class='num'>{cur_s}</td><td class='num'>{prev_s}</td>"
            f"<td class='num {cls}'>{chg_s}</td><td class='num {cls}'>{pct_s}</td></tr>"
        )
    st.markdown(
        f"""
        <div class="ps-card">
        <table class="ps-fin">
          <thead><tr><th>Line item</th><th style="text-align:right">FY {fin['fy_end']}</th>
          <th style="text-align:right">FY {fin['prev_fy_end'] or '—'}</th>
          <th style="text-align:right">YoY</th><th style="text-align:right">YoY %</th></tr></thead>
          <tbody>{rows_html}</tbody>
        </table>
        <div class="ps-note">Source: Yahoo Finance standardised income statement, in {fccy}.
        HEPS (headline earnings per share) is a JSE / SAICA Circular measure that is not carried by the
        data provider — use the "HEPS" field below to record it from the company's SENS results announcement.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Manual HEPS capture (JSE-specific; persisted alongside the watchlist)
    heps_store = store_load(HEPS_NAME, {})
    if not isinstance(heps_store, dict):
        heps_store = {}
    with st.expander("HEPS (manual entry)"):
        c1, c2 = st.columns(2)
        h_cur = c1.number_input(f"HEPS FY{fin['fy_end'][-4:]} ({fccy})", value=float(heps_store.get(sym, {}).get("cur", 0.0)), format="%.2f")
        h_prev = c2.number_input(f"HEPS FY{(fin['prev_fy_end'] or '')[-4:]} ({fccy})", value=float(heps_store.get(sym, {}).get("prev", 0.0)), format="%.2f")
        if st.button("Save HEPS"):
            heps_store[sym] = {"cur": h_cur, "prev": h_prev}
            if store_save(HEPS_NAME, heps_store):
                st.success("Saved.")
            else:
                st.warning("Saved for now, but not durably — set up the Gist storage (see README) to keep it.")
        if h_cur and h_prev:
            hv, hp = yoy(h_cur, h_prev)
            st.markdown(f"**HEPS YoY:** <span class='{css_dir(hv)}'>{hv:+.2f} ({hp:+.1f}%)</span>", unsafe_allow_html=True)

footer()
