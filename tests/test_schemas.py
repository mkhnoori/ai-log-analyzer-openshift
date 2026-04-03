"""Tests for Pydantic schemas — validates serialisation and field contracts."""
import pytest
from pydantic import ValidationError
from models.schemas import (
    AnalysisResult,
    FeedbackRequest,
    LogEntry,
    RetrievedIncident,
    AddIncidentRequest,
)


class TestAnalysisResult:
    def _base(self, **kw):
        defaults = dict(
            root_cause="npm peer dependency conflict",
            confidence=0.85,
            fix_suggestion="Run npm install --legacy-peer-deps",
            fix_steps=["Step 1: Run npm install --legacy-peer-deps"],
            evidence_steps=["npm ERR! ERESOLVE"],
            similar_incidents=[],
            causal_chain=["react version mismatch", "npm ERESOLVE", "build failed"],
            severity="medium",
            analysis_time_ms=1234,
        )
        defaults.update(kw)
        return AnalysisResult(**defaults)

    def test_valid_result_parses(self):
        r = self._base()
        assert r.root_cause == "npm peer dependency conflict"
        assert r.confidence == 0.85

    def test_incident_id_is_optional_and_defaults_none(self):
        r = self._base()
        assert r.incident_id is None

    def test_incident_id_can_be_set(self):
        r = self._base(incident_id="abc123")
        assert r.incident_id == "abc123"

    def test_confidence_rejects_above_one(self):
        with pytest.raises(ValidationError):
            self._base(confidence=1.5)

    def test_confidence_rejects_below_zero(self):
        with pytest.raises(ValidationError):
            self._base(confidence=-0.1)

    def test_fix_steps_defaults_to_empty_list(self):
        r = self._base(fix_steps=[])
        assert r.fix_steps == []

    def test_prevention_defaults_to_empty_string(self):
        r = self._base()
        assert r.prevention == ""

    def test_docs_links_defaults_empty(self):
        r = self._base()
        assert r.docs_links == []

    def test_serialise_includes_incident_id(self):
        r = self._base(incident_id="xyz789")
        d = r.model_dump()
        assert "incident_id" in d
        assert d["incident_id"] == "xyz789"


class TestFeedbackRequest:
    def test_valid_feedback(self):
        f = FeedbackRequest(incident_id="abc", fix_worked=True, rating=4)
        assert f.rating == 4
        assert f.fix_worked is True

    def test_rating_below_range_rejected(self):
        with pytest.raises(ValidationError):
            FeedbackRequest(incident_id="abc", fix_worked=True, rating=0)

    def test_rating_above_range_rejected(self):
        with pytest.raises(ValidationError):
            FeedbackRequest(incident_id="abc", fix_worked=True, rating=6)

    def test_all_optional_fields_default_none(self):
        f = FeedbackRequest(incident_id="abc", fix_worked=False, rating=2)
        assert f.log_snippet is None
        assert f.correct_root_cause is None
        assert f.notes is None

    def test_source_defaults_to_unknown(self):
        f = FeedbackRequest(incident_id="abc", fix_worked=True, rating=3)
        assert f.source == "unknown"


class TestLogEntry:
    def test_minimal_entry(self):
        e = LogEntry(source="jenkins", raw_log="build failed")
        assert e.source == "jenkins"
        assert e.build_id is None

    def test_timestamp_auto_set(self):
        e = LogEntry(source="gitlab", raw_log="error")
        assert e.timestamp is not None


class TestAddIncidentRequest:
    def test_all_fields_required(self):
        with pytest.raises(ValidationError):
            AddIncidentRequest(log_snippet="x", root_cause="y")  # missing fix_applied

    def test_valid_request(self):
        r = AddIncidentRequest(
            log_snippet="npm ERR! ERESOLVE",
            root_cause="peer dep conflict",
            fix_applied="npm install --legacy-peer-deps",
        )
        assert r.fix_applied == "npm install --legacy-peer-deps"
