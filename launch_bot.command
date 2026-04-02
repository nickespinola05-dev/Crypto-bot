#!/bin/bash
# ============================================================
# Hybrid Grid + Momentum Switch — One-Click Launcher
# Double-click this file to start both the bot and dashboard
# ============================================================

# Go to the project folder (same folder this script lives in)
cd "$(dirname "$0")"

echo "================================================"
echo "  HYBRID GRID + MOMENTUM SWITCH — LAUNCHING...  "
echo "================================================"
echo ""

# Start the trading bot in the background
echo "[1/2] Starting trading bot..."
python3 main.py &
BOT_PID=$!
echo "       Bot running (PID: $BOT_PID)"
echo ""

# Give the bot a moment to initialize before dashboard reads state
sleep 3

# Start the Streamlit dashboard
echo "[2/2] Starting dashboard..."
streamlit run dashboard.py &
DASH_PID=$!
echo "       Dashboard running (PID: $DASH_PID)"
echo ""

echo "================================================"
echo "  BOTH RUNNING — DO NOT CLOSE THIS WINDOW"
echo "  Press Ctrl+C to stop everything"
echo "================================================"
echo ""

# Wait for Ctrl+C, then kill both
trap "echo ''; echo 'Shutting down...'; kill $BOT_PID $DASH_PID 2>/dev/null; exit 0" INT TERM
wait
