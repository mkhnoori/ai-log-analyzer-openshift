import re
import hashlib
from loguru import logger
from models.schemas import LogEntry, LogChunk
from typing import List
import tiktoken

NOISE_PATTERNS = [
    r'^\s*[\.\-_=▇█]{6,}\s*$',
    r'Downloading.*?\[.*?%.*?\]',
    r'^\s*\d+%\|[█▉▊▋▌▍▎▏ ]+\|',
    r'Progress:\s+\d+/\d+',
]

ERROR_PATTERNS = [
    (r'(?i)\berror\b',       'error'),
    (r'(?i)\bexception\b',   'exception'),
    (r'(?i)\bfailed\b',      'failure'),
    (r'(?i)traceback',       'traceback'),
    (r'(?i)\bwarning\b',     'warning'),
    (r'(?i)\bfatal\b',       'fatal'),
    (r'(?i)\bkilled\b',      'killed'),
    (r'(?i)exit code [^0]',  'nonzero_exit'),
]


class LogParser:
    def __init__(self, chunk_size: int = 512, chunk_overlap: int = 64):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        try:
            self.enc = tiktoken.get_encoding("cl100k_base")
        except Exception:
            self.enc = None

    def _count_tokens(self, text: str) -> int:
        if self.enc:
            return len(self.enc.encode(text))
        return max(1, len(text.split()) * 4 // 3)

    def _clean(self, raw: str) -> str:
        lines = []
        for line in raw.splitlines():
            if line.strip() and not any(re.search(p, line) for p in NOISE_PATTERNS):
                lines.append(line)
        return "\n".join(lines)

    def chunk_log(self, log_entry: LogEntry) -> List[LogChunk]:
        cleaned = self._clean(log_entry.raw_log)
        lines = cleaned.splitlines()
        chunks, current, cur_tok, idx = [], [], 0, 0

        for line in lines:
            lt = self._count_tokens(line)
            if cur_tok + lt > self.chunk_size and current:
                text = "\n".join(current)
                cid = hashlib.md5(
                    f"{log_entry.build_id}:{idx}:{text[:40]}".encode()
                ).hexdigest()[:12]
                chunks.append(LogChunk(
                    chunk_id=cid, log_entry=log_entry,
                    content=text, token_count=cur_tok, chunk_index=idx,
                ))
                overlap, ov_tok = [], 0
                for line in reversed(current):
                    t = self._count_tokens(line)
                    if ov_tok + t <= self.chunk_overlap:
                        overlap.insert(0, line)
                        ov_tok += t
                    else:
                        break
                current, cur_tok, idx = overlap, ov_tok, idx + 1
            current.append(line)
            cur_tok += lt

        if current:
            text = "\n".join(current)
            cid = hashlib.md5(
                f"{log_entry.build_id}:{idx}:{text[:40]}".encode()
            ).hexdigest()[:12]
            chunks.append(LogChunk(
                chunk_id=cid, log_entry=log_entry,
                content=text, token_count=cur_tok, chunk_index=idx,
            ))

        logger.debug(f"Log split into {len(chunks)} chunk(s)")
        return chunks

    def extract_signals(self, text: str) -> dict:
        signals = {"error_lines": [], "error_types": set(), "exit_code": None}
        for line in text.splitlines():
            for pattern, etype in ERROR_PATTERNS:
                if re.search(pattern, line):
                    signals["error_lines"].append(line.strip())
                    signals["error_types"].add(etype)
                    break
            m = re.search(r'exit\s+code[:\s]+(\d+)', line, re.IGNORECASE)
            if m:
                signals["exit_code"] = int(m.group(1))
        signals["error_types"] = list(signals["error_types"])
        return signals
