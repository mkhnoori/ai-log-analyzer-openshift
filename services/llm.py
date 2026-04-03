import httpx
import json
import re
import time
from loguru import logger
from config import settings
from models.schemas import LogChunk, RetrievedIncident
from typing import List

SYSTEM_PROMPT = """You are a senior DevOps engineer and CI/CD expert specializing in diagnosing and fixing build and deployment failures.

Analyze the provided log and return ONLY a valid JSON object — no explanation, no markdown, no extra text outside the JSON.

Required JSON structure:
{
  "root_cause": "One sentence: the exact technical reason this failed, naming the specific command, service, file, or dependency involved.",
  "confidence": 0.85,
  "severity": "low|medium|high|critical",
  "fix_suggestion": "A clear 2-3 sentence summary of what needs to be done to fix this.",
  "fix_steps": [
    "Step 1: Exact command or action — e.g. 'Run: npm install --legacy-peer-deps'",
    "Step 2: Exact command or action — e.g. 'Commit the updated package-lock.json'",
    "Step 3: Exact command or action — e.g. 'Re-trigger the pipeline'"
  ],
  "evidence_steps": ["exact log line that proves the root cause"],
  "causal_chain": ["what first went wrong", "what that caused", "the final failure seen in the log"],
  "prevention": "One sentence: how to prevent this failure class in future pipelines.",
  "docs_links": ["optional: relevant official docs URL if applicable"]
}

Rules:
- fix_steps MUST be a list of 3 to 6 numbered, concrete, copy-paste-ready actions. Each step must start with an action verb (Run, Edit, Set, Add, Delete, Restart, Update, Check, etc.).
- fix_steps MUST include the actual commands to run — not vague advice like 'update your config'.
- root_cause MUST name something visible in the log (a specific error code, class name, file, service, or command).
- severity: low=warning only, medium=build failed, high=deploy/service failed, critical=data loss or security.
- Never return empty fix_steps. Always provide actionable steps even if confidence is low.
"""


def _build_prompt(chunk: LogChunk, retrieved: List[RetrievedIncident]) -> str:
    examples = ""
    if retrieved:
        examples = "\n\nSIMILAR RESOLVED INCIDENTS — use these fix_steps as inspiration:\n"
        for i, inc in enumerate(retrieved[:3], 1):
            examples += f"\n--- Past incident {i} (similarity {inc.similarity_score:.2f}) ---\n"
            examples += f"Log snippet: {inc.log_snippet[:300]}\n"
            examples += f"Root cause: {inc.root_cause}\n"
            examples += f"Fix applied: {inc.fix_applied}\n"

    m = chunk.log_entry
    return f"""SOURCE SYSTEM: {m.source}
BUILD ID: {m.build_id or 'unknown'}
STEP: {m.step_name or 'unknown'}
EXIT CODE: {m.exit_code if m.exit_code is not None else 'unknown'}
TIMESTAMP: {m.timestamp.isoformat()}

LOG OUTPUT:
{chunk.content}
{examples}

Analyze this log. Return the JSON with all fields including a detailed fix_steps list (3-6 concrete, numbered, copy-paste-ready steps).
JSON:"""


class LLMAnalyzer:
    def __init__(self):
        self.url = f"{settings.ollama_base_url}/api/generate"
        self.model = settings.llm_model

    async def analyze(self, chunk: LogChunk, retrieved: List[RetrievedIncident]) -> dict:
        prompt = _build_prompt(chunk, retrieved)
        t0 = time.time()

        async with httpx.AsyncClient(timeout=180) as client:
            r = await client.post(self.url, json={
                "model": self.model,
                "system": SYSTEM_PROMPT,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.1, "top_p": 0.9, "num_predict": 1500},
            })
            r.raise_for_status()

        elapsed = int((time.time() - t0) * 1000)
        raw = r.json().get("response", "{}")

        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            m = re.search(r'\{.*\}', raw, re.DOTALL)
            result = json.loads(m.group()) if m else {}

        result.setdefault("root_cause", "Could not determine root cause")
        result.setdefault("confidence", 0.3)
        result.setdefault("fix_suggestion", "Review the log output manually for error details.")
        result.setdefault("fix_steps", [
            "Step 1: Review the full log output above for the specific error message",
            "Step 2: Search for the error code or exception name in your project's documentation",
            "Step 3: Check recent commits or config changes that may have introduced this failure",
        ])
        result.setdefault("evidence_steps", [])
        result.setdefault("causal_chain", [])
        result.setdefault("severity", "medium")
        result.setdefault("prevention", "")
        result.setdefault("docs_links", [])
        result["analysis_time_ms"] = elapsed

        logger.info(
            f"LLM done in {elapsed}ms | confidence={result['confidence']:.0%} | "
            f"{result['root_cause'][:60]}"
        )
        return result
