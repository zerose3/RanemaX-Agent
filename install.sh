#!/data/data/com.termux/files/usr/bin/bash
# =============================================================
# RANEMAX Agent — Installer for Termux
#
# This script only does a ONE-TIME setup: it installs Python,
# downloads the agent files from YOUR OWN hosted copy (see the
# RAW_BASE_URL below), and installs dependencies. It does NOT run
# on every heartbeat and does NOT fetch new code after install —
# unlike the "curl | lua" pattern, there is nothing hidden here.
# Read this whole file before running it, or before sharing it
# with anyone else.
# =============================================================

set -e

RAW_BASE_URL="https://raw.githubusercontent.com/zerose3/RanemaX-Agent/main"

INSTALL_DIR="$HOME/ranemax-agent"
FILES=(
  "ranemax_agent.py"
  "security.py"
  "encrypt_config.py"
  "requirements.txt"
  "config.example.json"
)

echo "== RANEMAX Agent Installer =="

echo "[1/4] Installing Python..."
pkg update -y || echo "  (pkg update gagal/mirror sedang sync, lanjut pakai index yang ada)"
pkg install python -y

echo "[2/4] Downloading agent files from your repo..."
mkdir -p "$INSTALL_DIR"
cd "$INSTALL_DIR"
for f in "${FILES[@]}"; do
  echo "  - $f"
  curl -fsSL "$RAW_BASE_URL/$f" -o "$f"
done

echo "[3/4] Installing Python dependencies..."
pip install -r requirements.txt

echo "[4/4] Preparing config..."
if [ ! -f config.json ] && [ ! -f config.enc ]; then
  cp config.example.json config.json
  echo "  Created config.json — edit it with your Supabase + login details."
fi

echo ""
echo "Done! Next steps:"
echo "  1. cd $INSTALL_DIR"
echo "  2. nano config.json        (fill in your details)"
echo "  3. python encrypt_config.py  (lock it with a passphrase)"
echo "  4. python ranemax_agent.py   (start the agent)"