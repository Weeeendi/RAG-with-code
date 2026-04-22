import sys
import numpy as np
import requests
import json
import time
from typing import List, Dict, Any, Optional, Tuple
import os
from config import MINIMAX_API_KEY, MINIMAX_BASE_URL, PROXIES


class MiniMaxEmbedding:
    def __init__(self, api_key: str = None, base_url: str = None, group_id: str = None):
        self.api_key = api_key or MINIMAX_API_KEY
        self.base_url = base_url or MINIMAX_BASE_URL
        self.group_id = group_id or os.getenv("MINIMAX_GROUP_ID", "")
        self.session = requests.Session()
        if PROXIES:
            self.session.proxies = PROXIES
        else:
            self.session.trust_env = False
        self._embedding_cache = {}
        self.batch_size = 10
        self.rate_limit_delay = 0.1

    def get_embedding(self, text: str, emb_type: str = "db") -> List[float]:
        cache_key = f"{emb_type}:{text}"
        if cache_key in self._embedding_cache:
            return self._embedding_cache[cache_key]

        url = f"{self.base_url}/embeddings?GroupId={self.group_id}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        data = {
            "texts": [text],
            "model": "embo-01",
            "type": emb_type
        }

        try:
            response = self.session.post(url, headers=headers, data=json.dumps(data), timeout=(10, 30))
            if response.status_code == 200:
                res = response.json()
                if 'vectors' in res and len(res['vectors']) > 0:
                    embedding = res['vectors'][0]
                    self._embedding_cache[cache_key] = embedding
                    return embedding
        except Exception as e:
            print(f"[MiniMaxEmbedding] Error: {e}")
        return None

    def get_embeddings_batch(self, texts: List[str], emb_type: str = "db") -> List[List[float]]:
        url = f"{self.base_url}/embeddings?GroupId={self.group_id}"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        all_embeddings = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i:i + self.batch_size]
            data = {
                "texts": batch,
                "model": "embo-01",
                "type": emb_type
            }

            try:
                response = self.session.post(url, headers=headers, data=json.dumps(data), timeout=(30, 60))
                if response.status_code == 200:
                    res = response.json()
                    if 'vectors' in res:
                        all_embeddings.extend(res['vectors'])
                        time.sleep(self.rate_limit_delay)
                else:
                    all_embeddings.extend([None] * len(batch))
            except Exception as e:
                print(f"[MiniMaxEmbedding] Batch error: {e}")
                all_embeddings.extend([None] * len(batch))

        for emb in all_embeddings:
            if emb:
                cache_key = f"{emb_type}:{texts[all_embeddings.index(emb)]}"
                self._embedding_cache[cache_key] = emb

        return all_embeddings

    @staticmethod
    def cosine_similarity(a: List[float], b: List[float]) -> float:
        a = np.array(a)
        b = np.array(b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return np.dot(a, b) / (norm_a * norm_b)

    def similarity(self, text1: str, text2: str) -> float:
        emb1 = self.get_embedding(text1, "db")
        emb2 = self.get_embedding(text2, "db")
        if emb1 and emb2:
            return self.cosine_similarity(emb1, emb2)
        return 0.0


class MiniMaxEmbeddingStore:
    def __init__(self, embedding_func: MiniMaxEmbedding = None):
        self.embedding = embedding_func or MiniMaxEmbedding()
        self.doc_embeddings: Dict[str, List[float]] = {}
        self.doc_texts: Dict[str, str] = {}

    def add_doc(self, doc_id: str, text: str):
        self.doc_texts[doc_id] = text
        emb = self.embedding.get_embedding(text, "db")
        if emb:
            self.doc_embeddings[doc_id] = emb

    def add_docs_batch(self, docs: List[Dict[str, str]]):
        texts = [doc['text'] for doc in docs if 'text' in doc]
        ids = [doc['id'] for doc in docs if 'id' in doc]

        embeddings = self.embedding.get_embeddings_batch(texts, "db")

        for doc_id, text, emb in zip(ids, texts, embeddings):
            if emb:
                self.doc_texts[doc_id] = text
                self.doc_embeddings[doc_id] = emb

    def search(self, query: str, top_k: int = 5) -> List[Tuple[str, float]]:
        query_emb = self.embedding.get_embedding(query, "query")
        if not query_emb:
            return []

        results = []
        for doc_id, doc_emb in self.doc_embeddings.items():
            sim = self.cosine_similarity(query_emb, doc_emb)
            results.append((doc_id, sim))

        results.sort(key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def cosine_similarity(self, a: List[float], b: List[float]) -> float:
        return MiniMaxEmbedding.cosine_similarity(a, b)


def hybrid_search(
    query: str,
    bm25_results: List[Tuple[str, float]],
    dense_results: List[Tuple[str, float]],
    k: int = 60,
    alpha: float = 0.5
) -> List[Tuple[str, float]]:
    """
    混合检索融合

    Args:
        query: 查询文本
        bm25_results: BM25检索结果 [(doc_id, score), ...]
        dense_results: 稠密检索结果 [(doc_id, score), ...]
        k: RRF参数
        alpha: 权重因子 (0.5表示平等对待)

    Returns:
        融合后的排序结果
    """
    doc_scores = {}

    for rank, (doc_id, score) in enumerate(bm25_results):
        if doc_id not in doc_scores:
            doc_scores[doc_id] = {'bm25': 0, 'dense': 0}
        doc_scores[doc_id]['bm25'] += (1 - alpha) * (1.0 / (k + rank + 1))

    for rank, (doc_id, score) in enumerate(dense_results):
        if doc_id not in doc_scores:
            doc_scores[doc_id] = {'bm25': 0, 'dense': 0}
        doc_scores[doc_id]['dense'] += alpha * (1.0 / (k + rank + 1))

    final_scores = []
    for doc_id, scores in doc_scores.items():
        combined_score = scores['bm25'] + scores['dense']
        final_scores.append((doc_id, combined_score))

    final_scores.sort(key=lambda x: x[1], reverse=True)
    return final_scores


def rrf_fusion(results_list: List[List[Tuple[str, float]]], k: int = 60) -> List[Tuple[str, float]]:
    """
    多路RRF融合

    Args:
        results_list: 多个检索方法的结果列表
        k: RRF参数

    Returns:
        融合后的排序结果
    """
    doc_scores = {}

    for results in results_list:
        for rank, (doc_id, score) in enumerate(results):
            if doc_id not in doc_scores:
                doc_scores[doc_id] = 0.0
            doc_scores[doc_id] += 1.0 / (k + rank + 1)

    sorted_docs = sorted(doc_scores.items(), key=lambda x: x[1], reverse=True)
    return sorted_docs
