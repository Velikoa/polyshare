"""
PolyShare — a personal share watchlist with live quotes, charts and fundamentals.

Data source: Yahoo Finance via the `yfinance` package (no API key required).
Ticker conventions: JSE = SYMBOL.JO (e.g. NPN.JO), LSE = .L, ASX = .AX, US = bare symbol.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
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

.ps-brand { display:flex; align-items:center; gap:.6rem; margin-bottom:.25rem; }
.ps-logo { width:38px; height:38px; border-radius:11px;
  background: linear-gradient(135deg,#6EE7B7 0%,#3B82F6 60%,#8B5CF6 100%);
  display:flex; align-items:center; justify-content:center; font-weight:800; color:#0B1220; font-size:18px; }
.ps-title { font-size:1.65rem; font-weight:800; letter-spacing:-0.02em; margin:0; }
.ps-sub { color:#8B96A8; font-size:.85rem; margin-top:-.2rem; }

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
# Watchlist persistence
#   1) URL query param  ?w=NPN.JO,SOL.JO   (bookmark-able, works across devices)
#   2) watchlist.json next to app.py       (survives page refreshes on one host)
# --------------------------------------------------------------------------- #
WL_FILE = Path(__file__).with_name("watchlist.json")
DEFAULT_WATCHLIST = ["NPN.JO", "SOL.JO", "SBK.JO", "AGL.JO", "AAPL", "MSFT"]


def _load_watchlist() -> list[str]:
    q = st.query_params.get("w")
    if q:
        return [s.strip().upper() for s in q.split(",") if s.strip()]
    try:
        data = json.loads(WL_FILE.read_text())
        if isinstance(data, list) and data:
            return [str(s).upper() for s in data]
    except Exception:
        pass
    return DEFAULT_WATCHLIST.copy()


def _save_watchlist(wl: list[str]) -> None:
    st.query_params["w"] = ",".join(wl)
    try:
        WL_FILE.write_text(json.dumps(wl, indent=2))
    except Exception:
        pass  # read-only filesystem on some hosts – the URL still carries the list


if "watchlist" not in st.session_state:
    st.session_state.watchlist = _load_watchlist()
if "selected" not in st.session_state:
    st.session_state.selected = st.session_state.watchlist[0] if st.session_state.watchlist else None

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


@st.cache_data(ttl=60, show_spinner=False)
def get_quote(symbol: str) -> dict:
    t = yf.Ticker(symbol)
    hist = t.history(period="10d", interval="1d", auto_adjust=False)
    hist = hist.dropna(subset=["Close"])
    if hist.empty:
        raise ValueError(f"No price data for {symbol}")
    today, prev = hist.iloc[-1], (hist.iloc[-2] if len(hist) > 1 else hist.iloc[-1])
    fi = {}
    try:
        fi = {
            "last": t.fast_info.last_price,
            "currency": t.fast_info.currency,
            "exchange": t.fast_info.exchange,
        }
    except Exception:
        pass
    last = fi.get("last")
    if last is None or (isinstance(last, float) and math.isnan(last)):
        last = float(today["Close"])
    return {
        "symbol": symbol,
        "last": float(last),
        "currency": fi.get("currency") or "",
        "exchange": fi.get("exchange") or "",
        "as_of": hist.index[-1].to_pydatetime(),
        "open": float(today["Open"]),
        "high": float(today["High"]),
        "low": float(today["Low"]),
        "volume": float(today["Volume"]),
        "prev_close": float(prev["Close"]),
        "prev_high": float(prev["High"]),
        "prev_low": float(prev["Low"]),
        "prev_volume": float(prev["Volume"]),
        "prev_date": hist.index[-2].to_pydatetime() if len(hist) > 1 else None,
    }


@st.cache_data(ttl=300, show_spinner=False)
def get_history(symbol: str, period_key: str) -> pd.DataFrame:
    period, interval = PERIODS[period_key]
    df = yf.Ticker(symbol).history(period=period, interval=interval, auto_adjust=False)
    return df.dropna(subset=["Close"])


@st.cache_data(ttl=3600, show_spinner=False)
def get_profile(symbol: str) -> dict:
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
                st.session_state.selected = st.session_state.watchlist[0] if st.session_state.watchlist else None
            st.rerun()

    st.divider()
    if st.button("↻ Refresh data", width="stretch"):
        st.cache_data.clear()
        st.rerun()
    st.caption("Tip: bookmark this page — your watchlist is saved in the link.")

# --------------------------------------------------------------------------- #
# Watchlist selector
# --------------------------------------------------------------------------- #
wl = st.session_state.watchlist
if not wl:
    st.info("Your watchlist is empty. Open the sidebar (top-left ›) to add shares.")
    st.stop()

if st.session_state.selected not in wl:
    st.session_state.selected = wl[0]

chosen = st.pills(
    "Watchlist",
    wl,
    selection_mode="single",
    default=st.session_state.selected,
    label_visibility="collapsed",
)
if chosen and chosen != st.session_state.selected:
    st.session_state.selected = chosen
sym = st.session_state.selected

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
      <div class="ps-meta">{' · '.join(meta_bits)} · as of {qd['as_of'].strftime('%a %d %b %Y')}</div>
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
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

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

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=hist.index, y=y, mode="lines", name="Close",
        line=dict(color=color, width=2.2), fill="tozeroy", fillcolor=rgba,
        hovertemplate="%{x|%d %b %Y %H:%M}<br>" + ccy + " %{y:,.2f}<extra></extra>",
    ))
    fig.add_trace(go.Bar(
        x=hist.index, y=hist["Volume"], name="Volume", yaxis="y2",
        marker_color="rgba(139,150,168,.35)", hovertemplate="Vol %{y:,.0f}<extra></extra>",
    ))
    fig.update_layout(
        height=420, margin=dict(l=10, r=10, t=30, b=10),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, sans-serif", color="#C9D1DE"),
        hovermode="x unified", showlegend=False,
        title=dict(text=f"{period}: {pchg:+,.2f} ({ppct:+.2f}%)", font=dict(size=14, color=color), x=0),
        xaxis=dict(showgrid=False, rangeslider=dict(visible=False)),
        yaxis=dict(title=ccy, gridcolor="rgba(255,255,255,.06)", zeroline=False,
                   range=[float(y.min()) * 0.97, float(y.max()) * 1.02]),
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
    HEPS_FILE = Path(__file__).with_name("heps.json")
    try:
        heps_store = json.loads(HEPS_FILE.read_text())
    except Exception:
        heps_store = {}
    with st.expander("HEPS (manual entry)"):
        c1, c2 = st.columns(2)
        h_cur = c1.number_input(f"HEPS FY{fin['fy_end'][-4:]} ({fccy})", value=float(heps_store.get(sym, {}).get("cur", 0.0)), format="%.2f")
        h_prev = c2.number_input(f"HEPS FY{(fin['prev_fy_end'] or '')[-4:]} ({fccy})", value=float(heps_store.get(sym, {}).get("prev", 0.0)), format="%.2f")
        if st.button("Save HEPS"):
            heps_store[sym] = {"cur": h_cur, "prev": h_prev}
            try:
                HEPS_FILE.write_text(json.dumps(heps_store, indent=2))
                st.success("Saved.")
            except Exception:
                st.warning("Couldn't write to disk on this host — value kept for this session only.")
        if h_cur and h_prev:
            hv, hp = yoy(h_cur, h_prev)
            st.markdown(f"**HEPS YoY:** <span class='{css_dir(hv)}'>{hv:+.2f} ({hp:+.1f}%)</span>", unsafe_allow_html=True)

st.markdown(
    "<div class='ps-note' style='margin-top:1.5rem'>Prices may be delayed by 15–20 minutes depending on the exchange. "
    "Data: Yahoo Finance via yfinance. Not investment advice.</div>",
    unsafe_allow_html=True,
)
