from abc import ABC, abstractmethod
from typing import List, Dict, Any


class BaseReranker(ABC):
    @abstractmethod
    def rerank(self, query: str, candidates: List[Dict[str, Any]], top_k: int = 10) -> List[Dict[str, Any]]:
        pass


class CrossEncoderReranker(BaseReranker):
    def __init__(self, model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        self.model_name = model
        self._model = None

    def _get_model(self):
        if self._model is None:
            from sentence_transformers import CrossEncoder
            self._model = CrossEncoder(self.model_name)
        return self._model

    def rerank(self, query: str, candidates: List[Dict[str, Any]], top_k: int = 10) -> List[Dict[str, Any]]:
        if not candidates:
            return []

        model = self._get_model()
        doc_texts = [c.get('title', '') + ' ' + c.get('content', '')[:500] for c in candidates]
        pairs = [[query, doc] for doc in doc_texts]
        scores = model.predict(pairs)

        scored = [(c, float(s)) for c, s in zip(candidates, scores)]
        scored.sort(key=lambda x: x[1], reverse=True)
        return [c for c, _ in scored[:top_k]]


class SiliconFlowReranker(BaseReranker):
    def __init__(
        self,
        api_key: str,
        model: str = "BAAI/bge-reranker-v2-m3",
        api_url: str = "https://api.siliconflow.cn/v1/rerank"
    ):
        import requests
        self.api_key = api_key
        self.model = model
        self.api_url = api_url
        self._requests = requests

    def rerank(self, query: str, candidates: List[Dict[str, Any]], top_k: int = 10) -> List[Dict[str, Any]]:
        if not candidates:
            return []

        docs = [c.get('title', '') + ' ' + c.get('content', '')[:500] for c in candidates]
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": self.model,
            "query": query,
            "documents": docs,
            "top_n": top_k
        }
        response = self._requests.post(self.api_url, json=payload, headers=headers, timeout=60)
        if response.status_code == 200:
            result = response.json()
            indices = [r['index'] for r in result['results']]
            return [candidates[i] for i in indices if i < len(candidates)]
        return candidates[:top_k]


class NoOpReranker(BaseReranker):
    def rerank(self, query: str, candidates: List[Dict[str, Any]], top_k: int = 10) -> List[Dict[str, Any]]:
        return candidates[:top_k]
