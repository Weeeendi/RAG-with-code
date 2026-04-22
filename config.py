import os

MINIMAX_GROUP_ID = os.getenv("MINIMAX_GROUP_ID", "2043975034527027942")
MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY", "sk-cp-etkigx38MLrNIxi4D8FsUBWaq2slx7yxoRNdo4XopoPriY1dlxuVXvug-9CmTY17sk7S3WwV5HLV2kppVTKIG42XhZggQ8e3GTkpNL-2ZPPapsTdOv1hxSE")
MINIMAX_BASE_URL = "https://api.minimax.chat/v1"

PADDLEOCR_TOKEN = os.getenv("PADDLEOCR_TOKEN", "29d2c8c889390dd177ef650c0a843e2b504a4266")
PADDLEOCR_API_URL = "https://paddleocr.aistudio-app.com/api/v2/ocr/jobs"
PADDLEOCR_MODEL = "PaddleOCR-VL-1.5"

DB_PATH = "data/metadata.db"
VECTOR_DIR = "knowledge_base/vectorized"

SOURCE_DIRS = {
    "c_code": "knowledge_base/raw/c_code",
    "protocol_docs": "knowledge_base/raw/protocol_docs",
    "logs": "knowledge_base/raw/logs"
}

EMBEDDING_MODEL = "paraphrase-multilingual-MiniLM-L12-v2"
VECTOR_DIM = 384

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