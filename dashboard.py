"""
dashboard.py — V7 Institutional Trading Terminal
Uses st.fragment(run_every=...) so ONLY the data refreshes.
CSS, fonts, page skeleton are rendered once — zero flash.
Usage: streamlit run dashboard.py
"""

import os, json, time, math
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo
from collections import defaultdict

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import numpy as np

# =====================================================================
#  PAGE CONFIG  (runs once)
# =====================================================================
st.set_page_config(
    page_title="HYBRID GRID + MOMENTUM",
    page_icon="",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# =====================================================================
#  COLORS
# =====================================================================
BG       = "#0b0e17"
BG2      = "#0f1320"
PANEL    = "#141824"
PANEL2   = "#181d2e"
BORDER   = "#1e2538"
BORDER2  = "#262d42"
GOLD     = "#e5a90a"
GOLD_LT  = "#f0c040"
GOLD_DIM = "rgba(229,169,10,0.12)"
GREEN    = "#22c55e"
GREEN_DIM= "rgba(34,197,94,0.1)"
RED      = "#ef4444"
RED_DIM  = "rgba(239,68,68,0.1)"
CYAN     = "#38bdf8"
SILVER   = "#94a3b8"
DIM      = "#475569"
WHITE    = "#e2e8f0"
MUTED    = "#64748b"

# =====================================================================
#  CSS — rendered ONCE, never reloaded  (this is why there's no flash)
# =====================================================================
CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700;800&family=Inter:wght@400;500;600;700;800;900&display=swap');

*, html, body, .stApp, .main, .block-container,
section[data-testid="stSidebar"],
div[data-testid="stMetric"],
.stMarkdown, p, span, label, h1, h2, h3, h4, h5, h6 {{
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
}}
.mono {{ font-family: 'JetBrains Mono', 'SF Mono', monospace !important; }}

/* === ANTI-FLASH: dark bg on every layer === */
html, body {{
    background-color: {BG} !important;
    margin: 0 !important;
}}
.stApp {{
    background: {BG} !important;
    color: {WHITE} !important;
}}
/* Hide Streamlit chrome that causes visual noise */
div[data-testid="stStatusWidget"],
div[data-testid="stDecoration"],
.stDeployButton,
div[data-testid="stLoading"],
[data-testid="stNotification"],
div.stSpinner {{
    display: none !important;
}}
/* Keep stale content visible during fragment rerun */
.stApp [data-stale="true"] {{
    opacity: 1 !important;
}}
.element-container {{
    transition: none !important;
}}

.stApp > header {{ background: transparent !important; }}
footer, #MainMenu {{ visibility: hidden !important; }}
section[data-testid="stSidebar"] {{ display: none !important; }}
div[data-testid="stMetric"] {{ display: none !important; }}
details {{ border: none !important; }}

.block-container {{
    padding: 4rem 1.2rem 0 1.2rem !important;
    max-width: 100% !important;
}}

::-webkit-scrollbar {{ width: 3px; height: 3px; }}
::-webkit-scrollbar-track {{ background: transparent; }}
::-webkit-scrollbar-thumb {{ background: {BORDER2}; border-radius: 3px; }}

/* Top status strip */
.top-strip {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 8px 16px;
    margin-bottom: 10px;
    font-size: 0.78rem;
}}
.top-strip .logo {{
    font-weight: 800;
    font-size: 0.85rem;
    letter-spacing: 1.5px;
    color: {WHITE};
}}
.top-strip .logo .acc {{ color: {GOLD}; }}
.top-strip .pills {{ display: flex; gap: 6px; align-items: center; }}
.top-strip .ttime {{
    font-family: 'JetBrains Mono', monospace;
    color: {SILVER};
    font-size: 0.78rem;
    font-weight: 500;
}}

.pill {{
    display: inline-flex; align-items: center; gap: 4px;
    padding: 3px 10px; border-radius: 3px;
    font-size: 0.7rem; font-weight: 700;
    letter-spacing: 0.6px; text-transform: uppercase;
}}
.pill-live {{ background: {GOLD}; color: #000; }}
.pill-paper {{ background: {BORDER2}; color: {SILVER}; }}
.pill-green {{ background: {GREEN_DIM}; color: {GREEN}; border: 1px solid rgba(34,197,94,0.2); }}
.pill-dim {{ background: rgba(71,85,105,0.2); color: {MUTED}; border: 1px solid {BORDER}; }}
.pill-red {{ background: {RED_DIM}; color: {RED}; border: 1px solid rgba(239,68,68,0.2); }}
.pill-cyan {{ background: rgba(56,189,248,0.08); color: {CYAN}; border: 1px solid rgba(56,189,248,0.2); }}
.pill-gold {{ background: {GOLD_DIM}; color: {GOLD}; border: 1px solid rgba(229,169,10,0.2); }}

@keyframes blink {{ 0%,100% {{ opacity:1; }} 50% {{ opacity:0.3; }} }}
.blink-dot {{
    width: 6px; height: 6px; border-radius: 50%;
    display: inline-block; margin-right: 3px;
}}
.blink-dot.live {{ background: {GOLD}; animation: blink 2s infinite; }}
.blink-dot.green {{ background: {GREEN}; animation: blink 2s infinite; }}
.blink-dot.off {{ background: {DIM}; }}

/* Panel base */
.pnl {{
    background: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 12px 14px;
    margin-bottom: 8px;
}}
.pnl-header {{
    font-size: 0.68rem;
    color: {MUTED};
    text-transform: uppercase;
    letter-spacing: 1.5px;
    font-weight: 700;
    margin-bottom: 10px;
    padding-bottom: 6px;
    border-bottom: 1px solid {BORDER};
}}

/* Portfolio section */
.port-row {{
    display: flex;
    justify-content: space-between;
    padding: 5px 0;
    font-size: 0.82rem;
    border-bottom: 1px solid rgba(30,37,56,0.6);
}}
.port-row:last-child {{ border-bottom: none; }}
.port-label {{ color: {MUTED}; font-weight: 600; text-transform: uppercase; font-size: 0.7rem; letter-spacing: 0.8px; }}
.port-val {{ font-family: 'JetBrains Mono', monospace; font-weight: 700; }}
.port-val.g {{ color: {GREEN}; }}
.port-val.r {{ color: {RED}; }}
.port-val.w {{ color: {WHITE}; }}
.port-val.gold {{ color: {GOLD}; }}

/* Big equity number */
.eq-hero {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 2.0rem;
    font-weight: 800;
    line-height: 1;
    letter-spacing: -0.5px;
}}

/* Orders table */
.ord-head {{
    display: flex; padding: 4px 8px;
    font-size: 0.62rem; color: {MUTED};
    text-transform: uppercase; letter-spacing: 0.8px; font-weight: 700;
    border-bottom: 1px solid {BORDER};
}}
.ord-row {{
    display: flex; align-items: center;
    padding: 5px 8px; font-size: 0.78rem;
    border-bottom: 1px solid rgba(30,37,56,0.4);
}}
.ord-row:hover {{ background: rgba(229,169,10,0.03); }}
.ord-col {{ flex: 1; }}

/* Coin tiles */
.coin-tile {{
    background: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 14px 12px;
    text-align: center;
}}
.coin-tile:hover {{ border-color: {BORDER2}; }}
.coin-tile .sym {{
    font-size: 1.1rem;
    font-weight: 800;
    color: {WHITE};
    letter-spacing: 1px;
    margin-bottom: 4px;
}}
.coin-tile .cprice {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 1.2rem;
    font-weight: 700;
    color: {GOLD};
    margin: 6px 0 10px 0;
}}
.coin-tile .badges {{ display: flex; justify-content: center; gap: 5px; flex-wrap: wrap; }}
.coin-tile .meta {{
    font-size: 0.75rem; color: {MUTED}; margin-top: 8px; line-height: 1.7;
    font-family: 'JetBrains Mono', monospace;
}}
.coin-tile .meta b {{ color: {SILVER}; }}

/* Momentum bar */
.mom-track {{
    width: 100%; height: 4px; background: {BORDER};
    border-radius: 2px; overflow: hidden; margin-top: 8px;
}}
.mom-fill {{
    height: 100%; border-radius: 2px;
    background: linear-gradient(90deg, rgba(56,189,248,0.3), {CYAN});
}}

/* Gauge */
.gauge-wrap {{ text-align: center; }}
.gauge-lbl {{
    font-size: 0.65rem; color: {MUTED};
    text-transform: uppercase; letter-spacing: 1.2px;
    font-weight: 700; margin-top: 4px;
}}

/* Feed */
.feed-item {{
    padding: 6px 10px;
    font-size: 0.76rem;
    color: {SILVER};
    border-left: 2px solid {BORDER2};
    margin-bottom: 4px;
    background: rgba(15,19,32,0.5);
    border-radius: 0 4px 4px 0;
}}
.feed-item .fts {{ font-size: 0.65rem; color: {MUTED}; font-weight: 700; margin-bottom: 2px; }}
.feed-item.risk {{ border-left-color: {RED}; }}

/* Login */
.login-wrap {{
    max-width: 380px; margin: 14vh auto;
    background: {PANEL}; border: 1px solid {BORDER};
    border-radius: 8px; padding: 48px 40px; text-align: center;
}}
.login-wrap h2 {{ color: {WHITE}; font-weight: 900; letter-spacing: 3px; font-size: 1.3rem; margin-bottom: 4px; }}
.login-wrap .sub {{ color: {MUTED}; font-size: 0.72rem; margin-bottom: 24px; font-weight: 500; }}
.login-wrap .accent {{ color: {GOLD}; }}

input[type="password"], input[type="text"] {{
    background: {BG2} !important; color: {WHITE} !important;
    border: 1px solid {BORDER} !important; border-radius: 4px !important;
    font-family: 'JetBrains Mono', monospace !important;
}}
.stButton > button {{
    background: {GOLD} !important; color: #000 !important;
    font-weight: 800 !important; border: none !important;
    border-radius: 4px !important; letter-spacing: 1px !important;
    padding: 8px 20px !important;
}}
.stButton > button:hover {{ filter: brightness(1.1); }}

.stPlotlyChart {{ background: transparent !important; }}

.standalone-banner {{
    background: {GOLD_DIM}; border: 1px solid rgba(229,169,10,0.3);
    border-radius: 4px; padding: 8px 16px; margin-bottom: 8px;
    text-align: center; font-size: 0.78rem; color: {GOLD}; font-weight: 700;
}}

/* Responsive */
@media (max-width: 768px) {{
    .block-container {{ padding: 0.5rem 0.5rem 0 0.5rem !important; }}
    .top-strip {{ flex-direction: column; gap: 6px; text-align: center; padding: 8px 10px; }}
    .eq-hero {{ font-size: 1.5rem; }}
}}
</style>
"""
# Inject CSS ONCE — this never re-renders
st.markdown(CSS, unsafe_allow_html=True)

# =====================================================================
#  PASSWORD GATE  (runs once, outside the fragment)
# =====================================================================
DASHBOARD_PASSWORD = "hybrid2026"

def check_password() -> bool:
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if st.session_state.authenticated:
        return True
    st.markdown("""
    <div class="login-wrap">
        <h2>HYBRID <span class="accent">BOT</span></h2>
        <div class="sub">Operator Terminal v7</div>
    </div>
    """, unsafe_allow_html=True)
    _, col_m, _ = st.columns([1, 1, 1])
    with col_m:
        pw = st.text_input("Password", type="password", key="pw_input",
                           label_visibility="collapsed", placeholder="Access key...")
        if st.button("UNLOCK", use_container_width=True):
            if pw == DASHBOARD_PASSWORD:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Access denied")
    return False

if not check_password():
    st.stop()

# =====================================================================
#  STANDALONE MODE DETECTION  (runs once)
# =====================================================================
STANDALONE_MODE = False
STANDALONE_TIMESTAMP = ""

try:
    from config import settings
    from execution.coinbase_client import CoinbaseClient
    from data.fetcher import DataFetcher
    from data.indicators import add_indicators
    from ml.regime_classifier import RegimeClassifier
    from ml.momentum_predictor import MomentumPredictor
    from strategies.grid_strategy import GridStrategy
    from strategies.hybrid_strategy import HybridStrategy
    from strategies.position_manager import PositionManager
    from utils.risk_manager import RiskManager
    from utils.shared_state import read_state
    from utils.pnl_tracker import get_summary as get_pnl_summary, record_equity
except ImportError:
    STANDALONE_MODE = True

if not STANDALONE_MODE:
    try:
        if not settings.COINBASE_API_KEY or not settings.COINBASE_API_SECRET:
            STANDALONE_MODE = True
    except Exception:
        STANDALONE_MODE = True

# =====================================================================
#  CACHED RESOURCES  (created once, reused across fragment reruns)
# =====================================================================
if not STANDALONE_MODE:
    @st.cache_resource(show_spinner=False)
    def get_shared_objects():
        client = CoinbaseClient()
        fetcher = DataFetcher(client)
        classifier = RegimeClassifier()
        risk_mgr = RiskManager()
        pos_mgr = PositionManager(client)
        return client, fetcher, classifier, risk_mgr, pos_mgr
    client, fetcher, classifier, risk_mgr, pos_mgr = get_shared_objects()

# =====================================================================
#  DATA FETCHERS  (short TTL so fragment picks up fresh data)
# =====================================================================
def fetch_coin_data_live(symbol: str) -> dict:
    try:
        df_raw = fetcher.get_recent_candles(symbol, granularity="FIVE_MINUTE", limit=100)
        df = add_indicators(df_raw)
        if df.empty or len(df) < 10:
            return {"error": f"Insufficient data for {symbol}", "symbol": symbol}
        latest = df.iloc[-1]
        regime_result = classifier.classify(df)
        live_eq = pos_mgr.live_equity
        grid = GridStrategy(df, regime_result, capital_usd=live_eq if live_eq > 0 else settings.MAX_POSITION_SIZE_USD)
        grid_levels = grid.calculate_grid_levels()
        predictor = MomentumPredictor(df)
        momentum_result = predictor.get_momentum_score()
        hybrid = HybridStrategy(df, regime_result, grid_levels, momentum_result)
        decision = hybrid.decide_and_execute_plan()
        return {
            "symbol": symbol, "df": df, "latest": latest,
            "regime": regime_result, "grid_levels": grid_levels,
            "momentum": momentum_result, "decision": decision,
            "sparkline": df["close"].tail(20).tolist(), "price": latest["close"],
            "atr_pct": latest["atr_pct"], "rsi": latest["rsi_14"],
        }
    except Exception as e:
        return {"error": str(e), "symbol": symbol}

def fetch_account_data_live() -> dict:
    try:
        positions = pos_mgr.get_current_positions()
        equity_info = pos_mgr.get_account_equity(positions)
        exposure = pos_mgr.calculate_total_exposure(positions)
        current_equity = equity_info["total_equity"]
        peak = pos_mgr.update_peak_equity(current_equity)
        risk = risk_mgr.get_risk_summary(
            current_equity=current_equity, start_of_day_equity=current_equity,
            peak_equity=peak, current_exposure_usd=exposure)
        return {"positions": positions, "equity": equity_info, "exposure": exposure, "risk": risk, "peak_equity": peak}
    except Exception as e:
        return {"error": str(e)}

def fetch_equity_history_live() -> pd.DataFrame:
    try:
        pnl_path = os.path.join(os.path.dirname(__file__), "state", "pnl_history.json")
        if not os.path.exists(pnl_path): return pd.DataFrame()
        with open(pnl_path) as f: pnl_data = json.load(f)
        snapshots = pnl_data.get("equity_snapshots", [])
        if not snapshots: return pd.DataFrame()
        df = pd.DataFrame(snapshots)
        df["timestamp"] = pd.to_datetime(df["t"])
        df["equity"] = df["eq"].astype(float)
        starting = pnl_data.get("starting_equity", df["equity"].iloc[0])
        df["pnl"] = df["equity"] - starting
        return df[["timestamp", "equity", "pnl"]].reset_index(drop=True)
    except Exception:
        return pd.DataFrame()

# =====================================================================
#  STANDALONE DATA LOADER
# =====================================================================
def load_standalone_data() -> dict:
    global STANDALONE_TIMESTAMP
    trades_path = os.path.join(os.path.dirname(__file__), "exports", "trades.csv")
    state_path = os.path.join(os.path.dirname(__file__), "state", "bot_state.json")
    pnl_path = os.path.join(os.path.dirname(__file__), "state", "pnl_history.json")

    data = {
        "trades": pd.DataFrame(), "orders_history": [], "alerts_history": [],
        "equity": {"cash_usd": 0, "coin_value_usd": 0, "total_equity": 0},
        "risk": {"daily_pnl_pct": 0, "drawdown_pct": 0, "exposure_pct": 0, "trading_allowed": True,
                 "daily_loss_breached": False, "drawdown_breached": False, "max_position_usd": 0, "max_position_pct": 25},
        "positions": {}, "peak_equity": 0,
        "pnl_summary": {"starting_equity": 0, "current_equity": 0, "daily_pnl": 0,
                        "daily_pnl_pct": 0, "alltime_pnl": 0, "alltime_pnl_pct": 0, "today_open": 0, "days_trading": 0},
        "coin_data": {}, "bot_state": {},
    }
    if os.path.exists(trades_path):
        try:
            data["trades"] = pd.read_csv(trades_path)
            STANDALONE_TIMESTAMP = str(data["trades"]["timestamp"].iloc[0]) if len(data["trades"]) > 0 else ""
        except Exception: pass
    if os.path.exists(state_path):
        try:
            with open(state_path) as f: bs = json.load(f)
            data["bot_state"] = bs
            data["orders_history"] = bs.get("orders_history", [])
            data["alerts_history"] = bs.get("alerts_history", [])
            eq_snap = bs.get("equity_snapshot", {})
            data["equity"] = {"cash_usd": eq_snap.get("cash_usd", 0), "coin_value_usd": 0, "total_equity": eq_snap.get("total_equity", 0)}
            data["peak_equity"] = eq_snap.get("peak_equity", 0)
            STANDALONE_TIMESTAMP = bs.get("timestamp", STANDALONE_TIMESTAMP)
        except Exception: pass
    if os.path.exists(pnl_path):
        try:
            with open(pnl_path) as f: pnl_data = json.load(f)
            starting = pnl_data.get("starting_equity", 0)
            current = pnl_data.get("last_equity", starting)
            now = datetime.now(ZoneInfo("America/New_York"))
            today_str = now.strftime("%Y-%m-%d")
            has_paper = "paper_profit_total" in pnl_data
            if has_paper:
                alltime_pnl = pnl_data.get("paper_profit_total", 0)
                daily_data = pnl_data.get("paper_daily", {}).get(today_str, {})
                daily_pnl = daily_data.get("profit", 0)
                current = starting + alltime_pnl
                today_open = starting
            else:
                today_data = pnl_data.get("days", {}).get(today_str, {})
                today_open = today_data.get("open_equity", current)
                daily_pnl = current - today_open
                alltime_pnl = current - starting
            daily_pct = (daily_pnl / starting * 100) if starting > 0 else 0
            alltime_pct = (alltime_pnl / starting * 100) if starting > 0 else 0
            data["pnl_summary"] = {
                "starting_equity": round(starting, 4), "current_equity": round(current, 4),
                "daily_pnl": round(daily_pnl, 4), "daily_pnl_pct": round(daily_pct, 4),
                "alltime_pnl": round(alltime_pnl, 4), "alltime_pnl_pct": round(alltime_pct, 4),
                "today_open": round(today_open, 4), "days_trading": len(pnl_data.get("days", {})),
            }
        except Exception: pass
    if not data["trades"].empty:
        for sym in data["trades"]["symbol"].unique():
            sym_trades = data["trades"][data["trades"]["symbol"] == sym]
            last_price = sym_trades["price"].iloc[-1] if len(sym_trades) > 0 else 0
            data["coin_data"][sym] = {
                "symbol": sym, "price": last_price,
                "regime": {"regime": "RANGING", "confidence": 0.5, "details": "Standalone"},
                "momentum": {"score": 0.5, "direction": "NEUTRAL"},
                "decision": {"decision": "WAIT", "reason": "Standalone mode", "details": {}},
                "grid_levels": {"current_price": last_price, "buy_levels": [], "sell_levels": [],
                                "grid_spacing_pct": 0, "grid_spacing_usd": 0, "capital_per_level": 0,
                                "total_capital_deployed": 0, "est_profit_usd": 0, "est_profit_pct": 0, "regime": "RANGING"},
                "sparkline": sym_trades["price"].tail(20).tolist() if len(sym_trades) >= 2 else [last_price]*5,
                "atr_pct": 0, "rsi": 50,
            }
    if not data["coin_data"]:
        for sym in ["DOGE-USD", "SHIB-USD", "PEPE-USD"]:
            data["coin_data"][sym] = {
                "symbol": sym, "price": 0.0001,
                "regime": {"regime": "RANGING", "confidence": 0.6, "details": "Demo"},
                "momentum": {"score": 0.5, "direction": "NEUTRAL"},
                "decision": {"decision": "WAIT", "reason": "No live data", "details": {}},
                "grid_levels": {"current_price": 0.0001, "buy_levels": [], "sell_levels": [],
                                "grid_spacing_pct": 0, "grid_spacing_usd": 0, "capital_per_level": 0,
                                "total_capital_deployed": 0, "est_profit_usd": 0, "est_profit_pct": 0, "regime": "RANGING"},
                "sparkline": [0.0001]*5, "atr_pct": 0, "rsi": 50,
            }
        STANDALONE_TIMESTAMP = "No data"
    return data

# =====================================================================
#  SVG GAUGE HELPER
# =====================================================================
def svg_gauge(value: float, max_val: float, size: int = 100) -> str:
    pct = min(value / max_val, 1.0) if max_val > 0 else 0
    angle = pct * 270
    if pct < 0.5: stroke = GOLD
    elif pct < 0.8: stroke = "#f59e0b"
    else: stroke = RED

    r = int(size * 0.38)
    cx = cy = size // 2
    sw = max(int(size * 0.07), 4)
    sa = 135

    def ap(a):
        rad = math.radians(a)
        return cx + r * math.cos(rad), cy + r * math.sin(rad)
    def arc(s, e):
        sx, sy = ap(s); ex, ey = ap(e)
        sweep = e - s; large = 1 if sweep > 180 else 0
        if sweep >= 359.9:
            mx, my = ap(s + 180)
            return f"M {sx:.1f} {sy:.1f} A {r} {r} 0 1 1 {mx:.1f} {my:.1f} A {r} {r} 0 1 1 {sx:.1f} {sy:.1f}"
        if sweep <= 0: return ""
        return f"M {sx:.1f} {sy:.1f} A {r} {r} 0 {large} 1 {ex:.1f} {ey:.1f}"

    track = arc(sa, sa + 270)
    fill = arc(sa, sa + angle) if angle > 0 else ""
    nx, ny = ap(sa + angle) if angle > 0 else ap(sa)
    fs_big = int(size * 0.22)
    fs_sm = int(size * 0.11)

    return f"""<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}">
        <path d="{track}" fill="none" stroke="{BORDER2}" stroke-width="{sw}" opacity="0.3" stroke-linecap="round"/>
        <path d="{fill}" fill="none" stroke="{stroke}" stroke-width="{sw}" stroke-linecap="round"/>
        <circle cx="{nx:.1f}" cy="{ny:.1f}" r="{max(sw//2,2)}" fill="{stroke}"/>
        <text x="{cx}" y="{cy-2}" text-anchor="middle" dominant-baseline="middle"
              fill="{WHITE}" font-size="{fs_big}" font-weight="800"
              font-family="JetBrains Mono, monospace">{value:.1f}%</text>
        <text x="{cx}" y="{cy+fs_big//2+4}" text-anchor="middle" dominant-baseline="middle"
              fill="{MUTED}" font-size="{fs_sm}" font-weight="600"
              font-family="Inter, sans-serif">of {max_val:.0f}%</text>
    </svg>"""


# =====================================================================
#  ██████  THE LIVE FRAGMENT  ██████
#  Only this function re-runs every 15 seconds.
#  Everything above (CSS, fonts, page config) stays rendered.
# =====================================================================
@st.fragment(run_every=timedelta(seconds=15))
def live_dashboard():
    now_utc = datetime.now(timezone.utc)
    LOCAL_TZ = ZoneInfo("America/New_York")
    now_local = now_utc.astimezone(LOCAL_TZ)

    # ------ LOAD DATA ------
    if STANDALONE_MODE:
        standalone_data = load_standalone_data()
        account = {"positions": standalone_data["positions"], "equity": standalone_data["equity"],
                   "risk": standalone_data["risk"], "peak_equity": standalone_data["peak_equity"]}
        coin_data = standalone_data["coin_data"]
        bot_state = standalone_data["bot_state"]
        _trading_pairs = list(coin_data.keys()) if coin_data else ["DOGE-USD", "SHIB-USD", "PEPE-USD"]
        _paper_trading = True
        _daily_loss_limit = 5.0; _max_drawdown = 15.0; _max_position_pct = 25.0; _enable_telegram = False
        # Equity snapshots
        try:
            _pnl_path = os.path.join(os.path.dirname(__file__), "state", "pnl_history.json")
            if os.path.exists(_pnl_path):
                with open(_pnl_path) as _f: _pnl_raw = json.load(_f)
                _snaps = _pnl_raw.get("equity_snapshots", [])
                if _snaps:
                    equity_hist = pd.DataFrame(_snaps)
                    equity_hist["timestamp"] = pd.to_datetime(equity_hist["t"])
                    equity_hist["equity"] = equity_hist["eq"].astype(float)
                    _se = _pnl_raw.get("starting_equity", equity_hist["equity"].iloc[0])
                    equity_hist["pnl"] = equity_hist["equity"] - _se
                    equity_hist = equity_hist[["timestamp", "equity", "pnl"]].reset_index(drop=True)
                else: equity_hist = pd.DataFrame()
            else: equity_hist = pd.DataFrame()
        except Exception: equity_hist = pd.DataFrame()
    else:
        account = fetch_account_data_live()
        coin_data = {}
        for sym in settings.TRADING_PAIRS:
            coin_data[sym] = fetch_coin_data_live(sym)
        equity_hist = fetch_equity_history_live()
        bot_state = read_state()
        _trading_pairs = settings.TRADING_PAIRS
        _paper_trading = settings.PAPER_TRADING
        _daily_loss_limit = settings.DAILY_LOSS_LIMIT_PCT
        _max_drawdown = settings.MAX_DRAWDOWN_PCT
        _max_position_pct = settings.MAX_POSITION_PCT
        _enable_telegram = settings.ENABLE_TELEGRAM_ALERTS

    bot_running = False; bot_cycle = 0
    if bot_state:
        bot_cycle = bot_state.get("cycle_count", 0)
        bot_running = bot_state.get("bot_running", False)
        ts_str = bot_state.get("timestamp", "")
        if ts_str:
            try:
                st_time = datetime.fromisoformat(ts_str)
                if st_time.tzinfo is None: st_time = st_time.replace(tzinfo=timezone.utc)
                state_age_seconds = int((now_utc - st_time).total_seconds())
                if state_age_seconds > 360: bot_running = False
            except: pass

    # P/L
    if not STANDALONE_MODE:
        total_eq_val = account.get("equity", {}).get("total_equity", 0)
        if total_eq_val > 0: record_equity(total_eq_val)
        pnl = get_pnl_summary()
    else:
        pnl = standalone_data["pnl_summary"]

    daily_pnl = pnl["daily_pnl"]; daily_pct = pnl["daily_pnl_pct"]
    alltime_pnl = pnl["alltime_pnl"]; alltime_pct = pnl["alltime_pnl_pct"]
    eq = account.get("equity", {}); total_eq = eq.get("total_equity", 0)
    cash_usd = eq.get("cash_usd", 0)
    risk = account.get("risk", {}); drawdown = risk.get("drawdown_pct", 0)

    # ------ STANDALONE BANNER ------
    if STANDALONE_MODE:
        ts_display = STANDALONE_TIMESTAMP[:19] if STANDALONE_TIMESTAMP else "Unknown"
        st.markdown(f'<div class="standalone-banner">STANDALONE &mdash; {ts_display}</div>', unsafe_allow_html=True)

    # ------ TOP STATUS STRIP ------
    is_live = not _paper_trading
    mode_cls = "pill-live" if is_live else "pill-paper"
    mode_txt = "LIVE" if is_live else "PAPER"
    dot_cls = "live" if is_live else "off"

    bot_pill = (f'<span class="pill pill-green"><span class="blink-dot green"></span>RUNNING</span>'
                if bot_running else '<span class="pill pill-dim">OFFLINE</span>')
    cycle_pill = f'<span class="pill pill-dim">CYCLE {bot_cycle}</span>' if bot_cycle > 0 else ""
    tg_pill = (f'<span class="pill pill-green">TG ON</span>' if _enable_telegram
               else '<span class="pill pill-dim">TG OFF</span>')

    st.markdown(f"""
    <div class="top-strip">
        <div class="logo"><span class="acc">///</span> HYBRID GRID <span class="acc">+</span> MOMENTUM
            &nbsp;&nbsp;<span class="pill {mode_cls}"><span class="blink-dot {dot_cls}"></span>{mode_txt}</span></div>
        <div class="pills">
            {bot_pill} {cycle_pill}
            <span class="pill pill-dim">COINBASE</span>
            {tg_pill}
        </div>
        <div class="ttime">{now_local.strftime("%Y-%m-%d")} &nbsp; {now_local.strftime("%H:%M:%S")} EDT</div>
    </div>
    """, unsafe_allow_html=True)

    # ------ 3-COLUMN LAYOUT ------
    col_left, col_center, col_right = st.columns([1, 3.5, 1.5])

    # ---- LEFT: PORTFOLIO + RISK GAUGES ----
    with col_left:
        eq_color = "g" if alltime_pnl > 0.01 else ("r" if alltime_pnl < -0.01 else "w")
        st.markdown(f"""
        <div class="pnl">
            <div class="pnl-header">Portfolio</div>
            <div class="eq-hero port-val {eq_color}">${total_eq:,.2f}</div>
            <div style="margin-top:10px;">
                <div class="port-row"><span class="port-label">Cash</span><span class="port-val w mono">${cash_usd:,.2f}</span></div>
                <div class="port-row"><span class="port-label">Daily P&L</span><span class="port-val {'g' if daily_pnl > 0.01 else ('r' if daily_pnl < -0.01 else 'w')} mono">{'+'if daily_pnl>=0 else ''}${daily_pnl:,.2f}</span></div>
                <div class="port-row"><span class="port-label">All-Time</span><span class="port-val {'g' if alltime_pnl > 0.01 else ('r' if alltime_pnl < -0.01 else 'w')} mono">{'+'if alltime_pnl>=0 else ''}${alltime_pnl:,.2f}</span></div>
                <div class="port-row"><span class="port-label">Drawdown</span><span class="port-val {'r' if drawdown > 5 else 'w'} mono">{drawdown:.2f}%</span></div>
                <div class="port-row"><span class="port-label">Days</span><span class="port-val w mono">{pnl['days_trading']}</span></div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Risk gauges
        g1 = svg_gauge(abs(risk.get("daily_pnl_pct", 0)), _daily_loss_limit, 110)
        g2 = svg_gauge(risk.get("drawdown_pct", 0), _max_drawdown, 110)
        g3 = svg_gauge(risk.get("exposure_pct", 0), _max_position_pct, 110)

        st.markdown(f"""
        <div class="pnl">
            <div class="pnl-header">Risk Gauges</div>
            <div class="gauge-wrap">{g1}<div class="gauge-lbl">Daily Loss</div></div>
            <div class="gauge-wrap" style="margin-top:8px;">{g2}<div class="gauge-lbl">Drawdown</div></div>
            <div class="gauge-wrap" style="margin-top:8px;">{g3}<div class="gauge-lbl">Exposure</div></div>
        </div>
        """, unsafe_allow_html=True)

        # System rails
        hb_color = GREEN if bot_running else RED
        hb_text = "OK" if bot_running else "OFF"
        st.markdown(f"""
        <div class="pnl">
            <div class="pnl-header">System Rails</div>
            <div class="port-row"><span class="port-label">Heartbeat</span><span class="port-val" style="color:{hb_color};">{hb_text}</span></div>
            <div class="port-row"><span class="port-label">Account</span><span class="port-val" style="color:{GREEN};">OK</span></div>
            <div class="port-row"><span class="port-label">Kill Switch</span><span class="port-val" style="color:{GREEN if risk.get('trading_allowed', True) else RED};">{'OK' if risk.get('trading_allowed', True) else 'TRIPPED'}</span></div>
        </div>
        """, unsafe_allow_html=True)

    # ---- CENTER: EQUITY CURVE ----
    with col_center:
        start_eq = pnl.get("starting_equity", total_eq)
        eq_high = equity_hist["equity"].max() if not equity_hist.empty else total_eq
        eq_low = equity_hist["equity"].min() if not equity_hist.empty else total_eq
        n_pts = len(equity_hist) if not equity_hist.empty else 0

        chg = total_eq - start_eq
        chg_pct = (chg / start_eq * 100) if start_eq > 0 else 0
        chg_color = GREEN if chg >= 0 else RED
        chg_sign = "+" if chg >= 0 else ""

        st.markdown(f"""
        <div class="pnl" style="padding:10px 14px 6px 14px;">
            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap;">
                <div>
                    <span style="font-size:0.68rem; color:{MUTED}; text-transform:uppercase; letter-spacing:1.5px; font-weight:700;">
                        EQUITY CURVE</span>
                    <span style="font-size:0.65rem; color:{DIM}; margin-left:8px;">{n_pts} pts</span>
                </div>
                <div style="display:flex; gap:20px; font-family:'JetBrains Mono',monospace; font-size:0.75rem;">
                    <span style="color:{MUTED};">HIGH <b style="color:{WHITE};">${eq_high:,.2f}</b></span>
                    <span style="color:{MUTED};">LOW <b style="color:{WHITE};">${eq_low:,.2f}</b></span>
                    <span style="color:{MUTED};">CHG <b style="color:{chg_color};">{chg_sign}${abs(chg):,.2f} ({chg_sign}{chg_pct:.2f}%)</b></span>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        if not equity_hist.empty and len(equity_hist) >= 2:
            fig = go.Figure()
            curve_color = GOLD

            fig.add_trace(go.Scatter(
                x=equity_hist["timestamp"], y=equity_hist["equity"],
                mode="lines", name="Equity",
                line=dict(color=curve_color, width=2.5, shape="spline", smoothing=1.2),
                fill="tozeroy", fillcolor="rgba(229,169,10,0.04)",
                customdata=equity_hist["pnl"],
                hovertemplate="<b>$%{y:,.2f}</b><br>P&L: %{customdata:+,.2f}<extra></extra>",
            ))

            fig.add_hline(y=start_eq, line_dash="dot", line_color="rgba(100,116,139,0.3)", line_width=1)

            last_row = equity_hist.iloc[-1]
            fig.add_trace(go.Scatter(
                x=[last_row["timestamp"]], y=[last_row["equity"]],
                mode="markers+text", name="Now",
                marker=dict(color=GOLD, size=8, line=dict(color=WHITE, width=1.5)),
                text=[f"${last_row['equity']:,.2f}"],
                textposition="middle left", textfont=dict(color=GOLD, size=10, family="JetBrains Mono, monospace"),
                showlegend=False,
            ))

            eq_min = equity_hist["equity"].min(); eq_max = equity_hist["equity"].max()
            eq_range = eq_max - eq_min if eq_max != eq_min else max(eq_max * 0.01, 1)
            y_pad = max(eq_range * 0.12, 0.5)

            fig.update_layout(
                height=440, margin=dict(l=60, r=20, t=8, b=40),
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color=SILVER, size=10, family="JetBrains Mono, monospace"),
                xaxis=dict(gridcolor="rgba(30,37,56,0.5)", gridwidth=0.5, showline=False, zeroline=False,
                           tickfont=dict(size=9, color=MUTED), tickformat="%H:%M\n%b %d"),
                yaxis=dict(gridcolor="rgba(30,37,56,0.5)", gridwidth=0.5, showline=False, zeroline=False,
                           tickprefix="$", tickfont=dict(size=10, color=SILVER),
                           range=[eq_min - y_pad, eq_max + y_pad]),
                showlegend=False, hovermode="x unified",
                hoverlabel=dict(bgcolor=PANEL, bordercolor=BORDER2, font_color=WHITE, font_size=11),
            )
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        else:
            st.markdown(f"""
            <div class="pnl" style="padding:60px 30px; text-align:center;">
                <div style="font-size:0.75rem; color:{MUTED}; text-transform:uppercase; letter-spacing:1.5px; font-weight:700;">
                    Equity curve populates after bot cycles</div>
                <div class="eq-hero" style="color:{WHITE}; margin-top:12px;">${total_eq:,.2f}</div>
            </div>
            """, unsafe_allow_html=True)

        # ---- COIN TILES (below chart) ----
        coin_cols = st.columns(len(_trading_pairs))
        for i, sym in enumerate(_trading_pairs):
            with coin_cols[i]:
                cd = coin_data.get(sym, {})
                if "error" in cd:
                    st.markdown(f'<div class="coin-tile"><div class="sym">{sym.split("-")[0]}</div>'
                                f'<div style="color:{RED};font-size:0.78rem;margin-top:8px;">Unavailable</div></div>',
                                unsafe_allow_html=True)
                    continue
                price = cd["price"]
                regime = cd["regime"]["regime"]
                dec = cd["decision"]["decision"]
                mom = cd["momentum"]["score"]
                mom_w = int(mom * 100)
                r_cls = "pill-cyan" if regime == "RANGING" else "pill-gold"
                d_cls = "pill-gold" if dec == "GRID" else ("pill-red" if dec == "SCALP" else "pill-dim")

                if price >= 1: pf = f"${price:,.4f}"
                elif price >= 0.001: pf = f"${price:.6f}"
                else: pf = f"${price:.8f}"

                st.markdown(f"""
                <div class="coin-tile">
                    <div class="sym">{sym.split("-")[0].replace("USDC","")}</div>
                    <div class="cprice">{pf}</div>
                    <div class="badges">
                        <span class="pill {r_cls}">{regime}</span>
                        <span class="pill {d_cls}">{dec}</span>
                    </div>
                    <div class="mom-track"><div class="mom-fill" style="width:{mom_w}%;"></div></div>
                    <div class="meta">RSI <b>{cd['rsi']:.0f}</b> &middot; ATR <b>{cd['atr_pct']:.2f}%</b> &middot; Mom <b>{mom:.2f}</b></div>
                </div>
                """, unsafe_allow_html=True)

    # ---- RIGHT: ORDERS + PERFORMANCE + ACTIVITY ----
    with col_right:
        # Open orders
        try:
            if not STANDALONE_MODE:
                resp = client.client.list_orders(order_status=["OPEN"], limit=250)
                open_orders_list = resp.orders if hasattr(resp, 'orders') else []
                order_count = len(open_orders_list)
            else:
                order_count = len(bot_state.get("orders_history", []))
        except Exception:
            order_count = len(bot_state.get("orders_history", []) if bot_state else [])

        st.markdown(f"""
        <div class="pnl">
            <div class="pnl-header">Open Orders &nbsp;<span style="color:{WHITE};">{order_count}</span></div>
        """, unsafe_allow_html=True)

        try:
            if not STANDALONE_MODE:
                _resp = client.client.list_orders(order_status=["OPEN"], limit=250)
                _open_list = _resp.orders if hasattr(_resp, 'orders') else []
                real_orders = []
                for _o in _open_list:
                    _sym = getattr(_o, 'product_id', '')
                    _side = getattr(_o, 'side', 'BUY')
                    _cfg = getattr(_o, 'order_configuration', None)
                    _price = 0.0; _size_usd = 0.0
                    if _cfg:
                        _gtc = getattr(_cfg, 'limit_limit_gtc', None)
                        if _gtc:
                            _price = float(getattr(_gtc, 'limit_price', 0))
                            _base = float(getattr(_gtc, 'base_size', 0))
                            _size_usd = _price * _base
                    real_orders.append({"symbol": _sym, "side": _side, "price": _price, "size_usd": _size_usd,
                                        "timestamp": getattr(_o, 'created_time', '')})
            else:
                real_orders = bot_state.get("orders_history", []) if bot_state else []
        except Exception:
            real_orders = bot_state.get("orders_history", []) if bot_state else []

        if real_orders:
            coin_summ = defaultdict(lambda: {"b": 0, "s": 0, "usd": 0.0})
            for o in real_orders:
                sym = o.get("symbol", ""); coin = sym.split("-")[0] if sym else "?"
                if o.get("side", "BUY") == "BUY": coin_summ[coin]["b"] += 1
                else: coin_summ[coin]["s"] += 1
                coin_summ[coin]["usd"] += o.get("size_usd", 0) or 0

            st.markdown(f"""
            <div class="ord-head">
                <span class="ord-col" style="flex:1.2;">Coin</span>
                <span class="ord-col">Buy</span>
                <span class="ord-col">Sell</span>
                <span class="ord-col">USD</span>
            </div>
            """, unsafe_allow_html=True)

            for coin, info in sorted(coin_summ.items()):
                st.markdown(f"""
                <div class="ord-row">
                    <span class="ord-col" style="flex:1.2;font-weight:800;color:{WHITE};">{coin}</span>
                    <span class="ord-col" style="color:{GREEN};font-weight:700;">{info['b']}</span>
                    <span class="ord-col" style="color:{RED};font-weight:700;">{info['s']}</span>
                    <span class="ord-col mono" style="color:{SILVER};">${info['usd']:,.2f}</span>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.markdown(f'<div style="color:{MUTED};font-size:0.78rem;padding:8px 0;">No open orders</div>',
                        unsafe_allow_html=True)

        st.markdown("</div>", unsafe_allow_html=True)

        # Performance stats
        st.markdown(f"""
        <div class="pnl">
            <div class="pnl-header">Performance</div>
            <div class="port-row"><span class="port-label">EQ High</span><span class="port-val w mono">${account.get('peak_equity', 0):,.2f}</span></div>
            <div class="port-row"><span class="port-label">EQ Low</span><span class="port-val w mono">${eq_low:,.2f}</span></div>
            <div class="port-row"><span class="port-label">Start</span><span class="port-val w mono">${start_eq:,.2f}</span></div>
            <div class="port-row"><span class="port-label">Daily %</span><span class="port-val {'g' if daily_pct > 0 else ('r' if daily_pct < 0 else 'w')} mono">{'+'if daily_pct>=0 else ''}{daily_pct:.2f}%</span></div>
            <div class="port-row"><span class="port-label">All-Time %</span><span class="port-val {'g' if alltime_pct > 0 else ('r' if alltime_pct < 0 else 'w')} mono">{'+'if alltime_pct>=0 else ''}{alltime_pct:.2f}%</span></div>
        </div>
        """, unsafe_allow_html=True)

        # Activity log
        st.markdown(f'<div class="pnl"><div class="pnl-header">Activity Log</div>', unsafe_allow_html=True)

        feed_html = ""
        state_alerts = bot_state.get("alerts_history", []) if bot_state else []
        if state_alerts:
            for a in state_alerts[:8]:
                ts_raw = a.get("timestamp", "")
                try:
                    ts_dt = datetime.fromisoformat(ts_raw)
                    if ts_dt.tzinfo is None: ts_dt = ts_dt.replace(tzinfo=timezone.utc)
                    ts = ts_dt.astimezone(LOCAL_TZ).strftime("%H:%M")
                except: ts = "-"
                symbol = a.get("symbol", ""); coin_short = symbol.split("-")[0] if symbol else ""
                msg = a.get("message", ""); alert_type = a.get("type", "decision")
                bcls = " risk" if alert_type == "risk" else ""
                tsl = f"{ts} {coin_short}" if coin_short else ts
                feed_html += f'<div class="feed-item{bcls}"><div class="fts">{tsl}</div>{msg}</div>'

        if not feed_html:
            for sym, cd in coin_data.items():
                if "error" in cd: continue
                d = cd["decision"]["decision"]; reason = cd["decision"]["reason"][:70]
                coin_short = sym.split("-")[0]
                feed_html += (f'<div class="feed-item"><div class="fts">{now_local.strftime("%H:%M")} {coin_short}</div>'
                              f'{d} &mdash; {reason}</div>')

        if not feed_html:
            feed_html = f'<div class="feed-item"><div class="fts">{now_local.strftime("%H:%M")}</div>Waiting for first cycle...</div>'

        st.markdown(f'<div style="max-height:250px;overflow-y:auto;">{feed_html}</div></div>', unsafe_allow_html=True)


# =====================================================================
#  RUN THE FRAGMENT
# =====================================================================
live_dashboard()
