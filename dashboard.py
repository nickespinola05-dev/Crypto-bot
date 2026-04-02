"""
dashboard.py — V3 Premium Institutional Command Center
Hybrid Grid + Momentum Bot — Bloomberg-terminal aesthetic.
Auto-refreshes every 5s. Usage: streamlit run dashboard.py

# -------------------------------------------------------------------
# requirements.txt (for Streamlit Community Cloud deployment):
#   streamlit>=1.32.0
#   plotly>=5.18.0
#   pandas>=2.1.0
#   numpy>=1.26.0
#   coinbase-advanced-py>=1.2.0
#   python-dotenv>=1.0.0
#   schedule>=1.2.0
# -------------------------------------------------------------------
# .streamlit/config.toml:
#   [theme]
#   primaryColor = "#ffc107"
#   backgroundColor = "#0a1428"
#   secondaryBackgroundColor = "#1a253f"
#   textColor = "#e8edf5"
#   font = "sans serif"
#
#   [server]
#   headless = true
#   runOnSave = true
# -------------------------------------------------------------------
"""

import os
import time
import math
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

import streamlit as st
import plotly.graph_objects as go
import pandas as pd
import numpy as np

# =====================================================================
#  PAGE CONFIG
# =====================================================================
st.set_page_config(
    page_title="Hybrid Grid + Momentum Bot",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded",
)

# =====================================================================
#  COLOR CONSTANTS
# =====================================================================
BG        = "#0a1428"
BG_DARK   = "#060e1e"
PANEL     = "#1a253f"
PANEL_ALT = "#142035"
PANEL_LT  = "#1f2d4a"
SILVER    = "#a8b5cc"
GOLD      = "#ffc107"
GOLD_LT   = "#ffca28"
GOLD_DIM  = "rgba(255,193,7,0.15)"
GOLD_GLOW = "rgba(255,193,7,0.35)"
RED       = "#ff4d4d"
RED_DIM   = "rgba(255,77,77,0.12)"
GREEN     = "#00e676"
GREEN_DIM = "rgba(0,230,118,0.12)"
BLUE      = "#64b5f6"
PURPLE    = "#ce93d8"
WHITE     = "#e8edf5"
DIM       = "#3d4f6f"
DIMTEXT   = "#5a6a85"

# =====================================================================
#  PREMIUM CSS — full glass-morphism, glow, typography
# =====================================================================
CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap');

/* ---- GLOBAL RESET ---- */
*, html, body, .stApp, .main, .block-container,
section[data-testid="stSidebar"],
div[data-testid="stMetric"],
.stMarkdown, p, span, label, h1, h2, h3, h4, h5, h6 {{
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
}}
.stApp {{
    background: radial-gradient(ellipse at 20% 50%, rgba(26,37,63,0.5) 0%, {BG} 60%, {BG_DARK} 100%) !important;
    color: {WHITE} !important;
}}
.stApp > header {{ background: transparent !important; }}
footer, #MainMenu {{ visibility: hidden !important; }}
.block-container {{
    padding: 3.1rem 1rem 0 1rem !important;
    max-width: 100% !important;
}}

/* ---- SCROLLBAR ---- */
::-webkit-scrollbar {{ width: 4px; height: 4px; }}
::-webkit-scrollbar-track {{ background: transparent; }}
::-webkit-scrollbar-thumb {{ background: {DIM}; border-radius: 4px; }}
::-webkit-scrollbar-thumb:hover {{ background: {SILVER}; }}

/* ---- SIDEBAR ---- */
section[data-testid="stSidebar"] {{
    background: linear-gradient(180deg, rgba(26,37,63,0.95) 0%, rgba(6,14,30,0.98) 100%) !important;
    border-right: 1px solid rgba(61,79,111,0.4);
    width: 270px !important;
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
}}
section[data-testid="stSidebar"] * {{ color: {WHITE} !important; }}
section[data-testid="stSidebar"] hr {{
    border-color: rgba(61,79,111,0.3) !important;
    margin: 10px 0 !important;
}}

/* ---- METRIC CARDS ---- */
div[data-testid="stMetric"] {{
    background: linear-gradient(135deg, rgba(26,37,63,0.7) 0%, rgba(20,32,53,0.8) 100%);
    border: 1px solid rgba(61,79,111,0.3);
    border-radius: 10px;
    padding: 12px 14px;
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
    box-shadow: 0 2px 12px rgba(0,0,0,0.2), inset 0 1px 0 rgba(168,181,204,0.04);
    transition: all 0.3s ease;
}}
div[data-testid="stMetric"]:hover {{
    border-color: rgba(168,181,204,0.35);
    box-shadow: 0 4px 20px rgba(0,0,0,0.3), 0 0 15px rgba(168,181,204,0.06);
}}
div[data-testid="stMetric"] label {{
    color: {DIMTEXT} !important;
    font-size: 0.93rem !important;
    text-transform: uppercase !important;
    letter-spacing: 1px !important;
    font-weight: 700 !important;
}}
div[data-testid="stMetric"] div[data-testid="stMetricValue"] {{
    color: {WHITE} !important;
    font-weight: 700 !important;
    font-size: 1.5rem !important;
}}

/* ---- GLASS PANELS ---- */
.glass {{
    background: linear-gradient(135deg, rgba(26,37,63,0.7) 0%, rgba(20,32,53,0.8) 100%);
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    border: 1px solid rgba(168,181,204,0.08);
    border-radius: 14px;
    padding: 18px;
    margin-bottom: 14px;
    box-shadow: 0 8px 32px rgba(0,0,0,0.25), inset 0 1px 0 rgba(168,181,204,0.04);
    position: relative;
    overflow: hidden;
}}
.glass::before {{
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 1px;
    background: linear-gradient(90deg, transparent, rgba(255,193,7,0.15), transparent);
}}
.section-label {{
    color: {SILVER};
    font-size: 0.9rem;
    text-transform: uppercase;
    letter-spacing: 1.8px;
    font-weight: 800;
    margin-bottom: 14px;
    padding-bottom: 8px;
    border-bottom: 1px solid rgba(61,79,111,0.25);
    display: flex;
    align-items: center;
    gap: 6px;
}}
.section-label::before {{
    content: '';
    width: 3px;
    height: 12px;
    background: {SILVER};
    border-radius: 2px;
    box-shadow: 0 0 8px rgba(168,181,204,0.2);
}}

/* ---- TOP BAR ---- */
.topbar {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: linear-gradient(90deg, rgba(26,37,63,0.85) 0%, rgba(20,32,53,0.9) 100%);
    backdrop-filter: blur(16px);
    -webkit-backdrop-filter: blur(16px);
    border: 1px solid rgba(61,79,111,0.25);
    border-radius: 14px;
    padding: 14px 28px;
    margin-bottom: 18px;
    box-shadow: 0 4px 24px rgba(0,0,0,0.3);
    position: relative;
    overflow: hidden;
}}
.topbar::before {{
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 1px;
    background: linear-gradient(90deg, transparent, rgba(255,193,7,0.2), transparent);
}}
.topbar-logo {{
    font-size: 1.5rem;
    font-weight: 900;
    letter-spacing: 2px;
    color: {WHITE};
    display: flex;
    align-items: center;
    gap: 10px;
    text-shadow: 0 1px 4px rgba(0,0,0,0.3);
}}
.topbar-logo .accent {{ color: {GOLD}; text-shadow: 0 0 16px {GOLD_DIM}; }}
.topbar-pills {{ display: flex; gap: 10px; align-items: center; }}
.topbar-status {{
    display: flex; gap: 16px; align-items: center;
}}
.topbar-time {{
    font-size: 1.05rem;
    color: {SILVER};
    font-weight: 500;
    letter-spacing: 0.5px;
}}
.topbar-updated {{
    font-size: 0.87rem;
    color: {DIMTEXT};
    font-weight: 600;
}}

/* ---- PILLS ---- */
.pill {{
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 4px 14px;
    border-radius: 20px;
    font-size: 0.9rem;
    font-weight: 700;
    letter-spacing: 0.8px;
    text-transform: uppercase;
    border: 1px solid transparent;
    transition: all 0.3s ease;
}}
.pill:hover {{ filter: brightness(1.15); }}
.pill-live {{
    background: linear-gradient(135deg, {GOLD}, {GOLD_LT});
    color: #000;
    box-shadow: 0 0 16px {GOLD_GLOW}, 0 2px 8px rgba(0,0,0,0.2);
}}
.pill-paper {{
    background: rgba(90,106,133,0.2);
    color: {SILVER};
    border-color: rgba(90,106,133,0.3);
}}
.pill-connected {{
    background: {GREEN_DIM};
    color: {GREEN};
    border-color: rgba(0,230,118,0.25);
    box-shadow: 0 0 12px rgba(0,230,118,0.1);
}}
.pill-exchange {{
    background: rgba(168,181,204,0.06);
    color: {SILVER};
    border-color: rgba(61,79,111,0.3);
}}
.pill-ranging  {{ background: rgba(100,181,246,0.1); color: {BLUE}; border-color: rgba(100,181,246,0.25); }}
.pill-trending {{ background: rgba(206,147,216,0.1); color: {PURPLE}; border-color: rgba(206,147,216,0.25); }}
.pill-grid     {{ background: {GOLD_DIM}; color: {GOLD}; border-color: rgba(255,193,7,0.25); box-shadow: 0 0 8px rgba(255,193,7,0.08); }}
.pill-scalp    {{ background: {RED_DIM}; color: #ff8a80; border-color: rgba(255,138,128,0.25); }}
.pill-wait     {{ background: rgba(90,106,133,0.1); color: {DIMTEXT}; border-color: rgba(61,79,111,0.2); }}

/* ---- PULSE DOT ---- */
@keyframes pulse {{
    0%   {{ box-shadow: 0 0 0 0 rgba(255,193,7,0.7); }}
    50%  {{ box-shadow: 0 0 0 6px rgba(255,193,7,0); }}
    100% {{ box-shadow: 0 0 0 0 rgba(255,193,7,0); }}
}}
@keyframes pulse-green {{
    0%   {{ box-shadow: 0 0 0 0 rgba(0,230,118,0.7); }}
    50%  {{ box-shadow: 0 0 0 6px rgba(0,230,118,0); }}
    100% {{ box-shadow: 0 0 0 0 rgba(0,230,118,0); }}
}}
@keyframes glow-breathe {{
    0%, 100% {{ opacity: 0.5; }}
    50%      {{ opacity: 1.0; }}
}}
.pulse-dot {{
    width: 7px; height: 7px;
    border-radius: 50%;
    background: {GOLD};
    display: inline-block;
    animation: pulse 2s infinite;
    vertical-align: middle;
    margin-right: 3px;
}}
.pulse-dot-green {{
    width: 7px; height: 7px;
    border-radius: 50%;
    background: {GREEN};
    display: inline-block;
    animation: pulse-green 2s infinite;
    vertical-align: middle;
    margin-right: 3px;
}}

/* ---- COIN TILES ---- */
.coin-card {{
    background: linear-gradient(160deg, rgba(26,37,63,0.75) 0%, rgba(20,32,53,0.85) 100%);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border: 1px solid rgba(61,79,111,0.25);
    border-radius: 14px;
    padding: 18px 14px 12px 14px;
    text-align: center;
    transition: all 0.35s cubic-bezier(0.25, 0.46, 0.45, 0.94);
    box-shadow: 0 4px 20px rgba(0,0,0,0.2);
    position: relative;
    overflow: hidden;
}}
.coin-card::before {{
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 1px;
    background: linear-gradient(90deg, transparent, rgba(168,181,204,0.1), transparent);
}}
.coin-card:hover {{
    border-color: rgba(168,181,204,0.4);
    box-shadow: 0 0 30px rgba(168,181,204,0.1), 0 8px 32px rgba(0,0,0,0.3);
    transform: translateY(-3px);
}}
.coin-card.active {{
    border-color: rgba(168,181,204,0.5);
    box-shadow: 0 0 40px rgba(168,181,204,0.2), 0 8px 32px rgba(0,0,0,0.3);
}}
.coin-card.active::after {{
    content: '';
    position: absolute;
    top: -50%; left: -50%;
    width: 200%; height: 200%;
    background: radial-gradient(circle, rgba(168,181,204,0.03) 0%, transparent 70%);
    pointer-events: none;
}}
.coin-card .sym {{
    font-size: 1.8rem;
    font-weight: 900;
    color: {WHITE};
    letter-spacing: 1.5px;
    margin-bottom: 2px;
}}
.coin-card .price {{
    font-size: 1.58rem;
    font-weight: 700;
    color: {GOLD};
    margin: 6px 0 10px 0;
    text-shadow: 0 0 16px rgba(255,193,7,0.2);
}}
.coin-card .badges {{
    display: flex;
    justify-content: center;
    gap: 6px;
    margin-bottom: 8px;
    flex-wrap: wrap;
}}
.coin-card .meta {{
    font-size: 0.93rem;
    color: {DIMTEXT};
    margin-top: 8px;
    line-height: 1.6;
    font-weight: 500;
}}
.coin-card .meta b {{ color: {SILVER}; }}

/* ---- MOMENTUM BAR ---- */
.mom-wrap {{
    margin: 10px 0 4px 0;
}}
.mom-label {{
    font-size: 0.83rem;
    color: {DIMTEXT};
    text-transform: uppercase;
    letter-spacing: 0.8px;
    font-weight: 700;
    margin-bottom: 4px;
    display: flex;
    justify-content: space-between;
}}
.mom-bar-track {{
    width: 100%;
    height: 6px;
    background: rgba(168,181,204,0.08);
    border-radius: 4px;
    overflow: hidden;
    position: relative;
}}
.mom-bar-fill {{
    height: 100%;
    border-radius: 4px;
    background: linear-gradient(90deg, rgba(0,229,255,0.3), #00e5ff);
    box-shadow: 0 0 12px rgba(0,229,255,0.15);
    transition: width 0.6s cubic-bezier(0.25, 0.46, 0.45, 0.94);
    position: relative;
}}
.mom-bar-fill::after {{
    content: '';
    position: absolute;
    right: 0; top: 0; bottom: 0;
    width: 6px;
    background: #00e5ff;
    border-radius: 50%;
    box-shadow: 0 0 8px rgba(0,229,255,0.4);
    animation: glow-breathe 2s infinite;
}}

/* ---- P/L STRIP ---- */
.pnl-strip {{
    display: flex;
    gap: 14px;
    margin-bottom: 18px;
}}
.pnl-card {{
    flex: 1;
    background: linear-gradient(135deg, rgba(26,37,63,0.7) 0%, rgba(20,32,53,0.8) 100%);
    backdrop-filter: blur(12px);
    border: 1px solid rgba(61,79,111,0.25);
    border-radius: 12px;
    padding: 14px 16px;
    text-align: center;
}}
.pnl-card .pnl-label {{
    font-size: 0.78rem;
    color: {DIMTEXT};
    text-transform: uppercase;
    letter-spacing: 1.2px;
    font-weight: 700;
    margin-bottom: 6px;
}}
.pnl-card .pnl-value {{
    font-size: 1.35rem;
    font-weight: 800;
}}
.pnl-card .pnl-pct {{
    font-size: 0.85rem;
    font-weight: 600;
    margin-top: 2px;
}}
.pnl-green {{ color: #00e676 !important; text-shadow: 0 0 10px rgba(0,230,118,0.3); }}
.pnl-red   {{ color: #ff4d4d !important; text-shadow: 0 0 10px rgba(255,77,77,0.3); }}
.pnl-flat  {{ color: {SILVER} !important; }}

/* ---- POSITIONS TABLE ---- */
.pos-table {{
    width: 100%;
    margin-bottom: 14px;
}}
.pos-header {{
    display: flex;
    padding: 6px 12px;
    font-size: 0.75rem;
    color: {DIMTEXT};
    text-transform: uppercase;
    letter-spacing: 1px;
    font-weight: 700;
    border-bottom: 1px solid rgba(61,79,111,0.2);
}}
.pos-row {{
    display: flex;
    align-items: center;
    padding: 10px 12px;
    font-size: 0.95rem;
    border-radius: 8px;
    margin-bottom: 2px;
}}
.pos-row:nth-child(odd)  {{ background: rgba(168,181,204,0.02); }}
.pos-row:nth-child(even) {{ background: rgba(10,20,40,0.3); }}
.pos-col {{ flex: 1; }}
.pos-col.sym {{ font-weight: 800; color: {WHITE}; }}
.pos-col.val {{ color: {SILVER}; font-weight: 600; }}

/* ---- ORDERS TABLE ---- */
.order-row {{
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 12px;
    border-radius: 8px;
    font-size: 1.02rem;
    margin-bottom: 3px;
    transition: all 0.2s ease;
}}
.order-row:hover {{
    background: rgba(255,193,7,0.04) !important;
}}
.order-row:nth-child(odd)  {{ background: rgba(168,181,204,0.02); }}
.order-row:nth-child(even) {{ background: rgba(10,20,40,0.3); }}
.order-row .time  {{ color: {DIMTEXT}; width: 60px; font-weight: 600; font-size: 0.9rem; }}
.order-row .coin  {{ color: {WHITE}; width: 50px; font-weight: 800; letter-spacing: 0.5px; }}
.order-row .side  {{ width: 52px; font-weight: 700; }}
.order-row .side.buy  {{ color: {GOLD}; text-shadow: 0 0 8px {GOLD_DIM}; }}
.order-row .side.sell {{ color: {RED}; }}
.order-row .side.wait {{ color: {DIMTEXT}; }}
.order-row .type  {{ color: {DIMTEXT}; width: 52px; font-weight: 500; }}
.order-badge {{
    padding: 3px 12px;
    border-radius: 12px;
    font-size: 0.83rem;
    font-weight: 800;
    letter-spacing: 0.8px;
}}
.order-badge.sim  {{ background: {GOLD_DIM}; color: {GOLD}; border: 1px solid rgba(255,193,7,0.2); }}
.order-badge.live {{ background: {GREEN_DIM}; color: {GREEN}; border: 1px solid rgba(0,230,118,0.2); }}

/* ---- ALERT FEED ---- */
.feed-scroll {{
    max-height: 360px;
    overflow-y: auto;
    padding-right: 4px;
}}
.feed-bubble {{
    background: rgba(10,20,40,0.4);
    border-left: 3px solid rgba(255,193,7,0.4);
    border-radius: 0 10px 10px 0;
    padding: 10px 14px;
    margin-bottom: 6px;
    font-size: 1.02rem;
    color: {SILVER};
    line-height: 1.5;
    transition: all 0.25s ease;
}}
.feed-bubble:hover {{
    border-left-color: {GOLD};
    background: rgba(255,193,7,0.03);
    transform: translateX(2px);
}}
.feed-bubble .ts {{
    font-size: 0.84rem;
    color: {DIMTEXT};
    font-weight: 700;
    margin-bottom: 3px;
    letter-spacing: 0.3px;
}}
.feed-bubble.risk {{
    border-left-color: {RED};
    background: rgba(255,77,77,0.04);
}}
.feed-bubble.risk:hover {{
    border-left-color: #ff6b6b;
    background: rgba(255,77,77,0.06);
}}

/* ---- GAUGE ---- */
.gauge-wrap {{
    text-align: center;
    margin-bottom: 16px;
    position: relative;
}}
.gauge-label {{
    font-size: 0.84rem;
    color: {DIMTEXT};
    text-transform: uppercase;
    letter-spacing: 1.5px;
    font-weight: 800;
    margin-top: 6px;
}}

/* ---- LOGIN ---- */
.login-wrap {{
    max-width: 400px;
    margin: 12vh auto;
    background: linear-gradient(135deg, rgba(26,37,63,0.85) 0%, rgba(20,32,53,0.9) 100%);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    border: 1px solid rgba(61,79,111,0.3);
    border-radius: 20px;
    padding: 52px 44px;
    text-align: center;
    box-shadow: 0 16px 64px rgba(0,0,0,0.5), 0 0 40px rgba(255,193,7,0.03);
    position: relative;
    overflow: hidden;
}}
.login-wrap::before {{
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: linear-gradient(90deg, transparent, {GOLD}, transparent);
    opacity: 0.6;
}}
.login-wrap h2 {{
    color: {WHITE};
    font-weight: 900;
    letter-spacing: 3px;
    margin-bottom: 4px;
    font-size: 1.4rem;
}}
.login-wrap .sub {{
    color: {DIMTEXT};
    font-size: 0.75rem;
    margin-bottom: 28px;
    font-weight: 500;
    letter-spacing: 0.5px;
}}
.login-wrap .accent {{ color: {GOLD}; text-shadow: 0 0 20px {GOLD_DIM}; }}

/* ---- INPUT / BUTTON THEMING ---- */
div[data-baseweb="select"] {{
    background: rgba(20,32,53,0.8) !important;
    border-color: rgba(61,79,111,0.3) !important;
    border-radius: 10px !important;
}}
div[data-baseweb="select"] * {{ color: {WHITE} !important; }}
input[type="password"], input[type="text"] {{
    background: rgba(20,32,53,0.8) !important;
    color: {WHITE} !important;
    border-color: rgba(61,79,111,0.3) !important;
    border-radius: 10px !important;
}}
.stButton > button {{
    background: linear-gradient(135deg, {GOLD}, {GOLD_LT}) !important;
    color: #000 !important;
    font-weight: 800 !important;
    border: none !important;
    border-radius: 10px !important;
    letter-spacing: 1px !important;
    box-shadow: 0 4px 20px {GOLD_DIM} !important;
    transition: all 0.3s cubic-bezier(0.25, 0.46, 0.45, 0.94) !important;
    padding: 10px 24px !important;
}}
.stButton > button:hover {{
    box-shadow: 0 8px 32px {GOLD_GLOW} !important;
    transform: translateY(-2px) !important;
}}

/* ---- PLOTLY BG ---- */
.stPlotlyChart {{ background: transparent !important; }}

/* ---- GRID LADDER LABEL ---- */
.ladder-label {{
    font-size: 0.55rem;
    color: {DIMTEXT};
    text-transform: uppercase;
    letter-spacing: 0.6px;
    font-weight: 700;
    padding: 2px 0;
}}

/* ---- POSITION DETAIL BAR ---- */
.pos-bar {{
    display: flex;
    justify-content: space-between;
    padding: 10px 14px;
    background: rgba(26,37,63,0.5);
    border: 1px solid rgba(61,79,111,0.2);
    border-radius: 10px;
    margin-top: 8px;
}}
.pos-bar .item {{
    text-align: center;
}}
.pos-bar .item .val {{
    font-size: 1.28rem;
    font-weight: 700;
    color: {WHITE};
}}
.pos-bar .item .lbl {{
    font-size: 0.83rem;
    color: {DIMTEXT};
    text-transform: uppercase;
    letter-spacing: 0.8px;
    font-weight: 700;
}}

/* ---- HIDE DEFAULTS ---- */
details {{ border: none !important; }}

/* ---- STANDALONE BANNER ---- */
.standalone-banner {{
    background: linear-gradient(90deg, rgba(255,193,7,0.12), rgba(255,193,7,0.06));
    border: 1px solid rgba(255,193,7,0.3);
    border-radius: 10px;
    padding: 10px 20px;
    margin-bottom: 14px;
    text-align: center;
    font-size: 0.88rem;
    color: {GOLD};
    font-weight: 700;
    letter-spacing: 0.8px;
}}

/* ---- MOBILE RESPONSIVE ---- */
@media (max-width: 768px) {{
    .block-container {{
        padding: 1rem 0.5rem 0 0.5rem !important;
    }}
    .topbar {{
        flex-direction: column;
        gap: 10px;
        padding: 12px 16px;
        text-align: center;
    }}
    .topbar-logo {{
        font-size: 1.1rem;
        justify-content: center;
    }}
    .topbar-pills {{
        flex-wrap: wrap;
        justify-content: center;
    }}
    .topbar-status {{
        flex-direction: column;
        gap: 4px;
    }}
    .coin-card {{
        padding: 12px 8px 8px 8px;
    }}
    .coin-card .sym {{
        font-size: 1.3rem;
    }}
    .coin-card .price {{
        font-size: 1.15rem;
    }}
    .pill {{
        font-size: 0.75rem;
        padding: 3px 10px;
    }}
    .pnl-strip {{
        flex-direction: column;
        gap: 8px;
    }}
    .pnl-card .pnl-value {{
        font-size: 1.15rem;
    }}
    .section-label {{
        font-size: 0.78rem;
    }}
    .order-row {{
        font-size: 0.85rem;
        padding: 6px 8px;
    }}
    .feed-bubble {{
        font-size: 0.88rem;
        padding: 8px 10px;
    }}
    div[data-testid="stMetric"] {{
        padding: 8px 10px;
    }}
    div[data-testid="stMetric"] div[data-testid="stMetricValue"] {{
        font-size: 1.15rem !important;
    }}
    section[data-testid="stSidebar"] {{
        width: 220px !important;
    }}
    .gauge-wrap svg {{
        width: 90px;
        height: 90px;
    }}
}}
@media (max-width: 480px) {{
    .topbar-logo {{
        font-size: 0.9rem;
    }}
    .coin-card .sym {{
        font-size: 1.1rem;
    }}
    .coin-card .price {{
        font-size: 1rem;
    }}
}}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

# =====================================================================
#  PASSWORD GATE
# =====================================================================
DASHBOARD_PASSWORD = "hybrid2026"

def check_password() -> bool:
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if st.session_state.authenticated:
        return True

    st.markdown(f"""
    <div class="login-wrap">
        <h2>HYBRID <span class="accent">BOT</span></h2>
        <div class="sub">Institutional Command Center v3</div>
    </div>
    """, unsafe_allow_html=True)

    _, col_m, _ = st.columns([1, 1, 1])
    with col_m:
        pw = st.text_input("Password", type="password", key="pw_input",
                           label_visibility="collapsed", placeholder="Enter access key...")
        if st.button("UNLOCK DASHBOARD", use_container_width=True):
            if pw == DASHBOARD_PASSWORD:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Access denied")
    return False

if not check_password():
    st.stop()

# =====================================================================
#  STANDALONE MODE DETECTION
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

# If imports worked but Coinbase creds are missing, also go standalone
if not STANDALONE_MODE:
    try:
        if not settings.COINBASE_API_KEY or not settings.COINBASE_API_SECRET:
            STANDALONE_MODE = True
    except Exception:
        STANDALONE_MODE = True

# =====================================================================
#  STANDALONE DATA LOADER (from exports/ or demo data)
# =====================================================================
def load_standalone_data() -> dict:
    """Load data from exports/ files or generate demo data."""
    global STANDALONE_TIMESTAMP
    trades_path = os.path.join(os.path.dirname(__file__), "exports", "trades.csv")
    summary_path = os.path.join(os.path.dirname(__file__), "exports", "performance_summary.txt")
    state_path = os.path.join(os.path.dirname(__file__), "state", "bot_state.json")
    pnl_path = os.path.join(os.path.dirname(__file__), "state", "pnl_history.json")

    data = {
        "trades": pd.DataFrame(),
        "orders_history": [],
        "alerts_history": [],
        "equity": {"cash_usd": 0, "coin_value_usd": 0, "total_equity": 0},
        "risk": {"daily_pnl_pct": 0, "drawdown_pct": 0, "exposure_pct": 0, "trading_allowed": True,
                 "daily_loss_breached": False, "drawdown_breached": False,
                 "max_position_usd": 0, "max_position_pct": 25},
        "positions": {},
        "peak_equity": 0,
        "pnl_summary": {"starting_equity": 0, "current_equity": 0, "daily_pnl": 0,
                        "daily_pnl_pct": 0, "alltime_pnl": 0, "alltime_pnl_pct": 0,
                        "today_open": 0, "days_trading": 0},
        "coin_data": {},
        "bot_state": {},
    }

    # Load trades CSV
    if os.path.exists(trades_path):
        try:
            data["trades"] = pd.read_csv(trades_path)
            STANDALONE_TIMESTAMP = str(data["trades"]["timestamp"].iloc[0]) if len(data["trades"]) > 0 else ""
        except Exception:
            pass

    # Load bot state JSON
    if os.path.exists(state_path):
        import json
        try:
            with open(state_path) as f:
                bs = json.load(f)
            data["bot_state"] = bs
            data["orders_history"] = bs.get("orders_history", [])
            data["alerts_history"] = bs.get("alerts_history", [])
            eq_snap = bs.get("equity_snapshot", {})
            data["equity"] = {
                "cash_usd": eq_snap.get("cash_usd", 0),
                "coin_value_usd": 0,
                "total_equity": eq_snap.get("total_equity", 0),
            }
            data["peak_equity"] = eq_snap.get("peak_equity", 0)
            STANDALONE_TIMESTAMP = bs.get("timestamp", STANDALONE_TIMESTAMP)
        except Exception:
            pass

    # Load P/L history
    if os.path.exists(pnl_path):
        import json
        try:
            with open(pnl_path) as f:
                pnl_data = json.load(f)
            starting = pnl_data.get("starting_equity", 0)
            current = pnl_data.get("last_equity", starting)
            now = datetime.now(ZoneInfo("America/New_York"))
            today_str = now.strftime("%Y-%m-%d")
            today_data = pnl_data.get("days", {}).get(today_str, {})
            today_open = today_data.get("open_equity", current)
            daily_pnl = current - today_open
            daily_pct = (daily_pnl / today_open * 100) if today_open > 0 else 0
            alltime_pnl = current - starting
            alltime_pct = (alltime_pnl / starting * 100) if starting > 0 else 0
            data["pnl_summary"] = {
                "starting_equity": round(starting, 4),
                "current_equity": round(current, 4),
                "daily_pnl": round(daily_pnl, 4),
                "daily_pnl_pct": round(daily_pct, 4),
                "alltime_pnl": round(alltime_pnl, 4),
                "alltime_pnl_pct": round(alltime_pct, 4),
                "today_open": round(today_open, 4),
                "days_trading": len(pnl_data.get("days", {})),
            }
        except Exception:
            pass

    # Build coin_data from trades
    if not data["trades"].empty:
        for sym in data["trades"]["symbol"].unique():
            sym_trades = data["trades"][data["trades"]["symbol"] == sym]
            last_price = sym_trades["price"].iloc[-1] if len(sym_trades) > 0 else 0
            data["coin_data"][sym] = {
                "symbol": sym, "price": last_price,
                "regime": {"regime": "RANGING", "confidence": 0.5, "details": "Standalone mode"},
                "momentum": {"score": 0.5, "direction": "NEUTRAL"},
                "decision": {"decision": "WAIT", "reason": "Standalone mode — no live data", "details": {}},
                "grid_levels": {"current_price": last_price, "buy_levels": [], "sell_levels": [],
                                "grid_spacing_pct": 0, "grid_spacing_usd": 0,
                                "capital_per_level": 0, "total_capital_deployed": 0,
                                "est_profit_usd": 0, "est_profit_pct": 0, "regime": "RANGING"},
                "sparkline": sym_trades["price"].tail(20).tolist() if len(sym_trades) >= 2 else [last_price] * 5,
                "atr_pct": 0, "rsi": 50,
            }

    # If no data at all, generate demo
    if not data["coin_data"]:
        for sym in ["DOGE-USD", "SHIB-USD", "PEPE-USD"]:
            data["coin_data"][sym] = {
                "symbol": sym, "price": 0.0001,
                "regime": {"regime": "RANGING", "confidence": 0.6, "details": "Demo"},
                "momentum": {"score": 0.5, "direction": "NEUTRAL"},
                "decision": {"decision": "WAIT", "reason": "No live data available", "details": {}},
                "grid_levels": {"current_price": 0.0001, "buy_levels": [], "sell_levels": [],
                                "grid_spacing_pct": 0, "grid_spacing_usd": 0,
                                "capital_per_level": 0, "total_capital_deployed": 0,
                                "est_profit_usd": 0, "est_profit_pct": 0, "regime": "RANGING"},
                "sparkline": [0.0001] * 5,
                "atr_pct": 0, "rsi": 50,
            }
        STANDALONE_TIMESTAMP = "No data files found"

    return data

# =====================================================================
#  LIVE MODE: CACHED RESOURCES + DATA FETCHERS
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

    @st.cache_data(ttl=5, show_spinner=False)
    def fetch_coin_data(symbol: str) -> dict:
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
            sparkline = df["close"].tail(20).tolist()
            return {
                "symbol": symbol, "df": df, "latest": latest,
                "regime": regime_result, "grid_levels": grid_levels,
                "momentum": momentum_result, "decision": decision,
                "sparkline": sparkline, "price": latest["close"],
                "atr_pct": latest["atr_pct"], "rsi": latest["rsi_14"],
            }
        except Exception as e:
            return {"error": str(e), "symbol": symbol}

if not STANDALONE_MODE:
    @st.cache_data(ttl=5, show_spinner=False)
    def fetch_account_data() -> dict:
        try:
            positions = pos_mgr.get_current_positions()
            equity_info = pos_mgr.get_account_equity(positions)
            exposure = pos_mgr.calculate_total_exposure(positions)
            current_equity = equity_info["total_equity"]
            peak = pos_mgr.update_peak_equity(current_equity)
            risk = risk_mgr.get_risk_summary(
                current_equity=current_equity, start_of_day_equity=current_equity,
                peak_equity=peak, current_exposure_usd=exposure,
            )
            return {"positions": positions, "equity": equity_info,
                    "exposure": exposure, "risk": risk, "peak_equity": peak}
        except Exception as e:
            return {"error": str(e)}

    @st.cache_data(ttl=5, show_spinner=False)
    def fetch_equity_history(symbol: str = "PEPE-USD") -> pd.DataFrame:
        try:
            df_raw = fetcher.get_recent_candles(symbol, granularity="FIVE_MINUTE", limit=300)
            df = df_raw[["timestamp", "close"]].copy().rename(columns={"close": "price"})
            s = df["price"].iloc[0]
            live_eq = pos_mgr.live_equity
            capital = live_eq if live_eq > 0 else settings.MAX_POSITION_SIZE_USD
            if s > 0:
                df["equity"] = df["price"] / s * capital
            else:
                df["equity"] = capital
            df["pnl"] = df["equity"] - capital
            return df
        except Exception:
            return pd.DataFrame()

# =====================================================================
#  HELPERS — SVG GAUGE
# =====================================================================
def svg_gauge(label: str, value: float, max_val: float) -> str:
    pct = min(value / max_val, 1.0) if max_val > 0 else 0
    angle = pct * 270  # 270-degree sweep for premium look
    if pct < 0.5:
        stroke = GOLD
        glow_color = GOLD_GLOW
        track_opacity = "0.12"
    elif pct < 0.8:
        stroke = "#ff9800"
        glow_color = "rgba(255,152,0,0.35)"
        track_opacity = "0.15"
    else:
        stroke = RED
        glow_color = "rgba(255,77,77,0.35)"
        track_opacity = "0.18"

    r = 44
    cx, cy = 56, 56
    stroke_w = 7

    # Start at 135 degrees (bottom-left), sweep 270 degrees clockwise
    start_angle = 135
    end_angle_track = start_angle + 270
    end_angle_fill = start_angle + angle

    def arc_point(a):
        rad = math.radians(a)
        return cx + r * math.cos(rad), cy + r * math.sin(rad)

    def arc_path(start_a, end_a):
        sx, sy = arc_point(start_a)
        ex, ey = arc_point(end_a)
        sweep = end_a - start_a
        large = 1 if sweep > 180 else 0
        if sweep >= 359.9:
            mx, my = arc_point(start_a + 180)
            return (f"M {sx:.1f} {sy:.1f} A {r} {r} 0 1 1 {mx:.1f} {my:.1f} "
                    f"A {r} {r} 0 1 1 {sx:.1f} {sy:.1f}")
        if sweep <= 0:
            return ""
        return f"M {sx:.1f} {sy:.1f} A {r} {r} 0 {large} 1 {ex:.1f} {ey:.1f}"

    track_path = arc_path(start_angle, end_angle_track)
    fill_path = arc_path(start_angle, end_angle_fill) if angle > 0 else ""

    # Needle endpoint
    nx, ny = arc_point(end_angle_fill) if angle > 0 else arc_point(start_angle)

    uid = label.replace(" ", "").replace("/", "")

    return f"""
    <div class="gauge-wrap">
        <svg width="112" height="112" viewBox="0 0 112 112">
            <defs>
                <filter id="glow-{uid}">
                    <feGaussianBlur stdDeviation="3.5" result="blur"/>
                    <feMerge>
                        <feMergeNode in="blur"/>
                        <feMergeNode in="SourceGraphic"/>
                    </feMerge>
                </filter>
                <linearGradient id="grad-{uid}" x1="0%" y1="0%" x2="100%" y2="100%">
                    <stop offset="0%" stop-color="{stroke}" stop-opacity="0.6"/>
                    <stop offset="100%" stop-color="{stroke}" stop-opacity="1"/>
                </linearGradient>
            </defs>
            <!-- Track -->
            <path d="{track_path}" fill="none"
                  stroke="{DIM}" stroke-width="{stroke_w}" opacity="{track_opacity}"
                  stroke-linecap="round"/>
            <!-- Fill -->
            <path d="{fill_path}" fill="none"
                  stroke="url(#grad-{uid})" stroke-width="{stroke_w}" stroke-linecap="round"
                  filter="url(#glow-{uid})"/>
            <!-- Needle dot -->
            <circle cx="{nx:.1f}" cy="{ny:.1f}" r="4" fill="{stroke}"
                    filter="url(#glow-{uid})"/>
            <circle cx="{nx:.1f}" cy="{ny:.1f}" r="2" fill="{WHITE}"/>
            <!-- Value text -->
            <text x="{cx}" y="{cy - 2}" text-anchor="middle" dominant-baseline="middle"
                  fill="{WHITE}" font-size="28" font-weight="900" font-family="Inter, sans-serif">
                {value:.1f}%
            </text>
            <text x="{cx}" y="{cy + 18}" text-anchor="middle" dominant-baseline="middle"
                  fill="{DIMTEXT}" font-size="13" font-weight="600" font-family="Inter, sans-serif"
                  letter-spacing="0.5">
                of {max_val:.0f}%
            </text>
        </svg>
        <div class="gauge-label">{label}</div>
    </div>
    """

def make_sparkline(data: list, color: str = SILVER, h: int = 42) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        y=data, mode="lines",
        line=dict(color=color, width=1.5, shape="spline", smoothing=1.2),
        fill="tozeroy",
        fillcolor="rgba(168,181,204,0.04)",
        hoverinfo="skip",
    ))
    fig.update_layout(
        height=h, margin=dict(l=0, r=0, t=0, b=0),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        xaxis=dict(visible=False), yaxis=dict(visible=False),
        showlegend=False,
    )
    return fig

# =====================================================================
#  LOAD DATA + BOT STATE
# =====================================================================
now_utc = datetime.now(timezone.utc)
LOCAL_TZ = ZoneInfo("America/New_York")
now_local = now_utc.astimezone(LOCAL_TZ)

if STANDALONE_MODE:
    standalone_data = load_standalone_data()
    account = {
        "positions": standalone_data["positions"],
        "equity": standalone_data["equity"],
        "risk": standalone_data["risk"],
        "peak_equity": standalone_data["peak_equity"],
    }
    coin_data = standalone_data["coin_data"]
    equity_hist = pd.DataFrame()  # No live equity curve in standalone
    bot_state = standalone_data["bot_state"]
    _trading_pairs = list(coin_data.keys()) if coin_data else ["DOGE-USD", "SHIB-USD", "PEPE-USD"]
    _paper_trading = True
    _daily_loss_limit = 5.0
    _max_drawdown = 15.0
    _max_position_pct = 25.0
    _enable_telegram = False
else:
    account = fetch_account_data()
    coin_data = {}
    for sym in settings.TRADING_PAIRS:
        coin_data[sym] = fetch_coin_data(sym)
    equity_hist = fetch_equity_history(settings.TRADING_PAIRS[0])
    bot_state = read_state()
    _trading_pairs = settings.TRADING_PAIRS
    _paper_trading = settings.PAPER_TRADING
    _daily_loss_limit = settings.DAILY_LOSS_LIMIT_PCT
    _max_drawdown = settings.MAX_DRAWDOWN_PCT
    _max_position_pct = settings.MAX_POSITION_PCT
    _enable_telegram = settings.ENABLE_TELEGRAM_ALERTS
bot_running = False
bot_cycle = 0
bot_daily_cycles = 0
state_age_seconds = 999

if bot_state:
    bot_cycle = bot_state.get("cycle_count", 0)
    bot_daily_cycles = bot_state.get("daily_cycle_count", 0)
    bot_running = bot_state.get("bot_running", False)
    # Calculate how fresh the state is
    ts_str = bot_state.get("timestamp", "")
    if ts_str:
        try:
            state_time = datetime.fromisoformat(ts_str)
            if state_time.tzinfo is None:
                state_time = state_time.replace(tzinfo=timezone.utc)
            state_age_seconds = int((now_utc - state_time).total_seconds())
            # If state is older than 6 minutes, bot is probably not running
            if state_age_seconds > 360:
                bot_running = False
        except (ValueError, TypeError):
            pass

# Track refresh time
if "last_refresh" not in st.session_state:
    st.session_state.last_refresh = now_utc
seconds_ago = int((now_utc - st.session_state.last_refresh).total_seconds())
st.session_state.last_refresh = now_utc

# Track dashboard refresh count
if "dash_refresh_count" not in st.session_state:
    st.session_state.dash_refresh_count = 0
st.session_state.dash_refresh_count += 1

# =====================================================================
#  STANDALONE BANNER (if applicable)
# =====================================================================
if STANDALONE_MODE:
    ts_display = STANDALONE_TIMESTAMP[:19] if STANDALONE_TIMESTAMP else "Unknown"
    st.markdown(f'<div class="standalone-banner">STANDALONE MODE &mdash; Last data from {ts_display}</div>', unsafe_allow_html=True)

# =====================================================================
#  TOP NAV BAR
# =====================================================================
is_live = not _paper_trading
mode_cls = "pill-live" if is_live else "pill-paper"
mode_txt = "LIVE TRADING" if is_live else "PAPER TRADING"
pulse_cls = "pulse-dot" if is_live else "pulse-dot-green"

# Bot status pill
if bot_running:
    bot_status_pill = f'<span class="pill pill-connected"><span class="pulse-dot-green"></span> BOT LIVE</span>'
else:
    bot_status_pill = f'<span class="pill pill-wait">BOT OFFLINE</span>'

# Cycle pill
cycle_pill = ""
if bot_cycle > 0:
    cycle_pill = f'<span class="pill pill-exchange">CYCLE #{bot_cycle}</span>'

st.markdown(f"""
<div class="topbar">
    <div class="topbar-logo">
        <span class="accent">///</span> HYBRID GRID <span class="accent">+</span> MOMENTUM
    </div>
    <div class="topbar-pills">
        <span class="pill {mode_cls}"><span class="{pulse_cls}"></span> {mode_txt}</span>
        {bot_status_pill}
        {cycle_pill}
        <span class="pill pill-exchange">COINBASE</span>
    </div>
    <div class="topbar-status">
        <div class="topbar-time">
            {now_local.strftime("%Y-%m-%d")} &nbsp; <b>{now_local.strftime("%H:%M:%S")}</b> EDT
        </div>
        <div class="topbar-updated">
            Last updated {seconds_ago}s ago
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# =====================================================================
#  SIDEBAR — RISK GAUGES + ACCOUNT
# =====================================================================
with st.sidebar:
    st.markdown('<div class="section-label">Risk Gauges</div>', unsafe_allow_html=True)
    risk = account.get("risk", {})

    st.markdown(svg_gauge("Daily Loss", abs(risk.get("daily_pnl_pct", 0)),
                          _daily_loss_limit), unsafe_allow_html=True)
    st.markdown(svg_gauge("Drawdown", risk.get("drawdown_pct", 0),
                          _max_drawdown), unsafe_allow_html=True)
    st.markdown(svg_gauge("Exposure", risk.get("exposure_pct", 0),
                          _max_position_pct), unsafe_allow_html=True)

    st.markdown("---")
    st.markdown('<div class="section-label">Account</div>', unsafe_allow_html=True)
    eq = account.get("equity", {})
    st.metric("Cash USD", f"${eq.get('cash_usd', 0):,.4f}")
    st.metric("Coin Value", f"${eq.get('coin_value_usd', 0):,.6f}")
    total_eq = eq.get('total_equity', 0)
    st.markdown(f"""
    <div style="background:linear-gradient(135deg,rgba(26,37,63,0.7),rgba(20,32,53,0.8));
                border:1px solid rgba(61,79,111,0.3); border-radius:10px; padding:16px 14px;
                backdrop-filter:blur(8px); box-shadow:0 2px 12px rgba(0,0,0,0.2),inset 0 1px 0 rgba(168,181,204,0.04);">
        <div style="font-size:0.83rem; color:#00e676 !important; text-transform:uppercase;
                    letter-spacing:1px; font-weight:800;
                    text-shadow:0 0 12px rgba(0,230,118,0.4);">Total Equity</div>
        <div style="font-size:1.5rem; font-weight:900; color:#00e676 !important;
                    text-shadow:0 0 20px rgba(0,230,118,0.5), 0 0 40px rgba(0,230,118,0.2); margin-top:4px; line-height:1.1;">
            ${total_eq:,.4f}
        </div>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("<div style='height:4px;'></div>", unsafe_allow_html=True)
    st.metric("Peak Equity", f"${account.get('peak_equity', 0):,.4f}")

    st.markdown("---")
    tg_on = _enable_telegram
    tg_color = GREEN if tg_on else RED
    tg_text = "ON" if tg_on else "OFF"

    st.markdown(f"""
    <div style="text-align:center; padding: 8px 0;">
        <div style="font-size:0.83rem; color:{DIMTEXT}; text-transform:uppercase;
                    letter-spacing:1.2px; font-weight:700; margin-bottom:10px;">System Status</div>
        <div style="font-size:0.98rem; color:{SILVER}; line-height:2.2;">
            Telegram: <b style="color:{tg_color};">{tg_text}</b><br/>
            Refresh: <b style="color:{SILVER};">5s</b><br/>
            Updated: <b style="color:{SILVER};">{now_local.strftime("%H:%M:%S")}</b> EDT
        </div>
    </div>
    """, unsafe_allow_html=True)

# =====================================================================
#  MAIN LAYOUT: CENTER + RIGHT
# =====================================================================
center, right = st.columns([3, 1])

with center:
    # ---- EQUITY CURVE ----
    st.markdown('<div class="section-label">Equity Curve</div>', unsafe_allow_html=True)
    if not equity_hist.empty:
        fig = go.Figure()

        # Gold fill area
        fig.add_trace(go.Scatter(
            x=equity_hist["timestamp"], y=equity_hist["equity"],
            mode="lines", name="Equity",
            line=dict(color=GOLD, width=2.8, shape="spline", smoothing=1.2),
            fill="tozeroy",
            fillcolor="rgba(255,193,7,0.04)",
            customdata=equity_hist["pnl"],
            hovertemplate="<b>$%{y:,.4f}</b><br>P&L: %{customdata:+,.4f}<extra></extra>",
        ))

        # Start line
        fig.add_hline(
            y=account.get("equity", {}).get("total_equity", 100), line_dash="dot",
            line_color="rgba(90,106,133,0.4)", line_width=0.8,
            annotation_text="  Start", annotation_font_color=DIMTEXT,
            annotation_font_size=9,
        )

        # Peak marker
        if len(equity_hist) > 0:
            peak_idx = equity_hist["equity"].idxmax()
            peak_row = equity_hist.loc[peak_idx]
            fig.add_trace(go.Scatter(
                x=[peak_row["timestamp"]], y=[peak_row["equity"]],
                mode="markers", name="Peak",
                marker=dict(color=GOLD, size=8, symbol="diamond",
                            line=dict(color=WHITE, width=1.5)),
                hovertemplate="<b>PEAK</b><br>$%{y:,.4f}<extra></extra>",
                showlegend=False,
            ))

        fig.update_layout(
            height=310, margin=dict(l=52, r=16, t=10, b=40),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color=SILVER, size=10, family="Inter, sans-serif"),
            xaxis=dict(
                gridcolor="rgba(61,79,111,0.15)", gridwidth=0.5,
                showline=False, zeroline=False,
                tickfont=dict(size=9, color=DIMTEXT),
            ),
            yaxis=dict(
                gridcolor="rgba(61,79,111,0.15)", gridwidth=0.5,
                showline=False, zeroline=False,
                tickprefix="$", tickfont=dict(size=9, color=DIMTEXT),
            ),
            showlegend=False, hovermode="x unified",
            hoverlabel=dict(bgcolor=PANEL, bordercolor=DIM, font_color=WHITE, font_size=11),
        )
        st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
    else:
        st.info("Waiting for equity data...")

    # ---- OPEN POSITIONS + P/L ----
    # Record equity from dashboard side too (so P/L updates even if bot is offline)
    if not STANDALONE_MODE:
        total_eq_val = account.get("equity", {}).get("total_equity", 0)
        if total_eq_val > 0:
            record_equity(total_eq_val)
        pnl = get_pnl_summary()
    else:
        pnl = standalone_data["pnl_summary"]
    daily_pnl = pnl["daily_pnl"]
    daily_pct = pnl["daily_pnl_pct"]
    alltime_pnl = pnl["alltime_pnl"]
    alltime_pct = pnl["alltime_pnl_pct"]

    d_cls = "pnl-green" if daily_pnl > 0 else ("pnl-red" if daily_pnl < 0 else "pnl-flat")
    d_sign = "+" if daily_pnl >= 0 else ""
    a_cls = "pnl-green" if alltime_pnl > 0 else ("pnl-red" if alltime_pnl < 0 else "pnl-flat")
    a_sign = "+" if alltime_pnl >= 0 else ""

    # Open orders count
    order_count = len(bot_state.get("orders_history", []))

    st.markdown('<div class="section-label">Portfolio</div>', unsafe_allow_html=True)

    # P/L strip: 3 cards
    st.markdown(f"""
    <div class="pnl-strip">
        <div class="pnl-card">
            <div class="pnl-label">Open Orders</div>
            <div class="pnl-value" style="color:{WHITE};">{order_count}</div>
            <div class="pnl-pct" style="color:{DIMTEXT};">total</div>
        </div>
        <div class="pnl-card">
            <div class="pnl-label">Daily P/L</div>
            <div class="pnl-value {d_cls}">{d_sign}${abs(daily_pnl):,.2f}</div>
            <div class="pnl-pct {d_cls}">{d_sign}{daily_pct:.2f}%</div>
        </div>
        <div class="pnl-card">
            <div class="pnl-label">All-Time P/L</div>
            <div class="pnl-value {a_cls}">{a_sign}${abs(alltime_pnl):,.2f}</div>
            <div class="pnl-pct {a_cls}">{a_sign}{alltime_pct:.2f}% &middot; {pnl['days_trading']}d</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Open orders list from bot state
    state_orders = bot_state.get("orders_history", [])
    if state_orders:
        # Build header
        st.markdown(f"""<div style="display:flex; padding:6px 12px; font-size:0.75rem; color:{DIMTEXT};
                    text-transform:uppercase; letter-spacing:1px; font-weight:700;
                    border-bottom:1px solid rgba(61,79,111,0.2);">
            <span style="flex:1;">Time</span>
            <span style="flex:1;">Coin</span>
            <span style="flex:1;">Side</span>
            <span style="flex:1;">Type</span>
            <span style="flex:1;">Size</span>
            <span style="flex:1;">P/L</span>
        </div>""", unsafe_allow_html=True)

        for idx, o in enumerate(state_orders[:20]):
            ts_raw = o.get("timestamp", "")
            try:
                ts_dt = datetime.fromisoformat(ts_raw)
                if ts_dt.tzinfo is None:
                    ts_dt = ts_dt.replace(tzinfo=timezone.utc)
                ts = ts_dt.astimezone(LOCAL_TZ).strftime("%H:%M")
            except (ValueError, TypeError):
                ts = "—"

            coin_short = o.get("symbol", "").replace("-USD", "")
            side = o.get("side", "")
            order_type = o.get("type", "").replace("_", " ").upper()[:8]
            size_usd = o.get("size_usd")
            size_txt = f"${size_usd:.2f}" if size_usd else "—"
            tag = o.get("tag", "")

            # Color for side
            if side == "BUY":
                side_color = GREEN
            elif side == "SELL":
                side_color = RED
            else:
                side_color = DIMTEXT

            # Estimate P/L for grid orders (simulated) — show % and USDC
            order_price = o.get("price", 0)
            order_size = size_usd if size_usd else 5.0  # default grid size
            pnl_txt = "—"
            pnl_color = DIMTEXT
            if order_price and order_price > 0 and coin_short:
                cd_lookup = coin_data.get(f"{coin_short}-USD", {})
                if cd_lookup and "price" in cd_lookup:
                    current_p = cd_lookup["price"]
                    if side == "BUY" and current_p > 0:
                        pnl_pct = (current_p - order_price) / order_price * 100
                        pnl_usd = pnl_pct / 100 * order_size
                        pnl_txt = f"${pnl_usd:+.4f} / {pnl_pct:+.2f}%"
                        pnl_color = GREEN if pnl_pct >= 0 else RED
                    elif side == "SELL" and current_p > 0:
                        pnl_pct = (order_price - current_p) / order_price * 100
                        pnl_usd = pnl_pct / 100 * order_size
                        pnl_txt = f"${pnl_usd:+.4f} / {pnl_pct:+.2f}%"
                        pnl_color = GREEN if pnl_pct >= 0 else RED

            bg = "rgba(168,181,204,0.02)" if idx % 2 == 0 else "rgba(10,20,40,0.3)"

            st.markdown(f"""<div style="display:flex; align-items:center; padding:8px 12px;
                        font-size:0.92rem; border-radius:8px; margin-bottom:2px; background:{bg};">
                <span style="flex:1; color:{DIMTEXT}; font-weight:600;">{ts}</span>
                <span style="flex:1; color:{WHITE}; font-weight:800;">{coin_short}</span>
                <span style="flex:1; color:{side_color}; font-weight:700;">{side}</span>
                <span style="flex:1; color:{DIMTEXT}; font-weight:500;">{order_type}</span>
                <span style="flex:1; color:{SILVER}; font-weight:600;">{size_txt}</span>
                <span style="flex:1; color:{pnl_color}; font-weight:700;">{pnl_txt}</span>
            </div>""", unsafe_allow_html=True)
    else:
        st.markdown(f'<div style="color:{DIMTEXT}; padding:10px; font-size:0.95rem;">No orders yet — waiting for first bot cycle</div>', unsafe_allow_html=True)

    # ---- COIN TILES ----
    st.markdown('<div class="section-label">Live Markets</div>', unsafe_allow_html=True)
    cols = st.columns(len(_trading_pairs))
    for i, sym in enumerate(_trading_pairs):
        with cols[i]:
            cd = coin_data.get(sym, {})
            if "error" in cd:
                st.markdown(f"""<div class="coin-card">
                    <div class="sym">{sym.replace("-USD","")}</div>
                    <div style="color:{RED}; font-size:0.72rem; margin-top:10px;">Unavailable</div>
                </div>""", unsafe_allow_html=True)
                continue

            price = cd["price"]
            regime = cd["regime"]["regime"]
            r_cls = "pill-ranging" if regime == "RANGING" else "pill-trending"
            dec = cd["decision"]["decision"]
            d_cls = "pill-grid" if dec == "GRID" else ("pill-scalp" if dec == "SCALP" else "pill-wait")
            mom = cd["momentum"]["score"]
            mom_w = int(mom * 100)
            active = " active" if dec in ("GRID", "SCALP") else ""

            st.markdown(f"""
            <div class="coin-card{active}">
                <div class="sym">{sym.replace("-USD","")}</div>
                <div class="price">${price:.8f}</div>
                <div class="badges">
                    <span class="pill {r_cls}">{regime}</span>
                    <span class="pill {d_cls}">{dec}</span>
                </div>
                <div class="mom-wrap">
                    <div class="mom-label">
                        <span>Momentum</span>
                        <span style="color:{SILVER};">{mom:.2f}</span>
                    </div>
                    <div class="mom-bar-track"><div class="mom-bar-fill" style="width:{mom_w}%;"></div></div>
                </div>
                <div class="meta">
                    RSI: <b>{cd['rsi']:.0f}</b> &middot; ATR: <b>{cd['atr_pct']:.2f}%</b>
                </div>
            </div>
            """, unsafe_allow_html=True)

            if cd.get("sparkline"):
                st.plotly_chart(make_sparkline(cd["sparkline"]), use_container_width=True,
                                config={"displayModeBar": False})

    # ---- GRID LADDER ----
    st.markdown('<div class="section-label">Grid Ladder</div>', unsafe_allow_html=True)
    sel = st.selectbox("Coin", _trading_pairs, label_visibility="collapsed")
    cd_s = coin_data.get(sel, {})

    if "error" not in cd_s:
        gl = cd_s["grid_levels"]
        cp = gl["current_price"]

        fig_g = go.Figure()

        # Buy levels — green
        for lv in gl["buy_levels"]:
            fig_g.add_trace(go.Bar(
                y=[f"BUY L{lv['level']}"], x=[lv["size_usd"]], orientation="h",
                marker=dict(
                    color="rgba(0,230,118,0.2)",
                    line=dict(color="rgba(0,230,118,0.5)", width=1),
                ),
                showlegend=False,
                customdata=[[lv["price"], lv["size_coins"]]],
                hovertemplate=(
                    "<b>BUY Level %{y}</b><br>"
                    "Price: $%{customdata[0]:.10f}<br>"
                    "Size: $%{x:.2f}<br>"
                    "Coins: %{customdata[1]:,.2f}<extra></extra>"
                ),
            ))

        # Sell levels — red
        for lv in gl["sell_levels"]:
            fig_g.add_trace(go.Bar(
                y=[f"SELL L{lv['level']}"], x=[lv["size_usd"]], orientation="h",
                marker=dict(
                    color="rgba(255,77,77,0.2)",
                    line=dict(color="rgba(255,77,77,0.5)", width=1),
                ),
                showlegend=False,
                customdata=[[lv["price"], lv["size_coins"]]],
                hovertemplate=(
                    "<b>SELL Level %{y}</b><br>"
                    "Price: $%{customdata[0]:.10f}<br>"
                    "Size: $%{x:.2f}<br>"
                    "Coins: %{customdata[1]:,.2f}<extra></extra>"
                ),
            ))

        fig_g.update_layout(
            height=240, margin=dict(l=70, r=16, t=10, b=28),
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color=SILVER, size=9, family="Inter, sans-serif"),
            xaxis=dict(
                gridcolor="rgba(61,79,111,0.12)", showline=False,
                zeroline=False, title="USD per level", title_font_size=9,
                tickfont=dict(color=DIMTEXT),
            ),
            yaxis=dict(
                gridcolor="rgba(61,79,111,0.06)", showline=False,
                autorange="reversed", tickfont=dict(color=SILVER, size=9),
            ),
            bargap=0.3, showlegend=False,
            hoverlabel=dict(bgcolor=PANEL, bordercolor=DIM, font_color=WHITE, font_size=10),
        )
        st.plotly_chart(fig_g, use_container_width=True, config={"displayModeBar": False})

        # Position details
        pos = account.get("positions", {}).get(sel)
        if pos:
            st.markdown(f"""
            <div class="pos-bar">
                <div class="item">
                    <div class="val">{pos['size_coins']:.6f}</div>
                    <div class="lbl">Holding</div>
                </div>
                <div class="item">
                    <div class="val">${pos['value_usd']:.6f}</div>
                    <div class="lbl">Value</div>
                </div>
                <div class="item">
                    <div class="val">${pos['current_price']:.10f}</div>
                    <div class="lbl">Price</div>
                </div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(
                f'<div style="font-size:1.02rem; color:{DIMTEXT}; padding:6px 0; '
                f'font-weight:500;">No open position in {sel}</div>',
                unsafe_allow_html=True,
            )

# =====================================================================
#  RIGHT COLUMN — ORDERS + ALERT FEED
# =====================================================================
with right:
    # ---- RECENT ORDERS ----
    st.markdown('<div class="section-label">Recent Orders</div>', unsafe_allow_html=True)

    order_html = ""

    # First: show REAL orders from bot state (main.py executed these)
    state_orders = bot_state.get("orders_history", [])
    if state_orders:
        for o in state_orders[:15]:
            ts_raw = o.get("timestamp", "")
            try:
                ts_dt = datetime.fromisoformat(ts_raw)
                if ts_dt.tzinfo is None:
                    ts_dt = ts_dt.replace(tzinfo=timezone.utc)
                ts = ts_dt.astimezone(LOCAL_TZ).strftime("%H:%M")
            except (ValueError, TypeError):
                ts = ts_raw[:5] if ts_raw else "—"

            coin_short = o.get("symbol", "").replace("-USD", "")
            side = o.get("side", "")
            side_cls = "buy" if side == "BUY" else ("sell" if side == "SELL" else "wait")
            side_txt = side if side else "—"
            type_txt = o.get("type", "").replace("_", " ").upper()[:8] if o.get("type") else "—"
            status = o.get("status", "")

            badge_cls = "sim" if status == "simulated" else "live"
            badge_txt = "SIM" if status == "simulated" else "LIVE"
            badge = f'<span class="order-badge {badge_cls}">{badge_txt}</span>'

            order_html += f"""
            <div class="order-row">
                <span class="time">{ts}</span>
                <span class="coin">{coin_short}</span>
                <span class="side {side_cls}">{side_txt}</span>
                <span class="type">{type_txt}</span>
                {badge}
            </div>"""

    # Fallback: show current decisions if no bot state orders
    if not order_html:
        for sym, cd in coin_data.items():
            if "error" in cd:
                continue
            d = cd["decision"]["decision"]
            details = cd["decision"]["details"]
            ts = now_local.strftime("%H:%M")
            coin_short = sym.replace("-USD", "")

            if d == "GRID":
                side_cls = "buy"
                side_txt = "GRID"
                type_txt = "LIMIT"
            elif d == "SCALP":
                side_cls = "buy" if details.get("side") == "BUY" else "sell"
                side_txt = details.get("side", "BUY")
                type_txt = "MARKET"
            else:
                side_cls = "wait"
                side_txt = "WAIT"
                type_txt = "-"

            badge_cls = "sim" if _paper_trading else "live"
            badge_txt = "SIM" if _paper_trading else "LIVE"
            badge = f'<span class="order-badge {badge_cls}">{badge_txt}</span>' if d != "WAIT" else ""

            order_html += f"""
            <div class="order-row">
                <span class="time">{ts}</span>
                <span class="coin">{coin_short}</span>
                <span class="side {side_cls}">{side_txt}</span>
                <span class="type">{type_txt}</span>
                {badge}
            </div>"""

    no_orders = f'<div style="font-size:1.02rem; color:{DIMTEXT}; padding:8px; font-weight:500;">No orders yet</div>'
    orders_content = order_html if order_html else no_orders
    st.markdown(
        f'<div class="glass" style="padding:12px;">{orders_content}</div>',
        unsafe_allow_html=True,
    )

    # ---- ALERT FEED ----
    st.markdown('<div class="section-label">Alert Feed</div>', unsafe_allow_html=True)

    feed_html = ""

    # First: show REAL alerts from bot state
    state_alerts = bot_state.get("alerts_history", [])
    if state_alerts:
        for a in state_alerts[:20]:
            ts_raw = a.get("timestamp", "")
            try:
                ts_dt = datetime.fromisoformat(ts_raw)
                if ts_dt.tzinfo is None:
                    ts_dt = ts_dt.replace(tzinfo=timezone.utc)
                ts = ts_dt.astimezone(LOCAL_TZ).strftime("%H:%M")
            except (ValueError, TypeError):
                ts = ts_raw[:5] if ts_raw else "—"

            symbol = a.get("symbol", "")
            coin_short = symbol.replace("-USD", "") if symbol else ""
            msg = a.get("message", "")
            alert_type = a.get("type", "decision")
            bubble_cls = "risk" if alert_type == "risk" else ""

            ts_label = f"{ts} &middot; {coin_short}" if coin_short else ts
            feed_html += (
                f'<div class="feed-bubble {bubble_cls}">'
                f'<div class="ts">{ts_label}</div>'
                f'{msg}</div>'
            )

    # Fallback: show live risk + decision data
    if not feed_html:
        risk_data = account.get("risk", {})
        if risk_data.get("daily_loss_breached"):
            feed_html += (
                f'<div class="feed-bubble risk">'
                f'<div class="ts">{now_local.strftime("%H:%M")}</div>'
                f'Daily loss limit breached &mdash; trading halted</div>'
            )
        if risk_data.get("drawdown_breached"):
            feed_html += (
                f'<div class="feed-bubble risk">'
                f'<div class="ts">{now_local.strftime("%H:%M")}</div>'
                f'Max drawdown breached &mdash; trading halted</div>'
            )
        for sym, cd in coin_data.items():
            if "error" in cd:
                continue
            d = cd["decision"]["decision"]
            reason = cd["decision"]["reason"][:90]
            ts = now_local.strftime("%H:%M")
            coin_short = sym.replace("-USD", "")
            feed_html += (
                f'<div class="feed-bubble">'
                f'<div class="ts">{ts} &middot; {coin_short}</div>'
                f'{d} &mdash; {reason}...</div>'
            )

    tg_color = GREEN if _enable_telegram else RED
    tg_text = "ON" if _enable_telegram else "OFF"

    no_feed = '<div class="feed-bubble">Waiting for first cycle...</div>'
    feed_content = feed_html if feed_html else no_feed

    st.markdown(f"""
    <div class="glass" style="padding:12px;">
        <div style="font-size:0.83rem; color:{DIMTEXT}; margin-bottom:8px; font-weight:700;
                    letter-spacing:1px; text-transform:uppercase;">
            Telegram: <span style="color:{tg_color};">{tg_text}</span>
            &nbsp;&middot;&nbsp;
            Bot state: <span style="color:{'#00e676' if bot_running else '#ff4d4d'};">{'LIVE' if bot_running else 'OFFLINE'}</span>
        </div>
        <div class="feed-scroll">
            {feed_content}
        </div>
    </div>
    """, unsafe_allow_html=True)

# =====================================================================
#  AUTO-REFRESH (live mode only — standalone doesn't need it)
# =====================================================================
if not STANDALONE_MODE:
    time.sleep(5)
    st.rerun()

"""
DEPLOYMENT INSTRUCTIONS (for public phone link):
1. Push this project to a new GitHub repo
2. Go to https://share.streamlit.io
3. Connect your GitHub repo
4. Deploy — you will get a permanent link like https://yourname-hybrid-bot.streamlit.app
5. Open that link on your phone — it works 24/7 without your laptop running.
"""
