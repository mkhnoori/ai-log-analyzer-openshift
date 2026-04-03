"""
Learning engine — closes the feedback loop.

When a user confirms a fix worked, this module:
  1. Stores the feedback to a persistent JSON journal (data/feedback.jsonl)
  2. Automatically promotes the confirmed incident into ChromaDB
     so future RAG queries benefit immediately
  3. Tracks learning stats (total confirmed, correction rate, top error types)
  4. Exposes those stats for the /learn/stats endpoint

The model "learns" in two complementary ways:
  - Immediate: every confirmed fix is embedded and added to the vector store,
    so the very next similar log gets it as a RAG example.
  - Batch: the feedback journal is a dataset that can be used to fine-tune
    the base LLM offline (not implemented here — requires a GPU training run).
"""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from loguru import logger
from services.embedder import Embedder
from services.vector_store import VectorStore

# Derive from the chroma dir so it always lands on the same PVC mount
def _feedback_file() -> Path:
    from config import settings
    return Path(settings.chroma_persist_dir).parent / "feedback.jsonl"


def _load_journal() -> list[dict]:
    path = _feedback_file()
    if not path.exists():
        return []
    entries = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return entries


def _append_journal(entry: dict):
    path = _feedback_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(entry) + "\n")


async def process_feedback(
    embedder: Embedder,
    store: VectorStore,
    incident_id: str,
    log_snippet: str,
    root_cause: str,
    fix_applied: str,
    fix_worked: bool,
    correct_root_cause: str | None,
    rating: int,
    notes: str | None,
    source: str = "unknown",
) -> dict:
    """
    Process one feedback submission.
    Returns a dict describing what action was taken.
    """
    ts = datetime.now(timezone.utc).isoformat()

    # Determine the best root cause and fix to store
    actual_root_cause = correct_root_cause if correct_root_cause else root_cause
    action = "logged"
    new_incident_id = None

    if fix_worked and rating >= 3 and log_snippet:
        # ── Promote to knowledge base ──────────────────────────────────────────
        # Embed the log snippet and upsert into ChromaDB.
        # Use the actual (possibly corrected) root cause and fix.
        try:
            emb = await embedder.embed(log_snippet)
            new_incident_id = f"learned_{uuid.uuid4().hex[:8]}"
            confidence = min(0.5 + (rating - 1) * 0.1, 0.99)  # rating 1-5 → 0.6-1.0

            store.add_incident(
                incident_id=new_incident_id,
                embedding=emb,
                log_snippet=log_snippet,
                root_cause=actual_root_cause,
                fix_applied=fix_applied,
                confidence=confidence,
                metadata={
                    "source": source,
                    "learned_from_feedback": "true",
                    "original_incident_id": incident_id,
                    "rating": str(rating),
                    "timestamp": ts,
                },
            )
            action = "promoted_to_kb"
            logger.success(
                f"[LEARN] Promoted incident {new_incident_id} to knowledge base "
                f"(rating={rating}, confidence={confidence:.0%})"
            )
        except Exception as e:
            logger.error(f"[LEARN] Failed to promote incident: {e}")
            action = "logged_promotion_failed"

    elif not fix_worked and correct_root_cause:
        # Fix didn't work AND user provided the correct cause — log as correction
        action = "correction_logged"
        logger.info(
            f"[LEARN] Correction recorded for {incident_id}: "
            f"'{root_cause}' → '{correct_root_cause}'"
        )

    else:
        logger.info(
            f"[LEARN] Feedback logged (fix_worked={fix_worked}, rating={rating}) "
            f"— not promoted (threshold: worked=True and rating>=3)"
        )

    # ── Always persist to journal ──────────────────────────────────────────────
    entry = {
        "ts": ts,
        "incident_id": incident_id,
        "new_incident_id": new_incident_id,
        "source": source,
        "root_cause": root_cause,
        "correct_root_cause": correct_root_cause,
        "fix_applied": fix_applied,
        "fix_worked": fix_worked,
        "rating": rating,
        "notes": notes,
        "action": action,
    }
    _append_journal(entry)

    return {
        "action": action,
        "new_incident_id": new_incident_id,
        "total_in_kb": store.col.count(),
        "message": _action_message(action, rating),
    }


def _action_message(action: str, rating: int) -> str:
    messages = {
        "promoted_to_kb": (
            f"Thank you! This fix (rating {rating}/5) has been added to the knowledge base. "
            "The model will now suggest this solution for similar failures."
        ),
        "correction_logged": (
            "Correction recorded. This will improve future diagnoses for similar logs."
        ),
        "logged": (
            "Feedback logged. To promote a fix to the knowledge base, "
            "confirm fix_worked=true with a rating of 3 or higher."
        ),
        "logged_promotion_failed": (
            "Feedback logged but could not be added to the knowledge base. "
            "The embedding service may be unavailable."
        ),
    }
    return messages.get(action, "Feedback received.")


def get_learning_stats(store: VectorStore) -> dict:
    """
    Returns learning statistics from the feedback journal and vector store.
    """
    entries = _load_journal()

    total          = len(entries)
    worked         = sum(1 for e in entries if e.get("fix_worked"))
    not_worked     = sum(1 for e in entries if not e.get("fix_worked"))
    promoted       = sum(1 for e in entries if e.get("action") == "promoted_to_kb")
    corrections    = sum(1 for e in entries if e.get("action") == "correction_logged")

    avg_rating = (
        round(sum(e.get("rating", 0) for e in entries) / total, 2)
        if total else 0.0
    )

    # Top sources
    source_counts: dict[str, int] = {}
    for e in entries:
        s = e.get("source", "unknown")
        source_counts[s] = source_counts.get(s, 0) + 1
    top_sources = sorted(source_counts.items(), key=lambda x: -x[1])[:5]

    # Recent 5 learned incidents
    recent = [
        {
            "incident_id": e.get("new_incident_id"),
            "root_cause": e.get("correct_root_cause") or e.get("root_cause", ""),
            "fix_applied": e.get("fix_applied", ""),
            "rating": e.get("rating"),
            "ts": e.get("ts"),
            "source": e.get("source"),
        }
        for e in reversed(entries)
        if e.get("action") == "promoted_to_kb"
    ][:5]

    # Vector store breakdown — count seeded vs learned
    total_in_kb = store.col.count()
    seeded      = max(0, total_in_kb - promoted)

    return {
        "total_feedback_received": total,
        "fixes_confirmed_working": worked,
        "fixes_not_working": not_worked,
        "incidents_learned": promoted,
        "corrections_recorded": corrections,
        "average_rating": avg_rating,
        "knowledge_base_total": total_in_kb,
        "knowledge_base_seeded": seeded,
        "knowledge_base_learned": promoted,
        "fix_success_rate": round(worked / total, 2) if total else 0.0,
        "top_sources": [{"source": s, "count": c} for s, c in top_sources],
        "recently_learned": recent,
    }
