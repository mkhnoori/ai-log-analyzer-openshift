#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  cleanup.sh — removes ALL ai-log-analyzer resources from OpenShift Local
#
#  Usage:
#    chmod +x openshift/cleanup.sh
#    ./openshift/cleanup.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

RESET="\033[0m"; BOLD="\033[1m"; GREEN="\033[32m"
RED="\033[31m"; CYAN="\033[36m"; YELLOW="\033[33m"

ok()   { echo -e "  ${GREEN}✓${RESET} $1"; }
info() { echo -e "  ${CYAN}→${RESET} $1"; }
warn() { echo -e "  ${YELLOW}⚠${RESET} $1"; }
fail() { echo -e "\n  ${RED}✗${RESET} $1\n"; exit 1; }

NAMESPACE="ai-log-analyzer"

echo -e "\n${BOLD}${RED}════════════════════════════════════════${RESET}"
echo -e "${BOLD}  AI Log Analyzer — OpenShift Cleanup${RESET}"
echo -e "${BOLD}${RED}════════════════════════════════════════${RESET}\n"

warn "This will DELETE all resources in the '$NAMESPACE' namespace."
warn "ChromaDB data on the PVC will be permanently lost."
echo ""
read -p "  Are you sure? Type 'yes' to continue: " confirm
[[ "$confirm" == "yes" ]] || { echo "  Aborted."; exit 0; }

echo ""

# ── ensure oc is available ────────────────────────────────────────────────────
command -v oc &>/dev/null || { eval $(crc oc-env) 2>/dev/null || fail "oc not found. Run: eval \$(crc oc-env)"; }

# ── ensure logged in ──────────────────────────────────────────────────────────
oc whoami &>/dev/null || {
  info "Not logged in — logging in as kubeadmin..."
  oc login -u kubeadmin https://api.crc.testing:6443 --insecure-skip-tls-verify=true
}
ok "Logged in as $(oc whoami)"

# ── check namespace exists ───────────────────────────────────────────────────
if ! oc get project "$NAMESPACE" &>/dev/null; then
  warn "Namespace '$NAMESPACE' does not exist — nothing to clean up."
  exit 0
fi

info "Switching to project: $NAMESPACE"
oc project "$NAMESPACE" >/dev/null

# ── delete resources in safe order ───────────────────────────────────────────
echo ""
info "Deleting Route..."
oc delete route ai-log-analyzer --ignore-not-found=true
ok "Route deleted"

info "Deleting Service..."
oc delete service ai-log-analyzer --ignore-not-found=true
ok "Service deleted"

info "Deleting Deployment..."
oc delete deployment ai-log-analyzer --ignore-not-found=true
ok "Deployment deleted"

info "Waiting for pods to terminate..."
oc wait --for=delete pod -l app=ai-log-analyzer --timeout=60s 2>/dev/null || true
ok "Pods terminated"

info "Deleting ConfigMap..."
oc delete configmap ai-log-analyzer-config --ignore-not-found=true
ok "ConfigMap deleted"

info "Deleting PersistentVolumeClaim (ChromaDB data)..."
oc delete pvc ai-log-analyzer-data --ignore-not-found=true
ok "PVC deleted"

info "Deleting ImageStream (pushed image)..."
oc delete imagestream ai-log-analyzer --ignore-not-found=true 2>/dev/null || true
ok "ImageStream deleted"

# ── delete the project itself ─────────────────────────────────────────────────
echo ""
info "Deleting project '$NAMESPACE'..."
oc delete project "$NAMESPACE" --ignore-not-found=true
info "Waiting for project to be fully removed..."
for i in $(seq 1 20); do
  oc get project "$NAMESPACE" &>/dev/null || break
  sleep 3
done
ok "Project '$NAMESPACE' deleted"

# ── verify nothing remains ────────────────────────────────────────────────────
echo ""
if oc get project "$NAMESPACE" &>/dev/null; then
  warn "Project still terminating — this is normal, it will finish in the background."
else
  ok "All resources removed from OpenShift"
fi

echo ""
echo -e "${BOLD}${GREEN}════════════════════════════════════════${RESET}"
echo -e "${BOLD}${GREEN}  Cleanup complete!${RESET}"
echo -e "${BOLD}${GREEN}════════════════════════════════════════${RESET}"
echo ""
echo "  OpenShift is now clean."
echo "  To redeploy from GitHub Actions, push a commit to main."
echo "  The self-hosted runner will pick it up automatically."
echo ""
