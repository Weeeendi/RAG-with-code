"""
Hash utilities for file integrity verification
"""
import hashlib


def compute_md5(content) -> str:
    """计算内容的MD5哈希，支持bytes或str"""
    if isinstance(content, str):
        content = content.encode('utf-8')
    h = hashlib.md5()
    h.update(content)
    return h.hexdigest()


def compute_sha256(content) -> str:
    """计算内容的SHA256哈希，支持bytes或str"""
    if isinstance(content, str):
        content = content.encode('utf-8')
    h = hashlib.sha256()
    h.update(content)
    return h.hexdigest()


def compute_file_hash(file_path: str, algorithm: str = "md5") -> str:
    """计算文件的哈希值（支持 md5, sha256）"""
    h = hashlib.new(algorithm)
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            h.update(chunk)
    return h.hexdigest()
