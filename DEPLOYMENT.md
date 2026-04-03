# Deployment Guide

Complete step-by-step instructions for deploying AI Log Analyzer on
OpenShift Local (CRC) on macOS Apple Silicon (M1/M2/M3).

---

## Table of contents

1. [Prerequisites](#1-prerequisites)
2. [Install Ollama and pull models](#2-install-ollama-and-pull-models)
3. [Configure Ollama for OpenShift access](#3-configure-ollama-for-openshift-access)
4. [Install OpenShift Local (CRC)](#4-install-openshift-local-crc)
5. [Configure CRC resources](#5-configure-crc-resources)
6. [Run crc setup](#6-run-crc-setup)
7. [Start the cluster](#7-start-the-cluster)
8. [Log in and create the project](#8-log-in-and-create-the-project)
9. [Install Podman](#9-install-podman)
10. [Build and push the image](#10-build-and-push-the-image)
11. [Deploy to OpenShift](#11-deploy-to-openshift)
12. [Verify and access the app](#12-verify-and-access-the-app)
13. [Daily operations](#13-daily-operations)
14. [Troubleshooting](#14-troubleshooting)

---

## 1. Prerequisites

- macOS 13 (Ventura) or later
- Apple Silicon Mac (M1/M2/M3) — Intel not supported for this setup
- At least 60 GB free disk space
- At least 48 GB RAM recommended
- [Homebrew](https://brew.sh) installed
- Free [Red Hat account](https://console.redhat.com) — needed for the pull secret

Check macOS version:

```bash
sw_vers
# ProductVersion must be 13.x or higher
```

Check free disk:

```bash
df -h ~
# Need at least 60 GB free
```

---

## 2. Install Ollama and pull models

```bash
# Install
brew install ollama

# Start as a background service
brew services start ollama

# Pull both required models
ollama pull llama3.1:8b        # ~4.7 GB — main reasoning model
ollama pull nomic-embed-text   # ~274 MB — embedding model

# Verify
ollama list
curl http://localhost:11434
# Should return: Ollama is running
```

---

## 3. Configure Ollama for OpenShift access

By default Ollama only accepts connections from `127.0.0.1`. The OpenShift pod
connects from a different IP, so Ollama must listen on all interfaces.

```bash
# Stop the current service
brew services stop ollama

# Kill any lingering process on the port
lsof -ti :11434 | xargs kill -9 2>/dev/null || true

# Start with all-interfaces binding
OLLAMA_HOST=0.0.0.0 ollama serve &

# Verify
curl http://0.0.0.0:11434
# Should return: Ollama is running
```

To make this permanent across reboots:

```bash
echo 'export OLLAMA_HOST=0.0.0.0' >> ~/.zshrc
source ~/.zshrc
brew services restart ollama
```

> **Note:** `host.crc.testing` is the hostname that resolves to your Mac from
> inside CRC pods. This is set in `openshift/configmap.yaml` as `OLLAMA_BASE_URL`.

---

## 4. Install OpenShift Local (CRC)

1. Go to: https://console.redhat.com/openshift/create/local
2. Sign in with your Red Hat account
3. Set **Platform = macOS** and **Architecture = aarch64** (Apple Silicon)
4. Click **Download OpenShift Local** — saves `openshift-local.pkg`
5. Click **Copy pull secret** — paste into a new file: `~/Downloads/pull-secret.txt`
6. Double-click `openshift-local.pkg` and follow the installer prompts
7. Verify:

```bash
crc version
# CRC version: 2.49.0+e843be
# OpenShift version: 4.18.2
```

If `crc` is not found:

```bash
export PATH="$PATH:/usr/local/bin"
echo 'export PATH="$PATH:/usr/local/bin"' >> ~/.zshrc
```

---

## 5. Configure CRC resources

Your M3 Pro Max has 48 GB RAM — allocate generously to CRC. These settings give
CRC 20 GB RAM, 10 CPU cores, and 80 GB disk while leaving plenty for Ollama and macOS.

```bash
crc config set memory 20480          # 20 GB RAM
crc config set cpus 10               # 10 CPU cores
crc config set disk-size 80          # 80 GB disk
crc config set consent-telemetry no
crc config set host-network-access true   # lets pods reach Ollama on host
crc config set pull-secret-file ~/Downloads/pull-secret.txt

# Confirm
crc config view
```

---

## 6. Run crc setup

Downloads the OpenShift bundle (~4.25 GB) and configures the system.
Takes 5–15 minutes depending on your connection speed.

```bash
crc setup
```

Expected output includes:

```
INFO Downloading bundle: crc_vfkit_4.18.2_arm64.crcbundle  4.25 GiB
INFO Checking if vfkit is installed
INFO Configuring local DNS for *.crc.testing
INFO Setup is complete, you can now run 'crc start'
```

---

## 7. Start the cluster

First start takes 10–20 minutes. Save the credentials printed at the end.

```bash
crc start
```

Expected output at the end:

```
Started the OpenShift cluster.

The server is accessible via web console at:
  https://console-openshift-console.apps-crc.testing

Log in as administrator:
  Username: kubeadmin
  Password: <random-password>    ← SAVE THIS

Log in as user:
  Username: developer
  Password: developer
```

Add `oc` to your PATH:

```bash
eval $(crc oc-env)
echo 'eval $(crc oc-env)' >> ~/.zshrc
source ~/.zshrc
```

Verify the cluster is running:

```bash
crc status
# CRC VM:       Running
# OpenShift:    Running (v4.18.2)
```

---

## 8. Log in and create the project

```bash
# Log in as kubeadmin
oc login -u kubeadmin https://api.crc.testing:6443
# Enter the password from crc start output
# Or retrieve it: crc console --credentials

# Create the project (namespace)
oc new-project ai-log-analyzer

# Enable the internal image registry
oc patch configs.imageregistry.operator.openshift.io cluster \
  --type merge \
  --patch '{"spec":{"managementState":"Managed","storage":{"emptyDir":{}}}}'

# Expose the registry route
oc patch configs.imageregistry.operator.openshift.io/cluster \
  --patch='{"spec":{"defaultRoute":true}}' --type=merge

# Wait a few seconds for the route to appear
sleep 10

# Grant image pull permissions
oc policy add-role-to-user \
  system:image-puller system:serviceaccount:ai-log-analyzer:default \
  -n ai-log-analyzer
```

---

## 9. Install Podman

CRC no longer ships podman-remote. Install it via Homebrew:

```bash
brew install podman
podman machine init
podman machine start
podman version
```

Fix the Docker certs directory permissions if needed (from a previous Docker attempt):

```bash
sudo rm -rf /etc/docker/certs.d/default-route-openshift-image-registry.apps-crc.testing
```

Log in to the internal registry:

```bash
eval $(crc oc-env)

podman login \
  -u kubeadmin \
  -p $(oc whoami -t) \
  default-route-openshift-image-registry.apps-crc.testing \
  --tls-verify=false
# Should print: Login Succeeded!
```

---

## 10. Build and push the image

```bash
cd ai-log-analyzer-openshift

# Build
podman build -t ai-log-analyzer:latest .

# Tag for the internal registry
podman tag ai-log-analyzer:latest \
  default-route-openshift-image-registry.apps-crc.testing/ai-log-analyzer/ai-log-analyzer:latest

# Push
podman push \
  default-route-openshift-image-registry.apps-crc.testing/ai-log-analyzer/ai-log-analyzer:latest \
  --tls-verify=false
```

---

## 11. Deploy to OpenShift

```bash
cd openshift

oc apply -f configmap.yaml
oc apply -f pvc.yaml
oc apply -f deployment.yaml
oc apply -f service.yaml
oc apply -f route.yaml
```

Watch the pod come up:

```bash
oc get pods -w
# Wait for: READY = 1/1   STATUS = Running
```

Check the logs:

```bash
oc logs -f deployment/ai-log-analyzer
# Should show:
# ChromaDB ready — 0 incident(s) indexed
# Seeding knowledge base with curated incidents...
# Seeded 1/12 ... 12/12
# Knowledge base ready — 12 incidents indexed
# Ready — visit http://localhost:8000
# Application startup complete.
```

---

## 12. Verify and access the app

```bash
# Get the app URL
oc get route ai-log-analyzer
# HOST column shows: ai-log-analyzer-ai-log-analyzer.apps-crc.testing

# Open the dashboard
URL=$(oc get route ai-log-analyzer -o jsonpath='{.spec.host}')
open https://$URL

# Check health endpoint
curl -k https://$URL/health
# Returns: {"status":"ok","llm_model":"llama3.1:8b","incidents_indexed":12}
```

Open the OpenShift web console:

```bash
crc console
# Login: kubeadmin / <your password>
# Navigate to: Workloads > Pods > ai-log-analyzer project
```

---

## 13. Daily operations

### Start everything

```bash
# Start Ollama (all interfaces)
lsof -ti :11434 | xargs kill -9 2>/dev/null || true
OLLAMA_HOST=0.0.0.0 ollama serve &

# Start OpenShift cluster (~2 min)
crc start
eval $(crc oc-env)
```

### Stop everything

```bash
crc stop
kill $(lsof -ti :11434) 2>/dev/null || true
```

### Redeploy after code changes

```bash
podman build -t ai-log-analyzer:latest .

podman tag ai-log-analyzer:latest \
  default-route-openshift-image-registry.apps-crc.testing/ai-log-analyzer/ai-log-analyzer:latest

podman push \
  default-route-openshift-image-registry.apps-crc.testing/ai-log-analyzer/ai-log-analyzer:latest \
  --tls-verify=false

oc rollout restart deployment/ai-log-analyzer
oc rollout status deployment/ai-log-analyzer
```

### Useful oc commands

```bash
oc get pods -n ai-log-analyzer               # list pods
oc logs -f deployment/ai-log-analyzer        # stream logs
oc describe pod <pod-name>                   # debug a pod
oc exec -it <pod-name> -- /bin/bash          # shell into pod
oc get events --sort-by=.metadata.creationTimestamp  # recent events
oc adm top pods -n ai-log-analyzer           # resource usage
oc scale deployment/ai-log-analyzer --replicas=2     # scale up
```

### Add incidents to the knowledge base

```bash
URL=$(oc get route ai-log-analyzer -o jsonpath='{.spec.host}')

curl -X POST https://$URL/incidents \
  -H "Content-Type: application/json" \
  -k -d '{
    "log_snippet": "paste your log here",
    "root_cause": "what caused the failure",
    "fix_applied": "what fixed it"
  }'
```

---

## 14. Troubleshooting

### Pod is in CrashLoopBackOff

```bash
oc logs deployment/ai-log-analyzer --previous
```

Most common causes:

**403 Forbidden from Ollama** — Ollama is bound to localhost only:
```bash
lsof -ti :11434 | xargs kill -9
OLLAMA_HOST=0.0.0.0 ollama serve &
oc rollout restart deployment/ai-log-analyzer
```

**ChromaDB write error** — PVC permission issue. Rebuild and repush the image
(the Dockerfile includes `chmod -R g+rwX /app` to handle OpenShift random UIDs).

### podman login permission denied

```bash
sudo rm -rf /etc/docker/certs.d/default-route-openshift-image-registry.apps-crc.testing
# Then retry the podman login command
```

### Port 11434 already in use after brew services stop

```bash
lsof -ti :11434 | xargs kill -9
```

### CRC cluster stuck or not starting

```bash
crc stop
crc start
# If still broken:
crc delete
crc setup
crc start
```

### Image pull error in pod (ImagePullBackOff)

```bash
# Re-login and re-push
eval $(crc oc-env)
podman login -u kubeadmin -p $(oc whoami -t) \
  default-route-openshift-image-registry.apps-crc.testing --tls-verify=false
podman push \
  default-route-openshift-image-registry.apps-crc.testing/ai-log-analyzer/ai-log-analyzer:latest \
  --tls-verify=false
oc rollout restart deployment/ai-log-analyzer
```
