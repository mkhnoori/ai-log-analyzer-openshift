import httpx
from loguru import logger
from config import settings


class Embedder:
    def __init__(self):
        self.url = f"{settings.ollama_base_url}/api/embeddings"
        self.model = settings.embed_model

    async def embed(self, text: str) -> list[float]:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(self.url, json={"model": self.model, "prompt": text})
            r.raise_for_status()
            return r.json()["embedding"]

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        results = []
        for text in texts:
            results.append(await self.embed(text))
        return results
