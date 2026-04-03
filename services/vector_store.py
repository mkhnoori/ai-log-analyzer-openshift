import chromadb
from chromadb.config import Settings as CS
from loguru import logger
from config import settings
from models.schemas import RetrievedIncident
from typing import Optional


class VectorStore:
    def __init__(self):
        self.client = chromadb.PersistentClient(
            path=settings.chroma_persist_dir,
            settings=CS(anonymized_telemetry=False),
        )
        self.col = self.client.get_or_create_collection(
            name=settings.chroma_collection,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(f"ChromaDB ready — {self.col.count()} incident(s) indexed")

    def add_incident(
        self,
        incident_id: str,
        embedding: list[float],
        log_snippet: str,
        root_cause: str,
        fix_applied: str,
        confidence: float = 1.0,
        metadata: Optional[dict] = None,
    ):
        meta = {
            "root_cause": root_cause,
            "fix_applied": fix_applied,
            "confidence": str(confidence),
            **(metadata or {}),
        }
        self.col.upsert(
            ids=[incident_id],
            embeddings=[embedding],
            documents=[log_snippet],
            metadatas=[meta],
        )

    def query(self, embedding: list[float], top_k: int = 5) -> list[RetrievedIncident]:
        if self.col.count() == 0:
            return []
        k = min(top_k, self.col.count())
        res = self.col.query(
            query_embeddings=[embedding],
            n_results=k,
            include=["documents", "metadatas", "distances"],
        )
        out = []
        for i, doc_id in enumerate(res["ids"][0]):
            sim = 1.0 - res["distances"][0][i]
            if sim < settings.rag_min_similarity:
                continue
            meta = res["metadatas"][0][i]
            out.append(RetrievedIncident(
                incident_id=doc_id,
                log_snippet=res["documents"][0][i],
                root_cause=meta.get("root_cause", ""),
                fix_applied=meta.get("fix_applied", ""),
                confidence=float(meta.get("confidence", 1.0)),
                similarity_score=round(sim, 4),
            ))
        return out
