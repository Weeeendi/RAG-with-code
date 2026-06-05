import os

MINIMAX_GROUP_ID = ""
MINIMAX_API_KEY = "sk-cp-9YIBvviKc425wlAdd1te5ECHQoQQVfhvXldMZ4uleGcmiYcGWe5TE6ac0aXEq1kJCchp-pgUwS60_gMeg0j6nPE4WPm11wCveOFPi5r-nXsv-tV7AXxlh2c"
MINIMAX_BASE_URL = "https://api.minimax.chat/v1"

PADDLEOCR_TOKEN = "29d2c8c889390dd177ef650c0a843e2b504a4266"
PADDLEOCR_API_URL = "https://paddleocr.aistudio-app.com/api/v2/ocr/jobs"
PADDLEOCR_MODEL = "PaddleOCR-VL-1.6"

DB_PATH = "data/metadata.db"
VECTOR_DIR = "knowledge_base/vectorized"

LABS_DB_PATH = "data/labs.db"
LABS_UPLOAD_DIR = "labs/uploads"

SOURCE_DIRS = {
    "c_code": "knowledge_base/raw/c_code",
    "protocol_docs": "knowledge_base/raw/protocol_docs",
    "logs": "knowledge_base/raw/logs"
}

LLM_PROVIDER = "minimax"
LLM_MODEL = "MiniMax-M2.7"
LLM_MAX_TOKENS = 800
LLM_TEMPERATURE = 0.3

EMBEDDING_PROVIDER = "siliconflow"
SILICONFLOW_API_KEY = "sk-yuafbaisfogshowaunwnckbvlqgqrypadpgbnupimxvkqter"
SILICONFLOW_EMBEDDING_MODEL = "BAAI/bge-m3"
SILICONFLOW_VECTOR_DIM = 1024
SILICONFLOW_RERANK_MODEL = "BAAI/bge-reranker-v2-m3"

RERANK_PROVIDER = "siliconflow"
CROSSENCODER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"

OPENAI_API_KEY = ""
OPENAI_BASE_URL = "https://api.openai.com/v1"
OPENAI_MODEL = "gpt-4o-mini"

DEFAULT_TOP_K = 5
MAX_CONTEXT_CHARS = 4000

HTTP_PROXY = os.getenv("HTTP_PROXY", os.getenv("http_proxy", ""))
HTTPS_PROXY = os.getenv("HTTPS_PROXY", os.getenv("https_proxy", ""))

if HTTP_PROXY.lower() in ("", "none", "off"):
    os.environ.pop("HTTP_PROXY", None)
    os.environ.pop("http_proxy", None)
    HTTP_PROXY = ""
if HTTPS_PROXY.lower() in ("", "none", "off"):
    os.environ.pop("HTTPS_PROXY", None)
    os.environ.pop("https_proxy", None)
    HTTPS_PROXY = ""

PROXIES = None
if HTTP_PROXY and HTTP_PROXY.lower() not in ("", "none", "off"):
    PROXIES = {}
    PROXIES["http"] = HTTP_PROXY
if HTTPS_PROXY and HTTPS_PROXY.lower() not in ("", "none", "off"):
    if PROXIES is None:
        PROXIES = {}
    PROXIES["https"] = HTTPS_PROXY

GRAPH_RAG_ENABLED = True
GRAPH_EXTRACTOR = "regex"
GRAPH_RETRIEVAL_WEIGHT = 0.4
GRAPH_DIR = "knowledge_base/parsed/graph"
GRAPH_NODE_INDEX = "knowledge_base/vectorized/graph_nodes"
