"""Tests for the log parser — no external services needed."""
import pytest
from datetime import datetime, timezone
from services.parser import LogParser
from models.schemas import LogEntry


def make_entry(raw: str, source: str = "jenkins") -> LogEntry:
    return LogEntry(
        source=source,
        build_id="test-001",
        raw_log=raw,
        timestamp=datetime.now(timezone.utc),
    )


@pytest.fixture
def parser():
    return LogParser(chunk_size=512, chunk_overlap=64)


class TestChunking:
    def test_empty_log_returns_no_chunks(self, parser):
        entry = make_entry("   \n  \n  ")
        chunks = parser.chunk_log(entry)
        assert chunks == []

    def test_short_log_returns_one_chunk(self, parser):
        entry = make_entry("ERROR: build failed\nexit code 1")
        chunks = parser.chunk_log(entry)
        assert len(chunks) == 1
        assert "ERROR" in chunks[0].content

    def test_chunk_ids_are_unique(self, parser):
        entry = make_entry("\n".join([f"log line {i}" for i in range(200)]))
        chunks = parser.chunk_log(entry)
        ids = [c.chunk_id for c in chunks]
        assert len(ids) == len(set(ids))

    def test_noise_lines_are_stripped(self, parser):
        raw = "real error line\n" + ("=" * 40) + "\nDownloading [====>  ] 50%\nanother real line"
        entry = make_entry(raw)
        chunks = parser.chunk_log(entry)
        full = " ".join(c.content for c in chunks)
        assert "real error line" in full
        assert "another real line" in full
        assert "Downloading" not in full

    def test_chunk_index_is_sequential(self, parser):
        entry = make_entry("\n".join([f"line {i} with some extra text padding" for i in range(300)]))
        chunks = parser.chunk_log(entry)
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i


class TestSignalExtraction:
    def test_detects_error_lines(self, parser):
        text = "INFO: starting\nERROR: connection refused\nINFO: done"
        signals = parser.extract_signals(text)
        assert len(signals["error_lines"]) >= 1
        assert any("connection refused" in l for l in signals["error_lines"])

    def test_detects_exception_type(self, parser):
        text = "java.lang.OutOfMemoryError: Java heap space"
        signals = parser.extract_signals(text)
        assert "exception" in signals["error_types"] or "error" in signals["error_types"]

    def test_detects_exit_code(self, parser):
        text = "Build failed\nexit code 137\nDone"
        signals = parser.extract_signals(text)
        assert signals["exit_code"] == 137

    def test_no_exit_code_returns_none(self, parser):
        text = "all good\nno exit code here"
        signals = parser.extract_signals(text)
        assert signals["exit_code"] is None

    def test_detects_traceback(self, parser):
        text = "Traceback (most recent call last):\n  File 'app.py', line 42\nValueError: bad input"
        signals = parser.extract_signals(text)
        assert "traceback" in signals["error_types"]

    def test_detects_multiple_error_types(self, parser):
        text = "ERROR: something failed\nFATAL: cannot continue\nKilled"
        signals = parser.extract_signals(text)
        assert len(signals["error_types"]) >= 2
