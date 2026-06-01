import os
import requests
from typing import List, Optional, Union
import numpy as np


class SiliconEmbedding:
    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "BAAI/bge-m3",
        api_url: str = "https://api.siliconflow.cn/v1/embeddings",
        dimension: int = 1024
    ):
        self.api_key = api_key or os.getenv("SILICONFLOW_API_KEY", "")
        self.model = model
        self.api_url = api_url
        self.dimension = dimension

    def encode(self, texts: Union[str, List[str]], batch_size: int = 32) -> List[List[float]]:
        if isinstance(texts, str):
            texts = [texts]

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            payload = {
                "model": self.model,
                "input": batch
            }
            resp = requests.post(self.api_url, json=payload, headers=headers, timeout=120)
            resp.raise_for_status()
            data = resp.json()
            embeddings = [item["embedding"] for item in data["data"]]
            all_embeddings.extend(embeddings)

        return all_embeddings

    def similarity(self, text1: str, text2: str) -> float:
        emb1 = np.array(self.encode(text1)[0])
        emb2 = np.array(self.encode(text2)[0])
        return float(np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2)))


class TfidfEmbedding:
    def __init__(self, max_features: int = 2000):
        self.max_features = max_features
        import math
        import re
        from collections import Counter
        self._math = math
        self._re = re
        self._Counter = Counter

    def _tokenize(self, text: str) -> list:
        text = text.lower()
        english_words = self._re.findall(r'[a-z0-9_]+', text)
        chinese_chars = self._re.findall(r'[\u4e00-\u9fff]', text)
        chinese_bigrams = [chinese_chars[i]+chinese_chars[i+1] for i in range(len(chinese_chars)-1)]
        return english_words + chinese_bigrams

    def fit(self, documents: list) -> 'TfidfEmbedding':
        doc_count = len(documents)
        if doc_count == 0:
            return self

        tokenized = [self._tokenize(doc) for doc in documents]
        all_tokens = [t for doc in tokenized for t in doc]
        token_counts = self._Counter(all_tokens)

        self.vocab = {t: i for i, (t, c) in enumerate(token_counts.most_common(self.max_features))}

        df = self._Counter()
        for doc_tokens in tokenized:
            unique_tokens = set(doc_tokens)
            for t in unique_tokens:
                if t in self.vocab:
                    df[t] += 1

        self.idf = [0] * len(self.vocab)
        for token, idx in self.vocab.items():
            self.idf[idx] = self._math.log((doc_count + 1) / (df.get(token, 0) + 1)) + 1

        return self

    def transform(self, documents: list) -> list:
        if not documents or not hasattr(self, 'vocab') or not self.vocab:
            return []

        vectors = []
        for doc in documents:
            doc_tokens = self._tokenize(doc)
            tf = self._Counter(doc_tokens)
            vec = [0] * len(self.vocab)
            doc_len = len(doc_tokens) if doc_tokens else 1

            for token, count in tf.items():
                if token in self.vocab:
                    idx = self.vocab[token]
                    tf_val = count / doc_len
                    vec[idx] = tf_val * self.idf[idx]

            magnitude = self._math.sqrt(sum(v * v for v in vec))
            if magnitude > 0:
                vec = [v / magnitude for v in vec]
            vectors.append(vec)

        return vectors

    def fit_transform(self, documents: list) -> list:
        self.fit(documents)
        return self.transform(documents)

    def encode(self, texts: Union[str, List[str]]) -> List[List[float]]:
        if isinstance(texts, str):
            texts = [texts]
        return self.transform(texts)


def get_embedding_model(use_silicon: bool = True, dimension: int = 1024) -> Union[SiliconEmbedding, TfidfEmbedding]:
    if use_silicon:
        return SiliconEmbedding(dimension=dimension)
    return TfidfEmbedding()