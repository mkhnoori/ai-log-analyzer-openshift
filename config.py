from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    ollama_base_url: str = "http://localhost:11434"
    llm_model: str = "llama3.1:8b"
    embed_model: str = "nomic-embed-text"
    chroma_persist_dir: str = "./data/chroma"
    chroma_collection: str = "log_incidents"
    chunk_size: int = 512
    chunk_overlap: int = 64
    rag_top_k: int = 5
    rag_min_similarity: float = 0.72
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    low_confidence_threshold: float = 0.6

    class Config:
        env_file = ".env"


settings = Settings()
