import re
from models.schemas import AnalysisResult, RetrievedIncident, LogChunk
from typing import List

FALLBACK_RULES = [
    (
        r'OutOfMemoryError|OOM|out of memory|Cannot allocate memory',
        'Out of memory — JVM or process ran out of heap/RAM',
        'Increase memory: set -Xmx for Java, or increase Docker memory limit',
        'critical',
    ),
    (
        r'ECONNREFUSED|connection refused|cannot connect|Connection refused',
        'Service unreachable — dependent service is not running or wrong host/port',
        'Verify dependent service is started and the hostname/port in config is correct',
        'high',
    ),
    (
        r'permission denied|EACCES|Access Denied|403 Forbidden',
        'Permission denied — missing credentials or wrong file ownership',
        'Check API tokens, SSH keys, file permissions (chmod), or CI secret variables',
        'high',
    ),
    (
        r'No space left|ENOSPC|disk.*full|no space',
        'Disk full — runner or volume ran out of storage',
        'Clear Docker image cache (docker system prune), expand volume, or archive artifacts',
        'critical',
    ),
    (
        r'npm ERR!|yarn error|ERESOLVE|peer dep',
        'Package manager dependency conflict',
        'Run with --legacy-peer-deps or resolve version conflicts in package.json',
        'medium',
    ),
    (
        r'FileNotFoundError|ENOENT|No such file|not found.*file',
        'Missing file or directory',
        'Verify file paths in config and ensure all checkout/artifact steps ran successfully',
        'medium',
    ),
    (
        r'timed out|ETIMEDOUT|Timeout|deadline exceeded',
        'Operation timed out — network or service too slow',
        'Increase timeout value, check network connectivity, or optimize the slow operation',
        'medium',
    ),
    (
        r'FAILED.*test|test.*FAILED|AssertionError|assertion failed',
        'Test suite failure — one or more tests did not pass',
        'Check the test output for specific assertion failures and fix the underlying code',
        'medium',
    ),
    (
        r'SyntaxError|ParseError|unexpected token|invalid syntax',
        'Syntax error in code or config file',
        'Fix the syntax error at the indicated file and line number',
        'medium',
    ),
    (
        r'docker.*pull.*denied|pull access denied|unauthorized.*registry',
        'Docker registry authentication failure',
        'Refresh Docker credentials: re-run docker login and update CI secret variables',
        'high',
    ),
]


class RootCauseDetector:
    def _fallback(self, text: str) -> dict | None:
        for pattern, cause, fix, severity in FALLBACK_RULES:
            if re.search(pattern, text, re.IGNORECASE):
                return {
                    "root_cause": cause,
                    "confidence": 0.55,
                    "fix_suggestion": fix,
                    "severity": severity,
                    "causal_chain": [cause],
                    "evidence_steps": [],
                }
        return None

    def validate_and_enrich(
        self,
        llm_result: dict,
        chunk: LogChunk,
        retrieved: List[RetrievedIncident],
        elapsed_ms: int,
    ) -> AnalysisResult:
        confidence = float(llm_result.get("confidence", 0.5))

        # Fall back to rules when LLM confidence is low
        if confidence < 0.6:
            fb = self._fallback(chunk.content)
            if fb:
                llm_result.update({
                    k: fb[k]
                    for k in ["root_cause", "confidence", "fix_suggestion", "severity"]
                })
                if not llm_result.get("causal_chain"):
                    llm_result["causal_chain"] = fb["causal_chain"]

        # Boost confidence when a very similar past incident was found
        if retrieved and retrieved[0].similarity_score > 0.88:
            llm_result["confidence"] = min(
                float(llm_result.get("confidence", 0.5)) + 0.1, 0.99
            )

        return AnalysisResult(
            root_cause=llm_result.get("root_cause", "Unknown failure"),
            confidence=float(llm_result.get("confidence", 0.5)),
            fix_suggestion=llm_result.get("fix_suggestion", "Review logs manually"),
            fix_steps=llm_result.get("fix_steps", []),
            evidence_steps=llm_result.get("evidence_steps", []),
            similar_incidents=retrieved,
            causal_chain=llm_result.get("causal_chain", []),
            severity=llm_result.get("severity", "medium"),
            prevention=llm_result.get("prevention", ""),
            docs_links=llm_result.get("docs_links", []),
            analysis_time_ms=elapsed_ms,
        )
