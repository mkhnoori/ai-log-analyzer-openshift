# AI Log Analyzer

> A fully local AI system that analyzes CI/CD and build logs to identify root causes,
> suggest fixes, and learn from resolved incidents — deployed on OpenShift Local (CRC)
> with Ollama running natively on Apple Silicon.

![Python](https://img.shields.io/badge/Python-3.11-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green)
![OpenShift](https://img.shields.io/badge/OpenShift-4.18-red)
![Ollama](https://img.shields.io/badge/Ollama-llama3.1:8b-orange)
![ChromaDB](https://img.shields.io/badge/ChromaDB-0.5.18-purple)

---

## What it does

- **Analyzes** logs from Jenkins, GitLab CI/CD, GitHub Actions, Kubernetes, CircleCI, and any custom source
- **Identifies root causes** using a fine-tuned LLM with RAG retrieval against a knowledge base of resolved incidents
- **Suggests fixes** with concrete, actionable steps
- **Learns** from every resolved incident — confirmed fixes are stored in the vector DB and immediately improve future analyses
- **Runs 100% locally** — no API keys, no cloud, no data leaves your machine

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Your Mac (M3 Pro Max)                      │
│                                                               │
│  ┌─────────────────┐        ┌──────────────────────────────┐ │
│  │  Ollama (Metal) │        │   OpenShift Local (CRC VM)   │ │
│  │                 │        │                              │ │
│  │  llama3.1:8b    │◄──────►│   ai-log-analyzer pod        │ │
│  │  nomic-embed    │        │   ├── FastAPI server          │ │
│  │                 │        │   ├── ChromaDB (PVC)          │ │
│  │  0.0.0.0:11434  │        │   └── Log parser + RAG        │ │
│  └─────────────────┘        │                              │ │
│                              │   Route (HTTPS)              │ │
│                              │   *.apps-crc.testing         │ │
│                              └──────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

**Key design decision:** Ollama stays on the Mac host and uses the M3 Metal GPU directly.
The app pod reaches it via `host.crc.testing:11434`. This gives full GPU acceleration
without needing to pass through the VM.

---

## Tech stack

| Layer | Technology |
|-------|-----------|
| LLM inference | Ollama + Llama 3.1 8B (Metal-accelerated) |
| Embeddings | nomic-embed-text via Ollama |
| Vector store | ChromaDB (persistent via OpenShift PVC) |
| API server | FastAPI + Uvicorn |
| Container platform | Red Hat OpenShift Local (CRC) 4.18 |
| Container runtime | Podman |
| Frontend | Vanilla HTML/JS dashboard |

---

## Project structure

```
ai-log-analyzer-openshift/
├── Dockerfile                    # Multi-stage, non-root, OpenShift-compatible
├── README.md                     # This file
├── DEPLOYMENT.md                 # Full step-by-step deployment guide
├── requirements.txt              # Python dependencies
├── setup.py                      # Automated local setup script
├── config.py                     # Settings loaded from .env / ConfigMap
├── main.py                       # FastAPI app + all routes
├── .env                          # Local development config
├── .gitignore
│
├── models/
│   └── schemas.py                # Pydantic request/response models
│
├── services/
│   ├── parser.py                 # Log chunking + signal extraction
│   ├── embedder.py               # Ollama embedding client
│   ├── vector_store.py           # ChromaDB wrapper
│   ├── llm.py                    # LLM inference + prompt builder
│   ├── root_cause.py             # Validation + fallback rule engine
│   └── knowledge_base.py        # Seed data + KB management
│
├── dashboard/
│   └── index.html                # Web UI
│
├── data/
│   ├── chroma/                   # ChromaDB persistence (gitignored)
│   └── sample_logs/              # Drop .log files here for bulk testing
│
└── openshift/
    ├── configmap.yaml            # App configuration
    ├── pvc.yaml                  # 5Gi persistent volume for ChromaDB
    ├── deployment.yaml           # Deployment with probes + resource limits
    ├── service.yaml              # ClusterIP service
    ├── route.yaml                # HTTPS route (*.apps-crc.testing)
    ├── deploy.sh                 # One-shot build + push + deploy script
    └── ollama-host-config.sh     # Configure Ollama to listen on 0.0.0.0
```

---

## Quick start

### Prerequisites

- macOS with Apple Silicon (M1/M2/M3)
- 48 GB RAM recommended (20 GB allocated to CRC, rest for Mac + Ollama)
- 60 GB free disk space
- [Homebrew](https://brew.sh)
- [Podman](https://podman.io) for building/pushing images
- Free [Red Hat account](https://console.redhat.com) (for CRC pull secret)

### Option A — Local run without OpenShift

```bash
git clone https://github.com/mkhnoori/ai-log-analyzer-openshift.git
cd ai-log-analyzer-openshift
python setup.py
```

### Option B — Full OpenShift deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for the complete step-by-step guide.

**Short version:**

```bash
# 1. Install and start Ollama
brew install ollama
brew services start ollama
ollama pull llama3.1:8b
ollama pull nomic-embed-text

# 2. Configure Ollama to accept connections from the CRC VM
chmod +x openshift/ollama-host-config.sh
./openshift/ollama-host-config.sh

# 3. Install OpenShift Local and start the cluster
# (see DEPLOYMENT.md for full instructions)

# 4. One-shot deploy
chmod +x openshift/deploy.sh
./openshift/deploy.sh
```

---

## API reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/analyze` | Analyze a log — returns root cause, fix, confidence |
| `POST` | `/incidents` | Add a resolved incident to the knowledge base |
| `POST` | `/feedback` | Submit feedback on an analysis result |
| `GET` | `/health` | Server status + model info + incident count |
| `GET` | `/` | Open the web dashboard |

### Analyze a log

```bash
curl -X POST https://ai-log-analyzer-ai-log-analyzer.apps-crc.testing/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "log_entry": {
      "source": "jenkins",
      "build_id": "build-001",
      "exit_code": 1,
      "raw_log": "npm ERR! code ERESOLVE\nnpm ERR! ERESOLVE unable to resolve dependency tree"
    }
  }'
```

### Add a resolved incident

```bash
curl -X POST https://ai-log-analyzer-ai-log-analyzer.apps-crc.testing/incidents \
  -H "Content-Type: application/json" \
  -d '{
    "log_snippet": "your log snippet here",
    "root_cause": "what caused it",
    "fix_applied": "what fixed it"
  }'
```

---

## How the AI pipeline works

```
Raw log
  │
  ▼
Log Parser         — cleans noise, splits into 512-token chunks with 64-token overlap
  │
  ▼
Embedder           — encodes chunks to 384-dim vectors via nomic-embed-text
  │
  ▼
Vector Store       — finds top-5 most similar historical incidents (cosine similarity)
  │
  ▼
LLM Analyzer       — builds RAG prompt (system + log + few-shot examples) → Llama 3.1 8B
  │
  ▼
Root Cause Detector — validates output, applies rule-based fallback if confidence < 0.6
  │
  ▼
AnalysisResult     — root_cause, confidence, fix_suggestion, evidence_steps, causal_chain
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Pod `CrashLoopBackOff` | Run `oc logs deployment/ai-log-analyzer` |
| `403 Forbidden` from Ollama | Ollama bound to localhost — run `lsof -ti :11434 \| xargs kill -9` then `OLLAMA_HOST=0.0.0.0 ollama serve &` |
| `x509: certificate` on docker push | Use podman with `--tls-verify=false` |
| Port 11434 already in use | `lsof -ti :11434 \| xargs kill -9` |
| CRC won't start | `crc stop && crc start` or `crc delete && crc setup && crc start` |
| ChromaDB permission error | Dockerfile sets `chmod -R g+rwX /app` — rebuild and repush image |

---

## Daily workflow

```bash
# Morning — start everything
lsof -ti :11434 | xargs kill -9 2>/dev/null; OLLAMA_HOST=0.0.0.0 ollama serve &
crc start
eval $(crc oc-env)

# Evening — shut down
crc stop
kill $(lsof -ti :11434) 2>/dev/null

# After code changes — redeploy
podman build -t ai-log-analyzer:latest .
podman tag ai-log-analyzer:latest \
  default-route-openshift-image-registry.apps-crc.testing/ai-log-analyzer/ai-log-analyzer:latest
podman push \
  default-route-openshift-image-registry.apps-crc.testing/ai-log-analyzer/ai-log-analyzer:latest \
  --tls-verify=false
oc rollout restart deployment/ai-log-analyzer
```

---

## License

MIT
