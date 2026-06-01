"""
Provenance Service
溯源服务：分块 → 原始PDF位置映射
"""
import os
import uuid
import sqlite3
import json
from datetime import datetime
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from config import LABS_DB_PATH


@dataclass
class ChunkProvenance:
    """分块溯源信息"""
    mapping_id: str
    chunk_id: str
    asset_id: str
    file_name: str
    file_path: str
    chunk_index: int
    page_number: Optional[int]
    line_start: Optional[int]
    line_end: Optional[int]
    bounding_box: Optional[Dict]
    chunk_preview: Optional[str]


class ProvenanceService:
    """溯源可视化服务"""

    def __init__(self, db_path: str = LABS_DB_PATH):
        self.db_path = db_path

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def get_chunk_provenance(self, chunk_id: str) -> Optional[ChunkProvenance]:
        """
        获取分块的溯源信息

        Args:
            chunk_id: 分块ID

        Returns:
            ChunkProvenance 或 None
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT m.*, a.file_name, a.file_path
            FROM asset_chunk_mapping m
            JOIN asset_registry a ON m.asset_id = a.asset_id
            WHERE m.chunk_id = ?
        ''', (chunk_id,))

        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        bbox_str = row.get('original_bounding_box')
        bbox = json.loads(bbox_str) if bbox_str else None

        return ChunkProvenance(
            mapping_id=row['mapping_id'],
            chunk_id=row['chunk_id'],
            asset_id=row['asset_id'],
            file_name=row['file_name'],
            file_path=row['file_path'],
            chunk_index=row['chunk_index'],
            page_number=row['original_page_number'],
            line_start=row['original_line_start'],
            line_end=row['original_line_end'],
            bounding_box=bbox,
            chunk_preview=row['chunk_preview']
        )

    def get_asset_chunks(self, asset_id: str) -> List[ChunkProvenance]:
        """
        获取资产的所有分块溯源信息

        Args:
            asset_id: 资产ID

        Returns:
            分块溯源列表
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT m.*, a.file_name, a.file_path
            FROM asset_chunk_mapping m
            JOIN asset_registry a ON m.asset_id = a.asset_id
            WHERE m.asset_id = ?
            ORDER BY m.chunk_index
        ''', (asset_id,))

        rows = cursor.fetchall()
        conn.close()

        results = []
        for row in rows:
            bbox_str = row.get('original_bounding_box')
            bbox = json.loads(bbox_str) if bbox_str else None

            results.append(ChunkProvenance(
                mapping_id=row['mapping_id'],
                chunk_id=row['chunk_id'],
                asset_id=row['asset_id'],
                file_name=row['file_name'],
                file_path=row['file_path'],
                chunk_index=row['chunk_index'],
                page_number=row['original_page_number'],
                line_start=row['original_line_start'],
                line_end=row['original_line_end'],
                bounding_box=bbox,
                chunk_preview=row['chunk_preview']
            ))

        return results

    def get_pdf_preview_coords(self, asset_id: str, page_number: int = None) -> Dict[str, Any]:
        """
        获取PDF页面预览坐标

        Args:
            asset_id: 资产ID
            page_number: 页码（可选）

        Returns:
            预览坐标信息
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        # 获取资产信息
        cursor.execute("SELECT file_path, file_name FROM asset_registry WHERE asset_id = ?", (asset_id,))
        asset_row = cursor.fetchone()

        if not asset_row:
            conn.close()
            return {"error": "Asset not found"}

        file_path = asset_row['file_path']
        file_name = asset_row['file_name']

        # 获取该页的所有分块映射
        if page_number:
            cursor.execute('''
                SELECT chunk_id, original_bounding_box, chunk_preview
                FROM asset_chunk_mapping
                WHERE asset_id = ? AND original_page_number = ?
            ''', (asset_id, page_number))
        else:
            cursor.execute('''
                SELECT chunk_id, original_bounding_box, chunk_preview
                FROM asset_chunk_mapping
                WHERE asset_id = ?
            ''', (asset_id,))

        rows = cursor.fetchall()
        conn.close()

        # 计算高亮区域
        highlight_regions = []
        for row in rows:
            bbox_str = row.get('original_bounding_box')
            if bbox_str:
                bbox = json.loads(bbox_str)
                highlight_regions.append({
                    "chunk_id": row['chunk_id'],
                    "bbox": bbox,
                    "preview": row['chunk_preview'][:100] if row['chunk_preview'] else ''
                })

        # 估算总页数
        total_pages = 1  # 默认1页
        if page_number:
            # 查找最大页码
            conn2 = self._get_conn()
            cursor2 = conn2.cursor()
            cursor2.execute('''
                SELECT MAX(original_page_number) as max_page
                FROM asset_chunk_mapping
                WHERE asset_id = ?
            ''', (asset_id,))
            max_row = cursor2.fetchone()
            conn2.close()
            if max_row and max_row['max_page']:
                total_pages = max_row['max_page']

        return {
            "asset_id": asset_id,
            "file_name": file_name,
            "file_path": file_path,
            "page_number": page_number,
            "total_pages": total_pages,
            "highlight_regions": highlight_regions
        }

    def create_chunk_mapping(self, asset_id: str, chunk_id: str,
                            chunk_index: int, page_number: int = None,
                            line_start: int = None, line_end: int = None,
                            bounding_box: Dict = None,
                            chunk_preview: str = None) -> ChunkProvenance:
        """
        创建分块溯源记录

        Args:
            asset_id: 资产ID
            chunk_id: 分块ID
            chunk_index: 分块索引
            page_number: 原始页码
            line_start: 起始行号
            line_end: 结束行号
            bounding_box: 边界框坐标
            chunk_preview: 分块预览文本

        Returns:
            ChunkProvenance
        """
        mapping_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            cursor.execute('''
                INSERT INTO asset_chunk_mapping (
                    mapping_id, asset_id, chunk_id, chunk_index,
                    original_page_number, original_line_start, original_line_end,
                    original_bounding_box, chunk_preview, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                mapping_id, asset_id, chunk_id, chunk_index,
                page_number, line_start, line_end,
                json.dumps(bounding_box) if bounding_box else None,
                chunk_preview, now
            ))

            conn.commit()

            # 获取资产信息
            cursor.execute("SELECT file_name, file_path FROM asset_registry WHERE asset_id = ?", (asset_id,))
            asset_row = cursor.fetchone()

            return ChunkProvenance(
                mapping_id=mapping_id,
                chunk_id=chunk_id,
                asset_id=asset_id,
                file_name=asset_row['file_name'] if asset_row else '',
                file_path=asset_row['file_path'] if asset_row else '',
                chunk_index=chunk_index,
                page_number=page_number,
                line_start=line_start,
                line_end=line_end,
                bounding_box=bounding_box,
                chunk_preview=chunk_preview
            )

        finally:
            conn.close()

    def search_with_provenance(self, query: str, top_k: int = 5,
                               asset_id: str = None) -> List[Dict[str, Any]]:
        """
        搜索并返回带溯源信息的结果

        Args:
            query: 查询文本
            top_k: 返回数量
            asset_id: 可选，限制资产ID

        Returns:
            带溯源的搜索结果
        """
        # TODO: 与 KnowledgeBase 集成进行实际搜索
        # 目前返回空列表占位

        conn = self._get_conn()
        cursor = conn.cursor()

        if asset_id:
            cursor.execute('''
                SELECT m.*, a.file_name, a.file_path
                FROM asset_chunk_mapping m
                JOIN asset_registry a ON m.asset_id = a.asset_id
                WHERE m.asset_id = ?
                ORDER BY m.chunk_index
                LIMIT ?
            ''', (asset_id, top_k))
        else:
            cursor.execute('''
                SELECT m.*, a.file_name, a.file_path
                FROM asset_chunk_mapping m
                JOIN asset_registry a ON m.asset_id = a.asset_id
                ORDER BY m.chunk_index
                LIMIT ?
            ''', (top_k,))

        rows = cursor.fetchall()
        conn.close()

        results = []
        for row in rows:
            bbox_str = row.get('original_bounding_box')
            bbox = json.loads(bbox_str) if bbox_str else None

            results.append({
                "chunk_id": row['chunk_id'],
                "asset_id": row['asset_id'],
                "file_name": row['file_name'],
                "file_path": row['file_path'],
                "chunk_index": row['chunk_index'],
                "page_number": row['original_page_number'],
                "line_start": row['original_line_start'],
                "line_end": row['original_line_end'],
                "bounding_box": bbox,
                "chunk_preview": row['chunk_preview']
            })

        return results
