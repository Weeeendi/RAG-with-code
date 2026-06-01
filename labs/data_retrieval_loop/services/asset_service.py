"""
Asset Management Service
文件资产管理服务：上传、删除、状态机管理
"""
import os
import uuid
import sqlite3
import json
from datetime import datetime
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, asdict

from config import LABS_DB_PATH, LABS_UPLOAD_DIR
from labs.data_retrieval_loop.utils.hash_utils import compute_md5, compute_sha256
from labs.data_retrieval_loop.utils.state_machine import AssetStatus, can_transition, get_next_status


@dataclass
class Asset:
    asset_id: str
    file_name: str
    file_path: str
    file_size: int
    md5_hash: str
    sha256_hash: str
    mime_type: str
    category: str
    status: str
    error_message: Optional[str]
    retry_count: int
    tags: List[str]
    security_level: str
    expiry_date: Optional[str]
    owner: Optional[str]
    notes: Optional[str]
    version: int
    parent_asset_id: Optional[str]
    is_active: int
    created_at: str
    updated_at: str

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # Handle JSON fields
        if isinstance(self.tags, list):
            d['tags'] = json.dumps(self.tags)
        return d


class AssetService:
    """资产管理服务"""

    SUPPORTED_TYPES = {
        '.c', '.h',  # C代码
        '.pdf', '.docx', '.xlsx', '.txt', '.md', '.rtf',  # 协议文档
        '.log', '.txt'  # 日志
    }

    def __init__(self, db_path: str = LABS_DB_PATH, upload_dir: str = LABS_UPLOAD_DIR):
        self.db_path = db_path
        self.upload_dir = upload_dir
        os.makedirs(upload_dir, exist_ok=True)

    def _get_conn(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def upload_file(self, file_obj, tags: List[str] = None,
                    security_level: str = "internal", owner: str = None,
                    notes: str = None) -> Asset:
        """
        上传文件并进行MD5/SHA256校验

        Args:
            file_obj: 文件对象
            tags: 标签列表
            security_level: 安全级别
            owner: 责任人
            notes: 备注

        Returns:
            Asset: 创建的资产对象

        Raises:
            DuplicateAssetError: 文件已存在
            UnsupportedFileTypeError: 不支持的文件类型
        """
        # 检查文件类型
        original_filename = file_obj.filename
        ext = os.path.splitext(original_filename)[1].lower()
        if ext not in self.SUPPORTED_TYPES:
            raise UnsupportedFileTypeError(f"不支持的文件类型: {ext}")

        # 重置文件指针
        file_obj.seek(0)

        # 计算哈希
        content = file_obj.read()
        md5_hash = compute_md5(content) if isinstance(content, bytes) else compute_md5(content.encode())
        file_obj.seek(0)
        content = file_obj.read()
        sha256_hash = compute_sha256(content) if isinstance(content, bytes) else compute_sha256(content.encode())
        file_obj.seek(0)

        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            # 检查重复
            cursor.execute("SELECT asset_id, file_name FROM asset_registry WHERE md5_hash = ?", (md5_hash,))
            existing = cursor.fetchone()
            if existing:
                raise DuplicateAssetError(existing['asset_id'], existing['file_name'])

            # 保存文件
            asset_id = str(uuid.uuid4())
            file_size = len(content)
            file_path = os.path.join(self.upload_dir, f"{asset_id}_{original_filename}")

            with open(file_path, 'wb') as f:
                f.write(content if isinstance(content, bytes) else content.encode())

            # 创建资产记录
            now = datetime.now().isoformat()
            tags_json = json.dumps(tags or [])

            cursor.execute('''
                INSERT INTO asset_registry (
                    asset_id, file_name, file_path, file_size, md5_hash, sha256_hash,
                    mime_type, category, status, tags, security_level, owner, notes,
                    version, is_active, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                asset_id, original_filename, file_path, file_size, md5_hash, sha256_hash,
                ext, self._get_category(ext), AssetStatus.UPLOADED.value, tags_json,
                security_level, owner, notes, 1, 1, now, now
            ))

            conn.commit()

            return self._row_to_asset(asset_id, cursor, now, now)

        finally:
            conn.close()

    def get_asset(self, asset_id: str) -> Optional[Asset]:
        """获取资产详情"""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM asset_registry WHERE asset_id = ?", (asset_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return self._row_to_asset(row['asset_id'], cursor, row['created_at'], row['updated_at'], row)

    def list_assets(self, status: str = None, category: str = None,
                    limit: int = 50, offset: int = 0) -> List[Asset]:
        """列出资产"""
        conn = self._get_conn()
        cursor = conn.cursor()

        query = "SELECT * FROM asset_registry WHERE is_active = 1"
        params = []

        if status:
            query += " AND status = ?"
            params.append(status)
        if category:
            query += " AND category = ?"
            params.append(category)

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_asset(r['asset_id'], cursor, r['created_at'], r['updated_at'], r) for r in rows]

    def update_status(self, asset_id: str, new_status: AssetStatus,
                      error_message: str = None) -> bool:
        """
        更新资产状态（状态机转换）

        Args:
            asset_id: 资产ID
            new_status: 新状态
            error_message: 错误信息（可选）

        Returns:
            bool: 是否成功

        Raises:
            InvalidStateTransitionError: 状态转换不合法
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT status FROM asset_registry WHERE asset_id = ?", (asset_id,))
            row = cursor.fetchone()

            if not row:
                return False

            current_status = AssetStatus(row['status'])
            if not can_transition(current_status, new_status):
                raise InvalidStateTransitionError(current_status.value, new_status.value)

            now = datetime.now().isoformat()
            if error_message:
                cursor.execute('''
                    UPDATE asset_registry
                    SET status = ?, error_message = ?, updated_at = ?
                    WHERE asset_id = ?
                ''', (new_status.value, error_message, now, asset_id))
            else:
                cursor.execute('''
                    UPDATE asset_registry
                    SET status = ?, updated_at = ?
                    WHERE asset_id = ?
                ''', (new_status.value, now, asset_id))

            conn.commit()
            return True

        finally:
            conn.close()

    def delete_asset(self, asset_id: str, force: bool = False) -> bool:
        """
        删除资产（软删除或硬删除）

        Args:
            asset_id: 资产ID
            force: 是否硬删除（同时删除文件）

        Returns:
            bool: 是否成功
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT file_path FROM asset_registry WHERE asset_id = ?", (asset_id,))
            row = cursor.fetchone()

            if not row:
                return False

            file_path = row['file_path']

            if force:
                # 硬删除：同时删除文件和记录
                if os.path.exists(file_path):
                    os.remove(file_path)
                cursor.execute("DELETE FROM asset_registry WHERE asset_id = ?", (asset_id,))
            else:
                # 软删除：标记为非活跃
                now = datetime.now().isoformat()
                cursor.execute('''
                    UPDATE asset_registry SET is_active = 0, updated_at = ? WHERE asset_id = ?
                ''', (now, asset_id))

            conn.commit()
            return True

        finally:
            conn.close()

    def update_asset(self, asset_id: str, file_name: str = None, category: str = None,
                     tags: List[str] = None, security_level: str = None,
                     owner: str = None, notes: str = None) -> Optional[Asset]:
        """
        更新资产元数据

        Args:
            asset_id: 资产ID
            file_name: 文件名（可选）
            category: 分类（可选）
            tags: 标签列表（可选）
            security_level: 安全级别（可选）
            owner: 责任人（可选）
            notes: 备注（可选）

        Returns:
            Asset: 更新后的资产对象

        Raises:
            AssetNotFoundError: 资产不存在
        """
        conn = self._get_conn()
        cursor = conn.cursor()

        try:
            cursor.execute("SELECT * FROM asset_registry WHERE asset_id = ? AND is_active = 1", (asset_id,))
            row = cursor.fetchone()

            if not row:
                raise AssetNotFoundError(asset_id)

            updates = []
            params = []

            if file_name is not None:
                updates.append("file_name = ?")
                params.append(file_name)
                old_path = row['file_path']
                dir_name = os.path.dirname(old_path)
                new_path = os.path.join(dir_name, f"{asset_id}_{file_name}")
                if os.path.exists(old_path):
                    os.rename(old_path, new_path)
                updates.append("file_path = ?")
                params.append(new_path)

            if category is not None:
                updates.append("category = ?")
                params.append(category)

            if tags is not None:
                updates.append("tags = ?")
                params.append(json.dumps(tags))

            if security_level is not None:
                updates.append("security_level = ?")
                params.append(security_level)

            if owner is not None:
                updates.append("owner = ?")
                params.append(owner)

            if notes is not None:
                updates.append("notes = ?")
                params.append(notes)

            if not updates:
                return self._row_to_asset(asset_id, cursor, row['created_at'], row['updated_at'], row)

            now = datetime.now().isoformat()
            updates.append("updated_at = ?")
            params.append(now)
            params.append(asset_id)

            query = f"UPDATE asset_registry SET {', '.join(updates)} WHERE asset_id = ?"
            cursor.execute(query, params)
            conn.commit()

            return self._row_to_asset(asset_id, cursor, row['created_at'], now)

        finally:
            conn.close()

    def reprocess_asset(self, asset_id: str) -> str:
        """
        重新处理资产

        Returns:
            str: task_id
        """
        asset = self.get_asset(asset_id)
        if not asset:
            raise AssetNotFoundError(asset_id)

        # 重置状态
        self.update_status(asset_id, AssetStatus.PARSING)

        # 创建任务记录
        task_id = str(uuid.uuid4())
        now = datetime.now().isoformat()

        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute('''
            INSERT INTO processing_tasks (task_id, task_type, asset_id, status, progress, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', ('parse', task_id, asset_id, 'pending', 0.0, now))

        conn.commit()
        conn.close()

        return task_id

    def get_asset_status(self, asset_id: str) -> Optional[Dict[str, Any]]:
        """获取资产处理状态"""
        conn = self._get_conn()
        cursor = conn.cursor()

        cursor.execute("SELECT status, error_message, retry_count FROM asset_registry WHERE asset_id = ?", (asset_id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return None

        return {
            "asset_id": asset_id,
            "status": row['status'],
            "error_message": row['error_message'],
            "retry_count": row['retry_count']
        }

    def _get_category(self, ext: str) -> str:
        """根据扩展名判断资产类别"""
        if ext in ('.c', '.h'):
            return 'c_code'
        elif ext in ('.log', '.txt'):
            return 'log'
        else:
            return 'protocol'

    def _row_to_asset(self, asset_id: str, cursor, created_at: str, updated_at: str, row=None) -> Asset:
        """将数据库行转换为Asset对象"""
        if row is None:
            cursor.execute("SELECT * FROM asset_registry WHERE asset_id = ?", (asset_id,))
            row = cursor.fetchone()

        # Convert sqlite3.Row to dict for safe access
        if hasattr(row, 'keys'):
            row = dict(row)

        tags_str = row.get('tags')
        tags = json.loads(tags_str) if tags_str else []

        return Asset(
            asset_id=row['asset_id'],
            file_name=row['file_name'],
            file_path=row['file_path'],
            file_size=row['file_size'],
            md5_hash=row['md5_hash'],
            sha256_hash=row['sha256_hash'],
            mime_type=row['mime_type'],
            category=row['category'],
            status=row['status'],
            error_message=row['error_message'],
            retry_count=row['retry_count'],
            tags=tags,
            security_level=row['security_level'],
            expiry_date=row['expiry_date'],
            owner=row['owner'],
            notes=row['notes'],
            version=row['version'],
            parent_asset_id=row['parent_asset_id'],
            is_active=row['is_active'],
            created_at=row['created_at'],
            updated_at=row['updated_at']
        )


# Custom Exceptions
class DuplicateAssetError(Exception):
    def __init__(self, asset_id: str, file_name: str):
        self.asset_id = asset_id
        self.file_name = file_name
        super().__init__(f"文件已存在: {file_name} (asset_id: {asset_id})")


class UnsupportedFileTypeError(Exception):
    def __init__(self, file_type: str):
        self.file_type = file_type
        super().__init__(f"不支持的文件类型: {file_type}")


class InvalidStateTransitionError(Exception):
    def __init__(self, from_status: str, to_status: str):
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(f"状态转换不合法: {from_status} -> {to_status}")


class AssetNotFoundError(Exception):
    def __init__(self, asset_id: str):
        self.asset_id = asset_id
        super().__init__(f"资产不存在: {asset_id}")
