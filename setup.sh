#!/usr/bin/env bash
# ============================================================
# PodBot — One-Command Setup Script
# Run this once after cloning the repo:
#   chmod +x setup.sh && ./setup.sh
# ============================================================

set -e  # Exit on error

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m'

print_step() { echo -e "\n${BLUE}${BOLD}▶ $1${NC}"; }
print_ok()   { echo -e "${GREEN}  ✓ $1${NC}"; }
print_warn() { echo -e "${YELLOW}  ⚠ $1${NC}"; }
print_err()  { echo -e "${RED}  ✗ $1${NC}"; }

echo -e "\n${BOLD}╔══════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║          PODBOT — Setup Script           ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════╝${NC}"

# ── Check Python ─────────────────────────────────────────────
print_step "Checking Python version"
if ! command -v python3 &>/dev/null; then
  print_err "Python 3 not found. Install from https://python.org"
  exit 1
fi
PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
print_ok "Python $PY_VERSION found"

if [[ $(echo "$PY_VERSION < 3.10" | bc) -eq 1 ]]; then
  print_warn "Python 3.10+ recommended. You have $PY_VERSION"
fi

# ── Check FFmpeg ──────────────────────────────────────────────
print_step "Checking FFmpeg"
if command -v ffmpeg &>/dev/null; then
  print_ok "FFmpeg found: $(ffmpeg -version 2>&1 | head -1 | cut -d' ' -f3)"
else
  print_warn "FFmpeg not found — required for audio production"
  echo "  Install:"
  echo "    macOS:   brew install ffmpeg"
  echo "    Ubuntu:  sudo apt-get install -y ffmpeg"
  echo "    Windows: https://ffmpeg.org/download.html"
fi

# ── Create virtual environment ────────────────────────────────
print_step "Creating virtual environment"
if [ -d ".venv" ]; then
  print_ok "Virtual environment already exists"
else
  python3 -m venv .venv
  print_ok "Created .venv"
fi
source .venv/bin/activate
print_ok "Activated .venv"

# ── Install dependencies ──────────────────────────────────────
print_step "Installing Python dependencies"
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
print_ok "All dependencies installed"

# ── Create directory structure ────────────────────────────────
print_step "Creating runtime directories"
mkdir -p outputs/{briefs,scripts,audio,metadata}
mkdir -p database logs data assets
print_ok "Directories ready"

# ── Copy .env ─────────────────────────────────────────────────
print_step "Setting up environment file"
if [ -f ".env" ]; then
  print_ok ".env already exists — skipping"
else
  cp .env.example .env
  print_ok "Copied .env.example → .env"
  print_warn "IMPORTANT: Edit .env and add your API keys before running"
fi

# ── Placeholder assets ────────────────────────────────────────
print_step "Checking audio assets"
if [ ! -f "assets/intro_music.mp3" ]; then
  print_warn "No intro music found at assets/intro_music.mp3"
  echo "  Options:"
  echo "    1. Add your own royalty-free intro_music.mp3 and outro_music.mp3"
  echo "    2. Generate with Suno (https://suno.com) — prompt: 'professional news podcast intro, 8 seconds, upbeat, no vocals'"
  echo "    3. Download free from Pixabay: https://pixabay.com/music/"
  echo "  The pipeline will skip music if files are missing."
fi

# ── Summary ───────────────────────────────────────────────────
echo ""
echo -e "${BOLD}╔══════════════════════════════════════════╗${NC}"
echo -e "${BOLD}║              Setup Complete!             ║${NC}"
echo -e "${BOLD}╚══════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BOLD}Next steps:${NC}"
echo ""
echo -e "  ${YELLOW}1.${NC} Edit ${BOLD}.env${NC} and add your API keys"
echo -e "  ${YELLOW}2.${NC} Add intro/outro music to ${BOLD}assets/${NC}"
echo -e "  ${YELLOW}3.${NC} Run a dry run to test curation:"
echo ""
echo -e "     ${BLUE}source .venv/bin/activate"
echo -e "     python orchestrator.py --show example-show --dry-run${NC}"
echo ""
echo -e "  ${YELLOW}4.${NC} Run your first full episode:"
echo ""
echo -e "     ${BLUE}python orchestrator.py --show example-show${NC}"
echo ""
echo -e "  ${YELLOW}5.${NC} Inject a story into today's episode:"
echo ""
echo -e "     ${BLUE}python agents/inject_stories.py --show example-show --url 'https://...' --priority consider${NC}"
echo ""
echo -e "  ${YELLOW}6.${NC} Open the dashboard: ${BOLD}website/dashboard.html${NC} in your browser"
echo ""
