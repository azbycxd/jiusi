"""【生产化扩展设计，当前真实项目未实现】Dense Retrieval 协议，不加载真实模型。"""
from typing import Protocol, Sequence
from .retriever import RetrievalResult


class EmbeddingModel(Protocol):
    def embed_query(self, text: str) -> Sequence[float]: ...
    def embed_documents(self, texts: Sequence[str]) -> Sequence[Sequence[float]]: ...


class EmbeddingRetriever:
    def __init__(self, embedding_model: EmbeddingModel, vector_store):
        self.embedding_model = embedding_model
        self.vector_store = vector_store

    def search_with_scores(self, query, entries=None, top_k=3) -> RetrievalResult:
        vector = self.embedding_model.embed_query(query)
        return self.vector_store.search(vector, top_k=top_k)
