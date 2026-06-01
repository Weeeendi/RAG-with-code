"""
Asset status state machine
"""
from enum import Enum
from typing import Dict, List, Set


class AssetStatus(Enum):
    UPLOADED = "uploaded"
    PARSING = "parsing"
    PARSED = "parsed"
    INDEXING = "indexing"
    INDEXED = "indexed"
    ERROR = "error"


# Valid state transitions
ASSET_STATUS_TRANSITIONS: Dict[AssetStatus, Set[AssetStatus]] = {
    AssetStatus.UPLOADED: {AssetStatus.PARSING, AssetStatus.ERROR},
    AssetStatus.PARSING: {AssetStatus.PARSED, AssetStatus.ERROR},
    AssetStatus.PARSED: {AssetStatus.INDEXING, AssetStatus.ERROR},
    AssetStatus.INDEXING: {AssetStatus.INDEXED, AssetStatus.ERROR},
    AssetStatus.ERROR: {AssetStatus.PARSING},  # Can retry
    AssetStatus.INDEXED: set(),  # Terminal state
}


def can_transition(from_status: AssetStatus, to_status: AssetStatus) -> bool:
    """检查状态转换是否合法"""
    return to_status in ASSET_STATUS_TRANSITIONS.get(from_status, set())


def get_next_status(current: AssetStatus, success: bool = True) -> AssetStatus:
    """获取下一个状态"""
    if success:
        transitions = {
            AssetStatus.UPLOADED: AssetStatus.PARSING,
            AssetStatus.PARSING: AssetStatus.PARSED,
            AssetStatus.PARSED: AssetStatus.INDEXING,
            AssetStatus.INDEXING: AssetStatus.INDEXED,
        }
        return transitions.get(current, current)
    else:
        return AssetStatus.ERROR
