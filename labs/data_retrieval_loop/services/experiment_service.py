"""
Experiment Configuration Service
实验配置服务：分块参数管理、影子索引
"""
import os
import uuid
import sqlite3
import json
from datetime import datetime
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, asdict

from config import LABS_DB_PATH


@dataclass
class ExperimentConfig:
    config_id: str
    config_name: str
    description: Optional[str]
    chunk_size: int  # 500, 800, 1000
    overlap_ratio: float  # 0.10, 0.15
    splitter_type: str  # smart, recursive, character
    embedding_model: Optional[str]
    vector_weight_bm25: float
    vector_weight_tfidf: float
    vector_weight_faiss: float
    asset_ids: List[str]
    index_name: Optional[str]
    is_shadow: bool
    status: str  # draft, active, archived
    created_at: str
    updated_at: str

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d['asset_ids'] = json.dumps(self.asset_ids) if isinstance(self.asset_ids, list) else self.asset_ids
        return d


class ExperimentService:
    """实验配置服务"""

    VALID_CHUNK_SIZES = [500, 800, 1000]
    VALID_OVERLAP_RATIOS = [0.10, 0.15]
    VALID_SPLITTER_TYPES = ['smart', 'recursive', 'character']

    def __init__(self, db_path: str = LABS_DB_PATH):
        self.db_path = db_path

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def create_config(self, config_name: str, chunk_size: int = 800,
                      overlap_ratio: float = 0.15, splitter_type: str = 'smart',
                      description: str = None, asset_ids: List[str] = None,
                      is_shadow: bool = False) -> ExperimentConfig:
        """创建实验配置"""
        # 验证参数
        if chunk_size not in self.VALID_CHUNK_SIZES:
            raise InvalidChunkSizeError(chunk_size, self.VALID_CHUNK_SIZES)
        if overlap_ratio not in self.VALID_OVERLAP_RATIOS:
            raise InvalidOverlapRatioError(overlap_ratio, self.VALID_OVERLAP_RATIOS)
        if splitter_type not in self.VALID_SPLITTER_TYPES:
            raise InvalidSplitterTypeError(splitter_type, self.VALID_SPLITTER_TYPES)

        config_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        # 生成索引名
        if is_shadow:
            index_name = f"idx_{config_name}_v{self._get_next_version()}"
        else:
            index_name = f"idx_{config_name}"

        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                INSERT INTO experiment_configs (
                    config_id, config_name, description, chunk_size, overlap_ratio,
                    splitter_type, asset_ids, index_name, is_shadow, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                config_id, config_name, description, chunk_size, overlap_ratio,
                splitter_type, json.dumps(asset_ids or []), index_name, 1 if is_shadow else 0,
                'draft', now, now
            ))

            conn.commit()

            return ExperimentConfig(
                config_id=config_id,
                config_name=config_name,
                description=description,
                chunk_size=chunk_size,
                overlap_ratio=overlap_ratio,
                splitter_type=splitter_type,
                embedding_model=None,
                vector_weight_bm25=1.0,
                vector_weight_tfidf=1.0,
                vector_weight_faiss=1.0,
                asset_ids=asset_ids or [],
                index_name=index_name,
                is_shadow=is_shadow,
                status='draft',
                created_at=now,
                updated_at=now
            )

        finally:
            conn.close()

    def get_config(self, config_id: str) -> Optional[ExperimentConfig]:
        """获取配置详情"""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM experiment_configs WHERE config_id = ?", (config_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return self._row_to_config(row)

    def list_configs(self, status: str = None, is_shadow: bool = None,
                     limit: int = 50, offset: int = 0) -> List[ExperimentConfig]:
        """列出配置"""
        conn = self._get_conn()
        cursor = conn.cursor()

        query = "SELECT * FROM experiment_configs WHERE 1=1"
        params = []

        if status:
            query += " AND status = ?"
            params.append(status)
        if is_shadow is not None:
            query += " AND is_shadow = ?"
            params.append(1 if is_shadow else 0)

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_config(r) for r in rows]

    def update_config(self, config_id: str, **kwargs) -> Optional[ExperimentConfig]:
        """更新配置"""
        allowed_fields = ['config_name', 'description', 'chunk_size', 'overlap_ratio',
                         'splitter_type', 'status']
        updates = []
        params = []

        for field in allowed_fields:
            if field in kwargs:
                updates.append(f"{field} = ?")
                params.append(kwargs[field])

        if not updates:
            return self.get_config(config_id)

        params.append(config_id)
        now = datetime.now().isoformat()

        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            query = f"UPDATE experiment_configs SET {', '.join(updates)}, updated_at = ? WHERE config_id = ?"
            cursor.execute(query, params)
            conn.commit()

            return self.get_config(config_id)

        finally:
            conn.close()

    def activate_config(self, config_id: str) -> str:
        """
        激活配置（创建影子索引），同时停用其他配置，确保只有一个生效
        """
        config = self.get_config(config_id)
        if not config:
            raise ConfigNotFoundError(config_id)

        if config.status == 'active':
            raise ConfigAlreadyActiveError(config_id)

        index_version_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            # 停用所有其他配置
            cursor.execute('''
                UPDATE experiment_configs SET status = 'draft', updated_at = ?
                WHERE status = 'active'
            ''', (now,))

            # 创建索引版本记录
            cursor.execute('''
                INSERT INTO index_versions (
                    index_version_id, index_name, config_id, is_active, created_at
                ) VALUES (?, ?, ?, ?, ?)
            ''', (index_version_id, config.index_name, config_id, 1, now))

            # 更新配置状态为 active
            cursor.execute('''
                UPDATE experiment_configs SET status = 'active', updated_at = ?
                WHERE config_id = ?
            ''', (now, config_id))

            conn.commit()

            return index_version_id

        finally:
            conn.close()

    def delete_config(self, config_id: str, force: bool = False) -> bool:
        """
        删除配置
        - force=True: 硬删除（直接从数据库删除）
        - force=False: 软删除（标记为 archived）
        - Active 状态不能删除，必须先设为 draft
        - Archived 状态可以直接删除
        """
        config = self.get_config(config_id)
        if not config:
            return False

        # Active 配置不能直接删除
        if config.status == 'active' and not force:
            raise ConfigCannotDeleteError("Active 状态配置不能删除，请先设为非 Active")

        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            if force:
                # 硬删除
                cursor.execute("DELETE FROM experiment_configs WHERE config_id = ?", (config_id,))
            else:
                # 软删除 - 标记为 archived
                now = datetime.now().isoformat()
                cursor.execute('''
                    UPDATE experiment_configs SET status = 'archived', updated_at = ?
                    WHERE config_id = ?
                ''', (now, config_id))

            conn.commit()
            return True

        finally:
            conn.close()

    def unarchive_config(self, config_id: str) -> Optional[ExperimentConfig]:
        """解除归档状态，恢复为 draft"""
        config = self.get_config(config_id)
        if not config:
            raise ConfigNotFoundError(config_id)

        if config.status != 'archived':
            return config  # 只有 archived 需要 unarchive

        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            now = datetime.now().isoformat()
            cursor.execute('''
                UPDATE experiment_configs SET status = 'draft', updated_at = ?
                WHERE config_id = ?
            ''', (now, config_id))
            conn.commit()

            return self.get_config(config_id)
        finally:
            conn.close()

    def compare_configs(self, config_ids: List[str]) -> Dict[str, Any]:
        """
        对比多个配置的效果

        Returns:
            对比报告
        """
        results = []
        for cid in config_ids:
            config = self.get_config(cid)
            if not config:
                continue

            # 获取该配置的评估结果
            conn = self._get_conn()
            cursor = conn.cursor()
            cursor.execute('''
                SELECT AVG(hit_rate) as avg_hit_rate, AVG(mrr) as avg_mrr, COUNT(*) as eval_count
                FROM recall_evaluations
                WHERE config_id = ?
            ''', (cid,))
            row = cursor.fetchone()
            conn.close()

            results.append({
                "config_id": cid,
                "config_name": config.config_name,
                "chunk_size": config.chunk_size,
                "overlap_ratio": config.overlap_ratio,
                "avg_hit_rate": row['avg_hit_rate'] or 0,
                "avg_mrr": row['avg_mrr'] or 0,
                "eval_count": row['eval_count'] or 0
            })

        # 按 avg_hit_rate 降序排列
        results.sort(key=lambda x: x['avg_hit_rate'], reverse=True)

        return {
            "rankings": results,
            "best_config_id": results[0]['config_id'] if results else None
        }

    def _get_next_version(self) -> int:
        """获取下一个影子索引版本号"""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) as cnt FROM experiment_configs WHERE is_shadow = 1")
        row = cursor.fetchone()
        conn.close()

        return (row['cnt'] or 0) + 1

    def _row_to_config(self, row) -> ExperimentConfig:
        """将数据库行转换为 ExperimentConfig 对象"""
        if hasattr(row, 'keys'):
            row = dict(row)

        asset_ids_str = row.get('asset_ids', '[]')
        asset_ids = json.loads(asset_ids_str) if asset_ids_str else []

        return ExperimentConfig(
            config_id=row['config_id'],
            config_name=row['config_name'],
            description=row.get('description'),
            chunk_size=row['chunk_size'],
            overlap_ratio=row['overlap_ratio'],
            splitter_type=row['splitter_type'],
            embedding_model=row.get('embedding_model'),
            vector_weight_bm25=row.get('vector_weight_bm25', 1.0),
            vector_weight_tfidf=row.get('vector_weight_tfidf', 1.0),
            vector_weight_faiss=row.get('vector_weight_faiss', 1.0),
            asset_ids=asset_ids,
            index_name=row.get('index_name'),
            is_shadow=bool(row.get('is_shadow', 0)),
            status=row['status'],
            created_at=row['created_at'],
            updated_at=row['updated_at']
        )


# Custom Exceptions
class InvalidChunkSizeError(Exception):
    def __init__(self, size: int, valid_sizes: list):
        self.size = size
        self.valid_sizes = valid_sizes
        super().__init__(f"无效的 chunk_size: {size}，有效值: {valid_sizes}")


class InvalidOverlapRatioError(Exception):
    def __init__(self, ratio: float, valid_ratios: list):
        self.ratio = ratio
        self.valid_ratios = valid_ratios
        super().__init__(f"无效的 overlap_ratio: {ratio}，有效值: {valid_ratios}")


class InvalidSplitterTypeError(Exception):
    def __init__(self, splitter_type: str, valid_types: list):
        self.splitter_type = splitter_type
        self.valid_types = valid_types
        super().__init__(f"无效的 splitter_type: {splitter_type}，有效值: {valid_types}")


class ConfigNotFoundError(Exception):
    def __init__(self, config_id: str):
        self.config_id = config_id
        super().__init__(f"配置不存在: {config_id}")


class ConfigAlreadyActiveError(Exception):
    def __init__(self, config_id: str):
        self.config_id = config_id
        super().__init__(f"配置已经激活: {config_id}")


class ConfigCannotDeleteError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
