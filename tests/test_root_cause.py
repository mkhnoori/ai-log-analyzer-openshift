"""Tests for the rule-based root cause detector / fallback engine."""
import pytest
from datetime import datetime, timezone
from services.root_cause import RootCauseDetector
from models.schemas import LogEntry, LogChunk


def make_chunk(content: str) -> LogChunk:
    entry = LogEntry(
        source="jenkins",
        build_id="test-001",
        raw_log=content,
        timestamp=datetime.now(timezone.utc),
    )
    return LogChunk(
        chunk_id="test-chunk",
        log_entry=entry,
        content=content,
        token_count=len(content.split()),
        chunk_index=0,
    )


@pytest.fixture
def detector():
    return RootCauseDetector()


class TestFallbackRules:
    def test_oom_detected(self, detector):
        chunk = make_chunk("java.lang.OutOfMemoryError: Java heap space")
        llm = {"root_cause": "unknown", "confidence": 0.2, "fix_suggestion": "",
               "severity": "medium", "causal_chain": [], "evidence_steps": [],
               "fix_steps": [], "prevention": "", "docs_links": []}
        result = detector.validate_and_enrich(llm, chunk, [], 100)
        assert "memory" in result.root_cause.lower() or "heap" in result.root_cause.lower()
        assert result.severity == "critical"

    def test_connection_refused_detected(self, detector):
        chunk = make_chunk("ERROR: ECONNREFUSED 127.0.0.1:5432")
        llm = {"root_cause": "x", "confidence": 0.1, "fix_suggestion": "",
               "severity": "low", "causal_chain": [], "evidence_steps": [],
               "fix_steps": [], "prevention": "", "docs_links": []}
        result = detector.validate_and_enrich(llm, chunk, [], 100)
        assert result.severity in ("high", "critical")

    def test_disk_full_detected(self, detector):
        chunk = make_chunk("OSError: [Errno 28] No space left on device")
        llm = {"root_cause": "x", "confidence": 0.1, "fix_suggestion": "",
               "severity": "low", "causal_chain": [], "evidence_steps": [],
               "fix_steps": [], "prevention": "", "docs_links": []}
        result = detector.validate_and_enrich(llm, chunk, [], 100)
        assert result.severity == "critical"

    def test_high_confidence_llm_not_overridden(self, detector):
        chunk = make_chunk("some generic error")
        llm = {"root_cause": "custom llm root cause", "confidence": 0.92,
               "fix_suggestion": "do x", "severity": "medium", "causal_chain": [],
               "evidence_steps": [], "fix_steps": ["Step 1: do x"],
               "prevention": "", "docs_links": []}
        result = detector.validate_and_enrich(llm, chunk, [], 100)
        assert result.root_cause == "custom llm root cause"
        assert result.confidence == 0.92

    def test_high_similarity_boosts_confidence(self, detector):
        from models.schemas import RetrievedIncident
        chunk = make_chunk("npm ERR! ERESOLVE peer dep conflict")
        llm = {"root_cause": "npm conflict", "confidence": 0.70,
               "fix_suggestion": "fix", "severity": "medium", "causal_chain": [],
               "evidence_steps": [], "fix_steps": [], "prevention": "", "docs_links": []}
        similar = [
            RetrievedIncident(
                incident_id="x", log_snippet="...", root_cause="npm conflict",
                fix_applied="--legacy-peer-deps", confidence=1.0,
                similarity_score=0.95,
            )
        ]
        result = detector.validate_and_enrich(llm, chunk, similar, 100)
        assert result.confidence > 0.70
