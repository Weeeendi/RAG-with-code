from typing import Optional, Union, Dict, Any


LLM_PROVIDERS = {
    "minimax": "models.llm_provider.MiniMaxLLM",
    "siliconflow": "models.llm_provider.SiliconFlowLLM",
    "openai": "models.llm_provider.OpenAICompatibleLLM",
}

EMBEDDING_PROVIDERS = {
    "siliconflow": "models.silicon_embedding.SiliconEmbedding",
    "tfidf": "models.silicon_embedding.TfidfEmbedding",
}

RERANK_PROVIDERS = {
    "crossencoder": "models.rerank_provider.CrossEncoderReranker",
    "siliconflow": "models.rerank_provider.SiliconFlowReranker",
    "noop": "models.rerank_provider.NoOpReranker",
}


def create_llm(provider: str = None, **kwargs) -> 'BaseLLM':
    from models.llm_provider import BaseLLM, MiniMaxLLM, SiliconFlowLLM, OpenAICompatibleLLM
    from config import (
        LLM_PROVIDER, LLM_MODEL, LLM_MAX_TOKENS, LLM_TEMPERATURE,
        MINIMAX_API_KEY, MINIMAX_BASE_URL,
        SILICONFLOW_API_KEY,
        OPENAI_API_KEY, OPENAI_BASE_URL
    )

    if provider is None:
        provider = LLM_PROVIDER

    if provider == "minimax":
        return MiniMaxLLM(
            api_key=kwargs.get("api_key", MINIMAX_API_KEY),
            base_url=kwargs.get("base_url", MINIMAX_BASE_URL),
            model=kwargs.get("model", LLM_MODEL),
            max_tokens=kwargs.get("max_tokens", LLM_MAX_TOKENS),
            temperature=kwargs.get("temperature", LLM_TEMPERATURE),
        )
    elif provider == "siliconflow":
        return SiliconFlowLLM(
            api_key=kwargs.get("api_key", SILICONFLOW_API_KEY),
            base_url=kwargs.get("base_url", "https://api.siliconflow.cn/v1"),
            model=kwargs.get("model", LLM_MODEL),
            max_tokens=kwargs.get("max_tokens", LLM_MAX_TOKENS),
            temperature=kwargs.get("temperature", LLM_TEMPERATURE),
        )
    elif provider == "openai":
        return OpenAICompatibleLLM(
            api_key=kwargs.get("api_key", OPENAI_API_KEY),
            base_url=kwargs.get("base_url", OPENAI_BASE_URL),
            model=kwargs.get("model", LLM_MODEL),
            max_tokens=kwargs.get("max_tokens", LLM_MAX_TOKENS),
            temperature=kwargs.get("temperature", LLM_TEMPERATURE),
        )
    else:
        raise ValueError(f"Unknown LLM provider: {provider}")


def create_embedding(provider: str = None, **kwargs) -> Any:
    from models.silicon_embedding import SiliconEmbedding, TfidfEmbedding
    from config import (
        EMBEDDING_PROVIDER, SILICONFLOW_API_KEY,
        SILICONFLOW_EMBEDDING_MODEL, SILICONFLOW_VECTOR_DIM
    )

    if provider is None:
        provider = EMBEDDING_PROVIDER

    if provider == "siliconflow":
        return SiliconEmbedding(
            api_key=kwargs.get("api_key", SILICONFLOW_API_KEY),
            model=kwargs.get("model", SILICONFLOW_EMBEDDING_MODEL),
            api_url=kwargs.get("api_url", "https://api.siliconflow.cn/v1/embeddings"),
            dimension=kwargs.get("dimension", SILICONFLOW_VECTOR_DIM),
        )
    elif provider == "tfidf":
        return TfidfEmbedding(max_features=kwargs.get("max_features", 2000))
    else:
        raise ValueError(f"Unknown embedding provider: {provider}")


def create_reranker(provider: str = None, **kwargs) -> Any:
    from models.rerank_provider import BaseReranker, CrossEncoderReranker, SiliconFlowReranker, NoOpReranker
    from config import (
        RERANK_PROVIDER, SILICONFLOW_API_KEY, SILICONFLOW_RERANK_MODEL,
        CROSSENCODER_MODEL
    )

    if provider is None:
        provider = RERANK_PROVIDER

    if provider == "crossencoder":
        return CrossEncoderReranker(
            model=kwargs.get("model", CROSSENCODER_MODEL)
        )
    elif provider == "siliconflow":
        return SiliconFlowReranker(
            api_key=kwargs.get("api_key", SILICONFLOW_API_KEY),
            model=kwargs.get("model", SILICONFLOW_RERANK_MODEL),
            api_url=kwargs.get("api_url", "https://api.siliconflow.cn/v1/rerank"),
        )
    elif provider == "noop":
        return NoOpReranker()
    else:
        raise ValueError(f"Unknown rerank provider: {provider}")
