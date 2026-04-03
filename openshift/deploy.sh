#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  deploy.sh — build, push, and deploy AI Log Analyzer to OpenShift Local (CRC)
#
#  Usage:
#    chmod +x deploy.sh
#    ./deploy.sh           # full deploy
#    ./deploy.sh --redeploy  # rebuild image and do a rolling restart only
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

RESET="\033[0m"; BOLD="\033[1m"; GREEN="\033[32m"; YELLOW="\033[33m"
RED="\033[31m"; CYAN="\033[36m"; DIM="\033[2m"

ok()   { echo -e "  ${GREEN}✓${RESET} $1"; }
info() { echo -e "  ${CYAN}→${RESET} $1"; }
warn() { echo -e "  ${YELLOW}⚠${RESET} $1"; }
fail() { echo -e "\n  ${RED}✗ Error:${RESET} $1\n"; exit 1; }
step() { echo -e "\n${BOLD}${CYAN}[$1]${RESET} ${BOLD}$2${RESET}"; }

REDEPLOY_ONLY=${1:-""}
NAMESPACE="ai-log-analyzer"
APP_NAME="ai-log-analyzer"
REGISTRY="default-route-openshift-image-registry.apps-crc.testing"
IMAGE_TAG="latest"
FULL_IMAGE="${REGISTRY}/${NAMESPACE}/${APP_NAME}:${IMAGE_TAG}"
INTERNAL_IMAGE="image-registry.openshift-image-registry.svc:5000/${NAMESPACE}/${APP_NAME}:${IMAGE_TAG}"

echo -e "\n${BOLD}${CYAN}════════════════════════════════════════${RESET}"
echo -e "${BOLD}  AI Log Analyzer — OpenShift Deploy${RESET}"
echo -e "${BOLD}${CYAN}════════════════════════════════════════${RESET}\n"

# ── Step 1: check prerequisites ───────────────────────────────────────────────
step "1/7" "Checking prerequisites"

command -v crc  >/dev/null 2>&1 || fail "crc not found. Install OpenShift Local first."
command -v oc   >/dev/null 2>&1 || { eval $(crc oc-env) 2>/dev/null || fail "oc not found. Run: eval \$(crc oc-env)"; }
command -v docker >/dev/null 2>&1 || fail "docker not found. Install Docker Desktop."

# Check CRC is running
CRC_STATUS=$(crc status 2>/dev/null | grep "CRC VM" | awk '{print $3}' || echo "Unknown")
if [[ "$CRC_STATUS" != "Running" ]]; then
  warn "CRC is not running. Starting it now..."
  crc start
  sleep 10
fi
ok "CRC is running"

# Check Ollama is up
if curl -s --connect-timeout 3 http://localhost:11434 > /dev/null 2>&1; then
  ok "Ollama is running on host"
else
  warn "Ollama does not appear to be running on localhost:11434"
  warn "Start it with: brew services start ollama"
  warn "Then ensure it listens on all interfaces: OLLAMA_HOST=0.0.0.0 ollama serve"
  read -p "  Continue anyway? [y/N] " yn
  [[ "$yn" =~ ^[Yy]$ ]] || exit 1
fi

# ── Step 2: log in to OpenShift ───────────────────────────────────────────────
step "2/7" "Logging in to OpenShift"

eval $(crc oc-env) 2>/dev/null || true

if ! oc whoami &>/dev/null; then
  info "Not logged in — attempting login..."
  KUBEADMIN_PASS=$(crc console --credentials 2>/dev/null | grep kubeadmin | awk '{print $NF}')
  if [[ -n "$KUBEADMIN_PASS" ]]; then
    oc login -u kubeadmin -p "$KUBEADMIN_PASS" https://api.crc.testing:6443 --insecure-skip-tls-verify=true
  else
    oc login -u kubeadmin https://api.crc.testing:6443 --insecure-skip-tls-verify=true
  fi
fi
ok "Logged in as $(oc whoami)"

# ── Step 3: create project ────────────────────────────────────────────────────
step "3/7" "Creating / switching to project"

if oc get project "$NAMESPACE" &>/dev/null; then
  ok "Project $NAMESPACE already exists"
else
  oc new-project "$NAMESPACE"
  ok "Created project: $NAMESPACE"
fi
oc project "$NAMESPACE" >/dev/null

# Enable image registry default route if not already exposed
if ! oc get route default-route -n openshift-image-registry &>/dev/null; then
  info "Exposing image registry route..."
  oc patch configs.imageregistry.operator.openshift.io/cluster \
    --patch='{"spec":{"defaultRoute":true}}' --type=merge
  sleep 5
fi
ok "Image registry route active"

# Grant image pull permissions
oc policy add-role-to-user \
  system:image-puller system:serviceaccount:${NAMESPACE}:default \
  -n "$NAMESPACE" &>/dev/null || true
ok "Image pull permissions set"

# ── Step 4: log in to the image registry ─────────────────────────────────────
step "4/7" "Logging in to internal image registry"

TOKEN=$(oc whoami -t)
docker login -u kubeadmin -p "$TOKEN" "$REGISTRY" 2>/dev/null \
  || docker login -u "$(oc whoami)" -p "$TOKEN" "$REGISTRY"
ok "Logged in to $REGISTRY"

# ── Step 5: build and push Docker image ───────────────────────────────────────
step "5/7" "Building and pushing Docker image"

# Build from the project root (one level up from openshift/)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"

info "Building from: $PROJECT_ROOT"
docker build -t "${APP_NAME}:${IMAGE_TAG}" "$PROJECT_ROOT"
ok "Image built"

docker tag "${APP_NAME}:${IMAGE_TAG}" "$FULL_IMAGE"
info "Pushing to: $FULL_IMAGE"
docker push "$FULL_IMAGE"
ok "Image pushed"

# Skip apply if redeploy-only
if [[ "$REDEPLOY_ONLY" == "--redeploy" ]]; then
  step "6/7" "Rolling restart (--redeploy flag set, skipping manifest apply)"
  oc rollout restart deployment/"$APP_NAME" -n "$NAMESPACE"
  oc rollout status deployment/"$APP_NAME" -n "$NAMESPACE"
  ok "Redeployed"
  _print_url
  exit 0
fi

# ── Step 6: apply OpenShift manifests ─────────────────────────────────────────
step "6/7" "Applying OpenShift manifests"

MANIFEST_DIR="$SCRIPT_DIR"

oc apply -f "$MANIFEST_DIR/configmap.yaml"
ok "ConfigMap applied"

oc apply -f "$MANIFEST_DIR/pvc.yaml"
ok "PersistentVolumeClaim applied"

# Patch the deployment image reference to match exactly
sed "s|image-registry.openshift-image-registry.svc:5000/${NAMESPACE}/${APP_NAME}:latest|${INTERNAL_IMAGE}|g" \
  "$MANIFEST_DIR/deployment.yaml" | oc apply -f -
ok "Deployment applied"

oc apply -f "$MANIFEST_DIR/service.yaml"
ok "Service applied"

oc apply -f "$MANIFEST_DIR/route.yaml"
ok "Route applied"

# ── Step 7: wait for rollout ──────────────────────────────────────────────────
step "7/7" "Waiting for deployment to become ready"

info "This may take 60-90 seconds (model seeding on first start)..."
oc rollout status deployment/"$APP_NAME" -n "$NAMESPACE" --timeout=300s
ok "Deployment is live"

# Print the app URL
APP_URL=$(oc get route "$APP_NAME" -n "$NAMESPACE" \
  -o jsonpath='{.spec.host}' 2>/dev/null)

echo -e "\n${BOLD}${GREEN}════════════════════════════════════════${RESET}"
echo -e "${BOLD}${GREEN}  Deployment complete!${RESET}"
echo -e "${BOLD}${GREEN}════════════════════════════════════════${RESET}"
echo -e "\n  ${BOLD}App URL:${RESET}     https://${APP_URL}"
echo -e "  ${BOLD}Console:${RESET}     https://console-openshift-console.apps-crc.testing"
echo -e "  ${BOLD}Health:${RESET}      https://${APP_URL}/health"
echo -e "  ${BOLD}Namespace:${RESET}   $NAMESPACE"
echo -e "  ${BOLD}Pods:${RESET}\n"
oc get pods -n "$NAMESPACE"
echo -e ""
info "Opening app in browser..."
open "https://${APP_URL}" 2>/dev/null || true
