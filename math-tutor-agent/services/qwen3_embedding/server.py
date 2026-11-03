from __future__ import annotations

import os
from threading import Lock
from time import perf_counter
from typing import Literal

import torch
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from sentence_transformers import SentenceTransformer


MODEL_ID = os.getenv("QWEN_EMBEDDING_MODEL", "Qwen/Qwen3-Embedding-0.6B")
DIMENSIONS = int(os.getenv("QWEN_EMBEDDING_DIMENSIONS", "1024"))
MAX_BATCH_SIZE = int(os.getenv("QWEN_EMBEDDING_MAX_BATCH_SIZE", "32"))
QUERY_INSTRUCTION = os.getenv(
    "QWEN_EMBEDDING_QUERY_INSTRUCTION",
    "Given a math learning query, retrieve relevant textbook definitions, examples, "
    "problems, solution structures, and teaching guidance.",
)
DEVICE = "mps" if torch.backends.mps.is_available() else "cpu"


class EmbeddingRequest(BaseModel):
    """中文：定义“嵌入·请求”类，封装该职责相关的数据与行为。
    English: Defines the embedding request class and encapsulates data and behavior for that responsibility.
    """
    model: str
    input: str | list[str]
    dimensions: int | None = Field(default=None, ge=32, le=1024)
    encoding_format: Literal["float"] = "float"
    input_type: Literal["query", "document"] = "document"


class ModelState:
    """中文：定义“模型·state”类，封装该职责相关的数据与行为。
    English: Defines the model state class and encapsulates data and behavior for that responsibility.
    """
    def __init__(self) -> None:
        """中文：初始化当前对象及其依赖。
        English: Initializes the current object and its dependencies.
        """
        self.lock = Lock()
        self.model = SentenceTransformer(
            MODEL_ID,
            device=DEVICE,
            trust_remote_code=True,
            truncate_dim=DIMENSIONS,
        )
        self.model.encode(
            ["数学知识检索服务启动检查。"],
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )

    def encode(self, texts: list[str], input_type: str, dimensions: int) -> list[list[float]]:
        """中文：处理“encode”相关操作。
        English: Handles the encode operation.
        """
        prepared = (
            [f"Instruct: {QUERY_INSTRUCTION}\nQuery: {text}" for text in texts]
            if input_type == "query"
            else texts
        )
        with self.lock:
            vectors = self.model.encode(
                prepared,
                batch_size=min(MAX_BATCH_SIZE, len(prepared)),
                normalize_embeddings=True,
                convert_to_numpy=True,
                show_progress_bar=False,
            )
        return [row[:dimensions].astype(float).tolist() for row in vectors]


app = FastAPI(title="Qwen3 Embedding", version="1.0.0")
state: ModelState | None = None


@app.on_event("startup")
def load_model() -> None:
    """中文：处理“加载·模型”相关操作。
    English: Handles the load model operation.
    """
    global state
    state = ModelState()


@app.get("/health")
def health() -> dict:
    """中文：处理“健康状态”相关操作。
    English: Handles the health operation.
    """
    return {
        "status": "ready" if state is not None else "loading",
        "model": MODEL_ID,
        "dimensions": DIMENSIONS,
        "device": DEVICE,
    }


def model_catalog() -> dict:
    """中文：处理“模型·catalog”相关操作。
    English: Handles the model catalog operation.
    """
    return {
        "object": "list",
        "data": [{
            "id": MODEL_ID,
            "object": "model",
            "owned_by": "Qwen",
        }],
    }


@app.get("/models")
@app.get("/v1/models")
def models() -> dict:
    """中文：处理“models”相关操作。
    English: Handles the models operation.
    """
    return model_catalog()


@app.post("/embeddings")
@app.post("/v1/embeddings")
def embeddings(request: EmbeddingRequest) -> dict:
    """中文：处理“embeddings”相关操作。
    English: Handles the embeddings operation.
    """
    if state is None:
        raise HTTPException(status_code=503, detail="model_loading")
    if request.model not in {MODEL_ID, "qwen3-embedding-0.6b"}:
        raise HTTPException(status_code=404, detail="model_not_found")
    texts = [request.input] if isinstance(request.input, str) else request.input
    if not texts or len(texts) > MAX_BATCH_SIZE:
        raise HTTPException(status_code=400, detail="invalid_batch_size")
    if any(not text.strip() for text in texts):
        raise HTTPException(status_code=400, detail="empty_input")
    dimensions = request.dimensions or DIMENSIONS
    if dimensions > DIMENSIONS:
        raise HTTPException(status_code=400, detail="dimensions_exceed_model_limit")
    started = perf_counter()
    vectors = state.encode(texts, request.input_type, dimensions)
    elapsed_ms = round((perf_counter() - started) * 1000)
    token_estimate = sum(max(1, len(text) // 3) for text in texts)
    return {
        "object": "list",
        "model": MODEL_ID,
        "data": [
            {"object": "embedding", "index": index, "embedding": vector}
            for index, vector in enumerate(vectors)
        ],
        "usage": {
            "prompt_tokens": token_estimate,
            "total_tokens": token_estimate,
        },
        "service": {"device": DEVICE, "elapsed_ms": elapsed_ms},
    }

