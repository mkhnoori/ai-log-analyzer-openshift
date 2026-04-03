import time
import uuid
from contextlib import asynccontextmanager
from loguru import logger

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from config import settings
from models.schemas import (
    AnalysisRequest,
    AnalysisResult,
    FeedbackRequest,
    AddIncidentRequest,
)
from services.parser import LogParser
from services.embedder import Embedder
from services.vector_store import VectorStore
from services.llm import LLMAnalyzer
from services.root_cause import RootCauseDetector
from services.knowledge_base import seed_knowledge_base
from services.learning import process_feedback, get_learning_stats

parser   = LogParser(settings.chunk_size, settings.chunk_overlap)
embedder = Embedder()
store    = VectorStore()
llm      = LLMAnalyzer()
detector = RootCauseDetector()

# In-memory cache of recent analyses so feedback can reference them by ID
# key = incident_id, value = dict with log_snippet, root_cause, fix_steps
_recent_analyses: dict[str, dict] = {}
MAX_CACHE = 200


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting AI Log Analyzer...")
    await seed_knowledge_base(embedder, store)
    logger.success("Ready — visit http://localhost:8000")
    yield


app = FastAPI(title="AI Log Analyzer", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "llm_model": settings.llm_model,
        "embed_model": settings.embed_model,
        "incidents_indexed": store.col.count(),
    }


@app.post("/analyze", response_model=AnalysisResult)
async def analyze(request: AnalysisRequest):
    t0 = time.time()

    chunks = parser.chunk_log(request.log_entry)
    if not chunks:
        raise HTTPException(400, "Log is empty after cleaning")

    best, best_score = chunks[0], 0
    for c in chunks:
        sig = parser.extract_signals(c.content)
        score = len(sig["error_lines"]) + len(sig["error_types"]) * 2
        if score > best_score:
            best, best_score = c, score

    emb     = await embedder.embed(best.content)
    similar = store.query(emb, top_k=settings.rag_top_k)
    llm_out = await llm.analyze(best, similar)

    elapsed = int((time.time() - t0) * 1000)
    result  = detector.validate_and_enrich(llm_out, best, similar, elapsed)

    # Cache so feedback endpoint can look it up by incident_id
    incident_id = uuid.uuid4().hex[:12]
    _recent_analyses[incident_id] = {
        "log_snippet": best.content[:1000],
        "root_cause":  result.root_cause,
        "fix_applied": result.fix_suggestion,
        "source":      request.log_entry.source,
    }
    if len(_recent_analyses) > MAX_CACHE:
        oldest = next(iter(_recent_analyses))
        del _recent_analyses[oldest]

    # Attach incident_id directly on the result (field exists in schema)
    result.incident_id = incident_id

    logger.info(
        f"[{request.log_entry.source}] id={incident_id} "
        f"{result.root_cause[:60]} ({result.confidence:.0%})"
    )
    return result


@app.post("/feedback", summary="Submit feedback — confirmed fixes are auto-learned")
async def feedback(req: FeedbackRequest):
    # Try to look up cached analysis context
    cached = _recent_analyses.get(req.incident_id, {})

    log_snippet  = req.log_snippet  or cached.get("log_snippet", "")
    root_cause   = req.predicted_root_cause or cached.get("root_cause", "")
    fix_applied  = req.fix_applied  or cached.get("fix_applied", "")
    source       = req.source       or cached.get("source", "unknown")

    result = await process_feedback(
        embedder=embedder,
        store=store,
        incident_id=req.incident_id,
        log_snippet=log_snippet,
        root_cause=root_cause,
        fix_applied=fix_applied,
        fix_worked=req.fix_worked,
        correct_root_cause=req.correct_root_cause,
        rating=req.rating,
        notes=req.notes,
        source=source,
    )
    return result


@app.get("/learn/stats", summary="Learning statistics — what the model has learned")
async def learn_stats():
    return get_learning_stats(store)


@app.post("/incidents", summary="Manually add a resolved incident to the knowledge base")
async def add_incident(req: AddIncidentRequest):
    emb = await embedder.embed(req.log_snippet)
    iid = uuid.uuid4().hex[:8]
    store.add_incident(iid, emb, req.log_snippet, req.root_cause, req.fix_applied)
    return {"incident_id": iid, "total_indexed": store.col.count()}


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    with open("dashboard/index.html") as f:
        return f.read()
