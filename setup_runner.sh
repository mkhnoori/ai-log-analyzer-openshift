#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  setup_runner.sh
#  Installs and registers a GitHub Actions self-hosted runner on your Mac.
#  This runner is what lets GitHub Actions deploy to your local OpenShift CRC.
#
#  Usage:
#    chmod +x setup_runner.sh
#    ./setup_runner.sh --token <RUNNER_TOKEN>
#
#  Get your runner token from:
#    https://github.com/mkhnoori/ai-log-analyzer-openshift/settings/actions/runners/new
#    (Select macOS → copy the token from the --token line)
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

RESET="\033[0m"; BOLD="\033[1m"; GREEN="\033[32m"
CYAN="\033[36m"; YELLOW="\033[33m"; RED="\033[31m"

ok()   { echo -e "  ${GREEN}✓${RESET} $1"; }
info() { echo -e "  ${CYAN}→${RESET} $1"; }
warn() { echo -e "  ${YELLOW}⚠${RESET} $1"; }
fail() { echo -e "\n  ${RED}✗ Error:${RESET} $1\n"; exit 1; }

REPO="mkhnoori/ai-log-analyzer-openshift"
RUNNER_DIR="$HOME/actions-runner"
RUNNER_NAME="mac-m3-local"
RUNNER_LABELS="self-hosted,macOS,arm64"
TOKEN=""

# Parse args
while [[ $# -gt 0 ]]; do
  case $1 in
    --token) TOKEN="$2"; shift 2 ;;
    *) fail "Unknown argument: $1" ;;
  esac
done

echo -e "\n${BOLD}${CYAN}════════════════════════════════════════${RESET}"
echo -e "${BOLD}  GitHub Actions Self-Hosted Runner Setup${RESET}"
echo -e "${BOLD}${CYAN}════════════════════════════════════════${RESET}\n"

if [[ -z "$TOKEN" ]]; then
  echo -e "  ${YELLOW}No token provided.${RESET}"
  echo ""
  echo "  Get your runner token from:"
  echo "  https://github.com/$REPO/settings/actions/runners/new"
  echo ""
  echo "  Select: macOS → copy the value after --token"
  echo ""
  read -p "  Paste your runner token here: " TOKEN
  [[ -n "$TOKEN" ]] || fail "Token is required."
fi

# ── Step 1: Download runner ───────────────────────────────────────────────────
echo ""
info "Step 1: Downloading GitHub Actions runner for macOS ARM64..."

mkdir -p "$RUNNER_DIR"
cd "$RUNNER_DIR"

# Get latest runner version
LATEST=$(curl -s https://api.github.com/repos/actions/runner/releases/latest \
  | grep '"tag_name"' | sed 's/.*"v\([^"]*\)".*/\1/')
RUNNER_PKG="actions-runner-osx-arm64-${LATEST}.tar.gz"
RUNNER_URL="https://github.com/actions/runner/releases/download/v${LATEST}/${RUNNER_PKG}"

if [[ -f "run.sh" ]]; then
  warn "Runner already downloaded — skipping download"
else
  info "Downloading $RUNNER_PKG..."
  curl -L -o "$RUNNER_PKG" "$RUNNER_URL"
  tar xzf "$RUNNER_PKG"
  rm "$RUNNER_PKG"
  ok "Runner downloaded and extracted to $RUNNER_DIR"
fi

# ── Step 2: Configure runner ──────────────────────────────────────────────────
echo ""
info "Step 2: Configuring runner..."

if [[ -f ".runner" ]]; then
  warn "Runner already configured — reconfiguring..."
  ./config.sh remove --token "$TOKEN" 2>/dev/null || true
fi

./config.sh \
  --url "https://github.com/$REPO" \
  --token "$TOKEN" \
  --name "$RUNNER_NAME" \
  --labels "$RUNNER_LABELS" \
  --work "_work" \
  --unattended \
  --replace

ok "Runner configured: $RUNNER_NAME"
ok "Labels: $RUNNER_LABELS"

# ── Step 3: Install as launchd service ───────────────────────────────────────
echo ""
info "Step 3: Installing runner as a macOS service (launchd)..."

# The runner's svc.sh handles macOS service installation
./svc.sh install
./svc.sh start

ok "Runner installed and started as a background service"
ok "It will start automatically on login"

# ── Step 4: Verify ────────────────────────────────────────────────────────────
echo ""
info "Step 4: Verifying runner is running..."
sleep 3
./svc.sh status | head -5 || true

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${GREEN}════════════════════════════════════════${RESET}"
echo -e "${BOLD}${GREEN}  Self-hosted runner is ready!${RESET}"
echo -e "${BOLD}${GREEN}════════════════════════════════════════${RESET}"
echo ""
echo "  Runner name:  $RUNNER_NAME"
echo "  Labels:       $RUNNER_LABELS"
echo "  Working dir:  $RUNNER_DIR/_work"
echo ""
echo "  Check it's online at:"
echo "  https://github.com/$REPO/settings/actions/runners"
echo ""
echo "  To trigger a deploy, push a commit to main or go to:"
echo "  https://github.com/$REPO/actions → CD — Deploy to OpenShift Local → Run workflow"
echo ""
echo "  To stop the runner:  cd $RUNNER_DIR && ./svc.sh stop"
echo "  To remove it:        cd $RUNNER_DIR && ./svc.sh uninstall"
echo ""
